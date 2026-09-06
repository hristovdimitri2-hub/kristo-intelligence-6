"""Live verification of the canonical dashboard after deploy (read-only)."""
import json
import sys

import requests

BASE = "https://kristo-intelligence-api.onrender.com"


def main() -> int:
    ok = True

    r = requests.get(BASE + "/api/dashboard/data", timeout=40)
    print("GET /api/dashboard/data ->", r.status_code)
    if r.status_code != 200:
        print("  (deploy още не е готов?)", r.text[:100])
        return 1
    d = r.json()
    oc = d["sections"]["onchain"]
    print("  TOTAL:", oc["total_usdc"], "USDC /", oc["total_count"], "transfers"
          " / external payers:", oc["external_payers"])
    print("  by_class:", json.dumps(oc["by_class"]))
    print("  watermark block:", oc["last_scanned_block"])
    for h in oc["history"][:6]:
        print(f"  {h['ts'][:19]}  ${h['amount_usdc']:<8} {h['payer_class']:<9}"
              f" tx={h['tx_hash'][:20]}")
    # Priority-0 expectations
    if not (abs(oc["total_usdc"] - 0.017) < 1e-9 and oc["total_count"] == 5):
        print("  MISMATCH ❌ — очаквано 0.017 / 5")
        ok = False
    else:
        print("  on-chain числата СЪВПАДАТ с веригата ✅")

    crm = d["sections"]["crm_stripe"]
    print("  CRM/Stripe: excluded_from_onchain =", crm["excluded_from_onchain"],
          "| total_usd =", crm["total_usd"], "| source =", crm["source"])
    if crm["excluded_from_onchain"] is not True:
        print("  ❌ CRM не е маркирано като excluded!")
        ok = False

    pay = d["sections"]["payapi"]
    print("  PayAPI: available =", pay["available"], "| reason:", pay.get("reason"))

    rd = requests.get(BASE + "/dashboard", timeout=40)
    html = rd.text
    print("GET /dashboard ->", rd.status_code,
          "| On-Chain Sales section:", "On-Chain Sales" in html,
          "| OFF-CHAIN label:", "OFF-CHAIN" in html)

    rn = requests.get(BASE + "/nexus", timeout=40, allow_redirects=False)
    print("GET /nexus ->", rn.status_code, "Location:", rn.headers.get("Location"))

    rs = requests.get(BASE + "/api/dashboard-stats", timeout=40)
    print("GET /api/dashboard-stats (invariant) ->", rs.status_code)

    print("LIVE VERIFICATION:", "PASS ✅" if ok else "FAIL ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
