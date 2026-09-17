"""What a sale MUST record: when the money arrived, and which session paid.

Found while auditing the first human payment (16.09, $29 Starter): the CRM stored
neither, so the dashboard dated the sale by the LEAD's creation — right by luck
that time (38 seconds apart), wrong by hours whenever a buyer pays later — and no
CRM row could be joined to a Stripe payment at all. The same audit showed a second
hole next to it: a re-submitted checkout form carried fresh "pending"/$0 defaults
and was applied blindly, so it reset payment_status and amount_usd — erasing the
only off-chain money record there is.
"""

import sqlite3

from integrations.crm_store import CRMStore, LeadRecord

PAID_AT = "2026-09-16T08:56:08+00:00"
CHECKOUT = "cs_live_a14DQkU4yfws5IMIZ1v5cs8UVbw0gh8kwjzvXJzfGn16dkscLZrBsojexK"


def _lead(email="buyer@example.com", **kwargs):
    return LeadRecord(email=email, source="website", campaign="launch", **kwargs)


def test_mark_paid_records_when_the_money_arrived_and_which_session(tmp_path):
    store = CRMStore(tmp_path / "crm.db")
    store.add_lead(_lead())

    paid = store.mark_paid("buyer@example.com", 34.80, "starter",
                           checkout_id=CHECKOUT, paid_at=PAID_AT)

    assert paid["payment_status"] == "paid"
    assert paid["paid_at"] == PAID_AT, "the sale is dated by the PAYMENT"
    assert paid["checkout_id"] == CHECKOUT, "and joined to its Stripe session"
    stored = store.find_by_email("buyer@example.com")
    assert (stored["paid_at"], stored["checkout_id"]) == (PAID_AT, CHECKOUT)


def test_an_empty_timestamp_never_erases_a_known_payment_time(tmp_path):
    """A later event without a timestamp (a re-delivery, a manual mark) must not
    blank the record: an empty string means "unknown", not "never paid"."""
    store = CRMStore(tmp_path / "crm.db")
    store.add_lead(_lead())
    store.mark_paid("buyer@example.com", 34.80, "starter",
                    checkout_id=CHECKOUT, paid_at=PAID_AT)

    store.mark_paid("buyer@example.com", 34.80, "starter")

    stored = store.find_by_email("buyer@example.com")
    assert stored["paid_at"] == PAID_AT
    assert stored["checkout_id"] == CHECKOUT


def test_a_paid_lead_is_never_downgraded_by_a_resubmitted_form(tmp_path):
    """The form sends a FRESH lead ("pending", $0). It used to overwrite the stored
    row, so a buyer who re-opened the page after paying turned their own sale back
    into "pending" — and would now also wipe paid_at and checkout_id."""
    store = CRMStore(tmp_path / "crm.db")
    store.add_lead(_lead())
    store.mark_paid("buyer@example.com", 34.80, "starter",
                    checkout_id=CHECKOUT, paid_at=PAID_AT)

    again = store.add_lead(_lead(utm_source="twitter"))

    assert again["payment_status"] == "paid", "the sale survives the resubmission"
    assert again["amount_usd"] == 34.80
    assert again["paid_at"] == PAID_AT and again["checkout_id"] == CHECKOUT
    assert again["utm_source"] == "twitter", "new lead data is still merged in"
    assert store.get_sales_pipeline()["paid"] == 1


