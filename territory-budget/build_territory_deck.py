#!/usr/bin/env python3
"""Build the combined Territory (UI / UL / UT) 2027 budget deck.

Refresh workflow
  1. Drop the latest branch deck into ./sources/ (any file name containing
     "LongIsland", "Miami" or "Tampa"; the newest file per branch wins).
  2. Run:  python3 build_territory_deck.py
  3. Open ./output/2027_Annual_Budget_-_Territory_UI_UL_UT.pptx

Branch decks are read by slide TITLE and table position (not slide number), so
they must keep the template's slide titles and table column order.
"""
import copy
import glob
import os
import re
import sys
from datetime import datetime

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(HERE, "sources")
TEMPLATE = os.path.join(HERE, "template", "2027_Annual_Budget_-_Sales_Branch_TEMPLATE.pptx")
OUT = os.path.join(HERE, "output", "2027_Annual_Budget_-_Territory_UI_UL_UT.pptx")

# code, display name, file-name pattern
BRANCHES = [
    ("UI", "Long Island", "*LongIsland*"),
    ("UL", "Miami", "*Miami*"),
    ("UT", "Tampa", "*Tampa*"),
]
TABLE_STYLE_ID = "{35758FB7-9AC5-4552-8A53-C91805E547FA}"  # same style as the template tables
LEFT = 634340
WIDTH = 10920141

# --------------------------------------------------------------------------
# Personal content that must not appear in a territory deck.
# --------------------------------------------------------------------------
# Goals slide: drop everything from a paragraph that is exactly "Personal"
# onward, any paragraph starting with one of these prefixes, and any sentence
# starting with "Personally,".
PERSONAL_PARAGRAPH_PREFIXES = ("earn $",)
PERSONAL_SECTION_HEADINGS = ("personal",)


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------
NUM_RE = re.compile(r"(-)?\s*\$?\s*(-)?(\d[\d,]*(?:\.\d+)?)\s*([MK])?(?![\w])")


def money(s):
    """'$57.59M' / '$45,919,475' / '12,937,322.00' -> float dollars; None if no number."""
    if s is None:
        return None
    s = s.replace("\x0b", " ").strip()
    m = NUM_RE.search(s)
    if not m or not re.search(r"\d", s):
        return None
    v = float(m.group(3).replace(",", ""))
    if m.group(4) == "M":
        v *= 1e6
    elif m.group(4) == "K":
        v *= 1e3
    if m.group(1) or m.group(2):
        v = -v
    return v


def pct(s):
    if s is None:
        return None
    m = re.search(r"(-?\d[\d,]*(?:\.\d+)?)\s*%", s)
    return float(m.group(1).replace(",", "")) / 100 if m else None


def fm(v, d=2):
    return "—" if v is None else f"${v/1e6:,.{d}f}M"


def fp(v, d=1):
    return "—" if v is None else f"{v*100:.{d}f}%"


def newest(pattern):
    files = [
        f for f in glob.glob(os.path.join(SRC_DIR, pattern + ".pptx"))
        if "template" not in os.path.basename(f).lower() and not os.path.basename(f).startswith("~$")
    ]
    if not files:
        sys.exit(f"No source deck matching {pattern} in {SRC_DIR}")
    return max(files, key=os.path.getmtime)


def title_of(slide):
    for sh in slide.shapes:
        if sh.is_placeholder and sh.placeholder_format.type is not None and sh.placeholder_format.idx == 0:
            return sh.text_frame.text.strip()
    return ""


def table_rows(slide):
    for sh in slide.shapes:
        if sh.has_table:
            return [[c.text.replace("\x0b", " ").strip() for c in r.cells] for r in sh.table.rows]
    return None


def body_paragraphs(slide):
    for sh in slide.shapes:
        if sh.is_placeholder and sh.placeholder_format.idx == 1 and sh.has_text_frame:
            out = []
            for p in sh.text_frame.paragraphs:
                for line in p.text.split("\x0b"):
                    out.append(line.strip())
            while out and not out[-1]:
                out.pop()
            return out
    return []


