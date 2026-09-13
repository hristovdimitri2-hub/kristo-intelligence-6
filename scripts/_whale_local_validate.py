"""Live validation: local whale scan over the real chain (read-only).

Runs a SHORT backfill (default 2h) against public RPC and prints the whale
events >= $50k found — proves the data pipeline end-to-end without deploy.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")
from integrations.dashboard_store import DashboardStore  # noqa: E402

hours = int(sys.argv[1]) if len(sys.argv) > 1 else 2
td = tempfile.mkdtemp()
store = os.path.join(td, "whale.db")
s = __import__("integrations.dashboard_store", fromlist=["DashboardStore"]).DashboardStore(store)
added = s.whaleflow_backfill(hours=hours)
print(f"backfill {hours}h: {added} whale event(s) persisted")
summary = s.whaleflow_summary(window_hours=hours)
print("in-window events:", summary["count"])
print("scanned_until_block:", summary["scanned_until_block"])
for w in summary["whales"][:5]:
    print(f"  {w['ts'][:19]}  ${w['amount_usdc']:>12,.0f}  {w['from_label']:<18} → {w['to_label']:<18}  tx={w['tx_hash'][:18]}")