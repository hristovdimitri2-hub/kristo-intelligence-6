"""The organism's sense layer and journal — the rule enforced by construction.

THE ONE RULE THESE TESTS EXIST FOR. This codebase has spent a week closing one
version of the same defect: something could not be looked at, and the surface
reported it as a thing that was looked at and found empty. The dashboard learned
it panel by panel. The organism has to hold it for the whole system at once,
because its entire job is to answer "is the platform well" — and the most
dangerous possible answer is a confident `ok` produced by a check that never ran.

So `not_reached` is a first-class verdict here, it is counted as UNHEALTHY, and
the tests below pin that in both directions:

  * a check that raises must return `not_reached`, never `ok`;
  * a block that never reported must NOT be summed as healthy;
  * an empty journal and an unreadable journal must be distinguishable.

The journal half is the organism's memory: append-only, bounded, never raising.
Its tests exist because a journal that can be edited, or that grows without limit,
or that fails the caller it describes, is worse than no journal at all.
"""

import json

import pytest

from services import organism as org
from services import organism_journal as oj


class FakeHistory:
    """A durable-meta store with no database behind it.

    It implements BOTH access shapes the organism uses: the single-key
    `get_durable_meta` (for writes and one-off reads) and `_run` (for the batched
    `IN (...)` read that keeps the board build at one round-trip instead of
    eighteen). A fake that implemented only the first would let a regression in
    the second pass unnoticed.
    """

    def __init__(self):
        self.d = {}
        self.fail_reads = False
        self.fail_writes = False

    def get_durable_meta(self, key, default=None):
        if self.fail_reads:
            raise RuntimeError("store is unreachable")
        return self.d.get(key, default)

    def set_durable_meta(self, key, value):
        if self.fail_writes:
            raise RuntimeError("store is read-only")
        self.d[key] = value

    def _run(self, sql, params=(), fetch=""):
        """Just enough of the real signature for the batched heartbeat read."""
        if self.fail_reads:
            raise RuntimeError("store is unreachable")
        rows = [{"key": k, "value": self.d[k]} for k in params if k in self.d]
        return rows, len(rows)


class FakeStore:
    def __init__(self):
        self.history = FakeHistory()


@pytest.fixture()
def store():
    return FakeStore()


# ── the vocabulary ───────────────────────────────────────────────────────────

def test_the_four_verdicts_are_exactly_the_shared_vocabulary():
    """A fifth state would be handled by nobody, and a missing one would be
    invented by whoever needed it."""
    assert set(org.VERDICTS) == {"ok", "degraded", "failed", "not_reached"}


def test_not_reached_is_counted_as_unhealthy():
    """THE rule. "We did not look" is not a healthy state and must never be
    summed as one — that is the whole defect class, in one assertion."""
    assert org.NOT_REACHED in org.UNHEALTHY
    assert org.OK not in org.UNHEALTHY


def test_an_unknown_verdict_is_rejected_rather_than_accepted(store):
    """A typo must not silently create a state the callers do not handle."""
    with pytest.raises(ValueError):
        org.Verdict(block="data_store", verdict="fine")


def test_a_verdict_without_a_timestamp_gets_one():
    v = org.Verdict(block="data_store", verdict=org.OK)
    assert v.at and "T" in v.at, "a verdict must carry when it was reached"
    assert v.healthy is True


# ── the runner ───────────────────────────────────────────────────────────────

def test_a_check_that_raises_becomes_not_reached(store):
    """The most important test in this file.

    A self-check exploding is a fact about the CHECK. Reporting it as `ok` would
    be a lie about the block; omitting the block would hide it. `not_reached`
    says exactly the true thing.
    """
    reg = org.Registry()

    def exploding_check():
        raise RuntimeError("psycopg is on fire")

    reg.register("data_store", exploding_check)
    v = reg.run_one("data_store")
    assert v.verdict == org.NOT_REACHED, (
        "a throwing self-check was reported as %r" % v.verdict)
    assert "psycopg is on fire" in v.detail
    assert v.verdict != org.OK


def test_a_check_returning_the_wrong_type_becomes_not_reached(store):
    """A check that returns None (a forgotten `return`) must not be read as a
    pass — `None` is falsy and a careless caller would treat it as one."""
    reg = org.Registry()
    reg.register("chain_read", lambda: None)
    v = reg.run_one("chain_read")
    assert v.verdict == org.NOT_REACHED
    assert "not a Verdict" in v.detail


def test_a_block_with_no_registered_check_is_not_reached(store):
    reg = org.Registry()
    v = reg.run_one("delivery")
    assert v.verdict == org.NOT_REACHED, (
        "a block nobody checks was reported as healthy")
    assert "no self-check" in v.detail


