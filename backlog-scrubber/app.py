import os
from flask import Flask, jsonify, request, send_from_directory
from databricks import sql
from databricks.sdk.core import Config
import queries

app = Flask(__name__, static_folder="static")
# In Databricks Apps the platform supplies credentials. Run on your own computer, the app signs
# you in through your browser (OAuth) and runs queries as you.
LOCAL = "DATABRICKS_APP_PORT" not in os.environ
_cfg = None


def get_cfg():
    """Create the credentials on first use, so the app starts instantly and the browser
    sign-in only appears when a query actually runs."""
    global _cfg
    if _cfg is None:
        _cfg = (Config(host=os.environ["DATABRICKS_HOST"], auth_type="external-browser")
                if LOCAL else Config())
    return _cfg


WAREHOUSE = os.environ["DATABRICKS_WAREHOUSE_ID"]

# Status codes that mean "discontinued" in the product master. Set DISCONTINUED_CODES
# (comma-separated) in app.yaml to give the app a default; users can also override in the UI.
DEFAULT_CODES = os.environ.get("DISCONTINUED_CODES", "")


def run(query, params):
    cfg = get_cfg()
    with sql.connect(server_hostname=cfg.host, http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
                     credentials_provider=lambda: cfg.authenticate) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, [str(v) if v is not None else "" for v in r])) for r in cur.fetchall()]


@app.errorhandler(Exception)
def fail(e):
    return (str(e), 500)


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/meta")
def meta():
    rows = run(queries.ISRS, {})
    return jsonify(isrs=rows, default_codes=DEFAULT_CODES,
                   branches=sorted({(r["branch"], r["branch_name"]) for r in rows if r["branch"]}))


@app.post("/api/scrub")
def scrub():
    body = request.get_json(force=True)
    base = {"isr": body.get("isr", ""), "branch": body.get("branch", "")}
    out = {}
    if body.get("discontinued"):
        codes = ",".join(c.strip() for c in body.get("codes", "").split(",") if c.strip())
        out["discontinued"] = run(queries.DISCONTINUED, {**base, "codes": codes}) if codes else []
    if body.get("low_gp"):
        statuses = body.get("statuses") or ["On order", "Needs ordering"]
        out["low_gp"] = run(queries.LOW_GP, {**base, "statuses": ",".join(statuses)})
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="127.0.0.1" if LOCAL else "0.0.0.0", port=int(os.environ.get("DATABRICKS_APP_PORT", 8000)))
