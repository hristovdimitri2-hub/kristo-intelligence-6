"""The executors — idempotency and the guard order, both pinned.

STEP 5 IS THE FIRST CODE THAT CAN CHANGE PRODUCTION. So the tests that matter
are not "does each verb work" — they are the ones that prove it cannot work when
it must not:

  * the SHIPPED DEFAULT is no actions at all;
  * an escalation never reaches an executor even with actions enabled;
  * an unimplemented verb is reported as NOT DONE, never as done;
  * the blast radius refuses a thrashing block;
  * a verb run twice does the same thing, which is what makes retry safe;
  * an action whose symptom survives is reported as UNVERIFIED, because that is
    worse than not acting — it stops anyone looking.

Each of those would be invisible in normal operation and catastrophic on the day
it mattered.
"""

import threading
import time

import pytest

from services import organism_executors as E
from services import organism_rules as R


@pytest.fixture(autouse=True)
def _clean_ledger():
    R.reset_ledger()
    yield
    R.reset_ledger()


def _decision(signal="cache_violently_stale", klass=R.SELF_HEAL,
              action=R.REBUILD_CACHE, block="data_store"):
    return R.Decision(signal=signal, klass=klass, action=action,
                      why="test", block=block)


# ── the shipped default is "do not touch anything" ───────────────────────────

def test_actions_are_disabled_by_default():
    """THE most important assertion in this file. The organism ships observing,
    and a human turns action on deliberately."""
    assert E.actions_enabled() is False


def test_the_enable_flag_is_read_by_name(monkeypatch):
    assert E.ENABLE_FLAG == "KRISTO_ORGANISM_ACT"
    monkeypatch.setenv(E.ENABLE_FLAG, "1")
    assert E.actions_enabled() is True
    monkeypatch.setenv(E.ENABLE_FLAG, "no")
    assert E.actions_enabled() is False


def test_a_disabled_organism_does_not_call_the_executor():
    """Not "reports failure" — the function is never entered."""
    calls = []
    res = E.execute(_decision(), kwargs={"refresh": lambda: calls.append(1)})
    assert res.ok is False
    assert calls == [], "an executor ran while actions were disabled"
    assert E.ENABLE_FLAG in res.detail


def test_the_refusal_says_why(monkeypatch):
    res = E.execute(_decision(), kwargs={"refresh": lambda: 1})
    assert "disabled" in res.detail
    assert "nothing performed" in res.detail


# ── guard 1: class ───────────────────────────────────────────────────────────

def test_an_escalation_never_reaches_an_executor():
    """Even with actions fully enabled. This is the safety boundary."""
    d = _decision(signal="deploy_failed", klass=R.ESCALATE, action="")
    res = E.execute(d, allow_actions=True)
    assert res.ok is False
    assert "never reaches an executor" in res.detail


def test_an_observed_signal_never_reaches_an_executor():
    d = _decision(signal="anything_unrecognised", klass=R.OBSERVE, action="")
    res = E.execute(d, allow_actions=True)
    assert res.ok is False
    assert "never reaches an executor" in res.detail


# ── guard 2: implemented ─────────────────────────────────────────────────────

def test_re_warm_is_reported_as_not_done_not_as_done():
    """An unimplemented action must never be journalled as a success. `re_warm`
    needs a live HTTP client, so it lives with the caller that owns it."""
    d = _decision(signal="surface_returns_5xx", action=R.RE_WARM)
    res = E.execute(d, allow_actions=True)
    assert res.ok is False
    assert "not implemented" in res.detail
    assert R.RE_WARM not in E.IMPLEMENTED


def test_the_registry_covers_exactly_the_five_implemented_verbs():
    assert set(E.registry()) == set(E.IMPLEMENTED)
    assert R.RE_WARM not in E.registry()


# ── guard 3: blast radius ────────────────────────────────────────────────────

