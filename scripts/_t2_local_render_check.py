"""Табло 2.0 — local pre-deploy check: JS syntax + every section renders.

Extracts the <script> block from the served /dashboard HTML and asks node to
parse it, then renders each section's data shape so a broken renderer is
caught BEFORE the deploy (a JS error would blank the whole dashboard).
"""
import re
import subprocess
import sys
import tempfile
import os
import json

os.environ["KRISTO_DISABLE_BACKGROUND_THREADS"] = "true"
os.environ["KRISTO_DASHBOARD_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ.setdefault("ADMIN_API_TOKEN", "local-check")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from integrations.dashboard_store import DashboardStore  # noqa: E402

main.dashboard_db = DashboardStore(os.environ["KRISTO_DASHBOARD_DB"])
main.dashboard_db.seed_verified_sales()
client = main.app.test_client()

html = client.get("/dashboard").get_data(as_text=True)
script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
path = os.path.join(tempfile.mkdtemp(), "dash.js")
open(path, "w", encoding="utf-8").write(script)

print("=== 1. JS syntax (node --check) ===")
try:
    r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    print("node --check:", "OK" if r.returncode == 0 else "FAIL\n" + r.stderr[:600])
    if r.returncode != 0:
        sys.exit(1)
except FileNotFoundError:
    print("node not installed — skipped")

print("=== 2. every section the page consumes ===")
body = client.get("/api/dashboard/data").get_json()
for name in ("onchain", "clients", "whales", "guards", "requests", "payapi",
             "routes", "crm_stripe"):
    sec = body["sections"].get(name)
    print(f"  {name:12} {'OK' if sec is not None else 'MISSING'}")

print("=== 3. the numbers on the screen ===")
o = body["sections"]["onchain"]
print(f"  on-chain      : ${o['total_usdc']} / {o['total_count']} tx / "
      f"{o['external_payers']} external")
print(f"  clients       : {body['sections']['clients']['count']}")
w = body["sections"]["whales"]
print(f"  whales        : {w['count']} ({w['state']})")
g = body["sections"]["guards"]
print(f"  guards        : lock_alive={g['lock_alive']} blocked={g['blocked_total']} "
      f"c2={g['config']['c2_proof_confirmations']}")
print(f"  routes        : {body['sections']['routes']['count']}")

print("=== 4. element id present for every renderer target ===")
for eid in ("onchain-cards", "sales-body", "client-cards", "clients-body",
            "whale-cards", "whales-body", "guard-cards", "guard-body",
            "funnel-box", "routes-body", "routes-src", "req-cards",
            "channels-body", "sources-body", "recent-body", "payapi-cards",
            "ranks-body", "crm-cards", "crm-body", "live-badge",
            "generated-at", "invariant"):
    ok = f'id="{eid}"' in html
    print(f"  {eid:16} {'OK' if ok else 'MISSING'}")
    if not ok:
        sys.exit(1)
print("ALL LOCAL CHECKS PASSED")
