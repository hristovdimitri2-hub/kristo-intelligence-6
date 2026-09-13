"""Табло 2.0 — FINDING 2 proof: the /dashboard route table is STATIC text and
its /api/sales price disagrees with the live x402 challenge."""
import re

import requests

B = "https://kristo-intelligence-api.onrender.com"

disc = requests.get(B + "/.well-known/x402.json", timeout=45).json()
published = {a["endpoint"]: a["price_usdc"] for a in disc["agents"]}
print("=== published (from REAL_X402_ROUTES via /.well-known/x402.json) ===")
for ep, p in published.items():
    print(f"  {ep:28} ${p}")

html = requests.get(B + "/dashboard", timeout=45).text
static = dict(re.findall(
    r'GET\s+(/api/[^<]+)</td><td>[^<]*</td><td class="num">([0-9.]+)', html))
print("=== static table in the served /dashboard HTML ===")
for ep, p in static.items():
    print(f"  {ep:28} ${p}")

print("=== MISMATCHES (static vs published) ===")
bad = 0
for ep, p in static.items():
    pub = published.get(ep)
    if pub is None:
        print(f"  !! {ep}: in the table but NOT a real route")
        bad += 1
    elif abs(float(p) - float(pub)) > 1e-9:
        print(f"  !! {ep}: table ${p} vs real ${pub}  (x{float(p)/float(pub):.0f})")
        bad += 1
print("RESULT:", "no mismatch" if not bad else f"{bad} MISMATCH(ES) — phantom price on screen")

# Independent proof of the REAL /api/sales price: the canonical 402 body.
r = requests.get(B + "/api/sales", timeout=60)
print("live /api/sales ->", r.status_code)
if r.status_code == 402:
    print("   accepts amount (atomic):", r.json()["accepts"][0]["amount"])
