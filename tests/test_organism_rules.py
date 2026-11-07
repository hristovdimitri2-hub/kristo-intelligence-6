"""The rule table — the safety boundary, pinned by test.

THE TABLE IS THE WHOLE POLICY. If a signal is not in it, the organism does not
act on that signal. So the tests that matter most are not "does it classify
correctly" — they are the ones that prove the BOUNDARY holds:

  * an escalation can never reach an executor, in any mode;
  * an action outside the six safe verbs cannot be named by a rule at all;
  * a rule that has never fired is data, not a bug — and `digest` says which;
  * `not_reached` never becomes an action, because "nobody looked" is not
    "something is broken", and restarting on it would make the organism thrash
    on every single deploy;
  * observe-only mode really does not act.

Each of those is a mistake that would be invisible in normal operation and
catastrophic on the day it mattered.
"""

import pytest

from services import organism as org
from services import organism_rules as R


@pytest.fixture(autouse=True)
def _clean_ledger():
    """The blast-radius ledger is module state; leak it and tests interfere."""
    R.reset_ledger()
    yield
    R.reset_ledger()


class _History:
    def __init__(self):
        self.d = {}

    def get_durable_meta(self, key, default=None):
        return self.d.get(key, default)

    def set_durable_meta(self, key, value):
        self.d[key] = value

    def _run(self, sql, params=(), fetch=""):
        rows = [{"key": k, "value": self.d[k]} for k in params if k in self.d]
        return rows, len(rows)


class _Store:
    def __init__(self):
        self.history = _History()


@pytest.fixture()
def store():
    return _Store()


# ── the vocabulary ───────────────────────────────────────────────────────────

def test_there_are_exactly_three_classes():
    """A fourth would be invented by whoever needed it, and the difference
    between self_heal and escalate IS the safety boundary."""
    assert set(R.CLASSES) == {"self_heal", "escalate", "observe"}


def test_the_executor_vocabulary_is_exactly_the_six_safe_verbs():
    assert set(R.EXECUTORS) == {
        "rotate_endpoint", "restart_loop", "rebuild_cache", "recreate_index",
        "purge_older_than", "re_warm"}


def test_no_rule_names_a_forbidden_effect():
    """THE boundary rule: nothing in the table moves money, changes a price,
    edits a receiver, touches secrets, or pushes to main."""
    for r in R.RULES:
        assert r.action not in R.FORBIDDEN_EFFECTS, (
            "rule %r names forbidden effect %r" % (r.signal, r.action))


def test_a_rule_cannot_be_defined_with_a_forbidden_effect():
    """Not merely absent from the table — UNREPRESENTABLE in it."""
    with pytest.raises(ValueError):
        R.Rule("evil", R.SELF_HEAL, "move_money")


def test_a_self_heal_rule_cannot_name_an_unknown_action():
    with pytest.raises(ValueError):
        R.Rule("evil", R.SELF_HEAL, "delete_everything")


def test_a_self_heal_rule_with_no_action_is_rejected():
    with pytest.raises(ValueError):
        R.Rule("evil", R.SELF_HEAL, "")


def test_an_unknown_class_is_rejected():
    with pytest.raises(ValueError):
        R.Rule("x", "probably_fine")


def test_escalate_and_observe_rules_carry_no_action():
    """An escalating rule that named an action would read as a plan to act."""
    for r in R.RULES:
        if r.klass in (R.ESCALATE, R.OBSERVE):
            assert r.action == "", (
                "%s rule %r names action %r" % (r.klass, r.signal, r.action))


# ── the table's contents ─────────────────────────────────────────────────────

def test_the_six_self_heal_signals_are_the_six_safe_verbs():
    """One signal per verb, so every executor is reachable and none is
    unreachable. A verb with no signal is dead code; a signal with no verb is
    a hole."""
    mapping = {r.signal: r.action for r in R.RULES if r.klass == R.SELF_HEAL}
    assert set(mapping.values()) == set(R.EXECUTORS), (
        "the self-heal rules do not cover the executor vocabulary exactly")
    assert len(mapping) == len(R.EXECUTORS), "two signals share one action"


def test_every_rule_states_why():
    """A rule with no stated reason is a rule nobody can review."""
    for r in R.RULES:
        assert r.why.strip(), "rule %r has no reason" % r.signal


def test_the_business_signal_escalates_rather_than_self_heals():
    """Traffic arriving and nobody paying is not a technical fault. No amount of
    self-healing changes an offer, so this must never reach an executor."""
    r = R.lookup("conversion_below_floor")
    assert r.klass == R.ESCALATE
    assert r.action == ""


