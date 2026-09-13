"""Part C: fingerprint the NEW $0.005 external payer (0x902dcf34...)."""
import json
import os
import sys

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")
import requests  # noqa: E402
from scripts.competitor_recon import fingerprint_payer  # noqa: E402

d = requests.get("https://kristo-intelligence-api.onrender.com/api/dashboard/data",
                 timeout=40).json()
o = d["sections"]["onchain"]
full = None
for hh in o["history"]:
    if hh["sender"].startswith("0x902dcf34e536"):
        full = hh["sender"]
        break
print("пълен адрес:", full)
if full:
    fp = fingerprint_payer("https://base-pokt.nodies.app", full, days=30)
    print(json.dumps({k: fp[k] for k in ("distinct_receivers", "total_txs",
                                         "total_usdc", "classification")},
                     indent=1))
else:
    print("0x902dcf не е в историята (scan-ът още не го е стигнал)")