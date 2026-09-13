"""Табло 2.0 — AUDIT: why is the live whale watermark NULL?

Measures the real RPC behaviours the whale path depends on, so the diagnosis
is evidence, not a guess:
  1. is_connected()      — a HARD gate inside scan_whale_window
  2. eth_blockNumber
  3. a network-wide (unfiltered) get_logs chunk, 250 blocks — the whale query
  4. a receiver-filtered get_logs chunk, 250 blocks — the sales query
  5. whaleflow_backfill(hours=1) end-to-end, timed
  6. which meta values a failed backfill leaves behind
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web3 import Web3  # noqa: E402

RPC = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
print("RPC:", RPC)
w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={"timeout": 30}))

t0 = time.time()
try:
    conn = w3.is_connected()
    print(f"1. is_connected()      -> {conn}   ({time.time()-t0:.2f}s)")
except Exception as exc:
    print(f"1. is_connected()      -> RAISED {type(exc).__name__}: {exc}")
    conn = None

latest = None
t0 = time.time()
try:
    latest = w3.eth.block_number
    print(f"2. eth_blockNumber     -> {latest}   ({time.time()-t0:.2f}s)")
except Exception as exc:
    print(f"2. eth_blockNumber     -> RAISED {type(exc).__name__}: {exc}")

USDC = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
TRANSFER_TOPIC = ("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef")
RECEIVER = Web3.to_checksum_address("0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f")

if latest:
    span = 250
    lo, hi = latest - span, latest
    t0 = time.time()
    try:
        logs = w3.eth.get_logs({"fromBlock": lo, "toBlock": hi,
                                "address": USDC, "topics": [TRANSFER_TOPIC]})
        print(f"3. WIDE (no address filter, {span} blk) -> {len(logs)} logs "
              f"({time.time()-t0:.1f}s)  [WHALE query]")
    except Exception as exc:
        print(f"3. WIDE ({span} blk) -> RAISED {type(exc).__name__}: "
              f"{(str(exc) or '')[:130]}")
    t0 = time.time()
    try:
        logs = w3.eth.get_logs({"fromBlock": lo, "toBlock": hi,
                                "address": USDC, "topics": [TRANSFER_TOPIC,
                                                            None,
                                                            "0x" + "0" * 24 + RECEIVER[2:].lower()]})
        print(f"4. RECEIVER-filtered ({span} blk)          -> {len(logs)} logs "
              f"({time.time()-t0:.1f}s)  [SALES query]")
    except Exception as exc:
        print(f"4. RECEIVER-filtered ({span} blk) -> RAISED {type(exc).__name__}: "
              f"{(str(exc) or '')[:130]}")

print("5. whaleflow_backfill(hours=1) — how the live loop starts:")
import tempfile  # noqa: E402

from integrations.dashboard_store import DashboardStore  # noqa: E402

store = DashboardStore(os.path.join(tempfile.mkdtemp(), "w.db"))
t0 = time.time()
try:
    added = store.whaleflow_backfill(hours=1)
    print(f"   -> added={added} in {time.time()-t0:.1f}s")
except Exception as exc:
    print(f"   -> RAISED {type(exc).__name__}: {(str(exc) or '')[:200]} "
          f"after {time.time()-t0:.1f}s")
print("6. metas left behind:")
for key in ("whaleflow_last_block", "whaleflow_safe_scanned_block"):
    print(f"   {key} = {store.get_meta(key)!r}")
