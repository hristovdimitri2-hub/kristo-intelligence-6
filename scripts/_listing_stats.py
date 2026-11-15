# -*- coding: utf-8 -*-
"""Read-only: 30-дневни числа за SCAN_LISTING_DRAFT (плащания по endpoint)."""
import sqlite3

db = sqlite3.connect("data/dashboard_state.db")
cur = db.cursor()

WINDOW = "datetime('now', '-30 days')"

print("=== 30-дневни ПЛАТЕНИ ОБАЖДАНИЯ + УНИКАЛНИ ПЛАТЦИ (payment_guards) ===")
rows = cur.execute(f"""
    SELECT endpoint,
           COUNT(*)                AS calls,
           COUNT(DISTINCT payer)   AS payers,
           ROUND(SUM(amount_usdc), 4) AS usdc
    FROM payment_guards
    WHERE consumed_at >= {WINDOW}
    GROUP BY endpoint
    ORDER BY endpoint
""").fetchall()
tot_c = tot_p = 0
for ep, calls, payers, usdc in rows:
    print(f"  {ep:26} calls={calls:4}  payers={payers:3}  usdc={usdc}")
tot_c = sum(r[1] for r in rows)
print(f"  {'ОБЩО (всички endpoint-и)':26} calls={tot_c}")
print()
print("=== 30-дневни САМО /api/v1/signal и /api/v1/whaleflow ===")
rows2 = cur.execute(f"""
    SELECT endpoint,
           COUNT(*)              AS calls,
           COUNT(DISTINCT payer) AS payers
    FROM payment_guards
    WHERE consumed_at >= {WINDOW}
      AND endpoint IN ('/api/v1/signal', '/api/v1/whaleflow')
    GROUP BY endpoint
    ORDER BY endpoint
""").fetchall()
for ep, calls, payers in rows2:
    print(f"  {ep:26} calls={calls:4}  payers={payers:3}")
print()
print("=== всичко някога (all-time) по endpoint ===")
rows3 = cur.execute("""
    SELECT endpoint, COUNT(*), COUNT(DISTINCT payer), MIN(consumed_at), MAX(consumed_at)
    FROM payment_guards
    GROUP BY endpoint ORDER BY endpoint
""").fetchall()
for ep, calls, payers, lo, hi in rows3:
    print(f"  {ep:26} calls={calls:4}  payers={payers:3}  {lo} → {hi}")
print()
print("=== последни 12 плащания (контрол) ===")
for r in cur.execute("""
    SELECT consumed_at, endpoint, payer, amount_usdc
    FROM payment_guards ORDER BY consumed_at DESC LIMIT 12
"""):
    print("  ", r[0], r[1], (r[2] or "")[:12], r[3])