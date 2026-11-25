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
         b.part_number, b.open_quantity AS quantity, b.unit_resale AS resale,
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
SELECT control_number, line_number, customer_code, customer_name, part_number, quantity, resale,
       concat('Discontinued, ', cast(on_hand AS int), ' in stock; resale $', round(resale, 4),
              ' is below screen $', round(screen_resale, 4)) AS reason
FROM j
WHERE screen_resale IS NOT NULL AND resale < screen_resale
ORDER BY control_number, line_number
"""

# Scrub 2 - lines shipping from any warehouse except IW and GT, GP% under 15%, and no
# source note on the order. A comment that is only NCNR (or "NCNR ACKNOWLEDGED") does not count.
# Each line gets a supply status at its shipping warehouse:
#   In stock        on hand covers the open qty
#   On order        short on hand, but on hand + on order covers it
#   Needs ordering  short, and nothing (or not enough) is on order
# :statuses is a comma list of the statuses to return.
LOW_GP = """
WITH stock AS (
  SELECT product_code, part_number, location_code,
         sum(quantity_on_hand) AS on_hand, sum(quantity_on_order) AS on_order
  FROM me_prod.gold_products.inventory
  GROUP BY product_code, part_number, location_code
),
notes AS (
  SELECT control_number, location_code,
         max(CASE WHEN trim(regexp_replace(upper(coalesce(sourcing_comment, '')),
                                           '[^A-Z0-9]+|NCNR|ACKNOWLEDGED', ' ')) <> ''
                  THEN 1 ELSE 0 END) AS has_note
  FROM me_prod.gold_sales.sourcing_comments
  GROUP BY control_number, location_code
),
base AS (
  SELECT b.control_number, b.line_number, b.customer_code, c.bt_customer_name AS customer_name,
         b.part_number, b.open_quantity AS quantity, b.unit_resale AS resale, b.location_code,
         100 * (b.unit_resale - coalesce(b.ship_debit_cost, b.unit_cost)) / b.unit_resale AS gp,
         coalesce(s.on_hand, 0) AS on_hand, coalesce(s.on_order, 0) AS on_order,
         CASE WHEN coalesce(s.on_hand, 0) >= b.open_quantity THEN 'In stock'
              WHEN coalesce(s.on_hand, 0) + coalesce(s.on_order, 0) >= b.open_quantity THEN 'On order'
              ELSE 'Needs ordering' END AS supply_status
  FROM me_prod.gold_sales.backlog_detail b
  LEFT JOIN notes n ON n.control_number = b.control_number AND n.location_code = b.location_code
  LEFT JOIN stock s ON s.product_code = b.product_code AND s.part_number = b.part_number
                   AND s.location_code = b.location_code
  LEFT JOIN me_prod.gold_customers.customer_profile c ON c.customer_code = b.customer_code
  LEFT JOIN me_prod.gold_sales.lkp_isr i ON i.isr = b.isr
  WHERE b.location_code NOT IN ('IW', 'GT')
    AND coalesce(n.has_note, 0) = 0
    AND b.open_quantity > 0
    AND b.unit_resale > 0
    AND (b.unit_resale - coalesce(b.ship_debit_cost, b.unit_cost)) / b.unit_resale < 0.15
""" + FILTER + """
)
SELECT control_number, line_number, customer_code, customer_name, part_number, quantity, resale,
       supply_status,
       concat('GP ', round(gp, 1), '% (under 15%), ', location_code, ': ',
              CASE supply_status
                WHEN 'In stock' THEN concat(cast(on_hand AS int), ' in stock')
                WHEN 'On order' THEN concat(cast(on_hand AS int), ' in stock, ', cast(on_order AS int), ' on order')
                ELSE concat(CASE WHEN on_hand <= 0 THEN 'no stock' ELSE concat('only ', cast(on_hand AS int), ' in stock') END,
                            CASE WHEN on_order > 0 THEN concat(', only ', cast(on_order AS int), ' on order') ELSE ', nothing on order' END,
                            ', needs ordering') END,
              ', no source note') AS reason
FROM base
WHERE array_contains(split(:statuses, ','), supply_status)
ORDER BY control_number, line_number
"""

ISRS = """
SELECT DISTINCT b.isr, i.name, i.location_code AS branch, i.location_name AS branch_name
FROM me_prod.gold_sales.backlog_detail b
LEFT JOIN me_prod.gold_sales.lkp_isr i ON i.isr = b.isr
WHERE b.isr IS NOT NULL
ORDER BY b.isr
"""