def test_the_blast_radius_refuses_a_thrashing_block():
    for _ in range(R.BLAST_RADIUS_PER_HOUR):
        R._record_action("data_store")
    calls = []
    res = E.execute(_decision(), allow_actions=True,
                    kwargs={"refresh": lambda: calls.append(1)})
    assert res.ok is False
    assert calls == [], "an action ran past the blast radius"
    assert "blast radius" in res.detail


def test_an_action_within_budget_is_allowed():
    res = E.execute(_decision(), allow_actions=True,
                    kwargs={"refresh": lambda: 1})
    assert res.ok is True
    assert R.actions_last_hour()["data_store"] == 1


def test_an_escalation_does_not_spend_the_acting_budget():
    for _ in range(20):
        E.execute(_decision(signal="deploy_failed", klass=R.ESCALATE,
                            action=""), allow_actions=True)
    assert R.actions_last_hour().get("data_store", 0) == 0


# ── guard 4: verification happens AFTER the action ───────────────────────────

def test_a_repair_whose_symptom_survives_is_not_verified():
    """Worse than not acting, because it stops anyone looking."""
    res = E.execute(_decision(), allow_actions=True,
                    kwargs={"refresh": lambda: 1},
                    still_present=lambda: True)
    assert res.ok is True, "the action itself did run"
    assert res.verified is False, "a surviving symptom was reported as fixed"
    assert "NOT VERIFIED" in res.detail


def test_a_repair_whose_symptom_is_gone_is_verified():
    res = E.execute(_decision(), allow_actions=True,
                    kwargs={"refresh": lambda: 1},
                    still_present=lambda: False)
    assert res.verified is True


def test_no_verifier_means_unknown_not_passed():
    """`couldn't check` must never read as `fixed`."""
    res = E.execute(_decision(), allow_actions=True,
                    kwargs={"refresh": lambda: 1})
    assert res.verified is None


def test_a_verifier_that_raises_is_not_a_pass():
    def boom():
        raise RuntimeError("cannot check")

    res = E.execute(_decision(), allow_actions=True,
                    kwargs={"refresh": lambda: 1}, still_present=boom)
    assert res.verified is False


# ── idempotency of each verb ─────────────────────────────────────────────────

def test_rotate_endpoint_is_a_pure_choice():
    pool = ["a", "b", "c"]
    assert E.rotate_endpoint(pool, "a")["next"] == E.rotate_endpoint(pool, "a")["next"]


def test_rotate_endpoint_does_not_retry_the_same_host():
    """Rotation, not retry. Retrying a refusing endpoint is how a rate limit
    becomes an outage."""
    assert E.rotate_endpoint(["a", "b"], "a")["next"] == "b"


def test_rotate_endpoint_can_skip_a_host_that_fails_a_probe():
    out = E.rotate_endpoint(["a", "b", "c"], "a",
                            probe=lambda h: h == "c")
    assert out["ok"] is True
    assert out["next"] == "c"


def test_rotate_endpoint_reports_when_every_host_is_down():
    out = E.rotate_endpoint(["a", "b"], "a", probe=lambda h: False)
    assert out["ok"] is False
    assert "every endpoint" in out["detail"]


def test_rotate_endpoint_with_an_empty_pool_is_not_a_crash():
    assert E.rotate_endpoint([], "a")["ok"] is False


def test_restart_loop_never_stacks_on_a_live_thread():
    """THE idempotency that makes this verb safe: without the liveness check the
    repair would be the outage."""
    started = []
    t = threading.Thread(target=lambda: time.sleep(30), daemon=True)
    t.start()
    time.sleep(0.05)
    out = E.restart_loop(t, lambda: started.append(1))
    assert out["restarted"] is False
    assert started == [], "a live thread was restarted anyway"


def test_restart_loop_re_arms_a_dead_thread():
    started = []
    out = E.restart_loop(None, lambda: started.append(1))
    assert out["restarted"] is True
    assert len(started) == 1


def test_restart_loop_reports_a_failing_starter():
    def boom():
        raise RuntimeError("cannot start")

    out = E.restart_loop(None, boom)
    assert out["ok"] is False
    assert "restart failed" in out["detail"]


