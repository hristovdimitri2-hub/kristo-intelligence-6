"""The organism's sense layer: six blocks, each with a heartbeat and a self-check.

WHY THIS EXISTS. Every defect this project has had was found by a human-run audit,
diagnosed in a human-run session, and fixed by a human-run commit. The system
watches (the sentinel sends Telegram on health, revenue and GitHub changes) but it
carries **no model of its own health**, so each session re-discovers what the last
one already knew. The owner's words: *"решаваме един проблем, излиза друг."*

This module gives the system that model. It is deliberately the smallest useful
version of it:

  * SIX BLOCKS, matching the areas that actually fail here: the payment rail, the
    chain reads, the data store, discovery surfaces, alerting, delivery.
  * ONE VOCABULARY — `ok` / `degraded` / `failed` / `not_reached`. The fourth is
    the one that matters: a check that could not run must never be rendered as a
    check that found nothing. That is the defect class this codebase has spent the
    week closing one surface at a time, and it is enforced here by construction
    rather than by remembering.
  * A HEARTBEAT per block, written to the durable store, so "when did this last
    work" survives a restart and a deploy.
  * NO ACTIONS. This module observes and records. Executors are a later step, and
    they are gated separately — see `ORGANISM.md`.

THE HONESTY RULE, stated once and enforced by `Verdict`: a self-check returns a
verdict and an optional detail. A check that raises returns `not_reached` with the
exception recorded — never `ok`, and never a silent absence. A caller reading the
board therefore cannot mistake "we did not look" for "we looked and it was fine".

Nothing here reads or writes money, prices, receivers, `secrets/`, or git.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import logging

log = logging.getLogger("kristo.v6.organism")

# ── the shared vocabulary ────────────────────────────────────────────────────
# Ordered worst-last for reporting; `NOT_REACHED` is NOT simply "unknown" — it
# means the check did not run, which is a different fact from a check that ran
# and failed, and from one that ran and found nothing.
OK = "ok"
DEGRADED = "degraded"
FAILED = "failed"
NOT_REACHED = "not_reached"

VERDICTS = (OK, DEGRADED, FAILED, NOT_REACHED)

#: Verdicts that mean the block is NOT working, for alerting and for the count.
UNHEALTHY = (DEGRADED, FAILED, NOT_REACHED)

#: The blocks. Each owns a distinct failure domain, so one dying cannot make
#: another look dead — the property the dashboard already proves for its panels.
BLOCKS = (
    "payment_rail",
    "chain_read",
    "data_store",
    "discovery",
    "alerting",
    "delivery",
)

#: How long a heartbeat may be silent before the block counts as stale, PER
#: BLOCK — and one global number is WRONG here.
#:
#: The first version used a single 300-second window for all six blocks. Measured
#: against the loops that actually write the heartbeats, that produced permanent
#: false alarms:
#:
#:   discovery   written by the sentinel's GitHub check, which runs every 6 HOURS
#:               -> read as `failed` for 98.6% of the time
#:   chain_read  written by the revenue check, every 30 MINUTES
#:               -> read as `failed` for 83.3% of the time
#:
#: A warning nobody can act on is worse than no warning: it teaches the reader to
#: ignore the panel, and then the one real failure is invisible too. That is the
#: same defect class this whole codebase keeps closing, in the sense layer rather
#: than in a panel.
#:
#: So each block declares how often it is EXPECTED to report, and the threshold is
#: derived from that with a margin: a loop must miss two whole cycles in a row
#: before it is called stale. A block that reports every 60 seconds is stale after
#: 5 minutes; a block that reports every 6 hours is stale after 12.
EXPECTED_INTERVAL_SECONDS: Dict[str, int] = {
    # the dashboard scan loop and both warmers run every 30-60s
    "data_store": 60,
    # the dashboard warmer rebuilds every ~30s
    "delivery": 60,
    # a settled or failed payment can be minutes apart, so this block also beats
    # from the keep-alive path; its interval is the loosest of the fast ones
    "payment_rail": 300,
    # the sentinel's health check, every 10 minutes
    "alerting": 600,
    # the sentinel's revenue check, every 30 minutes
    "chain_read": 1800,
    # the sentinel's GitHub check, every 6 hours
    "discovery": 21600,
}

#: How many whole intervals may be missed before a block is called stale. Two, so
#: a single skipped cycle (a slow RPC, a long scan) is not reported as a fault.
STALE_AFTER_MISSED_CYCLES = 2

#: The floor, so a block with a very short interval is not called stale between
#: two heartbeats a second apart.
MIN_STALE_SECONDS = 300

#: The threshold used when a block declares no interval. Kept as the old global
#: value so an unregistered block behaves exactly as before rather than silently
#: becoming stricter.
HEARTBEAT_STALE_SECONDS = 300


def stale_after_seconds(block: str) -> int:
    """When this block's silence stops being normal.

    Derived from the block's own expected interval rather than one global number,
    because a 5-minute window over a 6-hourly loop is a permanent false alarm.
    """
    interval = EXPECTED_INTERVAL_SECONDS.get(block)
    if not interval:
        return HEARTBEAT_STALE_SECONDS
    return max(MIN_STALE_SECONDS, int(interval) * STALE_AFTER_MISSED_CYCLES)


_HEARTBEAT_PREFIX = "organism_hb_"


@dataclass
class Verdict:
    """One block's answer to "am I well?".

    `detail` is required to be honest but is free-form. `evidence` carries the
    numbers a human would otherwise re-measure by hand — the whole point of the
    module is that the next session does not have to.
    """

    block: str
    verdict: str
    detail: str = ""
    evidence: Dict[str, object] = field(default_factory=dict)
    at: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            # A typo must not invent a fifth state that callers do not handle.
            raise ValueError(
                "unknown verdict %r for block %r; expected one of %s"
                % (self.verdict, self.block, ", ".join(VERDICTS)))
        if not self.at:
            self.at = datetime.now(timezone.utc).isoformat()

    @property
    def healthy(self) -> bool:
        return self.verdict == OK

    def as_dict(self) -> dict:
        return {
            "block": self.block,
            "verdict": self.verdict,
            "detail": self.detail,
            "evidence": dict(self.evidence),
            "at": self.at,
        }


def _not_reached(block: str, exc: BaseException) -> Verdict:
    """The verdict for a check that could not run. NEVER `ok`.

    Kept as a function so the rule is stated once: an exception in a self-check is
    a fact about the CHECK, not a measurement of the block, and the two must not
    be confused in either direction.
    """
    return Verdict(block=block, verdict=NOT_REACHED,
                   detail="self-check did not run: %s: %s"
                          % (type(exc).__name__, str(exc)[:160]))


class Registry:
    """The set of self-checks, and the thing that runs them.

    Checks are registered rather than hard-coded so a block can be added without
    touching the runner, and so tests can register a throwing check to prove the
    `not_reached` path. That path is the one most likely to be got wrong, and it
    is the one this module exists to make impossible.
    """

    def __init__(self) -> None:
        self._checks: Dict[str, Callable[[], Verdict]] = {}

    def register(self, block: str,
                 check: Callable[[], Verdict]) -> Callable[[], Verdict]:
        if block not in BLOCKS:
            raise ValueError("unknown block %r; expected one of %s"
                             % (block, ", ".join(BLOCKS)))
        self._checks[block] = check
        return check

    def blocks(self) -> List[str]:
        return list(self._checks)

    def run_one(self, block: str) -> Verdict:
        """Run a block's check, converting any failure into a verdict.

        A check that raises must not take the run down: a block that dies does not
        take the building with it, which is the property the dashboard already has
        for its panels.
        """
        check = self._checks.get(block)
        if check is None:
            return Verdict(block=block, verdict=NOT_REACHED,
                           detail="no self-check registered for this block")
        try:
            v = check()
        except Exception as exc:  # noqa: BLE001 - see _not_reached
            log.warning("organism self-check %s raised: %s: %s",
                        block, type(exc).__name__, exc)
            return _not_reached(block, exc)
        if not isinstance(v, Verdict):
            return Verdict(block=block, verdict=NOT_REACHED,
                           detail="self-check returned %s, not a Verdict"
                                  % type(v).__name__)
        return v

    def run_all(self) -> List[Verdict]:
        """Every registered block, in a stable order. Never raises."""
        order = [b for b in BLOCKS if b in self._checks]
        order += [b for b in self._checks if b not in order]
        return [self.run_one(b) for b in order]


# ── the default checks ───────────────────────────────────────────────────────
#
# Each takes no arguments and reads only things that are already in memory or a
# single cheap query. They are run on the request path of the board, so a check
# that opens a transaction per call would be the 05.11 outage again.

def _age_seconds(stamp: Optional[str]) -> Optional[float]:
    """Seconds since an ISO timestamp, or None when it is absent or unreadable.

    None means "no timestamp", which callers must treat as unknown rather than as
    infinitely old OR perfectly fresh. Both mistakes have happened here.
    """
    if not stamp:
        return None
    try:
        t = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - t).total_seconds())
    except (TypeError, ValueError):
        return None


def check_heartbeat(block: str, store) -> Verdict:
    """Is this block's heartbeat fresh enough to believe?

    A missing heartbeat is `not_reached`, not `ok`: the block has never reported,
    which is the state every block starts in and the state a broken writer leaves
    behind. Treating it as healthy is exactly the mistake this module removes.
    """
    if store is None:
        return Verdict(block=block, verdict=NOT_REACHED,
                       detail="no durable store to read the heartbeat from")
    try:
        raw = store.history.get_durable_meta(_HEARTBEAT_PREFIX + block)
    except Exception as exc:  # noqa: BLE001
        return _not_reached(block, exc)
    if not raw:
        return Verdict(block=block, verdict=NOT_REACHED,
                       detail="no heartbeat recorded yet",
                       evidence={"heartbeat": None})
    age = _age_seconds(raw)
    if age is None:
        return Verdict(block=block, verdict=NOT_REACHED,
                       detail="heartbeat is unreadable: %r" % str(raw)[:60],
                       evidence={"heartbeat": str(raw)[:60]})
    limit = stale_after_seconds(block)
    if age > limit:
        return Verdict(block=block, verdict=FAILED,
                       detail="heartbeat is %.0fs old (limit %ds)"
                              % (age, limit),
                       evidence={"heartbeat_age_seconds": round(age, 1),
                                 "limit_seconds": limit})
    return Verdict(block=block, verdict=OK,
                   detail="heartbeat %.0fs old" % age,
                   evidence={"heartbeat_age_seconds": round(age, 1),
                             "limit_seconds": limit})


def beat(store, block: str, verdict: str = OK, detail: str = "") -> bool:
    """Record that a block just ran, and how it went. Never raises.

    A heartbeat is telemetry: it must not be able to fail the thing it describes.
    Returns whether it was written, so a caller that cares can say so — but no
    caller is required to care.
    """
    if store is None:
        return False
    if verdict not in VERDICTS:
        verdict = NOT_REACHED
    try:
        stamp = datetime.now(timezone.utc).isoformat()
        store.history.set_durable_meta(_HEARTBEAT_PREFIX + block, stamp)
        # The verdict rides along so the board can read the last known state
        # without re-running every check on every request.
        store.history.set_durable_meta(_HEARTBEAT_PREFIX + block + "_verdict",
                                       verdict)
        if detail:
            store.history.set_durable_meta(
                _HEARTBEAT_PREFIX + block + "_detail", str(detail)[:200])
        return True
    except Exception as exc:  # noqa: BLE001 - telemetry only
        log.warning("organism heartbeat write failed for %s: %s", block, exc)
        return False


def last_verdict(store, block: str) -> Dict[str, object]:
    """What the block last reported, without running its check.

    This is what the board renders: a cheap read. `verdict` is `not_reached` when
    nothing has ever been recorded, which is honest — we have not looked.
    """
    return last_verdicts(store, [block])[0]


def last_verdicts(store, blocks) -> List[Dict[str, object]]:
    """Every block's last verdict in ONE query, not three per block.

    WHY THIS IS NOT A LOOP OVER `last_verdict`. Three durable-meta reads per
    block is eighteen round-trips per board build, and the board rebuilds in the
    background every ~30 seconds on a SHARED Postgres connection with an 8-second
    statement timeout. Eighteen extra reads there is the same shape as the read
    that took the service down on 05.11, and it made the organism's own deploy
    hang past Render's port-binding deadline.

    One `IN (...)` against a primary-key table is served by the index and costs
    one round-trip for all six blocks.
    """
    out: List[Dict[str, object]] = []
    blocks = list(blocks)
    blank = {b: {"block": b, "verdict": NOT_REACHED, "detail": "", "at": None,
                 "age_seconds": None} for b in blocks}
    if store is None:
        return [blank[b] for b in blocks]

    keys = []
    for b in blocks:
        keys.extend((_HEARTBEAT_PREFIX + b,
                     _HEARTBEAT_PREFIX + b + "_verdict",
                     _HEARTBEAT_PREFIX + b + "_detail"))
    placeholders = ", ".join("?" for _ in keys)
    try:
        rows = store.history._run(
            "SELECT key, value FROM dashboard_meta WHERE key IN (%s)"
            % placeholders, tuple(keys), "all")[0] or []
        found = {}
        for r in rows:
            # `sqlite3.Row` has no `.get`; index by name and tolerate absence.
            try:
                found[r["key"]] = r["value"]
            except (KeyError, IndexError, TypeError):
                continue
    except Exception as exc:  # noqa: BLE001 - the fallback below is the point
        log.debug("organism batch heartbeat read failed: %s", exc)
        return [blank[b] for b in blocks]

    for b in blocks:
        row = dict(blank[b])
        at = found.get(_HEARTBEAT_PREFIX + b)
        row["at"] = at
        row["age_seconds"] = _age_seconds(at)
        v = found.get(_HEARTBEAT_PREFIX + b + "_verdict")
        if v in VERDICTS:
            row["verdict"] = v
        row["detail"] = found.get(_HEARTBEAT_PREFIX + b + "_detail") or ""
        limit = stale_after_seconds(b)
        row["limit_seconds"] = limit
        if row["age_seconds"] is not None and \
                row["age_seconds"] > limit and \
                row["verdict"] == OK:
            # A fresh verdict on a stale heartbeat is stale too: the writer
            # stopped, and the last thing it said was "fine".
            row["verdict"] = FAILED
            row["detail"] = ("last said ok, but %.0fs ago (limit %ds)"
                             % (row["age_seconds"], limit))
        out.append(row)
    return out


def summary(store) -> Dict[str, object]:
    """The whole organism at a glance: one verdict per block, and the counts.

    `unhealthy` counts the blocks that are NOT ok, including `not_reached`. A
    block that never reported is counted, because "we have no idea" is not a
    healthy state and must not be summed as one.
    """
    rows = last_verdicts(store, BLOCKS)
    counts = {v: 0 for v in VERDICTS}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {
        "blocks": rows,
        "counts": counts,
        "unhealthy": sum(counts[v] for v in UNHEALTHY),
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "note": ("`not_reached` means the check did not run and is counted as "
                 "unhealthy — it is not the same as a check that ran and found "
                 "nothing."),
    }


def signals_from_verdicts(store) -> List[dict]:
    """Translate block verdicts into rule-table signals, one per sick block.

    THIS IS WHERE THE SENSE LAYER MEETS THE BRAIN. The blocks answer "am I well";
    the rule table answers "what would be done about it". Without this function
    the table has nothing to decide on, and the two layers sit beside each other
    instead of in a chain.

    The mapping is deliberately narrow, and it is the honest one:

      * a STALE heartbeat for a block that owns a loop -> `heartbeat_stale`
      * a block whose verdict is `failed`               -> `heartbeat_stale`
        (its writer stopped, which is the same fault from the table's view)
      * `not_reached`                                   -> NOT a signal

    That last line is the important one. `not_reached` means NOBODY HAS LOOKED,
    and the correct response is to look — not to restart a loop that may be
    perfectly healthy and merely unobserved. Restarting on `not_reached` would
    make the organism thrash on every fresh deploy, when all six blocks are
    legitimately `not_reached` for the first few seconds. So it is reported to
    the board and deliberately not converted into an action.
    """
    out: List[dict] = []
    for row in last_verdicts(store, BLOCKS):
        verdict = row.get("verdict")
        block = row.get("block") or ""
        if verdict == NOT_REACHED:
            continue
        if verdict in (FAILED, DEGRADED):
            out.append({
                "signal": "heartbeat_stale",
                "block": block,
                "detail": str(row.get("detail") or "")[:200],
                "evidence": {"verdict": verdict,
                             "age_seconds": row.get("age_seconds")},
            })
    return out


def _now_monotonic() -> float:  # pragma: no cover - tiny shim for tests
    return time.monotonic()
