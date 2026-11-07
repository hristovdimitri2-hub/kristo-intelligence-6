"""The organism's brain: a deterministic rule table, in OBSERVE-ONLY mode first.

WHY A TABLE AND NOT A MODEL. A language model deciding whether to touch a payment
rail is a liability — it cannot be audited, it cannot be tested, and it can
hallucinate a reason to act. A rule table can be read in full, unit-tested, and
reasoned about by a human who is not a programmer. Every defect this project has
had was diagnosable from a table; none of them needed judgement.

WHY OBSERVE-ONLY FIRST, and this is the important part. A rule you have never
seen fire is a rule you cannot trust. Before the organism is allowed to act on
`rpc_endpoint_refused`, it must first record how often that signal actually
occurs, whether it clusters, and whether the action it would have taken was the
right one. Acting immediately would mean guessing the frequencies; the guess
would either be too timid to matter or too eager to be safe.

So this module DECIDES and RECORDS, and does not act. `decide()` returns what it
WOULD do. The executors arrive in step 5 and will call the same table.

THE THREE GUARDS, implemented here rather than promised:

1. BLAST RADIUS — at most N actions per hour per block. A system in a loop must
   not be allowed to keep looping. Enforced by `_within_blast_radius()`.
2. VERIFICATION — an action is not done when issued, it is done when the signal
   that triggered it is GONE. `verify()` answers that, and a rule whose signal
   persists is reported as unhealed rather than as a success.
3. JOURNAL — every decision is journalled, including the ones that match no rule.

WHAT IS PERMANENTLY ESCALATED, never automated: anything that moves money,
changes a price, edits a receiver, touches `secrets/`, or pushes to `main`.
Those are marked `escalate` in the table and no future step may promote them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger("kristo.v6.organism.rules")

# ── the classes ──────────────────────────────────────────────────────────────
# Three, and no more. A fourth would be invented by whoever needed it, and the
# difference between `self_heal` and `escalate` is the entire safety boundary.
SELF_HEAL = "self_heal"      # reversible, idempotent, verifiable — an executor may act
ESCALATE = "escalate"        # a human must decide; the organism only reports
OBSERVE = "observe"          # not understood well enough to classify; record it

CLASSES = (SELF_HEAL, ESCALATE, OBSERVE)

#: The action vocabulary. Deliberately small, and every verb is safe to run twice.
#:
#: NOTHING IN THIS LIST moves money, changes a price, edits a receiver, touches
#: `secrets/`, or pushes to `main`. That is the point of the list being small: a
#: verb that is not here cannot be reached by a rule.
ROTATE_ENDPOINT = "rotate_endpoint"
RESTART_LOOP = "restart_loop"
REBUILD_CACHE = "rebuild_cache"
RECREATE_INDEX = "recreate_index"
PURGE_OLDER_THAN = "purge_older_than"
RE_WARM = "re_warm"

EXECUTORS = (ROTATE_ENDPOINT, RESTART_LOOP, REBUILD_CACHE, RECREATE_INDEX,
             PURGE_OLDER_THAN, RE_WARM)

#: Verbs that a rule may NOT use, listed so a test can assert they are absent.
#: They are not "not yet implemented" — they are forbidden permanently.
FORBIDDEN_EFFECTS = ("move_money", "change_price", "edit_receiver",
                     "touch_secrets", "push_to_main")

#: At most this many auto-actions per hour PER BLOCK. Exceeding it means the
#: organism has stopped healing and started thrashing, and the correct response
#: to thrashing is to stop and escalate.
BLAST_RADIUS_PER_HOUR = 6


@dataclass(frozen=True)
class Rule:
    """One row of the table: a signal, its class, and what would be done."""

    signal: str
    klass: str
    action: str = ""
    #: Human-readable reason, shown in the journal and on the board. A rule with
    #: no stated reason is a rule nobody can review.
    why: str = ""
    #: Which block this signal belongs to, when it is block-specific.
    block: str = ""

    def __post_init__(self) -> None:
        if self.klass not in CLASSES:
            raise ValueError("unknown class %r for signal %r"
                             % (self.klass, self.signal))
        if self.klass == SELF_HEAL:
            if self.action not in EXECUTORS:
                raise ValueError(
                    "rule %r is self_heal but names action %r, which is not in "
                    "the executor vocabulary %s"
                    % (self.signal, self.action, ", ".join(EXECUTORS)))
            if self.action in FORBIDDEN_EFFECTS:
                raise ValueError(
                    "rule %r names a forbidden effect %r"
                    % (self.signal, self.action))


# ── THE TABLE ────────────────────────────────────────────────────────────────
# Read this as the organism's whole policy. If it is not here, the organism does
# not act on it.
RULES: Tuple[Rule, ...] = (
    # ── self-heal: reversible, idempotent, and the signal disappears when fixed
    Rule("rpc_endpoint_refused", SELF_HEAL, ROTATE_ENDPOINT,
         "an RPC endpoint refused us; try the next one in the pool. The old "
         "endpoint is probed again later, so this is a rotation, not a ban."),
    Rule("heartbeat_stale", SELF_HEAL, RESTART_LOOP,
         "a block stopped reporting; re-arm its thread. Safe to run twice "
         "because a live thread is detected before a second one is started."),
    Rule("cache_violently_stale", SELF_HEAL, REBUILD_CACHE,
         "the served payload is far past its freshness window; force a snapshot "
         "pass rather than waiting for the next scheduled one."),
    Rule("index_missing_or_invalid", SELF_HEAL, RECREATE_INDEX,
         "a query that should use an index is scanning; CREATE INDEX "
         "CONCURRENTLY IF NOT EXISTS is idempotent and does not lock reads."),
    Rule("retention_backlog_over_horizon", SELF_HEAL, PURGE_OLDER_THAN,
         "a table has rows past its retention horizon; purge in batches. "
         "Bounded per call so it can never become the long transaction."),
    Rule("surface_returns_5xx", SELF_HEAL, RE_WARM,
         "a public surface answered 5xx; hit it again and assert 2xx before "
         "believing it is healthy."),

    # ── escalate: a human decides. These are permanent, not deferred.
    Rule("deploy_failed", ESCALATE,
         why="a failed deploy can leave the service on an old build while the "
             "repo says otherwise. The organism must not retry a deploy: the "
             "failure is usually a configuration the owner controls."),
    Rule("env_missing_or_drifted", ESCALATE,
         why="an environment variable changed or vanished. Editing the "
             "environment is an action with an external effect and is the "
             "owner's alone."),
    Rule("payment_settles_but_not_recorded", ESCALATE,
         why="money moved and our records disagree. Any automatic repair here "
             "could hide a real accounting defect, and this is the one class of "
             "bug worth a human reading every instance."),
    Rule("conversion_below_floor", ESCALATE,
         why="traffic arriving and nobody paying is a BUSINESS fact, not a "
             "technical fault. No amount of self-healing changes an offer."),
    Rule("public_claim_contradicted", ESCALATE,
         why="something we publish differs from what was measured. Only the "
             "owner may change what the platform claims about itself."),

    # ── observe: not understood well enough to classify, so it is recorded
    Rule("anything_unrecognised", OBSERVE,
         why="no rule matched. Recorded so the real frequency can be measured "
             "before a rule is written for it."),
)


_BY_SIGNAL: Dict[str, Rule] = {r.signal: r for r in RULES}


def table() -> List[dict]:
    """The whole policy, for the board and for a human to read."""
    return [{"signal": r.signal, "class": r.klass, "action": r.action,
             "block": r.block, "why": r.why} for r in RULES]


def lookup(signal: str) -> Rule:
    """The rule for a signal, or the OBSERVE catch-all.

    Never raises and never returns None: an unmatched signal is a real outcome
    and must be RECORDED, not dropped. Dropping it is how a system ends up
    silently ignoring the one thing it had not seen before.
    """
    key = str(signal or "").strip().lower().replace(" ", "_")
    return _BY_SIGNAL.get(key) or _BY_SIGNAL["anything_unrecognised"]


@dataclass
class Decision:
    """What the organism decided, and why. Recorded whether or not it acts."""

    signal: str
    klass: str
    action: str
    why: str
    block: str = ""
    detail: str = ""
    #: False in observe-only mode. The executors arrive in step 5.
    acted: bool = False
    blocked_by: str = ""
    evidence: Dict[str, object] = field(default_factory=dict)
    at: str = ""

    def __post_init__(self) -> None:
        if not self.at:
            self.at = datetime.now(timezone.utc).isoformat()

    def as_dict(self) -> dict:
        return {"signal": self.signal, "class": self.klass,
                "action": self.action, "why": self.why, "block": self.block,
                "detail": self.detail, "acted": self.acted,
                "blocked_by": self.blocked_by, "evidence": dict(self.evidence),
                "at": self.at}


# ── guard 1: blast radius ────────────────────────────────────────────────────
# A module-level ledger of what WOULD have been done, per block, per hour. It is
# in memory because it is a rate limit, not a record — the journal is the record.
_ACTION_LEDGER: Dict[str, List[float]] = {}


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _within_blast_radius(block: str, limit: int = BLAST_RADIUS_PER_HOUR,
                         window_seconds: int = 3600) -> bool:
    """Has this block already had `limit` actions in the last hour?

    Exceeding it means the organism is thrashing, and the right response to
    thrashing is to stop and escalate rather than to heal harder.
    """
    cutoff = _now_ts() - window_seconds
    recent = [t for t in _ACTION_LEDGER.get(block, []) if t >= cutoff]
    _ACTION_LEDGER[block] = recent
    return len(recent) < limit


def _record_action(block: str) -> None:
    _ACTION_LEDGER.setdefault(block, []).append(_now_ts())


def actions_last_hour() -> Dict[str, int]:
    """How many actions each block has taken in the last hour."""
    cutoff = _now_ts() - 3600
    return {b: len([t for t in ts if t >= cutoff])
            for b, ts in _ACTION_LEDGER.items()}


def reset_ledger() -> None:
    """Clear the rate-limit ledger. For tests, and for a deliberate reset."""
    _ACTION_LEDGER.clear()


# ── decide ───────────────────────────────────────────────────────────────────

def decide(signal: str, *, block: str = "", detail: str = "",
           evidence: Optional[dict] = None,
           observe_only: bool = True) -> Decision:
    """Classify a signal and say what would be done about it.

    `observe_only=True` (the default, and the only mode implemented) returns the
    decision WITHOUT acting. The blast-radius guard still runs, so the journal
    records both what would have happened and whether it would have been allowed
    — which is exactly the frequency data step 5 needs before it may act.
    """
    rule = lookup(signal)
    d = Decision(signal=rule.signal, klass=rule.klass, action=rule.action,
                 why=rule.why, block=block or rule.block, detail=detail,
                 evidence=dict(evidence or {}))

    if rule.klass != SELF_HEAL:
        # escalate and observe never reach an executor, in any mode.
        d.blocked_by = ("escalated to the owner" if rule.klass == ESCALATE
                        else "no rule matched; recorded for measurement")
        return d

    if observe_only:
        d.blocked_by = "observe-only mode: decided but did not act"
        # Still counted, so the blast-radius guard is TESTED before it matters.
        if _within_blast_radius(d.block):
            _record_action(d.block)
        else:
            d.blocked_by = ("observe-only mode; and this block has already "
                            "reached its hourly action limit")
        return d

    if not _within_blast_radius(d.block):
        d.blocked_by = ("blast radius: %d actions already taken by %s in the "
                        "last hour" % (BLAST_RADIUS_PER_HOUR, d.block or "?"))
        log.warning("organism would act on %s but %s is out of budget",
                    d.signal, d.block)
        return d

    # Step 5 will run the executor here. Until then this line is unreachable,
    # and that is deliberate: an unimplemented action must not silently succeed.
    _record_action(d.block)
    d.acted = True
    d.blocked_by = "no executor wired yet (step 5) — recorded, not performed"
    d.acted = False
    return d


# ── guard 2: verification ────────────────────────────────────────────────────

def verify(signal: str, still_present: Callable[[], bool]) -> Dict[str, object]:
    """An action is done when the triggering signal is GONE, not when issued.

    This is the same rule the dashboard already follows, applied to repair: a
    repair that reports success while the symptom persists is worse than no
    repair, because it stops anyone looking.

    `still_present` is a callable rather than a value so the check happens at the
    moment of asking, not at the moment of planning.
    """
    try:
        present = bool(still_present())
    except Exception as exc:  # noqa: BLE001
        return {"signal": signal, "verified": False, "present": None,
                "note": "the verification itself could not run: %s: %s"
                        % (type(exc).__name__, str(exc)[:120])}
    return {
        "signal": signal,
        "verified": not present,
        "present": present,
        "note": ("the signal is gone; the action worked" if not present
                 else "the signal is STILL present; the action did not fix it"),
    }


# ── guard 3: the journal (thin wrapper, so callers cannot forget it) ─────────

def journal_decision(store, decision: Decision) -> bool:
    """Write one decision to the organism journal. Never raises.

    Severity maps from the class: a self-heal that WOULD have run is `warn`
    (something is wrong and would have been fixed), an escalation is `error`
    (a human is needed), an unmatched signal is `observe` (information only).
    """
    try:
        from services import organism_journal as oj
        if decision.klass == SELF_HEAL:
            severity = oj.WARN
        elif decision.klass == ESCALATE:
            severity = oj.ERROR
        else:
            severity = oj.OBSERVE
        return oj.append(
            store, decision.block or "organism", decision.signal,
            severity=severity,
            detail=decision.detail or decision.why,
            action=decision.action,
            outcome=decision.blocked_by,
            evidence=decision.evidence,
            # The decision's OWN timestamp, not the moment of writing. The two
            # differ whenever a decision is journalled after the fact — a
            # backfill, a retry, or a test — and a journal whose ordering
            # disagrees with its own timestamps is a journal nobody can trust.
            at=decision.at)
    except Exception as exc:  # noqa: BLE001 - telemetry only
        log.debug("rule decision not journalled (%s): %s",
                  decision.signal, exc)
        return False


def digest(store, hours: int = 24) -> Dict[str, object]:
    """What the table SAW in the window — the data step 5 needs to act safely.

    This is the answer to "has this rule ever fired, and how often". A rule that
    has never fired in a week is either a rule for a rare fault (fine) or a rule
    that can never fire (a defect in the signal), and the two are only
    distinguishable by counting.
    """
    try:
        from services import organism_journal as oj
        entries = oj.entries(store, limit=oj.MAX_ENTRIES)
    except Exception:  # noqa: BLE001
        return {"readable": False, "by_signal": {}, "by_class": {},
                "by_block": {}, "total": 0}

    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=max(1, int(hours)))).isoformat()
    by_signal: Dict[str, int] = {}
    by_class: Dict[str, int] = {c: 0 for c in CLASSES}
    by_block: Dict[str, int] = {}
    total = 0
    for e in entries:
        if str(e.get("at") or "") < cutoff:
            continue
        sig = str(e.get("kind") or "")
        if sig not in _BY_SIGNAL:
            continue                      # not a rule decision, just telemetry
        total += 1
        by_signal[sig] = by_signal.get(sig, 0) + 1
        by_class[_BY_SIGNAL[sig].klass] = by_class.get(
            _BY_SIGNAL[sig].klass, 0) + 1
        blk = str(e.get("block") or "")
        if blk:
            by_block[blk] = by_block.get(blk, 0) + 1

    never_fired = [r.signal for r in RULES
                   if r.signal not in by_signal
                   and r.signal != "anything_unrecognised"]
    return {
        "readable": True,
        "hours": hours,
        "total": total,
        "by_signal": by_signal,
        "by_class": by_class,
        "by_block": by_block,
        "never_fired": never_fired,
        "note": ("A rule that has never fired is either a rare fault or a "
                 "signal that cannot fire. Only counting tells them apart — "
                 "which is why this table observes before it acts."),
    }