def test_a_settled_payment_we_did_not_record_escalates():
    """The one class of bug worth a human reading every instance: money moved
    and our records disagree. Automatic repair could hide an accounting defect."""
    assert R.lookup("payment_settles_but_not_recorded").klass == R.ESCALATE


# ── lookup ───────────────────────────────────────────────────────────────────

def test_an_unrecognised_signal_is_recorded_not_dropped():
    """Dropping it is how a system silently ignores the one thing it had not
    seen before."""
    r = R.lookup("nobody_has_ever_seen_this")
    assert r.klass == R.OBSERVE
    assert r.signal == "anything_unrecognised"


def test_lookup_normalises_case_and_spaces():
    assert R.lookup("Heartbeat Stale").signal == "heartbeat_stale"


def test_lookup_of_nothing_is_the_catch_all():
    assert R.lookup("").klass == R.OBSERVE
    assert R.lookup(None).klass == R.OBSERVE


# ── observe-only ─────────────────────────────────────────────────────────────

def test_observe_only_never_acts():
    """The only mode implemented, and the reason for it: a rule you have never
    seen fire is a rule you cannot trust."""
    d = R.decide("heartbeat_stale", block="data_store")
    assert d.acted is False
    assert "observe-only" in d.blocked_by


def test_observe_only_still_counts_toward_the_blast_radius():
    """So the guard is TESTED before it is ever needed for real."""
    for _ in range(8):
        R.decide("heartbeat_stale", block="data_store")
    assert R.actions_last_hour()["data_store"] == R.BLAST_RADIUS_PER_HOUR


def test_a_decision_carries_what_would_be_done_and_why():
    d = R.decide("rpc_endpoint_refused", block="chain_read")
    assert d.klass == R.SELF_HEAL
    assert d.action == R.ROTATE_ENDPOINT
    assert d.why.strip()
    assert d.at


def test_the_decision_serialises_for_the_journal():
    d = R.decide("heartbeat_stale", block="data_store", detail="stale 900s")
    out = d.as_dict()
    for key in ("signal", "class", "action", "why", "block", "acted",
                "blocked_by", "at"):
        assert key in out, "the journal entry would be missing %r" % key


# ── guard 1: blast radius ────────────────────────────────────────────────────

def test_the_blast_radius_stops_a_thrashing_block():
    """A system in a loop must not be allowed to keep looping."""
    seen = [R.decide("heartbeat_stale", block="data_store") for _ in range(10)]
    blocked = [d for d in seen if "hourly action limit" in d.blocked_by]
    assert blocked, "ten decisions in a row were all allowed"
    assert len(seen) - len(blocked) == R.BLAST_RADIUS_PER_HOUR


def test_the_blast_radius_is_per_block_not_global():
    """One sick block must not consume another's budget."""
    for _ in range(R.BLAST_RADIUS_PER_HOUR + 2):
        R.decide("heartbeat_stale", block="data_store")
    d = R.decide("heartbeat_stale", block="chain_read")
    assert "hourly action limit" not in d.blocked_by, (
        "a second, healthy block inherited the first block's spent budget")


def test_an_escalation_does_not_consume_the_blast_radius():
    """Escalations never act, so they cannot exhaust an acting budget."""
    for _ in range(20):
        R.decide("deploy_failed", block="delivery")
    assert R.actions_last_hour().get("delivery", 0) == 0


# ── guard 2: verification ────────────────────────────────────────────────────

def test_an_action_is_done_only_when_the_signal_is_gone():
    assert R.verify("heartbeat_stale", lambda: False)["verified"] is True
    out = R.verify("heartbeat_stale", lambda: True)
    assert out["verified"] is False
    assert "STILL present" in out["note"]


def test_a_verification_that_cannot_run_is_not_a_pass():
    """`couldn't look` must never read as `fixed` — the same rule the dashboard
    keeps, applied to repair."""
    def boom():
        raise RuntimeError("cannot even check")

    out = R.verify("heartbeat_stale", boom)
    assert out["verified"] is False
    assert out["present"] is None
    assert "could not run" in out["note"]


# ── guard 3 & the sense→decide chain ─────────────────────────────────────────

def test_a_fresh_store_produces_no_signals(store):
    """THE anti-thrash rule. On a fresh deploy every block is `not_reached`, and
    converting that into "restart the loop" would restart six healthy loops on
    every single deploy."""
    assert org.signals_from_verdicts(store) == []


