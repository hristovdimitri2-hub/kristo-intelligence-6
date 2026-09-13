"""Табло 2.0 — AUDIT: the largest network-wide window the RPC accepts."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web3 import Web3  # noqa: E402

RPC = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={"timeout": 45}))
USDC = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
head = w3.eth.block_number
print(f"RPC={RPC}  head={head}")
print("network-wide USDC Transfer window sweep (the whale query shape):")
for width in (250, 100, 50, 20, 10, 5, 2, 1):
    hi = head
    lo = hi - width + 1
    t0 = time.time()
    try:
        logs = w3.eth.get_logs({"fromBlock": lo, "toBlock": hi, "address": USDC,
                                "topics": [TOPIC]})
        big = sum(1 for lg in logs
                  if int((lg["data"].hex() if hasattr(lg["data"], "hex")
                          else lg["data"]) or "0", 16) / 1e6 >= 50_000)
        print(f"  width {width:4} -> OK  {len(logs):6} logs, {big} whales "
              f"({time.time()-t0:.1f}s)")
    except Exception as exc:
        print(f"  width {width:4} -> {type(exc).__name__}: "
              f"{(str(exc) or '')[:90]}")
