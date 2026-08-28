# -*- coding: utf-8 -*-
"""Read-only check of the project wallet's ETH (gas) and USDC balances on Base."""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from web3 import Web3

w3 = Web3(Web3.HTTPProvider("https://mainnet.base.org", request_kwargs={"timeout": 30}))
print("RPC connected:", w3.is_connected())
print("Chain ID:", w3.eth.chain_id)

for label, addr in [
    ("RECEIVER  ", "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"),
    ("PAYER-NOW ", "0xd4cdA980839C8FED4374EE37EA8DBE8c4ECfd88f"),
    ("OLD-RENDER", "0x298268446cb8f5387258655527c7b70f876b7493"),
]:
    a = Web3.to_checksum_address(addr)
    eth_raw = w3.eth.get_balance(a)
    print(f"{label} {addr}")
    print(f"  ETH balance:  {eth_raw / 1e18:.9f} ETH (raw: {eth_raw})")

    USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    erc20 = [
        {"constant": True, "inputs": [{"name": "o", "type": "address"}], "name": "balanceOf",
         "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "decimals",
         "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    ]
    c = w3.eth.contract(address=Web3.to_checksum_address(USDC), abi=erc20)
    dec = c.functions.decimals().call()
    raw = c.functions.balanceOf(a).call()
    print(f"  USDC balance: {raw / 10**dec:.6f} USDC (raw: {raw}, decimals: {dec})")

print(f"Gas price:    {w3.eth.gas_price / 1e9:.6f} gwei")
print(f"Est gas cost (120k gas): {120000 * w3.eth.gas_price / 1e18:.9f} ETH")
