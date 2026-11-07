"""Chaos drills, as tests — because a drill nobody runs proves nothing.

THE RULE THIS FILE ENFORCES. A self-healing system that has never been tested
against a real fault is a claim, not a mechanism. These tests deliberately break
one thing at a time and require the organism to notice, classify, and — where a
repair exists — to heal it AND have the signal disappear.

The distinction that keeps this honest: a drill counts only when the fault was
SENSED and answered correctly. `would_heal` means the observe-only build got as
far as deciding; it is reported separately and is not a pass for the healing
path. Without that split it would be easy to write a chaos suite that never
verifies recovery and passes forever.

Everything runs against an in-memory store and threads the drills start
themselves. No network, no database, no deploy.
"""

from services import organism as org
from services import organism_chaos as C
from services import organism_executors as ex
from services import organism_rules as rules


def test_every_drill_reaches_a_definite_outcome():
    """No drill may end in an ambiguous state — an unmeasured drill is not a
    passing drill."""
    out = C.run_all()
    for d in out["drills"]:
        assert d.get("outcome"), "drill %r produced no outcome" % d["drill"]
        assert not str(d["outcome"]).startswith("WRONG"), (
            "drill %r ended %r" % (d["drill"], d["outcome"]))


def test_no_drill_fails():
    out = C.run_all()
    assert out["failed"] == 0, "failing drills: %r" % [
        d for d in out["drills"] if d.get("outcome") not in
        ("HEALED", "CORRECTLY NOT ACTED ON (not_reached is not a fault)")]


def test_every_fault_is_sensed():
    """If the sense layer misses it, nothing downstream can help."""
    out = C.run_all()
    for d in out["drills"]:
        assert d["steps"].get("sensed") is True, (
            "drill %r was never sensed" % d["drill"])


def test_the_stale_heartbeat_drill_actually_heals():
    """THE end-to-end proof: break it, sense it, decide it, repair it, VERIFY
    the signal is gone."""
    store = C._Store()
    C._break_heartbeat(store)
    assert org.last_verdict(store, "data_store")["verdict"] == org.FAILED

    sigs = org.signals_from_verdicts(store)
    assert [s["signal"] for s in sigs] == ["heartbeat_stale"]

    decision = rules.decide(sigs[0]["signal"], block=sigs[0]["block"])
    assert decision.action == rules.RESTART_LOOP

    rules.reset_ledger()
    kwargs = C._heal_heartbeat(store)
    result = ex.execute(decision, store, kwargs=kwargs,
                        still_present=lambda: org.last_verdict(
                            store, "data_store")["verdict"] != org.OK,
                        allow_actions=True)
    assert result.ok is True
    assert result.verified is True, (
        "the repair ran but the signal survived, and that was not noticed")
    assert org.last_verdict(store, "data_store")["verdict"] == org.OK
    rules.reset_ledger()


def test_a_repair_that_does_not_work_is_caught_by_the_drill():
    """The negative control. If a repair leaves the symptom in place, the drill
    must say so rather than report a heal."""
    store = C._Store()
    C._break_heartbeat(store)
    decision = rules.decide("heartbeat_stale", block="data_store")
    rules.reset_ledger()

    # A "repair" that does nothing at all.
    result = ex.execute(decision, store, kwargs={"thread": None,
                                                 "starter": lambda: True},
                        still_present=lambda: True,
                        allow_actions=True)
    rules.reset_ledger()
    assert result.ok is True, "the executor itself ran"
    assert result.verified is False, (
        "a repair that changed nothing was reported as verified")


def test_not_reached_is_drilled_as_a_non_action():
    """The anti-thrash rule, verified by a drill rather than asserted in prose.

    On a fresh deploy every block is `not_reached`. If that produced an action,
    the organism would restart six healthy loops on every single deploy.
    """
    store = C._Store()
    C._break_missing_block(store)
    for b in org.BLOCKS:
        assert org.last_verdict(store, b)["verdict"] == org.NOT_REACHED
    assert org.signals_from_verdicts(store) == [], (
        "a never-reported block produced an action")


def test_an_unreadable_store_is_sensed_and_not_acted_on():
    """A store that cannot be read is reported as `not_reached` — we could not
    look — and never as `ok`, and it raises no action because there is nothing
    to act ON: the store is the thing that is broken."""
    store = C._Store()
    C._break_unreadable_store(store)
    for b in org.BLOCKS:
        assert org.last_verdict(store, b)["verdict"] == org.NOT_REACHED
    assert org.signals_from_verdicts(store) == []


def test_every_drill_names_a_real_difference_from_a_healthy_system():
    """A drill that would also "break" a healthy system proves nothing. Each
    one must leave at least one block in a state a healthy system is never in."""
    for drill in C.DRILLS:
        store = C._Store()
        drill.break_it(store)
        verdicts = {org.last_verdict(store, b)["verdict"] for b in org.BLOCKS}
        assert verdicts & set(org.UNHEALTHY), (
            "drill %r left every block looking healthy" % drill.name)


def test_the_drills_do_not_touch_a_real_store():
    """They must be safe to run at any time, including in production CI."""
    import inspect
    src = inspect.getsource(C)
    for forbidden in ("requests.", "urlopen", "smtplib", "psycopg",
                      "subprocess", "sqlite3"):
        assert forbidden not in src, (
            "the chaos module reaches for %r; drills must stay in memory"
            % forbidden)


def test_the_chaos_report_separates_healed_from_decided():
    """The distinction that keeps the suite honest: deciding is not healing."""
    out = C.run_all()
    assert "healed" in out and "observe_only" in out
    assert out["passed"] == out["healed"] + out["withheld_correctly"]
    assert "verified" in out["note"] or "answered" in out["note"]
