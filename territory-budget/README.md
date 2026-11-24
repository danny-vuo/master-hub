# Territory 2027 budget deck (UI / UL / UT)

Builds one combined deck from the Long Island, Miami and Tampa branch decks.

1. Put the latest branch decks in `sources/` (file name must contain `LongIsland`, `Miami` or `Tampa`; newest file per branch wins).
2. `python3 build_territory_deck.py` (needs `python-pptx`).
3. Result: `output/2027_Annual_Budget_-_Territory_UI_UL_UT.pptx`.

Branch decks are read by slide title and table column order, so keep the template's slide titles and columns.
Source and output decks are git-ignored because they contain sales data and personal goals.
