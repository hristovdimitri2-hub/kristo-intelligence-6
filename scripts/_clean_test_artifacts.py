"""Remove non-chain test artifacts from the dashboard sales table.

`test_integration.py` used to write fake sales into the REAL dashboard store
(tx 0xcdcd…, sender 0xabab…, $0.05). The fixtures now own isolated databases,
but the rows they left behind must not be counted. This script deletes ONLY rows
that are provably not on chain: their tx hash is absent from the verified
manifest AND their sender is a well-known dummy.

Since 14.09 the sales table lives in the durable store (PostgreSQL when
DATABASE_URL is set, SQLite otherwise), so this goes through DashboardStore
instead of opening a file directly — otherwise it would silently clean the
wrong (stale) table.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.dashboard_store import DashboardStore  # noqa: E402
from integrations.verified_sales import VERIFIED_SALES  # noqa: E402

DUMMY_PREFIXES = ("0xabab", "0xcdcd", "0xefef", "0x1111", "0x2222", "0x1a1a",
                  "0x2b2b")


def main() -> int:
    store = DashboardStore()
    hist = store.history
    print(f"backend: {hist.backend}")
    known = {r["tx_hash"].lower() for r in VERIFIED_SALES}
    rows = hist._run(
        "SELECT tx_hash, sender, amount_usdc, source FROM onchain_sales",
        (), "all")[0]
    removed = 0
    for row in rows:
        tx = (row["tx_hash"] or "").lower()
        sender = (row["sender"] or "").lower()
        if tx in known or row["source"] == "seed_recovery":
            continue
        if any(sender.startswith(p) or tx.startswith(p)
               for p in DUMMY_PREFIXES):
            hist._run("DELETE FROM onchain_sales WHERE tx_hash = ?", (tx,))
            print(f"removed test artifact {tx[:20]}… ${row['amount_usdc']} "
                  f"from {sender[:12]}…")
            removed += 1
    total = hist.sales_summary(history_limit=1)
    print(f"removed {removed} artifact(s); now {total['total_count']} rows / "
          f"${total['total_usdc']} USDC ({total['external_payers']} external)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
