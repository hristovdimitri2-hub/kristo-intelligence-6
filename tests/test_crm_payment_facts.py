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