"""SQL for the two Backlog Scrubber scrubs. Kept separate so they never share logic."""

# Filters (both scrubs): :isr and :branch are '' when not used.
# "Branch" = the ISR's sales branch code (lkp_isr.location_code, e.g. UI), not a warehouse.
FILTER = """
  AND (:isr = '' OR b.isr = :isr)
  AND (:branch = '' OR i.location_code = :branch)
"""

# Scrub 1 - discontinued parts Master has in stock, where line resale < screen resale.
# Screen resale = price tier whose qty break fits the open qty (falls back to price_1).
DISCONTINUED = """
WITH stock AS (
  SELECT product_code, part_number, sum(quantity_on_hand) AS on_hand
  FROM me_prod.gold_products.inventory
  GROUP BY product_code, part_number
  HAVING sum(quantity_on_hand) > 0
),
tiers AS (
  SELECT product_code, part_number, price_1,
    filter(array(
      named_struct('q',qty_break_1,'p',price_1), named_struct('q',qty_break_2,'p',price_2),
      named_struct('q',qty_break_3,'p',price_3), named_struct('q',qty_break_4,'p',price_4),
      named_struct('q',qty_break_5,'p',price_5), named_struct('q',qty_break_6,'p',price_6),
      named_struct('q',qty_break_7,'p',price_7), named_struct('q',qty_break_8,'p',price_8),
      named_struct('q',qty_break_9,'p',price_9)),
      x -> x.q IS NOT NULL AND x.p IS NOT NULL) AS t
  FROM me_prod.gold_products.price
),
j AS (
  SELECT b.control_number, b.line_number, b.customer_code, c.bt_customer_name AS customer_name,
         b.part_number, b.open_quantity AS quantity, b.unit_resale AS resale, b.order_date AS order_entry_date,
         s.on_hand,
         coalesce(element_at(sort_array(filter(t.t, x -> x.q <= b.open_quantity)), -1).p, t.price_1) AS screen_resale
  FROM me_prod.gold_sales.backlog_detail b
  JOIN me_prod.gold_products.master_product m
    ON m.product_code = b.product_code AND m.part_number = b.part_number
  JOIN stock s ON s.product_code = b.product_code AND s.part_number = b.part_number
  LEFT JOIN tiers t ON t.product_code = b.product_code AND t.part_number = b.part_number
  LEFT JOIN me_prod.gold_customers.customer_profile c ON c.customer_code = b.customer_code
  LEFT JOIN me_prod.gold_sales.lkp_isr i ON i.isr = b.isr
  WHERE array_contains(split(:codes, ','), m.inventory_status_code)
    AND b.open_quantity > 0
""" + FILTER + """
)
SELECT control_number, line_number, customer_code, customer_name, part_number, quantity, resale, order_entry_date,
       concat('Discontinued, ', cast(on_hand AS int), ' in stock; resale $', round(resale, 4),
              ' is below screen $', round(screen_resale, 4)) AS reason
FROM j
WHERE screen_resale IS NOT NULL AND resale < screen_resale
ORDER BY control_number, line_number
"""

