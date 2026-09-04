"""Kristo Intelligence — public reference x402 client (demo agent).

Walks the EXACT path a paying agent takes, in three observable steps:

  1. Discovery   — GET /.well-known/x402 (free)
  2. Challenge   — GET a paid endpoint -> HTTP 402 with an x402 v2 challenge
  3. Pay & retry — send the challenge's USDC amount on Base, then retry with
                   the X-Payment-Proof header (base64url JSON)

No signup, no API keys — this is the whole integration surface. With no
--pay flag the script stops after step 2 (safe, no wallet needed), which
makes it a living smoke test of the discovery/402 layer. With --pay it
performs a REAL settlement: set DEMO_PRIVATE_KEY to a funded Base test
wallet first. Never use a production key.

Usage:
    python examples/demo_agent/demo_agent.py
    python examples/demo_agent/demo_agent.py --endpoint /api/v1/signal
    python examples/demo_agent/demo_agent.py --pay --endpoint /api/v1/signal
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

import requests

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def _b64url(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def parse_challenge(body: dict) -> dict:
    """Extract the payment requirements from a 402 body (v1 `accepts` or
    v2 flat challenge). Returns a uniform dict for the paying step."""
    if isinstance(body.get("accepts"), list) and body["accepts"]:
        c = body["accepts"][0]
    else:
        c = body
    return {
        "scheme": c.get("scheme") or c.get("x402Version") or "exact",
        "network": c.get("network") or c.get("chain") or "base",
        "amount_raw": str(c.get("amount") or c.get("maxAmountRequired") or ""),
        "pay_to": c.get("payTo") or c.get("to") or "",
        "resource": c.get("resource") or body.get("resource") or "",
        "description": c.get("description") or body.get("description") or "",
    }


def run(base_url: str, endpoint: str, pay: bool) -> int:
    print(f"── Kristo demo agent → {base_url}{endpoint} ──")

    # 1) Discovery
    r = requests.get(f"{base_url}/.well-known/x402", timeout=15)
    print(f"[1] discovery: {r.status_code}, "
          f"{len(r.json().get('resources', []))} resources listed")

    # 2) Challenge
    r = requests.get(f"{base_url}{endpoint}", timeout=30)
    if r.status_code != 402:
        print(f"[2] UNEXPECTED status {r.status_code}: {r.text[:300]}")
        return 2
    challenge = parse_challenge(r.json())
    print(f"[2] 402 challenge: scheme={challenge['scheme']} "
          f"network={challenge['network']} amount_raw={challenge['amount_raw']} "
          f"payTo={challenge['pay_to']}")
    if challenge["description"]:
        print(f"    description: {challenge['description'][:160]}")

    if not pay:
        print("[3] --pay not set: stopping before payment (demo mode). "
              "A paying agent would now send the USDC and retry.")
        return 0

    # 3) Pay & retry — REAL settlement, needs a funded test wallet
    key = os.getenv("DEMO_PRIVATE_KEY", "")
    if not key:
        print("[3] --pay set but DEMO_PRIVATE_KEY missing; aborting.")
        return 2
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(
        os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
        request_kwargs={"timeout": 30},
    ))
    acct = w3.eth.account.from_key(key)
    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_BASE),
        abi=[{"name": "transfer", "type": "function", "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"}],
            "outputs": [{"type": "bool"}], "stateMutability": "nonpayable"}],
    )
    amount_raw = int(challenge["amount_raw"])
    to = Web3.to_checksum_address(challenge["pay_to"])
    tx = usdc.functions.transfer(to, amount_raw).build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 80000,
        "maxFeePerGas": w3.eth.gas_price * 2,
        "maxPriorityFeePerGas": w3.to_wei(0.001, "gwei"),
        "chainId": w3.eth.chain_id,
    })
    signed = acct.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = w3.eth.send_raw_transaction(raw)
    print(f"[3] paying {amount_raw} raw units USDC to {to}… tx: "
          f"{Web3.to_hex(tx_hash)}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    print(f"    mined in block {receipt['blockNumber']} "
          f"(status={receipt['status']})")

    time.sleep(2)  # let the monitor index the transfer
    proof = _b64url({
        "payer": acct.address,
        "transaction_hash": Web3.to_hex(tx_hash),
        "amount_usdc": amount_raw / 1e6,
    })
    r2 = requests.get(f"{base_url}{endpoint}",
                      headers={"X-Payment-Proof": proof}, timeout=60)
    print(f"[3] paid retry: {r2.status_code}")
    print("    body:", r2.text[:600])
    return 0 if r2.status_code == 200 else 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.getenv(
        "KRISTO_BASE_URL", "https://kristo-intelligence-api.onrender.com"))
    ap.add_argument("--endpoint", default="/api/v1/signal")
    ap.add_argument("--pay", action="store_true",
                    help="perform a REAL USDC payment (DEMO_PRIVATE_KEY required)")
    args = ap.parse_args()
    return run(args.base, args.endpoint, args.pay)


if __name__ == "__main__":
    sys.exit(main())
