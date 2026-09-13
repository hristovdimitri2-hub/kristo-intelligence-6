"""Табло 2.0 — PROOF that the whale fix collects real whales.

Before: `WHALEFLOW_CHUNK_BLOCKS` default 250 behind a `max(50, …)` floor, no
halving → the live feed persisted ZERO rows and had no watermark.
After: the same call against the SAME public RPC must persist real whales.

Uses a small window (12 minutes of Base = ~360 blocks) so it finishes fast;
the production loop warm-starts one hour and then scans 60s increments.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web3 import Web3  # noqa: E402

from integrations.dashboard_store import DashboardStore  # noqa: E402

w3 = Web3(Web3.HTTPProvider(os.getenv("BASE_RPC_URL",
                                     "https://mainnet.base.org"),
                            request_kwargs={"timeout": 30}))
head = w3.eth.block_number
span = int(os.getenv("PROBE_SPAN_BLOCKS", "360"))

store = DashboardStore(os.path.join(tempfile.mkdtemp(), "whale.db"))
print(f"head={head}  scanning the last {span} blocks network-wide "
      f"(threshold ${os.getenv('WHALE_THRESHOLD', '50000')})…")
t0 = time.time()
added = store.scan_whale_window(head - span + 1, head, rpc_url="")
elapsed = time.time() - t0

s = store.whaleflow_summary(window_hours=24)
print(f"added={added} in {elapsed:.1f}s")
print(f"state={s['state']}  count={s['count']}  all_time={s['all_time_count']}")
print(f"scanned_until_block={s['scanned_until_block']}  "
      f"effective_chunk={s['effective_chunk_blocks']}")
print(f"last_attempt={s['last_attempt_at']}  last_error={s['last_error']}")
for w in s["whales"][:5]:
    print(f"  ${w['amount_usdc']:>12,.2f} {w['token']} blk {w['block']} "
          f"{w['from'][:10]}… -> {w['to'][:10]}… ({w['from_label']})")
print("RESULT:", "REAL WHALES PERSISTED ✅" if added > 0
      else "STILL EMPTY ❌ — investigate")
