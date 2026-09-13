"""Test: pokt 10-block recipient-filtered query at canary block 50783187."""
import sys

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")
import web3  # noqa: E402

w3 = web3.Web3(web3.HTTPProvider("https://base-pokt.nodies.app"))
TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
padded = "0x" + "0" * 24 + "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"

# canary 1 at block 50783187
tests = [
    (50783187, 50783187, "1-block"),
    (50783180, 50783190, "11-block"),
    (50783180, 50783189, "10-block"),
    (50783185, 50783194, "10-block (centered)"),
]
for lo, hi, tag in tests:
    try:
        logs = w3.eth.get_logs({
            "fromBlock": lo, "toBlock": hi,
            "address": web3.Web3.to_checksum_address(
                "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
            "topics": [TOPIC, None, padded],
        })
        print(f"  {tag} ({lo}-{hi}): {len(logs)} logs")
        for lg in logs:
            tx = web3.Web3.to_hex(lg["transactionHash"])
            print(f"    tx={tx[:24]} block={lg['blockNumber']}")
    except Exception as exc:
        print(f"  {tag} ({lo}-{hi}): ERR {str(exc)[:80]}")