def test_one_failing_block_does_not_stop_the_others(store):
    """The property the dashboard already proves for its panels, generalised:
    one block dying must not take the building with it."""
    reg = org.Registry()

    def exploding_check():
        raise ValueError("nope")

    def fine_check():
        return org.Verdict(block="data_store", verdict=org.OK)

    reg.register("payment_rail", exploding_check)
    reg.register("data_store", fine_check)

    out = reg.run_all()
    verdicts = {v.block: v.verdict for v in out}
    assert verdicts["payment_rail"] == org.NOT_REACHED
    assert verdicts["data_store"] == org.OK, (
        "a second block was lost because the first one raised")


def test_an_unknown_block_cannot_be_registered():
    reg = org.Registry()
    with pytest.raises(ValueError):
        reg.register("not_a_real_block", lambda: None)


# ── heartbeats ───────────────────────────────────────────────────────────────

def test_a_beat_is_recorded_and_read_back(store):
    assert org.beat(store, "data_store", org.OK, "answered in 4ms") is True
    v = org.last_verdict(store, "data_store")
    assert v["verdict"] == org.OK
    assert v["age_seconds"] is not None and v["age_seconds"] < 5


def test_a_block_that_never_beat_is_not_reached_not_ok(store):
    """Every block starts here. Calling it healthy would make a system that has
    never reported look perfect."""
    v = org.last_verdict(store, "delivery")
    assert v["verdict"] == org.NOT_REACHED
    assert v["at"] is None


def test_a_beat_never_raises_when_the_store_is_broken(store):
    """Telemetry must not be able to fail the thing it describes."""
    store.history.fail_writes = True
    assert org.beat(store, "data_store", org.OK) is False  # no exception


def test_a_stale_heartbeat_that_last_said_ok_is_reported_as_failed(store):
    """THE trap: a writer that stopped leaves behind a last word of "fine".

    Reading only the verdict would show a healthy block indefinitely after the
    loop died. The freshness window is what turns that into the truth.
    """
    store.history.d["organism_hb_data_store"] = "2020-01-01T00:00:00+00:00"
    store.history.d["organism_hb_data_store_verdict"] = org.OK
    v = org.last_verdict(store, "data_store")
    assert v["verdict"] == org.FAILED, (
        "a heartbeat from 2020 still reported %r" % v["verdict"])
    assert "last said ok" in v["detail"]


def test_an_unreadable_heartbeat_is_not_reached(store):
    store.history.d["organism_hb_chain_read"] = "not a timestamp"
    v = org.last_verdict(store, "chain_read")
    assert v["verdict"] == org.NOT_REACHED
    assert v["age_seconds"] is None


def test_a_broken_store_leaves_the_verdict_unknown(store):
    store.history.fail_reads = True
    v = org.last_verdict(store, "data_store")
    assert v["verdict"] == org.NOT_REACHED, (
        "a store we cannot read produced %r" % v["verdict"])


def test_no_store_at_all_is_not_reached_not_a_crash():
    v = org.last_verdict(None, "data_store")
    assert v["verdict"] == org.NOT_REACHED
    assert org.beat(None, "data_store", org.OK) is False


def test_the_summary_counts_every_block_and_counts_not_reached(store):
    """A fresh system must report six unhealthy blocks, not zero."""
    org.beat(store, "data_store", org.OK)
    s = org.summary(store)
    assert len(s["blocks"]) == len(org.BLOCKS)
    assert s["counts"][org.OK] == 1
    assert s["counts"][org.NOT_REACHED] == len(org.BLOCKS) - 1
    assert s["unhealthy"] == len(org.BLOCKS) - 1, (
        "blocks that never reported were not counted as unhealthy")


def test_the_summary_says_what_not_reached_means(store):
    """The page has to be able to explain the word to a human."""
    s = org.summary(store)
    assert "not_reached" in s["note"]
    assert "did not run" in s["note"]


# ── the journal ──────────────────────────────────────────────────────────────

def test_an_entry_carries_when_what_and_why(store):
    oj.append(store, "payment_rail", "settle_failed", severity=oj.ERROR,
              detail="facilitator refused", outcome="escalated")
    rows = oj.entries(store)
    assert len(rows) == 1
    r = rows[0]
    assert r["block"] == "payment_rail"
    assert r["kind"] == "settle_failed"
    assert r["severity"] == oj.ERROR
    assert r["at"], "an entry without a time cannot be ordered or aged"


def test_the_kind_is_normalised_so_the_rule_table_can_match_it(store):
    """`kind` is what a rule matches on. "Settle Failed" and "settle_failed"
    must not become two different rules."""
    oj.append(store, "payment_rail", "Settle Failed")
    assert oj.entries(store)[0]["kind"] == "settle_failed"


def test_an_unknown_severity_becomes_info_rather_than_a_new_state(store):
    oj.append(store, "data_store", "x", severity="catastrophic")
    assert oj.entries(store)[0]["severity"] == oj.INFO


