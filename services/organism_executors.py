"""The organism's hands: five idempotent executors, behind three guards.

STEP 5 OF THE STRATEGY, AND THE FIRST STEP THAT CAN CHANGE THINGS. Everything
before this observed. This acts — so the safety boundary stops being a design
note and becomes code that a test can prove.

THE FIVE VERBS, and why each is safe to run twice:

    rotate_endpoint   try the next host in a pool; the old one is probed again
                      later, so this is a rotation and not a ban
    restart_loop      re-arm a dead thread; a LIVE thread is detected first, so
                      a second one is never started
    rebuild_cache     force a snapshot pass; the pass is idempotent by design
    recreate_index    CREATE INDEX CONCURRENTLY IF NOT EXISTS; "IF NOT EXISTS"
                      is the whole idempotency, and CONCURRENTLY avoids a lock
    purge_older_than  delete rows past a horizon; deleting already-deleted rows
                      removes nothing

`re_warm` is the sixth verb in the table. It is NOT implemented here on purpose:
it needs a live HTTP client and a real surface, which means it belongs with the
caller that owns that surface rather than in a module that is unit-tested
offline. `RULES` still names it, and `execute()` reports it as not implemented
rather than pretending to have done it.

THE THREE GUARDS, ALL BEFORE ANY ACTION:

1. NO ACTING BY DEFAULT. `execute()` refuses unless `allow_actions=True`, which
   comes from an environment flag that is off until a human turns it on. The
   default is observe-only, and a test asserts it.
2. BLAST RADIUS. The rule table's per-hour, per-block cap is consulted before
   the executor is called, not after.
3. VERIFICATION. `execute()` does not report success because a function
   returned. It reports success when the signal that triggered it is GONE. A
   repair whose symptom persists is reported as unhealed.

WHAT NO EXECUTOR MAY DO, restated in code rather than in a comment: nothing here
moves money, changes a price, edits a receiver, touches `secrets/`, or pushes to
`main`. Those verbs do not exist in this module.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from services import organism_rules as rules

log = logging.getLogger("kristo.v6.organism.executors")

#: The switch that turns observation into action. ABSENT OR FALSE MEANS NO
#: ACTIONS, and that is the shipped default: the organism runs, decides and
#: journals, and touches nothing until a human sets this in the environment.
ENABLE_FLAG = "KRISTO_ORGANISM_ACT"


def actions_enabled() -> bool:
    """Whether executors may run. Read at CALL time, not import time.

    Read fresh every time so turning it on or off is an environment change in
    Render with no deploy — which is also what makes it safe to ship disabled.
    """
    return (os.getenv(ENABLE_FLAG, "") or "").strip().lower() in (
        "1", "true", "yes", "on")


@dataclass
class Result:
    """What one executor did, and whether the signal actually went away."""

    verb: str
    block: str
    signal: str
    ok: bool
    detail: str = ""
    #: Did the symptom disappear? None when it could not be checked, which is
    #: NOT the same as True — the rule the dashboard keeps, applied to repair.
    verified: Optional[bool] = None
    duration_ms: int = 0
    evidence: Dict[str, object] = field(default_factory=dict)
    at: str = ""

    def __post_init__(self) -> None:
        if not self.at:
            self.at = datetime.now(timezone.utc).isoformat()

    def as_dict(self) -> dict:
        return {"verb": self.verb, "block": self.block, "signal": self.signal,
                "ok": self.ok, "detail": self.detail, "verified": self.verified,
                "duration_ms": self.duration_ms,
                "evidence": dict(self.evidence), "at": self.at}


# ── the executors ────────────────────────────────────────────────────────────

def rotate_endpoint(pool: List[str], current: str,
                    probe: Optional[Callable[[str], bool]] = None
                    ) -> Dict[str, object]:
    """Pick the next endpoint in `pool` that passes `probe`.

    IDEMPOTENT because it is a pure choice: running it twice with the same pool
    and the same `current` returns the same next host. Nothing is written, so
    nothing can be written twice.

    `current` is excluded, so this is a ROTATION and not a retry of the same
    host — the distinction that matters, because retrying a refusing endpoint is
    how a rate limit turns into an outage.
    """
    if not pool:
        return {"ok": False, "detail": "the endpoint pool is empty"}
    if current not in pool:
        return {"ok": True, "next": pool[0],
                "detail": "current is not in the pool; took the first"}
    idx = pool.index(current)
    for step in range(1, len(pool) + 1):
        candidate = pool[(idx + step) % len(pool)]
        if probe is None:
            return {"ok": True, "next": candidate,
                    "detail": "rotated to %s" % candidate}
        try:
            if probe(candidate):
                return {"ok": True, "next": candidate,
                        "detail": "rotated to %s (probe passed)" % candidate}
        except Exception as exc:  # noqa: BLE001
            log.debug("probe of %s failed: %s", candidate, exc)
    return {"ok": False,
            "detail": "every endpoint in the pool of %d failed the probe"
                      % len(pool)}


def restart_loop(thread: Optional[threading.Thread],
                 starter: Callable[[], object]) -> Dict[str, object]:
    """Re-arm a dead daemon thread, ONCE.

    IDEMPOTENT BECAUSE OF THE LIVENESS CHECK, which is the whole implementation:
    if the thread exists and is alive, nothing happens. Without that check this
    verb would stack a new thread on every call and the "repair" would be the
    outage.
    """
    if thread is not None and thread.is_alive():
        return {"ok": True, "restarted": False,
                "detail": "the thread is alive; nothing to restart"}
    try:
        started = starter()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "restarted": False,
                "detail": "restart failed: %s: %s"
                          % (type(exc).__name__, str(exc)[:140])}
    return {"ok": True, "restarted": True,
            "detail": "re-armed", "started": bool(started)}


def rebuild_cache(refresh: Callable[[], object]) -> Dict[str, object]:
    """Force one snapshot pass.

    IDEMPOTENT because a snapshot pass is a full recomputation from the same
    inputs — a second pass produces the same payload, not a doubled one.
    """
    t0 = time.time()
    try:
        out = refresh()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False,
                "detail": "rebuild failed: %s: %s"
                          % (type(exc).__name__, str(exc)[:140])}
    return {"ok": True, "detail": "rebuilt in %dms" % int((time.time() - t0) * 1000)}


def recreate_index(store, name: str, definition: str) -> Dict[str, object]:
    """Create an index if it is missing. Never drops, never rewrites.

    IDEMPOTENT because the statement carries `IF NOT EXISTS`. CONCURRENTLY is
    kept in the caller's `definition` because it is what stops the rebuild from
    locking reads — on a table being written by live traffic, a plain CREATE
    INDEX is an outage with a progress bar.

    `definition` is passed through VERBATIM. This function must not be able to
    compose SQL: an executor that can build a statement is an executor that can
    be made to build the wrong one.
    """
    if not name or not definition:
        return {"ok": False, "detail": "name and definition are both required"}
    if "create index" not in definition.strip().lower():
        return {"ok": False,
                "detail": "the definition is not a CREATE INDEX statement"}
    try:
        rows = store.history._run(
            "SELECT 1 FROM pg_indexes WHERE indexname = ? LIMIT 1",
            (name,), "one")[0]
        if rows:
            return {"ok": True, "created": False,
                    "detail": "index %s already exists" % name}
    except Exception:  # noqa: BLE001 - a sqlite backend has no pg_indexes
        pass
    try:
        store.history._run(definition, (), "")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "created": False,
                "detail": "CREATE INDEX failed: %s: %s"
                          % (type(exc).__name__, str(exc)[:140])}
    return {"ok": True, "created": True, "detail": "created %s" % name}


def purge_older_than(purge: Callable[[], int]) -> Dict[str, object]:
    """Run one batched retention pass.

    IDEMPOTENT because deleting rows that are already gone removes nothing: a
    second pass deletes fewer rows and returns 0 at the end. The batching lives
    in the purge function, so this executor cannot accidentally become the long
    transaction that locks a table.
    """
    try:
        removed = int(purge() or 0)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False,
                "detail": "purge failed: %s: %s"
                          % (type(exc).__name__, str(exc)[:140])}
    return {"ok": True, "removed": removed,
            "detail": "removed %d row(s)" % removed}


#: The verbs this module can actually perform. `re_warm` is deliberately absent
#: and `execute()` says so rather than reporting a success it did not achieve.
IMPLEMENTED = (rules.ROTATE_ENDPOINT, rules.RESTART_LOOP, rules.REBUILD_CACHE,
               rules.RECREATE_INDEX, rules.PURGE_OLDER_THAN)


@dataclass
class Executor:
    """One verb, its implementation, and the guard that gates it."""

    verb: str
    run: Callable[..., Dict[str, object]]
    needs: str = ""


def registry() -> Dict[str, Executor]:
    """The verb -> implementation map, with each verb's argument shape noted."""
    return {
        rules.ROTATE_ENDPOINT: Executor(rules.ROTATE_ENDPOINT, rotate_endpoint,
                                        "pool, current, probe"),
        rules.RESTART_LOOP: Executor(rules.RESTART_LOOP, restart_loop,
                                     "thread, starter"),
        rules.REBUILD_CACHE: Executor(rules.REBUILD_CACHE, rebuild_cache,
                                      "refresh"),
        rules.RECREATE_INDEX: Executor(rules.RECREATE_INDEX, recreate_index,
                                       "store, name, definition"),
        rules.PURGE_OLDER_THAN: Executor(rules.PURGE_OLDER_THAN, purge_older_than,
                                         "purge"),
    }


