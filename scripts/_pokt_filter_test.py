"""pokt recipient-filtered: 10blk vs 50blk at the canary block."""
import sys

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")
import web3  # noqa: E402

w3 = web3.Web3(web3.HTTPProvider("https://base-pokt.nodies.app"))
TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
padded = "0x" + "0" * 24 + "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"
anchor = 50943758
for size in (10, 50):
    lo, hi = anchor - size // 2, anchor + size - 1
    try:
        logs = w3.eth.get_logs({
            "fromBlock": lo, "toBlock": hi,
            "address": web3.Web3.to_checksum_address(
                "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
            "topics": [TOPIC, None, padded],
        })
        print(size, "blk ->", len(logs), "logs")
    except Exception as exc:
        print(size, "blk -> ERR", str(exc)[:80])
