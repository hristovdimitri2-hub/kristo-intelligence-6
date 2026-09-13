"""One-shot: exact incoming USDC transfers to our payTo, last 48h."""
import time
from datetime import datetime, timezone

from web3 import Web3

w3 = Web3(Web3.HTTPProvider("https://mainnet.base.org",
                            request_kwargs={"timeout": 30}))
USDC = w3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bDA02913")
T = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
latest = w3.eth.block_number
s = latest - int(2 * 86400 / 2)
p = "0x" + "0" * 24 + "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"
print("scanning 48h incoming to our payTo...")
while s <= latest:
    e = min(s + 5000 - 1, latest)
    try:
        logs = w3.eth.get_logs({"fromBlock": s, "toBlock": e, "address": USDC,
                                "topics": [T, None, p]})
        for lg in logs:
            frm = "0x" + bytes(lg["topics"][1]).hex()[-40:]
            amt = int.from_bytes(bytes(lg["data"]), "big") / 1e6
            ts = w3.eth.get_block(lg["blockNumber"]).timestamp
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            tx = "0x" + bytes(lg["transactionHash"]).hex()
            print(f"IN {amt} USDC | from {frm} | tx {tx} | block "
                  f"{lg['blockNumber']} | {dt}")
    except Exception as ex:
        print("chunk err", str(ex)[:60])
    s = e + 1
    if s <= latest:
        time.sleep(0.05)
print("done")