"""Post-deploy live verification of the catalog cleanup (read-only)."""
import json

import requests

B = "https://kristo-intelligence-api.onrender.com"
h = {"User-Agent": "Mozilla/5.0"}
SKU = ["whaleflow", "WhaleFlow", "gas-route", "sentiment", "rug-risk",
       "security-triage", "channel-publisher", "Divergence", "playground"]
REAL = {"/api/v1/signal", "/api/stats", "/api/arb/opportunities",
        "/api/bot-status", "/api/sales"}


def leak(t, where):
    hits = [s for s in SKU if s in t]
    print("  SKU leak:", hits if hits else "НИКАКЪВ ✅")
    return not hits


ok = True

print("=== /.well-known/x402.json ===")
r = requests.get(B + "/.well-known/x402.json", timeout=40)
d = r.json()
eps = sorted(a["endpoint"] for a in d["agents"])
print("  agents:", len(d["agents"]), "->", eps)
ok &= set(eps) == REAL and len(d["agents"]) == 5
ok &= leak(r.text, "x402.json")

print("=== /api/v1/agents ===")
r = requests.get(B + "/api/v1/agents", timeout=40)
eps = sorted(a["endpoint"] for a in r.json()["agents"])
print("  agents:", len(r.json()["agents"]), "->", eps)
ok &= set(eps) == REAL
ok &= leak(r.text, "/api/v1/agents")

print("=== /api/dashboard-stats (products) ===")
r = requests.get(B + "/api/dashboard-stats", timeout=60)
d = r.json()
eps = sorted(p["endpoint"] for p in d["products"])
print("  products_summary:", d["products_summary"])
print("  products:", eps)
ok &= set(eps) == REAL
ok &= leak(r.text, "dashboard-stats")

print("=== /agents redirect ===")
r = requests.get(B + "/agents", timeout=40, allow_redirects=False)
print("  ", r.status_code, "->", r.headers.get("Location"))
ok &= r.status_code == 302

print("=== /dashboard ===")
r = requests.get(B + "/dashboard", timeout=40)
print("  'Реални маршрути' секция:", "Реални маршрути" in r.text)
for endpoint in sorted(REAL):
    print(f"  {endpoint} в HTML:", endpoint in r.text)
ok &= "Реални маршрути" in r.text
ok &= leak(r.text, "/dashboard")

print("=== /api/mcp/manifest ===")
r = requests.get(B + "/api/mcp/manifest", timeout=40)
ok &= leak(r.text, "manifest")

print("=== PayAPI /agent/get (външен кеш — очаквам стари данни до re-crawl) ===")
g = requests.get("https://payapi.market/agent/get?id=kristo-intelligence-defi-signals-api",
                 headers=h, timeout=30).json()
print("  status:", g.get("status"), "| payment_verified:", g.get("payment_verified"))
gt = json.dumps(g)
leaks = [s for s in SKU if s in gt]
print("  SKU имена в PayAPI кеша:", leaks if leaks else "няма ✅")
print("  (PayAPI преиндексира сам при следващ crawl/compute)")

print()
print("LIVE CLEANUP VERIFICATION:", "PASS ✅" if ok else "FAIL ❌")
