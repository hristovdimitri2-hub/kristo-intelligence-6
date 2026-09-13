"""Sales restoration diagnosis + targeted payTo-only scan via dRPC (read-only).

1. Live dashboard: onchain rows + watermark.
2. Direct dRPC: incoming USDC to OUR payTo over 50783000..latest-1
   (recipient-filtered — counting drops, not the ocean; small results).
   Expected: 7 transfers (4 canary + 2 external + 1 crawler).
"""
import sys
import time

import requests

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")
from integrations.dashboard_store import DashboardStore  # noqa: E402
import web3  # noqa: E402

B = "https://kristo-intelligence-api.onrender.com"
d = requests.get(B + "/api/dashboard/data", timeout=40).json()
o = d["sections"]["onchain"]
print("=== 1. LIVE dashboard (onchain) ===")
print("total:", o["total_usdc"], "| tx:", o["total_count"],
      "| watermark:", o["last_scanned_block"], "| external:", o["external_payers"])
print("by_class:", o["by_class"])

# 2. Direct dRPC scan: incoming to payTo over the 30d sales range
w3 = web3.Web3(web3.HTTPProvider("https://base.drpc.org"))
TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
latest = w3.eth.block_number
start, end_all = 50783000, latest - 1
print(f"\n=== 2. dRPC targeted scan: {start}..{end_all} (~{(end_all - start) / 43000:.1f} days) ===")
fmt = lambda n: "0x" + format(n, "x")  # noqa: E731
found = []
chunk = 5000
start_cur = start
fails = 0
t0 = time.time()
while start_cur <= end_all:
    end = min(start_cur + chunk - 1, end_all)
    try:
        logs = w3.eth.get_logs({
            "fromBlock": start_cur, "toBlock": end,
            "address": web3.Web3.to_checksum_address(USDC),
            "topics": [TOPIC, None, "0x" + "0" * 24 +
                       "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"],
        })
    except Exception as exc:
        fails += 1
        time.sleep(1)
        continue                      # honest retry, no skip
    for lg in logs:
        raw = lg["data"]
        amt = int(raw.hex() if hasattr(raw, "hex") else raw, 16) / 1e6
        frm = "0x" + bytes(lg["topics"][1]).hex()[-40:]
        found.append((lg["blockNumber"], amt, frm,
                      web3.Web3.to_hex(lg["transactionHash"])))
    start_cur = end + 1
    if start_cur <= end_all:
        time.sleep(0.2)
print(f"scan done in {time.time() - t0:.0f}s | fails-retried: {fails} | found: {len(found)}")
for b, amt, frm, tx in sorted(found):
    print(f"  block={b}  ${amt:<8}  from={frm}  tx={tx[:20]}")

# 3. Store comparison
td = __import__("tempfile").mkdtemp()
store = DashboardStore(td + "/probe.db")
print("\n=== 3. LOCAL store (for label check on found txs) ===")
for b, amt, frm, tx in sorted(found):
    store.record_sale(tx_hash=tx, amount_usdc=amt, sender=frm, block_number=b)
s = store.sales_summary()
print("local store:", s["total_usdc"], "/", s["total_count"], "| external:", s["external_payers"])
print("labels:")
for h in s["history"]:
    print(f"  {h['ts'][:19]}  ${h['amount_usdc']:<8} {h['payer_class']:<9} {h['payer_label'][:28]} {h['sender'][:14]}")