def test_entries_come_back_newest_first(store):
    oj.append(store, "data_store", "first", at="2026-01-01T00:00:00+00:00")
    oj.append(store, "data_store", "second", at="2026-01-02T00:00:00+00:00")
    rows = oj.entries(store)
    assert [r["kind"] for r in rows] == ["second", "first"]


def test_entries_can_be_filtered_by_block_kind_and_severity(store):
    oj.append(store, "data_store", "a", severity=oj.WARN)
    oj.append(store, "chain_read", "b", severity=oj.ERROR)
    assert len(oj.entries(store, block="data_store")) == 1
    assert len(oj.entries(store, severity=oj.ERROR)) == 1
    assert len(oj.entries(store, kind="a")) == 1


def test_the_journal_is_bounded_however_many_entries_arrive(store):
    """A table with no limit is what took the service down on 07.11. The bound
    is applied on WRITE, so a purge that never runs cannot let it grow."""
    for i in range(oj.MAX_ENTRIES + 50):
        oj.append(store, "data_store", "tick", detail=str(i))
    assert len(oj.entries(store, limit=oj.MAX_ENTRIES + 100)) == oj.MAX_ENTRIES


def test_appending_never_raises_when_the_store_is_broken(store):
    store.history.fail_writes = True
    assert oj.append(store, "data_store", "tick") is False  # no exception


def test_a_corrupt_journal_reads_as_empty_rather_than_crashing(store):
    store.history.d["organism_journal"] = "{not json"
    assert oj.entries(store) == []


def test_a_journal_that_is_not_a_list_reads_as_empty(store):
    """A JSON object where a list belongs — a shape change — must not be
    iterated as if it were entries."""
    store.history.d["organism_journal"] = json.dumps({"oops": True})
    assert oj.entries(store) == []


def test_an_empty_journal_is_readable_and_an_unreadable_one_is_not(store):
    """The distinction the whole codebase keeps: "nothing has happened" and "we
    cannot see what happened" call for opposite reactions."""
    assert oj.readable(store) is True
    assert oj.entries(store) == []
    store.history.fail_reads = True
    assert oj.readable(store) is False


def test_counts_are_per_severity_over_a_window(store):
    oj.append(store, "a", "x", severity=oj.WARN)
    oj.append(store, "a", "y", severity=oj.ERROR)
    oj.append(store, "a", "z", severity=oj.INFO)
    c = oj.counts(store, hours=24)
    assert c[oj.WARN] == 1 and c[oj.ERROR] == 1 and c[oj.INFO] == 1
    assert c["total"] == 3


def test_an_old_entry_is_outside_the_window(store):
    oj.append(store, "a", "old", severity=oj.ERROR,
              at="2020-01-01T00:00:00+00:00")
    c = oj.counts(store, hours=24)
    assert c[oj.ERROR] == 0, "an entry from 2020 was counted in the last 24h"
    assert c["total"] == 0


def test_prune_drops_the_oldest_and_is_idempotent(store):
    for i in range(10):
        oj.append(store, "a", "t%d" % i)
    assert oj.prune(store, keep=4) == 6
    assert len(oj.entries(store, limit=100)) == 4
    assert oj.prune(store, keep=4) == 0, "a second prune removed something"


def test_prune_keeps_the_newest_entries(store):
    for i in range(5):
        oj.append(store, "a", "t%d" % i)
    oj.prune(store, keep=2)
    assert [r["kind"] for r in oj.entries(store)] == ["t4", "t3"]


# ── the board must show it ───────────────────────────────────────────────────
#
# A verdict nobody renders is a verdict nobody has. These guard the projection
# the dashboard payload builds, in the same style as the other panel guards.

def test_the_board_reports_an_unavailable_organism_as_unavailable(monkeypatch):
    """If the organism cannot answer, the board must NOT show six healthy
    blocks — it must say it could not read them.

    The failure is injected by making the module's own `summary` raise, through
    the same import path `_safe_organism_summary` uses, so the test exercises the
    real guard rather than a stand-in for it.
    """
    import main
    from services import organism as real_org

    def explode(store):
        raise RuntimeError("module exploded")

    monkeypatch.setattr(real_org, "summary", explode)
    out = main._safe_organism_summary()
    assert out.get("available") is False, (
        "a failed organism read was reported as a normal summary: %r" % out)
    assert out.get("unhealthy") is None, (
        "an unread organism reported a count, which reads as a measurement")
    assert "NOT the same as every block being well" in out["note"]


def test_the_board_marks_an_unreadable_journal_as_unreadable(monkeypatch):
    import main
    from services import organism_journal as real_oj

    monkeypatch.setattr(real_oj, "readable", lambda store: False)
    out = main._safe_organism_journal()
    assert out["unreadable"] is True, (
        "a journal we cannot read was presented as an empty one")
