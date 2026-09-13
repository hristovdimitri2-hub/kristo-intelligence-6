"""Part B: verify the 8 known txs via receipts + Part C: new external fingerprint."""
import json
import sys
import tempfile

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")
import web3  # noqa: E402

from integrations.dashboard_store import DashboardStore  # noqa: E402

RPCS = ["https://base-pokt.nodies.app", "https://base.drpc.org"]
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
PAYTO = "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"

KNOWN = [
    ("0xb8a52dcd61962af4b2d15d05d43efaa32b13b3de8e5b53b4bcbb35dcbbe4457",
     "canary 1 (02.09 13:28)"),
    ("0xf5cff040a181876efd3434f63c55cbafba970e3dd0860edd36c06c17e6993016",
     "canary 2 (02.09 16:06)"),
    ("0x1cf2a51caa352a1943c873a4d64efb4aa1b809553a4d3a4789d80b6f97b1ab8a",
     "canary 3 (02.09 22:00)"),
    ("0x0cc98ef96e5e5d9a12f3021b77e2a67bba9439745b9eaf61efdb414491295a5f",
     "canary 4 (03.09 10:11)"),
    ("0xb881f9dcdd0df72bf1853ebbf3328cf8d140ae8966871136b6cbe0cf852d5fc3",
     "external 0x4dB7 (06.09 06:41)"),
    ("0x770d21789f4c5034bf923252c34e8ad6bb41e6b6c68c73e4a09440a95a3a9b7",
     "crawler 0x54E1 (08.09 08:28)"),
    ("0xb66077d16909973aa1a2d0492343b9e22a6b41ba2e6e2a76a0e99f7f2b9d38c",
     "external 0xA19F (09.09 10:21)"),
]

w3 = web3.Web3(web3.HTTPProvider("https://base-pokt.nodies.app"))
print("=== 3. RECEIPTS на 8-те известни tx (dRPC/pokt) ===")
verified = []
for txh, label in KNOWN:
    try:
        r = w3.eth.get_transaction_receipt(txh)
        found = None
        for lg in r["logs"]:
            if (lg["address"].lower() == USDC.lower()
                    and str(lg["topics"][2].hex())[-40:] == PAYTO):
                raw = lg["data"]
                amt = int(raw.hex() if hasattr(raw, "hex") else raw, 16) / 1e6
                blk = lg["blockNumber"]
                blk_d = w3.eth.get_block(blk)
                ts = blk_d["timestamp"]
                found = (blk, amt, ts)
                break
        if found:
            blk, amt, ts = found
            when = __import__("datetime").datetime.fromtimestamp(
                ts, tz=__import__("datetime").timezone.utc)
            print(f"  ✅ {label}: block={blk} ${amt} {when.strftime('%m.%d %H:%M')} UTC")
            verified.append((txh, blk, amt, ts))
        else:
            print(f"  ⚠ {label}: receipt OK, но НЯМА USDC→payTo лог!")
    except Exception as exc:
        print(f"  ❌ {label}: {str(exc)[:80]}")

print(f"\nверифицирани: {len(verified)} / {len(KNOWN)}")

# Part C: fingerprint the NEW $0.005 external payer
PAYER = "0x902dcf34e536"
print("\n=== PART C: fingerprint на новия external (платил $0.005) ===")
# Full address from the live dashboard
d = requests.get("https://kristo-intelligence-api.onrender.com/api/dashboard/data",
                 timeout=40).json()
o = d["sections"]["onchain"]
full = None
for hh in o["history"]:
    if hh["sender"].startswith("0x902dcf34e536"):
        full = hh["sender"]
        print("пълен адрес:", full)
        break
if full:
    from scripts.competitor_recon import fingerprint_payer
    fp = fingerprint_payer("https://base-pokt.nodies.app", full, days=30)
    print(json.dumps({k: fp[k] for k in ("distinct_receivers", "total_txs",
                                         "total_usdc", "classification")}, indent=1))
