"""Full-hash recovery: local scan of payTo transfers via mainnet.base.org."""
import sys
import tempfile

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")
import web3  # noqa: E402
from web3 import Web3  # noqa: E402
from integrations.dashboard_store import DashboardStore  # noqa: E402

RPC = "https://mainnet.base.org"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
padded = "0x" + "0" * 24 + "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"

w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={"timeout": 30}))
latest = w3.eth.block_number
print("latest:", latest)

# Scan the sales range (06.09 → now)
start, end_target = 50783000, latest
found = []
start_cur = start
fails = 0
t0 = __import__("time").time()
while start_cur <= end_target:
    end = min(start_cur + 5000 - 1, end_target)
    try:
        logs = w3.eth.get_logs({
            "fromBlock": start_cur, "toBlock": end,
            "address": Web3.to_checksum_address(USDC),
            "topics": [TOPIC, None, padded],
        })
        for lg in logs:
            raw = lg["data"]
            amt = int(raw.hex() if hasattr(raw, "hex") else raw, 16) / 1e6
            frm = "0x" + bytes(lg["topics"][1]).hex()[-40:]
            found.append((lg["blockNumber"], amt, frm,
                          Web3.to_hex(lg["transactionHash"])))
    except Exception:
        fails += 1
    start_cur = end + 1
    if start_cur <= end_target:
        __import__("time").sleep(0.3)

print(f"scan {start}..{end_target}: {len(found)} transfers "
      f"({fails} failed chunks) in {__import__('time').time() - t0:.0f}s")
for b, amt, frm, tx in sorted(found):
    print(f"  block={b}  ${amt:<8}  from={frm}  tx_hash={tx}")