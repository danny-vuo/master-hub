# Backlog Scrubber

Two scrubs over the open backlog, filterable by ISR or sales branch code:
1. Discontinued parts Master has in stock where line resale is below screen resale.
2. Lines shipping from any warehouse except IW/GT with GP under 15% and no source note
   (NCNR-only does not count), grouped by supply status: In stock / On order / Needs ordering.

Try it on your computer: double-click `run-local.bat` (Windows), then open http://localhost:8000.
Deploy for everyone: create a Databricks App from this folder with a SQL warehouse resource
keyed `sql-warehouse`, and give its service principal SELECT on the tables in `queries.py`.
