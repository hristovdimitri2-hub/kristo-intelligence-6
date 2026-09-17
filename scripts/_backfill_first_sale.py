"""Backfill the FIRST sale's payment facts — the one row that predates the columns.

The values are not invented: both come from the verified Stripe event of
2026-09-16 08:56:08 UTC (event `evt_1UGEdQPz7WIGP94b829zoDXH`, session
`cs_live_a14DQkU4yfws5IMIZ1v5cs8UVbw0gh8kwjzvXJzfGn16dkscLZrBsojexK`, $34.80 =
$29.00 + $5.80 VAT), the same pair the audit proved and the Stripe feed
cross-checks.

Guards: touches exactly two columns, only on a row that is ALREADY paid, and only
when `paid_at` is still empty (idempotent — a second run changes nothing).
"""
from __future__ import annotations

import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = "srv-d9maroe7bikc73adkaug"
EMAIL = "hristovdimitri2@gmail.com"
PAID_AT = "2026-09-16T08:56:08+00:00"
CHECKOUT = "cs_live_a14DQkU4yfws5IMIZ1v5cs8UVbw0gh8kwjzvXJzfGn16dkscLZrBsojexK"


def render_env():
    key = open(os.path.join(ROOT, "secrets", "render_api_key.txt"),
               encoding="utf-8").read().strip()
    for _ in range(5):
        try:
            out = {}
            for item in requests.get(
                    "https://api.render.com/v1/services/%s/env-vars?limit=100"
                    % SERVICE,
                    headers={"Authorization": "Bearer " + key,
                             "Accept": "application/json"},
                    timeout=90).json():
                ev = item.get("envVar", item)
                out[ev.get("key")] = ev.get("value")
            return out
        except Exception:
            time.sleep(4)
    return {}


url = (render_env().get("DATABASE_URL") or "").strip()
if not url:
    sys.exit("no DATABASE_URL in the Render env")

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
    cur.execute("SELECT email, plan, amount_usd, payment_status, created_at, "
                "paid_at, checkout_id FROM leads WHERE email = %s",
                (EMAIL,))
    before = cur.fetchone()
    print("BEFORE:", before)
    if not before:
        sys.exit("that lead is not in the table — nothing to do")
    if (before.get("payment_status") or "") != "paid":
        sys.exit("the row is NOT paid — refusing to touch it")
    if before.get("paid_at"):
        print("already backfilled — nothing to do")
    else:
        cur.execute(
            """
            UPDATE leads
            SET paid_at = %s, checkout_id = %s
            WHERE email = %s AND payment_status = 'paid' AND paid_at IS NULL
            """,
            (PAID_AT, CHECKOUT, EMAIL))
        print("rows updated:", cur.rowcount)
    conn.commit()
    cur.execute("SELECT email, plan, amount_usd, payment_status, created_at, "
                "paid_at, checkout_id FROM leads WHERE email = %s", (EMAIL,))
    after = cur.fetchone()
print("AFTER :", after)
print("paid_at == the Stripe event time:",
      after.get("paid_at") == PAID_AT)
print("checkout_id matches the verified session:",
      after.get("checkout_id") == CHECKOUT)