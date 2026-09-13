"""Day-of-Truth: cross-verify every seeded sale against an RPC receipt.

Runs independently of Blockscout: each hash is fetched via eth_getTransactionReceipt
and the USDC Transfer log is matched to the receiver + amount. Prints a PASS/FAIL
table and exits non-zero on any mismatch (honesty gate).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web3 import Web3  # noqa: E402

from integrations.verified_sales import (  # noqa: E402
    VERIFIED_RECEIVER,
    VERIFIED_SALES,
    VERIFIED_TOKEN,
)

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

RPCS = [
    os.getenv("BASE_RPC_URL", ""),
    "https://base.blockscout.com/api/eth-rpc",
    "https://mainnet.base.org",
]


def _w3() -> Web3:
    for url in RPCS:
        if not url:
            continue
        try:
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 25}))
            if w3.is_connected():
                print(f"RPC: {url} (block {w3.eth.block_number})")
                return w3
        except Exception as exc:  # pragma: no cover - network probe
            print(f"  probe failed {url}: {exc}")
    raise SystemExit("no reachable RPC")


def main() -> int:
    w3 = _w3()
    ok_all = True
    total = 0.0
    for row in VERIFIED_SALES:
        tx = row["tx_hash"]
        try:
            r = w3.eth.get_transaction_receipt(tx)
        except Exception as exc:
            print(f"FAIL {tx[:18]}… receipt: {type(exc).__name__}")
            ok_all = False
            continue
        found = None
        for lg in r["logs"]:
            topics = lg["topics"]
            if len(topics) < 3:
                continue
            if str(lg["address"]).lower() != VERIFIED_TOKEN:
                continue
            def _raw(t) -> str:
                return t.hex() if hasattr(t, "hex") else str(t)

            t0 = _raw(topics[0]).lower().replace("0x", "")
            if t0 != TRANSFER_TOPIC.replace("0x", ""):
                continue
            to_addr = "0x" + _raw(topics[2]).replace("0x", "")[-40:]
            frm = "0x" + _raw(topics[1]).replace("0x", "")[-40:]
            data = lg["data"]
            raw = data.hex() if isinstance(data, (bytes, bytearray)) else str(data)
            amt = int(raw or "0", 16) / 1e6
            if to_addr.lower() == VERIFIED_RECEIVER and frm.lower() == row["sender"]:
                found = (amt, frm, int(r["blockNumber"]), int(r["status"]))
        if not found:
            print(f"FAIL {tx[:18]}… no matching Transfer(receiver, sender)")
            ok_all = False
            continue
        amt, frm, blk, status = found
        good = (abs(amt - row["amount_usdc"]) < 1e-9
                and blk == row["block_number"] and status == 1)
        total += amt
        print(f"{'PASS' if good else 'FAIL'} {tx[:18]}… ${amt:<6} "
              f"blk={blk} status={status} from={frm[:12]}…")
        ok_all = ok_all and good

    print("-" * 72)
    print(f"TOTAL: ${round(total, 6)} over {len(VERIFIED_SALES)} transfers | "
          f"receiver {VERIFIED_RECEIVER}")
    print("RESULT:", "ALL 8 VERIFIED ✅" if ok_all else "MISMATCH ❌")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