def test_an_old_database_gains_the_payment_columns_in_place(tmp_path):
    """The live CRM predates these columns: the row holding the first sale must
    survive the migration (ALTER in place, never a rebuild)."""
    path = tmp_path / "old.db"
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """CREATE TABLE leads (
                email TEXT PRIMARY KEY, source TEXT, campaign TEXT,
                utm_source TEXT, utm_medium TEXT, utm_campaign TEXT,
                status TEXT DEFAULT 'new', created_at TEXT, plan TEXT,
                telegram_chat_id TEXT, amount_usd REAL DEFAULT 0.0,
                payment_status TEXT DEFAULT 'pending')""")
        conn.execute(
            "INSERT INTO leads (email, created_at, plan, amount_usd, "
            "payment_status) VALUES ('first@example.com', "
            "'2026-09-16T08:55:30+00:00', 'Starter', 34.8, 'paid')")

    store = CRMStore(path)                      # opening performs the migration
    with sqlite3.connect(str(path)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(leads)")}

    assert {"paid_at", "checkout_id"} <= columns
    kept = store.find_by_email("first@example.com")
    assert kept["payment_status"] == "paid" and kept["amount_usd"] == 34.8
    store.mark_paid("first@example.com", 34.8, "Starter",
                    checkout_id="cs_live_old", paid_at=PAID_AT)
    assert store.find_by_email("first@example.com")["checkout_id"] == "cs_live_old"
# ── REFUNDS: the mirror of the payment facts, with ONE writer ───────────────

REFUND_AT = "2026-09-17T06:23:30+00:00"


def test_mark_refund_records_the_return_and_add_lead_cannot_touch_it(tmp_path):
    """`mark_refund` is the ONLY writer of refund facts — exactly like `mark_paid`
    for payments. A refunded sale is still a sale that happened, so the payment
    facts stay exactly as they were and the return is its own pair of fields.
    """
    store = CRMStore(tmp_path / "crm.db")
    store.add_lead(_lead())
    store.mark_paid("buyer@example.com", 34.80, "starter",
                    checkout_id=CHECKOUT, paid_at=PAID_AT)

    refunded = store.mark_refund("buyer@example.com", 34.80, REFUND_AT)

    assert refunded["refund_usd"] == 34.80
    assert refunded["refunded_at"] == REFUND_AT
    # the sale itself is untouched
    assert refunded["payment_status"] == "paid"
    assert refunded["amount_usd"] == 34.80 and refunded["paid_at"] == PAID_AT

    # a re-submitted form carries "pending"/$0 and no refund fields: it must not
    # erase the return either
    again = store.add_lead(_lead(utm_source="twitter"))
    assert again["refund_usd"] == 34.80 and again["refunded_at"] == REFUND_AT
    assert again["payment_status"] == "paid"


def test_a_refund_before_its_payment_is_refused_by_design(tmp_path, caplog):
    """Money that was never booked as received cannot be refunded on the books:
    the refusal is the correct answer, and it is LOGGED (a silent no-op would look
    like a recorded refund)."""
    import logging

    store = CRMStore(tmp_path / "crm.db")
    store.add_lead(_lead())                      # exists, but payment_status=pending

    with caplog.at_level(logging.WARNING, logger="integrations.crm_store"):
        refused = store.mark_refund("buyer@example.com", 34.80, REFUND_AT)

    assert refused is None, "refund before payment must not be written"
    stored = store.find_by_email("buyer@example.com")
    assert stored["refund_usd"] in (0, 0.0, None) and not stored["refunded_at"]
    assert any("Refusing a refund" in r.getMessage() for r in caplog.records)
    assert "buyer@example.com" not in caplog.text, "emails stay masked in logs"


def test_partial_refunds_accumulate_through_the_cumulative_amount(tmp_path):
    """Stripe reports `amount_refunded` CUMULATIVELY, and that is what the handler
    stores: two partial refunds must add up, never overwrite each other."""
    store = CRMStore(tmp_path / "crm.db")
    store.add_lead(_lead())
    store.mark_paid("buyer@example.com", 34.80, "starter",
                    checkout_id=CHECKOUT, paid_at=PAID_AT)

    store.mark_refund("buyer@example.com", 10.00, "2026-09-17T07:00:00+00:00")
    final = store.mark_refund("buyer@example.com", 34.80, REFUND_AT)

    assert final["refund_usd"] == 34.80, "the cumulative total, not the last part"
    assert final["refunded_at"] == REFUND_AT


def test_an_old_database_gains_the_refund_columns_in_place(tmp_path):
    """The live CRM predates these columns too: they are ALTERed in, and the row
    holding the first sale survives."""
    path = tmp_path / "old.db"
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """CREATE TABLE leads (
                email TEXT PRIMARY KEY, source TEXT, campaign TEXT,
                utm_source TEXT, utm_medium TEXT, utm_campaign TEXT,
                status TEXT DEFAULT 'new', created_at TEXT, plan TEXT,
                telegram_chat_id TEXT, amount_usd REAL DEFAULT 0.0,
                payment_status TEXT DEFAULT 'pending', paid_at TEXT,
                checkout_id TEXT)""")
        conn.execute(
            "INSERT INTO leads (email, created_at, plan, amount_usd, "
            "payment_status, paid_at) VALUES ('first@example.com', "
            "'2026-09-16T08:55:30+00:00', 'Starter', 34.8, 'paid', "
            "'2026-09-16T08:56:08+00:00')")

    store = CRMStore(path)
    with sqlite3.connect(str(path)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(leads)")}

    assert {"refunded_at", "refund_usd"} <= columns
    kept = store.find_by_email("first@example.com")
    assert kept["payment_status"] == "paid" and kept["paid_at"]
    assert store.mark_refund("first@example.com", 34.8, REFUND_AT)["refund_usd"] \
        == 34.8