"""Chaos drills — deliberately break one thing and prove the organism notices.

STEP 6, AND THE ONLY WAY TO TRUST ANY OF THIS. A self-healing system that has
never been tested against a real fault is a claim, not a mechanism. The day it
matters is the day nobody can afford to discover it does not work.

Each drill does four things, and the fourth is the point:

    1. BREAK one thing, in a controlled and reversible way
    2. SENSE it — the block's verdict must change to something unhealthy
    3. DECIDE it — the rule table must name the right signal and action
    4. HEAL it — with actions enabled, the executor must run AND the signal must
       be GONE afterwards, which is the only definition of "fixed" this project
       accepts

A drill that only reaches step 3 is a drill for the observe-only build, and is
reported as `would_heal` rather than as a pass. That distinction is deliberate:
it would be easy to write a "chaos test" that never actually verifies recovery
and passes forever, and it would prove nothing.

NO DRILL TOUCHES PRODUCTION. Everything here runs against an in-memory store and
threads this module starts itself. There is no network, no database, and no
deploy.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from services import organism as org
from services import organism_executors as ex
from services import organism_journal as oj
from services import organism_rules as rules

log = logging.getLogger("kristo.v6.organism.chaos")


class _History:
    """An in-memory durable store. The drills must not touch a real database."""

    def __init__(self) -> None:
        self.d: Dict[str, str] = {}
        self.fail_reads = False
        self.fail_writes = False

    def get_durable_meta(self, key, default=None):
        if self.fail_reads:
            raise RuntimeError("chaos: the store is unreachable")
        return self.d.get(key, default)

    def set_durable_meta(self, key, value):
        if self.fail_writes:
            raise RuntimeError("chaos: the store is read-only")
        self.d[key] = value

    def _run(self, sql, params=(), fetch=""):
        if self.fail_reads:
            raise RuntimeError("chaos: the store is unreachable")
        rows = [{"key": k, "value": self.d[k]} for k in params if k in self.d]
        return rows, len(rows)


class _Store:
    def __init__(self) -> None:
        self.history = _History()


class Drill:
    """One controlled fault, with its own break / sense / decide / heal steps."""

    def __init__(self, name: str, what: str,
                 break_it: Callable[[_Store], None],
                 signal: str,
                 block: str,
                 heal: Optional[Callable[[_Store], Dict[str, object]]] = None,
                 settled: Optional[Callable[[_Store], bool]] = None,
                 expect_no_signal: bool = False) -> None:
        self.name = name
        self.what = what
        self.break_it = break_it
        self.signal = signal
        self.block = block
        self.heal = heal
        self.settled = settled
        #: For the faults whose CORRECT behaviour is to produce no signal at all
        #: — `not_reached` means nobody looked, and converting that into an
        #: action would restart healthy loops. A drill for it must assert the
        #: absence, not the presence.
        self.expect_no_signal = expect_no_signal


def _run_drill(drill: Drill) -> Dict[str, object]:
    """Break it, sense it, decide it, and (if the drill can) heal it."""
    store = _Store()
    out: Dict[str, object] = {"drill": drill.name, "what": drill.what,
                              "steps": {}}

    # 1. BREAK
    drill.break_it(store)
    out["steps"]["broken"] = True

    # 2. SENSE — the block must be reported unhealthy, and never as ok
    verdict = org.last_verdict(store, drill.block)
    sensed = verdict["verdict"] in org.UNHEALTHY
    out["steps"]["sensed"] = sensed
    out["steps"]["verdict"] = verdict["verdict"]
    if not sensed:
        out["outcome"] = "NOT SENSED"
        return out

    # the sense layer must convert it into the right signal
    signals = [s for s in org.signals_from_verdicts(store)
               if s["block"] == drill.block]
    got = [s["signal"] for s in signals]
    out["steps"]["signals"] = got

    if drill.expect_no_signal:
        # THE drill for the anti-thrash rule. The block IS unhealthy and IS
        # reported as such, and the organism deliberately raises no action:
        # "nobody looked" is not "something is broken".
        if got:
            out["outcome"] = ("WRONG: a non-action fault produced %r" % got)
            return out
        if verdict["verdict"] != org.NOT_REACHED:
            out["outcome"] = ("expected not_reached, got %r"
                              % verdict["verdict"])
            return out
        out["outcome"] = "CORRECTLY NOT ACTED ON (not_reached is not a fault)"
        return out

    if drill.signal not in got:
        out["outcome"] = "WRONG SIGNAL (got %r, wanted %r)" % (got, drill.signal)
        return out

    # 3. DECIDE — the table must name the action
    decision = rules.decide(drill.signal, block=drill.block)
    out["steps"]["class"] = decision.klass
    out["steps"]["action"] = decision.action
    rules.journal_decision(store, decision)
    if decision.klass != rules.SELF_HEAL:
        out["outcome"] = "ESCALATED (correct for this signal?)"
        return out

    # 4. HEAL — only if the drill can express the repair
    if drill.heal is None:
        out["outcome"] = "would_heal (observe-only build: no repair expressed)"
        return out

    rules.reset_ledger()
    kwargs = drill.heal(store)
    result = ex.execute(decision, store, kwargs=kwargs,
                        still_present=(lambda: not drill.settled(store))
                        if drill.settled else None,
                        allow_actions=True)
    out["steps"]["acted"] = result.ok
    out["steps"]["verified"] = result.verified
    out["steps"]["detail"] = result.detail
    ex.journal_result(store, decision, result)

    if result.ok and result.verified:
        out["outcome"] = "HEALED"
    elif result.ok and result.verified is False:
        out["outcome"] = "NOT HEALED (action ran, signal survived)"
    elif result.ok:
        out["outcome"] = "acted, unverified"
    else:
        out["outcome"] = "refused: %s" % result.detail[:60]
    return out


# ── the drills ───────────────────────────────────────────────────────────────

def _break_heartbeat(store: _Store) -> None:
    """A writer stops: the heartbeat is old but last said `ok`."""
    store.history.d["organism_hb_data_store"] = "2020-01-01T00:00:00+00:00"
    store.history.d["organism_hb_data_store_verdict"] = org.OK


def _heal_heartbeat(store: _Store) -> Dict[str, object]:
    """The repair is to start the writer again, which updates the heartbeat."""
    def starter():
        org.beat(store, "data_store", org.OK, "restarted by the drill")
        return True
    return {"thread": None, "starter": starter}


def _break_unreadable_store(store: _Store) -> None:
    """The store itself becomes unreadable — the nastiest case."""
    store.history.fail_reads = True


def _break_missing_block(store: _Store) -> None:
    """A block has never reported. The correct answer is not_reached."""
    store.history.d.clear()


def _break_stale_but_degraded(store: _Store) -> None:
    """A block reported `degraded`, which is also a signal."""
    store.history.d["organism_hb_chain_read"] = \
        "2020-01-01T00:00:00+00:00"
    store.history.d["organism_hb_chain_read_verdict"] = org.FAILED


DRILLS: List[Drill] = [
    Drill("stale_heartbeat",
          "a block's writer stopped; the heartbeat is old and last said ok",
          _break_heartbeat, "heartbeat_stale", "data_store",
          heal=_heal_heartbeat,
          settled=lambda s: org.last_verdict(s, "data_store")["verdict"] == org.OK),
    Drill("degraded_block",
          "a block reported a failure rather than silence",
          _break_stale_but_degraded, "heartbeat_stale", "chain_read"),
    Drill("never_reported",
          "a block has never reported: not_reached, which must NOT be an action",
          _break_missing_block, "", "delivery",
          expect_no_signal=True),
    Drill("unreadable_store",
          "the durable store cannot be read at all",
          _break_unreadable_store, "", "data_store",
          expect_no_signal=True),
]


def run_all() -> Dict[str, object]:
    """Every drill, with a verdict that cannot be faked.

    A drill counts as PASSED only when the fault was sensed, the right signal
    was produced, the right action was chosen, AND the repair was verified. An
    observe-only drill is reported separately, because it proves the first three
    steps and not the fourth. A drill whose correct answer is "do not act" is
    counted as passed when it correctly does not.
    """
    results = [_run_drill(d) for d in DRILLS]
    healed = [r for r in results if r["outcome"] == "HEALED"]
    withheld = [r for r in results
                if str(r["outcome"]).startswith("CORRECTLY NOT ACTED ON")]
    observed = [r for r in results if str(r["outcome"]).startswith("would_heal")]
    failed = [r for r in results
              if r not in healed and r not in withheld and r not in observed]
    return {
        "drills": results,
        "healed": len(healed),
        "withheld_correctly": len(withheld),
        "observe_only": len(observed),
        "failed": len(failed),
        "passed": len(healed) + len(withheld),
        "note": ("A drill passes when the fault was sensed and answered "
                 "correctly — either by a verified repair, or by deliberately "
                 "not acting on `not_reached`. Anything else is reported as "
                 "what it is."),
    }


if __name__ == "__main__":  # pragma: no cover - manual run
    import json
    print(json.dumps(run_all(), indent=2, ensure_ascii=False))
    _ = (threading, time, oj)