def test_purge_converges_to_zero():
    """An idempotent purge removes nothing the second time."""
    left = {"n": 5}

    def purge():
        took = min(3, left["n"])
        left["n"] -= took
        return took

    assert E.purge_older_than(purge)["removed"] == 3
    assert E.purge_older_than(purge)["removed"] == 2
    assert E.purge_older_than(purge)["removed"] == 0


def test_a_failing_purge_is_reported_not_swallowed():
    def boom():
        raise RuntimeError("table locked")

    out = E.purge_older_than(boom)
    assert out["ok"] is False
    assert "table locked" in out["detail"]


# ── recreate_index cannot compose SQL ────────────────────────────────────────

class _FakeStore:
    class history:
        calls = []

        @staticmethod
        def _run(sql, params=(), fetch=""):
            _FakeStore.history.calls.append(sql)
            return ([], 0)


def test_recreate_index_refuses_a_statement_that_is_not_a_create_index():
    """An executor that can build a statement is an executor that can be made to
    build the wrong one. The definition is passed through verbatim."""
    for bad in ("DROP TABLE users", "DELETE FROM request_log", "SELECT 1"):
        out = E.recreate_index(_FakeStore(), "idx_x", bad)
        assert out["ok"] is False, "%r was accepted" % bad
        assert "not a CREATE INDEX" in out["detail"]


def test_recreate_index_requires_a_name():
    assert E.recreate_index(_FakeStore(), "", "CREATE INDEX x ON y (z)")["ok"] is False


def test_recreate_index_runs_the_definition_verbatim():
    _FakeStore.history.calls = []
    definition = "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_x ON t (c)"
    out = E.recreate_index(_FakeStore(), "idx_x", definition)
    assert out["ok"] is True
    assert definition in _FakeStore.history.calls, (
        "the definition was rewritten rather than passed through")


# ── journalling the result ───────────────────────────────────────────────────

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


def test_a_verified_action_is_journalled_as_information():
    from services import organism_journal as oj
    store = _Store()
    d = _decision()
    res = E.execute(d, allow_actions=True, kwargs={"refresh": lambda: 1},
                    still_present=lambda: False)
    E.journal_result(store, d, res)
    row = oj.entries(store)[0]
    assert row["kind"] == "executor_rebuild_cache"
    assert row["severity"] == oj.INFO
    assert row["outcome"] == "done"


def test_an_unverified_action_is_journalled_as_an_error():
    """The severity is the point: a repair that did not work needs a human."""
    from services import organism_journal as oj
    store = _Store()
    d = _decision()
    res = E.execute(d, allow_actions=True, kwargs={"refresh": lambda: 1},
                    still_present=lambda: True)
    E.journal_result(store, d, res)
    assert oj.entries(store)[0]["severity"] == oj.ERROR


def test_a_refused_action_is_journalled_as_a_warning():
    from services import organism_journal as oj
    store = _Store()
    d = _decision()
    res = E.execute(d, allow_actions=True,
                    kwargs={"refresh": lambda: (_ for _ in ()).throw(
                        RuntimeError("boom"))})
    E.journal_result(store, d, res)
    assert oj.entries(store)[0]["severity"] == oj.WARN


def test_journalling_a_result_never_raises():
    class Boom:
        class history:
            @staticmethod
            def get_durable_meta(*a, **k):
                raise RuntimeError("gone")

            @staticmethod
            def set_durable_meta(*a, **k):
                raise RuntimeError("gone")

    d = _decision()
    res = E.execute(d, allow_actions=True, kwargs={"refresh": lambda: 1})
    assert E.journal_result(Boom(), d, res) is False


# ── the result carries what a human needs ────────────────────────────────────

def test_a_result_serialises_for_the_board():
    res = E.execute(_decision(), allow_actions=True,
                    kwargs={"refresh": lambda: 1})
    out = res.as_dict()
    for key in ("verb", "block", "signal", "ok", "detail", "verified",
                "duration_ms", "at"):
        assert key in out