def parse_branch(code, name, path):
    prs = Presentation(path)
    d = {"code": code, "name": name, "file": os.path.basename(path),
         "mtime": datetime.fromtimestamp(os.path.getmtime(path)),
         "narr": {}}
    for s in prs.slides:
        t = title_of(s)
        tl = t.lower()
        rows = table_rows(s)
        if "overview" in tl and rows:
            ov = {}
            for r in rows[1:]:
                k = r[0].lower()
                key = ("booking" if "book" in k else "shipping" if "ship" in k
                       else "backlog" if "backlog" in k else "gp" if k.startswith("gp") else None)
                if key:
                    ov[key] = r
            d["overview"] = ov
        elif tl == "2027 budget goal" and rows:
            g = {}
            for r in rows[1:]:
                k = r[0].lower()
                key = ("bookings" if "book" in k else "shipments" if ("ship" in k or "sales" in k)
                       else "backlog" if "backlog" in k else "gp" if "gp" in k else None)
                if key:
                    g[key] = r
            d["goal"] = g
        elif tl.startswith("2026 performance breakdown") and rows:
            d["perf"] = [r for r in rows[1:] if r[0] and not re.match(r"(total|.*branch total)", r[0].lower())]
        elif tl.startswith("budget breakdown by isr") and rows:
            d["budget"] = [r[:4] for r in rows[1:] if r[0] and not re.match(r"(total|.*branch total)", r[0].lower())]
        elif tl == "budget breakdown":
            d["narr"]["plan"] = body_paragraphs(s)
        elif tl == "successes":
            d["narr"]["successes"] = body_paragraphs(s)
        elif tl == "challenges":
            d["narr"]["challenges"] = body_paragraphs(s)
        elif tl == "goals":
            d["narr"]["goals"] = body_paragraphs(s)
    for need in ("overview", "goal", "perf", "budget"):
        if need not in d:
            sys.exit(f"{d['file']}: could not find the '{need}' slide/table. Check slide titles match the template.")
    return d


# --------------------------------------------------------------------------
# Deck-building helpers
# --------------------------------------------------------------------------
def delete_slides(prs, keep=1):
    ids = prs.slides._sldIdLst
    for sldId in list(ids)[keep:]:
        prs.part.drop_rel(sldId.rId)
        ids.remove(sldId)


def new_slide(prs, title, with_body=False):
    layout = prs.slide_layouts.get_by_name("Content Slide - Gray")
    s = prs.slides.add_slide(layout)
    for ph in list(s.placeholders):
        idx = ph.placeholder_format.idx
        if idx == 0:
            ph.text_frame.text = title
            ph.left, ph.top, ph.width, ph.height = Emu(190500), Emu(0), Emu(11846246), Emu(768387)
        elif idx == 1 and with_body:
            ph.left, ph.top, ph.width, ph.height = Emu(737227), Emu(900000), Emu(10930898), Emu(5000000)
        else:
            ph._element.getparent().remove(ph._element)
    return s


def add_table(slide, rows, widths, top, font=11, bold_rows=(), left_cols=(0,), row_h=330000, left=LEFT):
    n, m = len(rows), len(rows[0])
    gf = slide.shapes.add_table(n, m, Emu(left), Emu(top), Emu(sum(widths)), Emu(row_h * n))
    tbl = gf.table
    tbl._tbl.tblPr.find("{http://schemas.openxmlformats.org/drawingml/2006/main}tableStyleId").text = TABLE_STYLE_ID
    tbl.first_row = True
    tbl.horz_banding = True
    for j, w in enumerate(widths):
        tbl.columns[j].width = Emu(w)
    for i, r in enumerate(rows):
        tbl.rows[i].height = Emu(row_h)
        for j, val in enumerate(r):
            c = tbl.cell(i, j)
            c.margin_left = c.margin_right = Emu(60000)
            c.margin_top = c.margin_bottom = Emu(25000)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if (j in left_cols and i > 0) else PP_ALIGN.CENTER
            run = p.add_run()
            run.text = val
            run.font.size = Pt(font)
            if i in bold_rows:
                run.font.bold = True
    return gf, row_h * n


