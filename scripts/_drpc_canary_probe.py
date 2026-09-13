"""MINIMAL test: does drpc serve the recipient-filtered canary log?"""
import sys

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")
import web3  # noqa: E402

w3 = web3.Web3(web3.HTTPProvider("https://base.drpc.org"))
TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
padded = "0x" + "0" * 24 + "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"

print("=== drpc: recipient-filtered canary query (block 50943758) ===")
try:
    logs = w3.eth.get_logs({
        "fromBlock": 50943758, "toBlock": 50943758,
        "address": web3.Web3.to_checksum_address(
            "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
        "topics": [TOPIC, None,
                   "0x" + "0" * 24 + "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"],
    })
    print("logs returned:", len(logs))
    for lg in logs:
        print("  tx:", web3.Web3.to_hex(lg["transactionHash"])[:30],
              "| block:", lg["blockNumber"])
except Exception as exc:
    print("ERR:", str(exc)[:200])

print("\n=== pokt: same query (50-block max) ===")
w3b = web3.Web3(web3.HTTPProvider("https://base-pokt.nodies.app"))
try:
    logs = w3b.eth.get_logs({
        "fromBlock": 50943755, "toBlock": 50943765,   # 11 blocks < 50 max
        "address": web3.Web3.to_checksum_address(
            "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
        "topics": [TOPIC, None,
                   "0x" + "0" * 24 + "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"],
    })
    print("logs returned:", len(logs))
    for lg in logs:
        print("  tx:", web3.Web3.to_hex(lg["transactionHash"])[:30],
              "| block:", lg["blockNumber"])
except Exception as exc:
    print("ERR:", str(exc)[:150])