def test_a_stale_block_becomes_a_heartbeat_signal(store):
    store.history.d["organism_hb_data_store"] = "2020-01-01T00:00:00+00:00"
    store.history.d["organism_hb_data_store_verdict"] = org.OK
    sigs = org.signals_from_verdicts(store)
    assert [s["signal"] for s in sigs] == ["heartbeat_stale"]
    assert sigs[0]["block"] == "data_store"
    assert sigs[0]["evidence"]["verdict"] == org.FAILED


def test_a_healthy_block_produces_no_signal(store):
    org.beat(store, "data_store", org.OK)
    assert org.signals_from_verdicts(store) == []


def test_not_reached_is_never_converted_into_an_action(store):
    """Stated separately because it is the rule most likely to be "fixed" by
    somebody who thinks a silent block should be restarted."""
    for b in org.BLOCKS:
        assert org.last_verdict(store, b)["verdict"] == org.NOT_REACHED
    assert org.signals_from_verdicts(store) == []


def test_a_decision_reaches_the_journal(store):
    d = R.decide("heartbeat_stale", block="data_store", detail="stale 900s")
    assert R.journal_decision(store, d) is True
    from services import organism_journal as oj
    rows = oj.entries(store)
    assert len(rows) == 1
    assert rows[0]["kind"] == "heartbeat_stale"
    assert rows[0]["severity"] == oj.WARN, (
        "a fault that would have been repaired is not routine information")


def test_an_escalation_is_journalled_as_an_error(store):
    from services import organism_journal as oj
    d = R.decide("deploy_failed", block="delivery")
    R.journal_decision(store, d)
    assert oj.entries(store)[0]["severity"] == oj.ERROR


def test_an_unmatched_signal_is_journalled_as_observe(store):
    from services import organism_journal as oj
    d = R.decide("something_new")
    R.journal_decision(store, d)
    assert oj.entries(store)[0]["severity"] == oj.OBSERVE


def test_journalling_never_raises(store):
    class Boom:
        class history:
            @staticmethod
            def get_durable_meta(*a, **k):
                raise RuntimeError("no store")

            @staticmethod
            def set_durable_meta(*a, **k):
                raise RuntimeError("no store")

    assert R.journal_decision(Boom(), R.decide("heartbeat_stale")) is False


# ── the digest: the data step 5 needs ────────────────────────────────────────

def test_the_digest_counts_what_fired_and_what_never_did(store):
    """The answer to "has this rule ever fired". A rule that has never fired is
    either a rare fault or a signal that cannot fire, and only counting tells
    them apart."""
    for _ in range(3):
        R.journal_decision(store, R.decide("heartbeat_stale", block="data_store"))
    d = R.digest(store, hours=24)
    assert d["readable"] is True
    assert d["by_signal"] == {"heartbeat_stale": 3}
    assert d["by_class"]["self_heal"] == 3
    assert d["by_block"]["data_store"] == 3
    assert "rpc_endpoint_refused" in d["never_fired"]
    assert "heartbeat_stale" not in d["never_fired"]


def test_the_digest_ignores_telemetry_that_is_not_a_decision(store):
    """Heartbeats and boot notes share the journal with decisions. Counting them
    as rule activity would inflate every frequency."""
    from services import organism_journal as oj
    oj.append(store, "delivery", "boot", detail="started")
    oj.append(store, "data_store", "some_other_event")
    d = R.digest(store, hours=24)
    assert d["total"] == 0
    assert d["by_signal"] == {}


def test_the_digest_excludes_entries_outside_the_window(store):
    """An old decision must not be counted as recent activity.

    `hours` is floored at 1 (a 0-hour window would exclude everything and make
    the digest useless), so the entry is backdated instead of the window
    shrunk — which is also the more honest test of the cutoff.
    """
    d = R.decide("heartbeat_stale", block="data_store")
    d.at = "2020-01-01T00:00:00+00:00"
    R.journal_decision(store, d)
    assert R.digest(store, hours=24)["total"] == 0, (
        "a decision from 2020 was counted in the last 24 hours")


def test_the_digest_survives_an_unreadable_journal(store):
    class Boom:
        class history:
            @staticmethod
            def get_durable_meta(*a, **k):
                raise RuntimeError("gone")

    d = R.digest(Boom(), hours=24)
    assert d["total"] == 0
    assert "readable" in d


def test_the_board_can_read_the_whole_policy():
    """A policy nobody can read is a policy nobody can review."""
    rows = R.table()
    assert len(rows) == len(R.RULES)
    for row in rows:
        assert row["signal"] and row["class"] and row["why"]