def add_note(slide, lines, top, size=12, left=862788, width=10463248, bold_first=True, height=900000):
    tb = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        is_head = bold_first and i == 0
        if not is_head:
            pPr = p._p.get_or_add_pPr()
            pPr.set("marL", "228600")
            pPr.set("indent", "-228600")
            bu = pPr.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}buChar", {"char": "•"})
            pPr.append(bu)
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.bold = is_head
    return tb


def add_footnote(slide, text, top=5700000, size=10):
    tb = slide.shapes.add_textbox(Emu(LEFT), Emu(top), Emu(WIDTH), Emu(400000))
    tb.text_frame.word_wrap = True
    r = tb.text_frame.paragraphs[0].add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.italic = True
    r.font.color.rgb = RGBColor(0x59, 0x59, 0x59)


def fill_body(slide, paragraphs):
    body = [p for p in slide.placeholders if p.placeholder_format.idx == 1][0]
    tf = body.text_frame
    chars = sum(len(p) for p in paragraphs)
    n = len([p for p in paragraphs if p])
    size = 16 if chars < 600 else 14 if chars < 1000 else 12 if chars < 1400 else 11 if chars < 1700 else 10 if chars < 2100 else 9
    # Each paragraph also costs roughly one extra line of spacing.
    if chars >= 1800 or n >= 19:
        # Very long slide: two columns at a readable size instead of tiny text.
        bp = tf._txBody.find("{http://schemas.openxmlformats.org/drawingml/2006/main}bodyPr")
        bp.set("numCol", "2")
        bp.set("spcCol", "360000")
        size = 11
    first = True
    for line in paragraphs:
        if not line and not first:
            continue  # collapse blank lines; spacing comes from paragraph spacing
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", "0")
        pPr.set("indent", "0")
        pPr.append(pPr.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}buNone", {}))
        p.space_before = Pt(0)
        p.space_after = Pt(3 if size >= 11 else 2)
        r = p.add_run()
        text = line[1:].strip() if line.startswith(("•", "-")) else line
        is_bullet = line.startswith(("•", "-"))
        r.text = ("• " + text) if is_bullet else text
        r.font.size = Pt(size)
        r.font.bold = line.endswith("?") or line.lower().rstrip(":") in ("key measurable activities", "professional", "key accomplishments this year")
        r.font.color.theme_color = 13  # tx1


def filter_goals(paras):
    out = []
    for p in paras:
        low = p.lower().strip()
        if low in PERSONAL_SECTION_HEADINGS:
            break
        if low.startswith(PERSONAL_PARAGRAPH_PREFIXES):
            continue
        sentences = re.split(r"(?<=[.!?])\s+", p)
        kept = [s for s in sentences if not s.startswith("Personally,")]
        if kept:
            out.append(" ".join(kept))
    return out


