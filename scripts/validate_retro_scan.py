"""One-shot validation: run the real retro scan against the live chain.

Expected (per on-chain truth, 06.09): 5 transfers / $0.017 total /
first external payer 0x4dB7… with $0.003 on 06.09 06:41 UTC.
Run: python scripts/_validate_retro_scan.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["KRISTO_DISABLE_BACKGROUND_THREADS"] = "true"

from integrations.dashboard_store import DashboardStore  # noqa: E402

td = tempfile.mkdtemp()
store = DashboardStore(os.path.join(td, "scan.db"))
added = store.retro_scan(days=30)
print("NEW sales persisted by retro scan:", added)

r = store.sales_summary()
print("TOTAL:", r["total_usdc"], "USDC across", r["total_count"], "transfers")
print("external payers:", r["external_payers"])
print("by_class:", r["by_class"])
print("--- history (oldest first) ---")
for h in reversed(r["history"]):
    print(f"{h['ts'][:19]}  ${h['amount_usdc']:<8} {h['payer_class']:<9} "
          f"{h['sender'][:12]}...  block={h['block_number']}  tx={h['tx_hash'][:20]}...")

expected_total, expected_count = 0.017, 5
ok = abs(r["total_usdc"] - expected_total) < 1e-9 and r["total_count"] == expected_count
print("VALIDATION:", "PASS ✅" if ok else "MISMATCH ❌ (провери ръчно)")
sys.exit(0 if ok else 1)
