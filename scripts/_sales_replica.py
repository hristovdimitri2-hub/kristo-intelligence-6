"""Replicate the EXACT production sales scan path locally via drpc."""
import os
import sys
import tempfile

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")
os.environ["SALES_CHUNK_BLOCKS"] = "250"
os.environ["BASE_RPC_URL"] = "https://base.drpc.org"
os.environ["WHALE_THRESHOLD"] = "50000"

from integrations.dashboard_store import DashboardStore  # noqa: E402

td = tempfile.mkdtemp()
store = DashboardStore(td + "/sales.db")
added = store.retro_scan(days=7)
s = store.sales_summary()
print(f"retro 7d (250-block chunks): {added} sale(s) | {s['total_usdc']} / {s['total_count']}")
print("external:", s["external_payers"], "| classes:", s["by_class"])
for h in s["history"]:
    print(f"  {h['ts'][:19]}  ${h['amount_usdc']:<8} {h['payer_class']:<9} {h['payer_label'][:26]}  {h['sender'][:14]}")
print("sales_safe_scanned_block:", store.get_meta("sales_safe_scanned_block"))
print("last_scanned_block:", store.get_meta("last_scanned_block"))