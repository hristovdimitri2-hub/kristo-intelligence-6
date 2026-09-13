"""Probe: drpc recipient-filtered 250-block query on a 2-day-old range."""
import sys

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")
import web3  # noqa: E402

w3 = web3.Web3(web3.HTTPProvider("https://base.drpc.org"))
TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
latest = w3.eth.block_number
print("latest:", latest)
padded = "0x" + "0" * 24 + "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"

for offset in (250, 5000, 30000, 100000, 300000):
    lo = latest - offset - 250
    hi = latest - offset
    try:
        logs = w3.eth.get_logs({
            "fromBlock": lo, "toBlock": hi,
            "address": web3.Web3.to_checksum_address(
                "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
            "topics": [TOPIC, None, padded],
        })
        print(f"  {lo}-{hi} ({offset} blk old): {len(logs)} logs")
    except Exception as exc:
        print(f"  {lo}-{hi} ({offset} blk old): ERR {str(exc)[:110]}")