"""The public ledger must say WHOSE payment each row is, and not how to verify it.

THE COMPLAINT, in the owner's words on 09.11: four fresh settlements appeared and
he could not tell whether they were his or a customer's. Thirteen of that day's
fourteen payments were his own tests, and the page rendered them as one
undifferentiated column of `$0.003`s.

The cause was one line. The public row was built as

    {"ts": row.get("ts"), "amount": row.get("amount_usdc")}

— no `payer_class` — as part of F-01, the rule that the free surface must not hand
over what the paid `/api/sales` sells. The rule is right and the FIELD WAS CAUGHT
IN THE SAME NET BY ACCIDENT.

A category is not an identity. `/api/sales` sells how to FIND and VERIFY a payment:
the 66-character hash, the sender address, the route, the block number. Whether a
payment was our own probe, a market robot, or a stranger reveals nothing BaseScan
does not, and it is precisely what is needed to read the ledger honestly.

These tests pin BOTH halves, because fixing one by breaking the other would be the
expensive mistake.
"""

import main


def _public_history():
    client = main.app.test_client()
    doc = client.get("/api/dashboard/data").get_json()
    return ((doc.get("sections") or {}).get("onchain") or {}).get("history") or []


# ── the half that had to be added ───────────────────────────────────────────

def test_every_public_row_carries_its_payer_class():
    rows = _public_history()
    assert rows, "no history at all"
    missing = [r for r in rows if "payer_class" not in r]
    assert not missing, (
        "%d public rows say nothing about whose payment they are, which is "
        "exactly what made 13 of 14 self-payments indistinguishable from a "
        "customer's" % len(missing))


def test_the_public_class_is_a_known_one():
    """A class with no label is a class the legend cannot explain."""
    rows = _public_history()
    labels = main.PAYER_CLASS_LABELS_BG
    for r in rows:
        cls = r.get("payer_class")
        if cls:
            assert cls in labels, (
                "%r appears on the board with no label, so a reader sees a "
                "colour and no words" % cls)


def test_our_own_payments_are_distinguishable_from_a_customers():
    """THE POINT, asserted directly: if both are present, they must differ."""
    rows = _public_history()
    classes = {r.get("payer_class") for r in rows}
    if "own_key" in classes and "external" in classes:
        assert main.PAYER_CLASS_LABELS_BG["own_key"] != \
            main.PAYER_CLASS_LABELS_BG["external"]
    # and the labels themselves must say which is business
    assert "клиент" in main.PAYER_CLASS_LABELS_BG["external"]
    assert "не е клиент" in main.PAYER_CLASS_LABELS_BG["own_key"]


# ── the half that must NOT be given away ────────────────────────────────────

def test_the_public_row_still_hides_what_the_paid_route_sells():
    """F-01. `payer_class` was added; nothing else may follow it."""
    rows = _public_history()
    assert rows, "no history at all"
    for row in rows:
        for paid in ("tx_hash", "sender", "route", "block_number",
                     "payer_label"):
            assert paid not in row, (
                "%r is on the free board, and it is what /api/sales sells — "
                "the free surface must not hand it over" % paid)


def test_the_public_row_is_still_small():
    """A shape check against the net widening quietly over time."""
    rows = _public_history()
    assert rows
    assert set(rows[0]) <= {"ts", "amount", "payer_class"}, (
        "the public row grew beyond what the board needs: %s" % sorted(rows[0]))


# ── the board can actually draw it ──────────────────────────────────────────

def test_the_public_table_has_a_column_for_it():
    """A field nobody renders answers no question. This is the assertion that
    would have caught the original bug on the template side too."""
    from pathlib import Path

    tpl = (Path(__file__).resolve().parent.parent
           / "templates" / "dashboard.html").read_text(encoding="utf-8")
    head = tpl.split("const SALES_HEAD_PUBLIC")[1].split(";")[0]
    assert "Кой" in head, (
        "the public sales table has no column for the payer class, so the field "
        "is served and never seen")
    assert "h.payer_class" in tpl
    # and the legend must not be a second, hand-written copy of the words
    assert "lb[pubCls] || CLS_WORDS[pubCls]" in tpl, (
        "the public row invents its own wording instead of using the server's "
        "labels, so the legend and the table can disagree about one class")
