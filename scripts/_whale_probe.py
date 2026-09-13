"""Live whale-scan diagnostic (read-only)."""
import os
import sys
import tempfile

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")

hours = int(sys.argv[1]) if len(sys.argv) > 1 else 1
threshold = sys.argv[2] if len(sys.argv) > 2 else "1000"
os.environ["WHALE_THRESHOLD"] = threshold

from integrations.dashboard_store import DashboardStore  # noqa: E402
import web3  # noqa: E402

w3 = web3.Web3(web3.HTTPProvider("https://mainnet.base.org",
                                 request_kwargs={"timeout": 30}))
latest = w3.eth.block_number
probe = w3.eth.get_logs({
    "fromBlock": latest - 500, "toBlock": latest,
    "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "topics": ["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
               None, None],
})
print(f"probe (500 blocks): {len(probe)} USDC transfers")
if probe:
    raw = probe[0]["data"]
    amt = int(raw.hex() if hasattr(raw, "hex") else raw, 16) / 1e6
    print("  first amount:", amt)

td = tempfile.mkdtemp()
s = DashboardStore(os.path.join(td, "whale.db"))
added = s.whaleflow_backfill(hours=hours)
print(f"backfill {hours}h @ ${threshold}: {added} event(s)")
su = s.whaleflow_summary(window_hours=hours)
print("in-window:", su["count"], "| threshold:", su["threshold_usdc"])
for w in su["whales"][:5]:
    print("  %s  $%s  %s -> %s" % (w["ts"][:19], w["amount_usdc"],
                                    w["from_label"], w["to_label"]))
