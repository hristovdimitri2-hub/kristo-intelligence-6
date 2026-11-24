# -*- coding: utf-8 -*-
"""One real paid call through the Python client, end to end.

This is the proof that the client works, not just parses: it signs an EIP-3009
authorization, presents it, and prints the delivered JSON. It costs whatever the
route costs — use a cheap one.

    KRISTO_PRIVATE_KEY=0x... python examples/live_dry_run.py

The key is read from the environment and never written to disk. Use a dedicated
wallet with a few cents in it, not a wallet holding real money.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kristo_x402_client import KristoX402Client  # noqa: E402

CHAIN_ID = 8453


def make_signer(private_key):
    """Return a ``pay`` callback that signs an EIP-3009 authorization.

    This is the only piece of wallet code the client needs; everything else is
    the handshake. Swap ``eth_account`` for your own wallet library.
    """
    from eth_account import Account

    def sign(challenge):
        accepted = challenge["accepted"]
        extra = accepted.get("extra") or {}
        name, version = extra.get("name"), extra.get("version")
        if not name or not version:
            raise RuntimeError(
                "the challenge carries no EIP-712 domain (extra.name/version)")

        payer = Account.from_key(private_key).address
        value = int(challenge["amount_atomic"])
        valid_after = 0
        valid_before = int(time.time()) + 55
        nonce = os.urandom(32)

        domain = {
            "name": name,
            "version": version,
            "chainId": CHAIN_ID,
            "verifyingContract": accepted["asset"],
        }
        types = {
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ]
        }
        message = {
            "from": payer,
            "to": accepted["payTo"],
            "value": value,
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": nonce,
        }
        signed = Account.sign_typed_data(
            private_key, domain_data=domain, message_types=types,
            message_data=message)
        signature = signed.signature.hex()
        if not signature.startswith("0x"):
            signature = "0x" + signature
        return {
            "signature": signature,
            "authorization": {
                "from": payer,
                "to": accepted["payTo"],
                "value": str(value),
                "validAfter": str(valid_after),
                "validBefore": str(valid_before),
                "nonce": "0x" + nonce.hex(),
            },
        }

    return sign


def main():
    key = os.getenv("KRISTO_PRIVATE_KEY", "").strip()
    if not key:
        print("set KRISTO_PRIVATE_KEY to run the paid call", file=sys.stderr)
        return 2
    path = sys.argv[1] if len(sys.argv) > 1 else "/api/sales"

    client = KristoX402Client(pay=make_signer(key))
    result = client.get(path)
    print("status:", result.get("status"), "ok:", result.get("ok"))
    print(json.dumps(result.get("data"), indent=2)[:1500])
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
