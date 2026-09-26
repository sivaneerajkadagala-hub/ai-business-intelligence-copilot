"""End-to-end smoke test against a running backend on :8000.

Usage:
    python tests/e2e/smoke.py

Exits non-zero on any failure. Requires seeded demo accounts and datasets
(`python -m seed.run` against the same DATABASE_URL).
"""

import sys
import urllib.request
import urllib.error
import json

BASE = "http://localhost:8000/api/v1"
PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = ""):
    (PASS if ok else FAIL).append(name)
    safe = detail.encode("ascii", errors="replace").decode() if detail else ""
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" - {safe}" if safe else ""))


def req(method: str, path: str, body=None, token=None, raw=False):
    r = urllib.request.Request(
        f"{BASE}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        res = urllib.request.urlopen(r)
        data = res.read()
        return res.status, (data if raw else json.loads(data))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


print("== AI BI Copilot smoke test ==")

# Health
code, body = req("GET", "/health")
check("health ok", code == 200 and body.get("success"))

# Auth
code, body = req("POST", "/auth/login", {"email": "analyst@bicopilot.dev", "password": "Demo1234!"})
token = (body.get("data") or {}).get("accessToken", "")
check("analyst login", code == 200 and bool(token))

code, body = req("POST", "/auth/login", {"email": "viewer@bicopilot.dev", "password": "Demo1234!"})
viewer = (body.get("data") or {}).get("accessToken", "")
check("viewer login", code == 200 and bool(viewer))

# Datasets
code, body = req("GET", "/datasets", token=token)
items = body.get("data", {}).get("items", [])
sales = next((d for d in items if d["name"] == "Sales"), None)
check("seeded datasets present", bool(sales), f"{len(items)} datasets")
check("sales dataset ready", (sales or {}).get("status") == "ready")

# Analytics
code, body = req("GET", "/analytics/summary", token=token)
check(
    "analytics summary", code == 200
    and body.get("data", {}).get("totalRecords", 0) > 10000,
    f"{body.get('data', {}).get('totalRecords')} records",
)
code, body = req(
    "GET",
    f"/analytics/series?dataset_id={sales['id']}&date_column=date&metric_column=revenue&bucket=month",
    token=token,
)
points = (body.get("data") or {}).get("points", [])
check("revenue series", len(points) >= 20, f"{len(points)} points")

# Copilot
code, body = req(
    "POST", "/copilot/chat",
    {"question": "top 5 categories by revenue", "datasetId": sales["id"]},
    token,
)
msg = (body.get("data") or {}).get("message", {})
check(
    "copilot NL->SQL", code == 200 and "SUM" in (msg.get("sql") or "").upper(),
    (msg.get("content") or "")[:60],
)
check("copilot chart inferred", (msg.get("chartSpec") or {}).get("type") == "bar")

code, body = req(
    "POST", "/copilot/chat",
    {"question": "forecast next 3 months of revenue", "datasetId": sales["id"]},
    token,
)
check("copilot forecast", (body.get("data") or {}).get("message", {}).get("chartSpec", {}).get("type") == "forecast")

# Insights
code, body = req("POST", f"/insights/generate?dataset_id={sales['id']}", token=token)
check("insight generation", code == 200 and len(body.get("data", [])) >= 3)

# RBAC
code, _ = req("GET", "/users", token=viewer)
check("viewer blocked from /users (403)", code == 403)
code, _ = req("GET", "/audit-logs", token=viewer)
check("viewer blocked from /audit-logs (403)", code == 403)

# Reports + CSV export
code, body = req("POST", "/reports/generate", {"datasetId": sales["id"], "format": "pdf"}, token)
rid = (body.get("data") or {}).get("id", "")
check("pdf report ready", code == 201 and body.get("data", {}).get("status") == "ready")
code, data = req("GET", f"/reports/{rid}/download", token=token, raw=True)
check("pdf downloads", code == 200 and data[:5] == b"%PDF-")
code, data = req("GET", f"/datasets/{sales['id']}/export.csv", token=token, raw=True)
check("csv export streams", code == 200 and b"revenue" in data[:500])

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
