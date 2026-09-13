"""Remove non-chain test artifacts from the local dashboard DB.

`test_integration.py` used to write fake sales into the REAL
data/dashboard_state.db (tx 0xcdcd…, sender 0xabab…, $0.05). The fixtures now
own isolated databases, but the rows they left behind must not be counted.
This script deletes ONLY rows that are provably not on chain: their tx hash is
absent from the verified manifest AND their sender is a well-known dummy.
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.verified_sales import VERIFIED_SALES  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "dashboard_state.db")

DUMMY_PREFIXES = ("0xabab", "0xcdcd", "0xefef", "0x1111", "0x2222", "0x1a1a",
                  "0x2b2b")


def main() -> int:
    if not os.path.exists(DB):
        print("no local dashboard DB — nothing to do")
        return 0
    known = {r["tx_hash"].lower() for r in VERIFIED_SALES}
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    removed = 0
    for row in conn.execute(
            "SELECT tx_hash, sender, amount_usdc, source FROM onchain_sales"):
        tx = (row["tx_hash"] or "").lower()
        sender = (row["sender"] or "").lower()
        if tx in known or row["source"] == "seed_recovery":
            continue
        if any(sender.startswith(p) or tx.startswith(p)
               for p in DUMMY_PREFIXES):
            conn.execute("DELETE FROM onchain_sales WHERE tx_hash = ?", (tx,))
            print(f"removed test artifact {tx[:20]}… ${row['amount_usdc']} "
                  f"from {sender[:12]}…")
            removed += 1
    conn.commit()
    total = conn.execute(
        "SELECT COUNT(*) AS n, ROUND(COALESCE(SUM(amount_usdc),0),6) AS t "
        "FROM onchain_sales").fetchone()
    print(f"removed {removed} artifact(s); now {total['n']} rows / "
          f"${total['t']} USDC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
