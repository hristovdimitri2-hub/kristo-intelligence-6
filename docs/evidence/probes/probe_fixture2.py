# -*- coding: utf-8 -*-
"""Read-only: precise field-by-field compare (expected vs live discovery)
+ fixture values dump."""
from __future__ import annotations

import json
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# expected values EXACTLY as provided in the task
EXP = {
    "payTo": "0xbF428071027402E9b0cE85e22146Edc028cEB3b",
    "amount": "20000",
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "network": "eip155:8453",
    "scheme": "exact",
    "version": 2,
}

PATH = (r"C:\Users\AlienWare\Downloads"
        r"\returncheck-reverse-test (4).json")
fx = json.loads(open(PATH, encoding="utf-8").read())
print("FIXTURE VALUES:")
for k, v in fx.items():
    s = v if not isinstance(v, str) or len(v) <= 140 else v[:140] + "…"
    print(f"  {k} = {s!r}")

url = ("https://returncheck.m-angelmartinez-fer.workers.dev"
       "/.well-known/x402")
r = requests.get(url, timeout=30,
                 headers={"User-Agent": "readonly-probe"})
d = r.json()
acc = (d.get("accepts") or [{}])[0]
GOT = {
    "payTo": acc.get("payTo"),
    "amount": acc.get("amount"),
    "asset": acc.get("asset"),
    "network": acc.get("network"),
    "scheme": acc.get("scheme"),
    "version": d.get("x402Version"),
}

print("\nFIELD COMPARE (sign-by-sign):")
for k in EXP:
    e, g = EXP[k], GOT[k]
    ok = (e == g)
    line = f"  {k}: expected={e!r} got={g!r} equal={ok}"
    if not ok and isinstance(e, str) and isinstance(g, str):
        line += f" | len {len(e)} vs {len(g)}"
        line += (f" | first_diff@{next((i for i, (a, b) in enumerate(zip(e, g)) if a != b), 'len')}")
        line += f" | casefold_equal={e.lower() == g.lower()}"
    print(line)

blob = json.dumps(d, ensure_ascii=False)
print("\npayment-identifier occurrences in discovery:",
      blob.count("payment-identifier"),
      "| identifier_required:",
      ((d.get("payment_instructions") or {})
       .get("identifier_required")),
      "| extensions keys:",
      list((d.get("extensions") or {}).keys()))
print("DONE", flush=True)
