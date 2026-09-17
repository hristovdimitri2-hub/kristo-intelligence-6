"""Fill the payment facts of a sale that predates them (paid_at / checkout_id).

WHY IT MUST RUN INSIDE RENDER: the database host (`dpg-…`) is internal to Render's
network and does not resolve from the outside, so this cannot be run from a laptop
against production. On a Render shell (or a one-off job) it works as is.

Use it for rows written before 17.09 — the columns did not exist, so their sale is
still dated by the LEAD, and the dashboard falls back to that. Never guess the
values: take them from the verified Stripe event (`GET /v1/events/<evt_id>`:
`created` and `data.object.id`), the same pair the Stripe feed cross-checks.

Default values are the project's FIRST sale, verified twice (event
`evt_1UGEdQPz7WIGP94b829zoDXH`, session `cs_live_a14DQkU4yfws5IMIZ1v5cs8UVbw0gh8kwjzvXJzfGn16dkscLZrBsojexK`,
$34.80 = $29.00 + $5.80 VAT):

    python -X utf8 scripts/backfill_payment_facts.py

Guards: touches exactly two columns, only on a row that is ALREADY paid, and only
while `paid_at` is still empty (idempotent — a second run changes nothing).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = "srv-d9maroe7bikc73adkaug"
DEFAULT_EMAIL = "hristovdimitri2@gmail.com"
DEFAULT_PAID_AT = "2026-09-16T08:56:08+00:00"
DEFAULT_CHECKOUT = ("cs_live_a14DQkU4yfws5IMIZ1v5cs8UVbw0gh8kwjzvXJzfGn16dkscLZr"
                    "BsojexK")
#: The refund of that same sale, verified at Stripe on 17.09 (refund
#: `re_3UGEdKPz7WIGP94b0eWVeE61`, charge `ch_3UGEdKPz7WIGP94b0H7e62si`,
#: `amount_refunded` 3480, status succeeded, created 06:23:30 UTC).
DEFAULT_REFUND_USD = 34.80
DEFAULT_REFUNDED_AT = "2026-09-17T06:23:30+00:00"


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

ap = argparse.ArgumentParser()
ap.add_argument("--email", default=DEFAULT_EMAIL)
ap.add_argument("--paid-at", default=DEFAULT_PAID_AT,
                help="the Stripe EVENT's created time (ISO-8601, UTC)")
ap.add_argument("--checkout-id", default=DEFAULT_CHECKOUT)
ap.add_argument("--refund-usd", type=float, default=DEFAULT_REFUND_USD,
                help="the CUMULATIVE refunded amount (Stripe's amount_refunded)")
ap.add_argument("--refunded-at", default=DEFAULT_REFUNDED_AT,
                help="the refund's own created time (ISO-8601, UTC)")
args = ap.parse_args()
EMAIL, PAID_AT, CHECKOUT = args.email, args.paid_at, args.checkout_id
REFUND_USD, REFUNDED_AT = args.refund_usd, args.refunded_at

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
    cur.execute("SELECT email, plan, amount_usd, payment_status, created_at, "
                "paid_at, checkout_id, refund_usd, refunded_at "
                "FROM leads WHERE email = %s",
                (EMAIL,))
    before = cur.fetchone()
    print("BEFORE:", before)
    if not before:
        sys.exit("that lead is not in the table — nothing to do")
    if (before.get("payment_status") or "") != "paid":
        sys.exit("the row is NOT paid — refusing to touch it")
    if before.get("paid_at"):
        print("payment facts already backfilled")
    else:
        cur.execute(
            """
            UPDATE leads
            SET paid_at = %s, checkout_id = %s
            WHERE email = %s AND payment_status = 'paid' AND paid_at IS NULL
            """,
            (PAID_AT, CHECKOUT, EMAIL))
        print("payment rows updated:", cur.rowcount)

    if float(before.get("refund_usd") or 0) > 0:
        print("refund already recorded:", before.get("refund_usd"))
    else:
        cur.execute(
            """
            UPDATE leads
            SET refund_usd = %s,
                refunded_at = CASE WHEN %s <> '' THEN %s ELSE refunded_at END
            WHERE email = %s AND payment_status = 'paid'
            """,
            (REFUND_USD, REFUNDED_AT, REFUNDED_AT, EMAIL))
        print("refund rows updated:", cur.rowcount)
    conn.commit()
    cur.execute("SELECT email, plan, amount_usd, payment_status, created_at, "
                "paid_at, checkout_id, refund_usd, refunded_at "
                "FROM leads WHERE email = %s", (EMAIL,))
    after = cur.fetchone()
print("AFTER :", after)
print("paid_at == the Stripe event time:",
      after.get("paid_at") == PAID_AT)
print("checkout_id matches the verified session:",
      after.get("checkout_id") == CHECKOUT)
print("refund_usd == the verified cumulative refund:",
      float(after.get("refund_usd") or 0) == REFUND_USD)
print("refunded_at == the refund's own time:",
      after.get("refunded_at") == REFUNDED_AT)