# Scrub 2 - lines shipping from any warehouse except IW and GT with no source note on the order
# (a comment that is only NCNR does not count) and margin under 15%.
# Cost per line: ship-and-debit cost if present, else the Regular Costing break (gold_products.cost,
# USD) for the part's TOTAL quantity on the sales order across all its schedules (highest break at or
# below that quantity; the first break when the quantity is under it), else the line's own cost.
# Margin is judged on the whole order (:judge = 'order') or on each line alone (:judge = 'line').
# Supply status at the shipping warehouse: In stock / On order / Needs ordering (:statuses is a list).
LOW_GP = """
WITH sc AS (
  SELECT DISTINCT b.control_number
  FROM me_prod.gold_sales.backlog_detail b
  LEFT JOIN me_prod.gold_sales.lkp_isr i ON i.isr = b.isr
  WHERE b.open_quantity > 0
""" + FILTER + """
),
k AS (
  SELECT DISTINCT b.product_code, b.part_number
  FROM me_prod.gold_sales.backlog_detail b JOIN sc ON sc.control_number = b.control_number
  WHERE b.open_quantity > 0
),
stock AS (
  SELECT s.product_code, s.part_number, s.location_code,
         sum(s.quantity_on_hand) AS on_hand, sum(s.quantity_on_order) AS on_order
  FROM me_prod.gold_products.inventory s
  JOIN k ON k.product_code = s.product_code AND k.part_number = s.part_number
  GROUP BY s.product_code, s.part_number, s.location_code
),
notes AS (
  SELECT control_number, location_code,
         max(CASE WHEN trim(regexp_replace(upper(coalesce(sourcing_comment, '')),
                                           '[^A-Z0-9]+|NCNR|ACKNOWLEDGED', ' ')) <> ''
                  THEN 1 ELSE 0 END) AS has_note
  FROM me_prod.gold_sales.sourcing_comments
  GROUP BY control_number, location_code
),
rc AS (
  SELECT c.product_code, c.part_number,
    filter(array(
      named_struct('q',c.qty_break_1,'c',c.cost_1,'n',1), named_struct('q',c.qty_break_2,'c',c.cost_2,'n',2),
      named_struct('q',c.qty_break_3,'c',c.cost_3,'n',3), named_struct('q',c.qty_break_4,'c',c.cost_4,'n',4),
      named_struct('q',c.qty_break_5,'c',c.cost_5,'n',5), named_struct('q',c.qty_break_6,'c',c.cost_6,'n',6),
      named_struct('q',c.qty_break_7,'c',c.cost_7,'n',7), named_struct('q',c.qty_break_8,'c',c.cost_8,'n',8),
      named_struct('q',c.qty_break_9,'c',c.cost_9,'n',9)),
      x -> x.q IS NOT NULL AND x.c IS NOT NULL AND x.c > 0) AS t
  FROM me_prod.gold_products.cost c
  JOIN k ON k.product_code = c.product_code AND k.part_number = c.part_number
  WHERE c.currency_code = 'USD'
),
ot AS (
  SELECT o.control_number, o.part_number, sum(o.order_quantity) AS tq
  FROM me_prod.gold_sales.backlog_detail o JOIN sc ON sc.control_number = o.control_number
  GROUP BY o.control_number, o.part_number
),
base0 AS (
  SELECT b.control_number, b.line_number, b.customer_code, c.bt_customer_name AS customer_name,
         b.isr, i.location_code AS br, b.part_number, b.open_quantity AS quantity, b.unit_resale AS resale,
         b.order_date AS order_entry_date, b.location_code AS loc, ot.tq, coalesce(n.has_note, 0) AS nn, b.ship_debit_cost AS sdc, b.unit_cost AS lc,
         coalesce(element_at(sort_array(filter(rc.t, x -> x.q <= ot.tq)), -1), element_at(sort_array(rc.t), 1)) AS brk,
         coalesce(s.on_hand, 0) AS oh, coalesce(s.on_order, 0) AS oo,
         CASE WHEN coalesce(s.on_hand, 0) >= b.open_quantity THEN 'In stock'
              WHEN coalesce(s.on_hand, 0) + coalesce(s.on_order, 0) >= b.open_quantity THEN 'On order'
              ELSE 'Needs ordering' END AS supply_status
  FROM me_prod.gold_sales.backlog_detail b
  JOIN sc ON sc.control_number = b.control_number
  LEFT JOIN notes n ON n.control_number = b.control_number AND n.location_code = b.location_code
  LEFT JOIN stock s ON s.product_code = b.product_code AND s.part_number = b.part_number
                   AND s.location_code = b.location_code
  LEFT JOIN rc ON rc.product_code = b.product_code AND rc.part_number = b.part_number
  LEFT JOIN ot ON ot.control_number = b.control_number AND ot.part_number = b.part_number
  LEFT JOIN me_prod.gold_customers.customer_profile c ON c.customer_code = b.customer_code
  LEFT JOIN me_prod.gold_sales.lkp_isr i ON i.isr = b.isr
  WHERE b.open_quantity > 0 AND b.unit_resale > 0
),
base1 AS (
  SELECT *, coalesce(sdc, brk.c, lc) AS cost,
         CASE WHEN sdc IS NOT NULL THEN 'ship and debit'
              WHEN brk.c IS NOT NULL THEN concat('Regular Costing break ', brk.n)
              ELSE 'line cost' END AS cost_source
  FROM base0
),
base2 AS (
  SELECT *, 100 * (resale - cost) / resale AS line_gp,
         CASE WHEN cost IS NOT NULL THEN quantity * resale END AS rev,
         CASE WHEN cost IS NOT NULL THEN quantity * (resale - cost) END AS prf
  FROM base1
),
base AS (
  SELECT *, 100 * sum(prf) OVER (PARTITION BY control_number)
                / sum(rev) OVER (PARTITION BY control_number) AS order_gp
  FROM base2
)
SELECT control_number, line_number, customer_code, customer_name, part_number, quantity, resale, order_entry_date,
       supply_status, round(cost, 4) AS cost, round(line_gp, 1) AS line_gp, round(order_gp, 1) AS order_gp,
       concat(CASE WHEN :judge = 'line' THEN concat('Line GP ', round(line_gp, 1), '% (order ', round(order_gp, 1), '%)')
                   ELSE concat('Order GP ', round(order_gp, 1), '% (line ', round(line_gp, 1), '%)') END,
              ' under 15%, cost $', round(cost, 4), ' (', cost_source, ', order qty ', cast(tq AS bigint), '), ', loc, ': ',
              CASE supply_status
                WHEN 'In stock' THEN concat(cast(oh AS int), ' in stock')
                WHEN 'On order' THEN concat(cast(oh AS int), ' in stock, ', cast(oo AS int), ' on order')
                ELSE concat(CASE WHEN oh <= 0 THEN 'no stock' ELSE concat('only ', cast(oh AS int), ' in stock') END,
                            CASE WHEN oo > 0 THEN concat(', only ', cast(oo AS int), ' on order') ELSE ', nothing on order' END,
                            ', needs ordering') END,
              ', no source note') AS reason
FROM base
WHERE loc NOT IN ('IW', 'GT') AND nn = 0
  AND (:isr = '' OR isr = :isr) AND (:branch = '' OR br = :branch)
  AND (CASE WHEN :judge = 'line' THEN line_gp ELSE order_gp END) < 15
  AND array_contains(split(:statuses, ','), supply_status)
ORDER BY control_number, line_number
"""

ISRS = """
SELECT DISTINCT b.isr, i.name, i.location_code AS branch, i.location_name AS branch_name
FROM me_prod.gold_sales.backlog_detail b
LEFT JOIN me_prod.gold_sales.lkp_isr i ON i.isr = b.isr
WHERE b.isr IS NOT NULL
ORDER BY b.isr
"""
