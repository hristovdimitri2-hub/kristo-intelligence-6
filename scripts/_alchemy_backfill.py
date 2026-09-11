"""One-shot local backfill: scan the sales range 50783000-51180200 (06-09.09)
against the Alchemy RPC (from Render env — never printed) and push the found
sales DIRECTLY to the live dashboard store via a one-time admin route.

Actually simpler: use the Render API to read the env var, scan locally, and
then push the sales via the dashboard_db — but there is no admin route for
this. Instead: print the found transfers and compare with the expected
5/0.017 — then the live store self-heals on next retro_scan (which now has
honest chunk retry).
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")

# Pull the RPC from Render env (API read), never print it
import requests
key = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "secrets", "render_api_key.txt")).read().strip()
h = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
envs = requests.get("https://api.render.com/v1/services/srv-d9maroe7bikc73adkaug/env-vars",
                    headers=h, timeout=30).json()
rpc = next((e["envVar"]["value"] for e in envs
            if e["envVar"]["key"] == "BASE_RPC_URL"), "")
assert rpc.startswith("https://"), "BASE_RPC_URL missing on Render"

# Scan locally with the SAME code path as production
os.environ["WHALE_THRESHOLD"] = "50000"
from integrations.dashboard_store import DashboardStore  # noqa: E402
import tempfile
td = tempfile.mkdtemp()
store = DashboardStore(os.path.join(td, "backfill.db"))

# Direct probe: does the receiver topic actually return logs via Alchemy?
from web3 import Web3  # noqa: E402
w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
print("connected:", w3.is_connected())
try:
    print("chain_id:", w3.eth.chain_id)
    latest = w3.eth.block_number
    print("latest block:", latest)
except Exception as exc:
    print("probe base ERR:", str(exc)[:120])
    raise SystemExit(1)
receiver = "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"
padded = "0x" + "0" * 24 + receiver[2:].lower()
try:
    probe = w3.eth.get_logs({
        "fromBlock": 50943750, "toBlock": 50943770,
        "address": Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
        "topics": ["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                   None, padded],
    })
    print("PROBE (canary payment block range):", len(probe), "logs")
    if probe:
        for lg in probe[:2]:
            print("  log block:", lg["blockNumber"], "| topics[1]:", str(lg["topics"][1])[-40:])
except Exception as exc:
    # Pull the RPC response body for the exact error
    print("PROBE ERR:", str(exc)[:200])
    try:
        import requests as rq
        rr = requests.post(rpc, json={
            "jsonrpc": "2.0", "id": 1, "method": "eth_getLogs",
            "params": [{"fromBlock": hex(50943750), "toBlock": hex(50943770),
                        "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}]
        }, timeout=30)
        print("RPC error body:", rr.text[:300])
    except Exception as exc2:
        print("RPC probe ERR2:", str(exc2)[:120])

# ── Scan the exact sales range in 10-block chunks (Alchemy free tier) ──────
import time  # noqa: E402
CHUNK = 10
start = 50783000           # 06.09 sales start range
end_target = 50944000      # past the last sale (09.09 0xA19F at 50943758+)
found = []
total_calls = 0
t0 = time.time()
print(f"\nScanning {start}..{end_target} in {CHUNK}-block chunks "
      f"({(end_target - start) // CHUNK} calls)...")
while start <= end_target:
    end = min(start + CHUNK - 1, end_target)
    try:
        logs = w3.eth.get_logs({
            "fromBlock": start, "toBlock": end,
            "address": Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
            "topics": ["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                       None, padded],
        })
        for lg in logs:
            raw = lg["data"]
            amt = int(raw.hex() if hasattr(raw, "hex") else raw, 16) / 1e6
            frm = "0x" + bytes(lg["topics"][1]).hex()[-40:]
            found.append((lg["blockNumber"], amt, frm,
                          Web3.to_hex(lg["transactionHash"])))
    except Exception as exc:
        print(f"  chunk {start}-{end} ERR: {str(exc)[:80]}")
        time.sleep(2)     # rate limit — wait
        continue          # retry same chunk (do NOT skip — honesty)
    start = end + 1
    if start <= end_target:
        time.sleep(0.1)   # gentle pacing
print(f"done in {time.time() - t0:.1f}s | {len(found)} sale logs found")
for b, amt, frm, tx in sorted(found):
    print(f"  block={b}  ${amt:<8}  from={frm}  tx={tx[:22]}")

added = store.retro_scan(days=5, rpc_url=rpc)
s = store.sales_summary()
print(f"LOCAL retro scan (5d): {added} sale(s) | total: {s['total_usdc']} / {s['total_count']}")
for w in reversed(s["history"]):
    print(f"  {w['ts'][:19]}  ${w['amount_usdc']:<8} {w['payer_class']:<9} {w['sender'][:14]}  tx={w['tx_hash'][:20]}")
