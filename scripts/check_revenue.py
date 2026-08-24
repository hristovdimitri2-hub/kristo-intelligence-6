"""On-chain revenue check for the Kristo Intelligence 6 fee receiver.

Queries Base mainnet directly via RPC:
  - ETH balance of the fee receiver (eth_getBalance)
  - USDC balance (balanceOf on the native USDC contract)

Run:  python scripts/check_revenue.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402
from config import BASE_RPC_URL, BASE_USDC_CONTRACT, get_base_fee_receiver  # noqa: E402

RECEIVER = get_base_fee_receiver()
USDC_DECIMALS = 6


def rpc(method: str, params: list):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(BASE_RPC_URL, json=payload, timeout=30)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"RPC error: {body['error']}")
    return body["result"]


def main() -> int:
    print(f"RPC endpoint:  {BASE_RPC_URL}")
    print(f"Fee receiver:  {RECEIVER}")
    print(f"USDC contract: {BASE_USDC_CONTRACT}")
    print("-" * 60)

    # Chain id sanity check
    chain_id = int(rpc("eth_chainId", []), 16)
    print(f"Chain ID:       {chain_id} ({'Base mainnet OK' if chain_id == 8453 else 'UNEXPECTED!'})")

    # ETH balance
    eth_wei = int(rpc("eth_getBalance", [RECEIVER, "latest"]), 16)
    print(f"ETH balance:    {eth_wei / 1e18:.8f} ETH")

    # USDC balance via balanceOf(address)
    padded = RECEIVER[2:].lower().rjust(64, "0")
    data = "0x70a08231" + padded
    result = rpc("eth_call", [{"to": BASE_USDC_CONTRACT, "data": data}, "latest"])
    usdc_raw = int(result, 16)
    usdc = usdc_raw / (10 ** USDC_DECIMALS)
    print(f"USDC balance:   {usdc:.6f} USDC")
    print("-" * 60)

    if usdc > 0:
        print(f"REVENUE DETECTED: {usdc:.6f} USDC received on Base mainnet.")
    else:
        print("No USDC revenue received yet (balance = 0).")
        print("This is expected until the app is deployed and real clients pay.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
