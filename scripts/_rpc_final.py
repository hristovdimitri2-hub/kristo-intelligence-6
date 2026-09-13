"""Final RPC test: pokt wildcard 50-block + drpc recipient 10-block viability."""
import sys

sys.path.insert(0, r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6")
import web3  # noqa: E402
import requests  # noqa: E402

TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

w3 = web3.Web3(web3.HTTPProvider("https://base-pokt.nodies.app"))
latest = w3.eth.block_number
print("pokt latest:", latest)
ok = err = 0
import time  # noqa: E402
t0 = time.time()
for i in range(10):
    lo = latest - 50 * (i + 1)
    hi = latest - 50 * i - 1
    try:
        logs = w3.eth.get_logs({
            "fromBlock": lo, "toBlock": hi,
            "address": web3.Web3.to_checksum_address(USDC),
            "topics": [TOPIC, None, None],
        })
        ok += 1
        if i < 3:
            print(f"  chunk {i}: {len(logs)} logs")
    except Exception as exc:
        err += 1
        print(f"  chunk {i}: ERR {str(exc)[:60]}")
print(f"pokt wildcard 50blk x10: {ok} ok / {err} err | {time.time() - t0:.0f}s")

# drpc recipient-filtered 10-block: rate over 20 calls at the sales range
w3d = web3.Web3(web3.HTTPProvider("https://base.drpc.org"))
padded = "0x" + "0" * 24 + "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"
okd = errd = 0
t0 = time.time()
start = 50783000
for i in range(30):
    lo, hi = start + i * 10, start + i * 10 + 9
    try:
        logs = w3d.eth.get_logs({
            "fromBlock": lo, "toBlock": hi,
            "address": web3.Web3.to_checksum_address(USDC),
            "topics": [TOPIC, None, padded],
        })
        okd += 1
        for lg in logs:
            print("  SALE FOUND:", web3.Web3.to_hex(lg["transactionHash"])[:24],
                  "block", lg["blockNumber"])
    except Exception as exc:
        errd += 1
        if errd <= 2:
            print(f"  call {i}: ERR {str(exc)[:70]}")
        time.sleep(0.5)
print(f"drpc recipient 10blk x30: {okd} ok / {errd} err | {time.time() - t0:.0f}s")
