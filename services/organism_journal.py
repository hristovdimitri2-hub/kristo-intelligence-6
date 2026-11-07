"""The organism's memory: an append-only journal of what it sensed and did.

WHY THIS IS THE POINT OF THE WHOLE EXERCISE. Every defect this project has had was
re-discovered from zero by the next session, because nothing the system learned
about itself survived the session that learned it. The owner's cost is not the
fixing — it is the re-discovery.

An append-only journal is what removes that cost. Three consumers:

  * the OWNER, who reads "what did the system notice and do" instead of asking a
    session to audit from scratch;
  * the RULE TABLE, which must learn the real frequency of a signal before it is
    allowed to act on it — a rule you cannot see firing is a rule you cannot
    trust;
  * the NEXT SESSION, which can read the last N entries and start where the
    previous one stopped.

DESIGN CONSTRAINTS, each of which is a mistake this codebase has already paid for:

  * APPEND-ONLY. No update, no delete. A journal that can be edited is a journal
    that can be made to say anything, and then it is worse than none.
  * NEVER RAISES. Journal writing happens next to payment handling. Telemetry
    must not be able to fail the thing it describes.
  * BOUNDED. A table with no retention is what took the service down on 07.11:
    `request_log` grew without limit and its aggregates took 10-21 seconds each.
    This one keeps a horizon and purges in batches, at boot and on a loop.
  * `not_reached` IS A FIRST-CLASS OUTCOME. An entry may record that something was
    never looked at. Omitting the entry would be the silent version of the same
    lie.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

log = logging.getLogger("kristo.v6.organism.journal")

#: Where the journal lives. A prefix keeps it greppable next to the other durable
#: operational keys and impossible to confuse with a heartbeat.
_KEY = "organism_journal"

#: How many entries to keep. Each is small (a few hundred bytes), so this is tens
#: of kilobytes — trivial next to `request_log`, and enough that a week of
#: self-heals is readable in one place.
MAX_ENTRIES = 2000

#: Severities, worst last. `observe` is the quiet one: something worth a human's
#: eye that the organism deliberately did NOT act on.
OBSERVE = "observe"
INFO = "info"
WARN = "warn"
ERROR = "error"
SEVERITIES = (OBSERVE, INFO, WARN, ERROR)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def entry(block: str, kind: str, *, severity: str = INFO, detail: str = "",
          action: str = "", outcome: str = "", evidence: Optional[dict] = None,
          at: str = "") -> Dict[str, object]:
    """Build one journal entry.

    `kind` is the signal name (`heartbeat_stale`, `rpc_endpoint_refused`, …) and
    is what the rule table matches on, so it is normalised to a lower-case token.
    """
    if severity not in SEVERITIES:
        severity = INFO
    return {
        "at": at or _now(),
        "block": str(block or "")[:40],
        "kind": str(kind or "").strip().lower().replace(" ", "_")[:60],
        "severity": severity,
        "detail": str(detail or "")[:300],
        "action": str(action or "")[:60],
        "outcome": str(outcome or "")[:120],
        "evidence": dict(evidence or {}),
    }


def _read_raw(store) -> List[dict]:
    """The stored list, or [] when absent/corrupt. Never raises."""
    if store is None:
        return []
    try:
        import json
        raw = store.history.get_durable_meta(_KEY)
        if not raw:
            return []
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, list) else []
    except Exception as exc:  # noqa: BLE001
        log.debug("organism journal read failed: %s", exc)
        return []


def _write_raw(store, items: List[dict]) -> bool:
    if store is None:
        return False
    try:
        import json
        store.history.set_durable_meta(
            _KEY, json.dumps(items[-MAX_ENTRIES:], ensure_ascii=False))
        return True
    except Exception as exc:  # noqa: BLE001 - telemetry only
        log.debug("organism journal write failed: %s", exc)
        return False


def append(store, block: str, kind: str, **kwargs) -> bool:
    """Add one entry. Append-only, bounded, and it never raises.

    The bounding is `[-MAX_ENTRIES:]` on write rather than a separate purge step,
    so the table can never grow past the limit even if a purge never runs.
    """
    items = _read_raw(store)
    items.append(entry(block, kind, **kwargs))
    return _write_raw(store, items)


def entries(store, *, block: str = "", severity: str = "",
            kind: str = "", limit: int = 50) -> List[dict]:
    """Read the journal, newest first. Filters are exact matches.

    Returns [] both when the journal is empty and when it cannot be read — the
    one place in this module where the two are collapsed, because the caller is a
    display surface that will show its own "unreadable" marker from a separate
    call. Anything making a DECISION must use `readable()` as well.
    """
    items = _read_raw(store)
    if block:
        items = [i for i in items if i.get("block") == block]
    if severity:
        items = [i for i in items if i.get("severity") == severity]
    if kind:
        items = [i for i in items if i.get("kind") == kind]
    return list(reversed(items))[:max(1, int(limit))]


def readable(store) -> bool:
    """Whether the journal can actually be read, as distinct from being empty.

    Kept separate for the same reason the dashboard keeps it separate: a surface
    that reported a broken journal as "nothing has happened" would be inventing a
    quiet week.
    """
    if store is None:
        return False
    try:
        store.history.get_durable_meta(_KEY)
        return True
    except Exception:
        return False


def counts(store, hours: int = 24) -> Dict[str, int]:
    """How many entries per severity in the last `hours`.

    This is the number the owner should watch: a RISING self-heal count is itself
    the signal. A monitor that silently restarts forever looks identical to a
    healthy one, and this is what tells them apart.
    """
    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=max(1, int(hours)))).isoformat()
    items = [i for i in _read_raw(store) if str(i.get("at") or "") >= cutoff]
    out = {s: 0 for s in SEVERITIES}
    for i in items:
        s = i.get("severity")
        if s in out:
            out[s] += 1
    out["total"] = len(items)
    return out


def prune(store, keep: int = MAX_ENTRIES) -> int:
    """Drop the oldest entries beyond `keep`. Returns how many went.

    Idempotent: a second call with nothing to remove returns 0. Present as a
    separate verb because the rule table may want to call it explicitly, even
    though `append` already bounds the list.
    """
    items = _read_raw(store)
    keep = max(1, int(keep))
    if len(items) <= keep:
        return 0
    removed = len(items) - keep
    _write_raw(store, items[-keep:])
    return removed