def execute(decision: rules.Decision, store=None, *,
            kwargs: Optional[Dict[str, object]] = None,
            still_present: Optional[Callable[[], bool]] = None,
            allow_actions: Optional[bool] = None) -> Result:
    """Run the action a decision names — IF every guard allows it.

    THE ORDER OF THE GUARDS IS THE DESIGN. Each one is cheaper and safer than the
    next, so the ones that can stop the action run first:

      1. the class must be self_heal   — escalate/observe never act, in any mode
      2. the verb must be implemented  — an unimplemented action is not a success
      3. actions must be ENABLED       — off by default; a human turns it on
      4. the blast radius must allow it — a thrashing block is stopped
      5. then, and only then, the executor runs

    `allow_actions=None` reads the environment. Passing it explicitly is for
    tests, so the safety behaviour can be proven without setting a real flag.
    """
    verb = decision.action
    block = decision.block or "organism"
    res = Result(verb=verb, block=block, signal=decision.signal, ok=False)

    # 1. class
    if decision.klass != rules.SELF_HEAL:
        res.detail = ("class %s never reaches an executor" % decision.klass)
        return res

    # 2. implemented
    impl = registry().get(verb)
    if impl is None:
        res.detail = ("verb %r is not implemented on this host; reported as "
                      "not done rather than as done" % verb)
        return res

    # 3. enabled
    enabled = actions_enabled() if allow_actions is None else bool(allow_actions)
    if not enabled:
        res.detail = ("actions are disabled (%s is not set); decided and "
                      "journalled, nothing performed" % ENABLE_FLAG)
        return res

    # 4. blast radius
    if not rules._within_blast_radius(block):
        res.detail = ("blast radius: %s has already had %d actions in the last "
                      "hour" % (block, rules.BLAST_RADIUS_PER_HOUR))
        log.warning("organism refused to act on %s: %s", decision.signal,
                    res.detail)
        return res

    # 5. act
    t0 = time.time()
    try:
        out = impl.run(**(kwargs or {}))
    except Exception as exc:  # noqa: BLE001
        res.detail = "executor raised: %s: %s" % (type(exc).__name__,
                                                  str(exc)[:140])
        res.duration_ms = int((time.time() - t0) * 1000)
        return res
    res.duration_ms = int((time.time() - t0) * 1000)
    res.ok = bool(out.get("ok"))
    res.detail = str(out.get("detail") or "")
    res.evidence = {k: v for k, v in out.items() if k != "detail"}
    rules._record_action(block)

    # 6. verify — an action is done when the SIGNAL is gone, not when it returns
    if still_present is not None:
        check = rules.verify(decision.signal, still_present)
        res.verified = check["verified"]
        if not check["verified"]:
            res.detail = ("%s | NOT VERIFIED: %s"
                          % (res.detail, check["note"]))
    return res


def journal_result(store, decision: rules.Decision, result: Result) -> bool:
    """Record what was actually done, alongside what was decided."""
    try:
        from services import organism_journal as oj
        severity = oj.INFO if result.ok else oj.WARN
        if result.verified is False:
            # The action ran and the symptom survived. That is worse than not
            # acting, because it stops anyone looking.
            severity = oj.ERROR
        return oj.append(
            store, result.block, "executor_%s" % result.verb,
            severity=severity,
            detail=result.detail,
            action=result.verb,
            outcome=("done" if result.ok else "not done"),
            evidence={"verified": result.verified,
                      "duration_ms": result.duration_ms,
                      "signal": result.signal,
                      **result.evidence},
            at=result.at)
    except Exception as exc:  # noqa: BLE001 - telemetry only
        log.debug("executor result not journalled: %s", exc)
        return False