# --------------------------------------------------------------------------
# Main build
# --------------------------------------------------------------------------
def main():
    data = []
    for code, name, pat in BRANCHES:
        data.append(parse_branch(code, name, newest(pat)))
    log = []

    def note(msg):
        log.append(msg)

    # ---- headline figures per branch ------------------------------------
    for b in data:
        ov, g = b["overview"], b["goal"]
        b["ship25"] = money(ov["shipping"][1])
        b["ship_goal26"] = money(ov["shipping"][2])
        b["ship_act"] = money(ov["shipping"][3])
        b["ship_rr"] = money(ov["shipping"][4])
        b["book25"] = money(ov["booking"][1])
        b["book_goal26"] = money(ov["booking"][2])
        b["book_act"] = money(ov["booking"][3])
        b["book_rr"] = money(ov["booking"][4])
        b["backlog"] = money(ov["backlog"][3])
        b["gp25"], b["gp26"] = pct(ov["gp"][1]), pct(ov["gp"][3])
        b["goal_ship_rr"] = money(g["shipments"][1])
        b["goal_ship27"] = money(g["shipments"][2])
        b["goal_book_rr"] = money(g["bookings"][1])
        b["goal_book27"] = money(g["bookings"][2])
        # ISR-level sums
        b["perf_25"] = sum(money(r[1]) or 0 for r in b["perf"])
        b["perf_rr"] = sum(money(r[2]) or 0 for r in b["perf"])
        b["bud_rr"] = sum(money(r[1]) or 0 for r in b["budget"])
        b["bud_27"] = sum(money(r[2]) or 0 for r in b["budget"])
        # reconciliation log
        c = b["code"]
        for label, a, z in [
            ("ISR performance run-rate vs overview run-rate", b["perf_rr"], b["ship_rr"]),
            ("ISR 2027 budget vs 2027 shipment goal", b["bud_27"], b["goal_ship27"]),
            ("ISR budget-slide run-rate vs goal-slide run-rate", b["bud_rr"], b["goal_ship_rr"]),
            ("Overview run-rate vs goal-slide run-rate", b["ship_rr"], b["goal_ship_rr"]),
        ]:
            if a and z and abs(a - z) / z > 0.005:
                note(f"{c}: {label}: {fm(a)} vs {fm(z)} (diff {fm(a - z)})")

    T = {k: sum(b[k] for b in data) for k in
         ("ship25", "ship_act", "ship_rr", "book25", "book_act", "book_rr", "backlog",
          "goal_ship_rr", "goal_ship27", "goal_book_rr", "goal_book27")}
    T["gp25"] = sum(b["gp25"] * b["ship25"] for b in data) / T["ship25"]
    T["gp26"] = sum(b["gp26"] * b["ship_act"] for b in data) / T["ship_act"]

    # ---- presentation ----------------------------------------------------
    prs = Presentation(TEMPLATE)
    delete_slides(prs, keep=1)
    # title slide
    sub = [sh for sh in prs.slides[0].shapes if sh.is_placeholder][0]
    first_p = sub.text_frame.paragraphs[0]
    runs = first_p.runs
    runs[0].text = "TERRITORY: UI · UL · UT"
    for r in runs[1:]:
        r.text = ""

    # ---- slide: territory overview ---------------------------------------
    s = new_slide(prs, "Territory (UI · UL · UT) – 2026 Overview")
    hdr = ["Branch", "2025", "2026 Goal", "Actual (10 Mo.)", "2026 runrate", "YOY %"]
    rows = [hdr]
    for label, key25, keyg, keya, keyr in [
        ("Shipping", "ship25", "ship_goal26", "ship_act", "ship_rr"),
        ("Booking", "book25", "book_goal26", "book_act", "book_rr"),
    ]:
        for b in data:
            rows.append([f"{label} – {b['code']}", fm(b[key25]), fm(b[keyg]), fm(b[keya]), fm(b[keyr]),
                         fp(b[keyr] / b[key25] - 1)])
        rows.append([f"{label} – Territory", fm(T[key25]), "—", fm(T[keya]), fm(T[keyr]),
                     fp(T[keyr] / T[key25] - 1)])
    gf, h = add_table(s, rows, [2300000, 1500000, 1500000, 1700000, 1700000, 1300000], 880000,
                      font=12, bold_rows={4, 8}, row_h=335000, left=837000)
    b2b = T["book_rr"] / T["ship_rr"]
    lines = [
        "High level commentary:",
        f"Territory shipments of {fm(T['ship_act'],1)} through October; run-rate {fm(T['ship_rr'],1)} is "
        f"{fp(T['ship_rr']/T['ship25']-1)} vs 2025 ({fm(T['ship25'],1)}).",
        f"Bookings run-rate {fm(T['book_rr'],1)} is {fp(T['book_rr']/T['book25']-1)} vs 2025 ({fm(T['book25'],1)}); "
        f"book-to-bill {b2b:.2f}. Open backlog {fm(T['backlog'],1)}.",
        "Run-rate = Jan–Oct actual × 1.2. YOY % is recalculated here as 2026 run-rate vs 2025 for every row. "
        "2026 Goal is shown where a branch provided one.",
    ]
    add_note(s, lines, 880000 + h + 150000, size=13, left=837000)
    add_footnote(s, "Built from branch decks: " + "; ".join(f"{b['code']} – {b['file']}" for b in data),
                 top=5650000, size=9)

    # ---- slide: backlog & GP ----------------------------------------------
    s = new_slide(prs, "Backlog & Gross Profit by Branch")
    rows = [["Branch", "Open backlog", "GP % 2025", "GP % 2026 (Jan–Oct)", "Change"]]
    for b in data:
        rows.append([f"{b['code']} – {b['name']}", fm(b["backlog"]), fp(b["gp25"]), fp(b["gp26"]),
                     f"{(b['gp26']-b['gp25'])*100:+.1f} pts"])
    rows.append(["Territory", fm(T["backlog"]), fp(T["gp25"]), fp(T["gp26"]),
                 f"{(T['gp26']-T['gp25'])*100:+.1f} pts"])
    gf, h = add_table(s, rows, [2900000, 1900000, 1600000, 2300000, 1500000], 1000000,
                      font=14, bold_rows={4}, row_h=420000, left=837000)
    add_note(s, [
        "Notes:",
        "Backlog is each branch's current open backlog from its own deck (UI as of its deck, UL open today, UT at October).",
        "Territory GP % is sales-weighted from the branch figures (2025 by 2025 shipments, 2026 by Jan–Oct shipments).",
    ], 1000000 + h + 250000, size=13, left=837000)

    # ---- slide: 2027 goal -----------------------------------------------------
    s = new_slide(prs, "Territory 2027 Budget Goal")
    rows = [["Branch", "2026 Run Rate", "2027 Goal", "% Increase"]]
    for label, krr, k27 in [("Shipments", "goal_ship_rr", "goal_ship27"), ("Bookings", "goal_book_rr", "goal_book27")]:
        for b in data:
            rows.append([f"{b['code']} – {label}", fm(b[krr]), fm(b[k27]), fp(b[k27] / b[krr] - 1)])
        rows.append([f"Territory – {label}", fm(T[krr]), fm(T[k27]), fp(T[k27] / T[krr] - 1)])
    gf, h = add_table(s, rows, [3300000, 2200000, 2200000, 1800000], 880000, font=13,
                      bold_rows={4, 8}, row_h=360000, left=837000)
    lines = ["High level commentary:"]
    for b in data:
        lines.append(f"{b['code']} {b['name']}: 2027 book-to-bill implied {b['goal_book27']/b['goal_ship27']:.2f} "
                     f"(2026 run-rate {b['goal_book_rr']/b['goal_ship_rr']:.2f}).")
    lines.append(f"Territory: shipments goal {fm(T['goal_ship27'],1)} (+{(T['goal_ship27']/T['goal_ship_rr']-1)*100:.1f}%), "
                 f"bookings goal {fm(T['goal_book27'],1)}, implied book-to-bill {T['goal_book27']/T['goal_ship27']:.2f}.")
    add_note(s, lines, 880000 + h + 120000, size=12, left=837000)
    if any(abs(b["ship_rr"] - b["goal_ship_rr"]) / b["goal_ship_rr"] > 0.002 for b in data):
        diffs = ", ".join(f"{b['code']} {fm(b['ship_rr'])} → {fm(b['goal_ship_rr'])}" for b in data
                          if abs(b["ship_rr"] - b["goal_ship_rr"]) / b["goal_ship_rr"] > 0.002)
        add_footnote(s, f"Run-rate here is the figure each branch used to set its 2027 goal; it differs from the "
                        f"Overview slide for: {diffs}.", top=5700000)

    # ---- ISR slides -----------------------------------------------------------
    for b in data:
        s = new_slide(prs, f"{b['code']} {b['name']} – 2026 ISR/OSR Performance")
        rows = [["ISR/OSR", "2025 Sales", "2026 Sales (run-rated)", "Growth %", "Comments", "Concerns"]]
        for r in b["perf"]:
            rows.append([r[0], r[1], r[2], r[3], r[4] if len(r) > 4 else "", r[5] if len(r) > 5 else ""])
        t25, trr = b["perf_25"], b["perf_rr"]
        rows.append([f"{b['code']} TOTAL", fm(t25), fm(trr), fp(trr / t25 - 1) if t25 else "—", "Sum of ISR/OSR rows", ""])
        n = len(rows)
        font = 12 if n <= 9 else 11 if n <= 13 else 10
        gf, h = add_table(s, rows, [1750000, 1050000, 1150000, 850000, 3300000, 2820000], 850000,
                          font=font, bold_rows={n - 1}, left_cols=(0, 4, 5), row_h=300000)
        if abs(trr - b["ship_rr"]) / b["ship_rr"] > 0.005:
            add_footnote(s, f"ISR/OSR rows sum to {fm(trr)}; branch run-rate on the Overview is {fm(b['ship_rr'])}.")

    for b in data:
        s = new_slide(prs, f"{b['code']} {b['name']} – 2027 ISR/OSR Budget")
        rows = [["ISR/OSR", "2026 Sales runrate", "2027 Budget", "Growth %"]]
        for r in b["budget"]:
            rows.append(r)
        rows.append([f"{b['code']} TOTAL", fm(b["bud_rr"]), fm(b["bud_27"]), fp(b["bud_27"] / b["bud_rr"] - 1)])
        n = len(rows)
        gf, h = add_table(s, rows, [3700000, 2400000, 2400000, 1800000], 900000, font=13 if n <= 9 else 12,
                          bold_rows={n - 1}, row_h=340000, left=1000000)
        notes = []
        if abs(b["bud_27"] - b["goal_ship27"]) / b["goal_ship27"] > 0.002:
            notes.append(f"ISR budgets sum to {fm(b['bud_27'])}; the branch 2027 goal is {fm(b['goal_ship27'])}.")
        if abs(b["bud_rr"] - b["goal_ship_rr"]) / b["goal_ship_rr"] > 0.005:
            notes.append(f"ISR run-rates sum to {fm(b['bud_rr'])} vs branch run-rate {fm(b['goal_ship_rr'])} "
                         f"(accounts without an ISR budget, e.g. transferred out).")
        if notes:
            add_footnote(s, " ".join(notes))

    # ---- narrative slides -----------------------------------------------------
    titles = [("plan", "Plan to Support Budget"), ("successes", "Successes"),
              ("challenges", "Challenges"), ("goals", "Professional Goals")]
    for key, label in titles:
        for b in data:
            paras = b["narr"].get(key)
            if not paras:
                note(f"{b['code']}: no '{key}' slide found")
                continue
            if key == "goals":
                paras = filter_goals(paras)
            s = new_slide(prs, f"{b['code']} {b['name']} – {label}", with_body=True)
            fill_body(s, paras)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    prs.save(OUT)
    print("Saved", OUT, f"({len(prs.slides)} slides)")
    print("\nSource decks used:")
    for b in data:
        print(f"  {b['code']}: {b['file']} (modified {b['mtime']:%Y-%m-%d %H:%M})")
    print("\nReconciliation flags (source-deck inconsistencies):")
    for m in log or ["  none"]:
        print("  " + m if not m.startswith("  ") else m)


if __name__ == "__main__":
    main()
