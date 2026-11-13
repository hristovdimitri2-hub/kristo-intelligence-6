"""Honest on-chain audit of an x402 seller's receiver.

WHY THIS EXISTS
---------------
The single most-asked question in the x402 ecosystem is whether a seller's money
is real. Measured demand from a directory that logs what agents search for
(07.11) puts three queries at the top, each from ~50 independent client
addresses over eight consecutive days: `seller conformance`, `settlement ledger`
and `funded sellers` — plus about ten more of the same kind ("is this x402 seller
safe to pay", "x402 seller reputation unique payers", "x402 endpoint reliability
uptime data"). The directory's own words: a search with no good answer is a
service nobody is selling yet.

We already had the machinery. `scripts/competitor_recon.py` reads incoming USDC
transfers to ANY receiver with adaptive chunking, reports its own coverage, and
classifies payers so operator/treasury flows and reviewer canaries never inflate
the customer count. What it was missing was being reachable from the product.
This module is that bridge — and it deliberately IMPORTS that logic instead of
reimplementing it, so the two cannot drift.

THE RULE THIS MODULE ENFORCES
-----------------------------
"Could not look" must never be published as "found nothing". A window that was
not fully read is reported as `read: "partial"`, never as zero payers, and a
failed read is `read: "failed"` with its reason. That is the same rule the rest
of this service applies to every surface, and it matters most here: this report
is meant to be used by somebody deciding whether to send money.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

#: Default window. Seven days matches the weekly cadence the community already
#: publishes with, and keeps one audit inside a bounded number of eth_getLogs
#: calls on a public RPC.
DEFAULT_AUDIT_DAYS = 7

#: Bounds accepted from a caller. A 90-day window on a public RPC is thousands of
#: chunked calls; refusing is kinder than timing out, and the refusal says so.
MIN_AUDIT_DAYS = 1
MAX_AUDIT_DAYS = 30

#: How long a finished audit may be reused. An audit costs real RPC calls, so the
#: same receiver must not pay for them twice in a minute — and a result this fresh
#: cannot mislead anybody about the chain.
AUDIT_CACHE_SECONDS = 900

_CACHE: Dict[str, tuple] = {}
_CACHE_LOCK = threading.Lock()


def _cache_key(receiver: str, days: int) -> str:
    return f"{receiver.lower()}:{days}"


def cached_audit(receiver: str, days: int) -> Optional[dict]:
    """Return a still-fresh audit, or None. Never raises."""
    try:
        with _CACHE_LOCK:
            hit = _CACHE.get(_cache_key(receiver, days))
        if not hit:
            return None
        stamped, payload = hit
        if time.time() - stamped > AUDIT_CACHE_SECONDS:
            return None
        # A copy, so a caller cannot mutate what the next caller will read.
        return dict(payload)
    except Exception:
        return None


def store_audit(receiver: str, days: int, payload: dict) -> None:
    """Remember a finished audit. Never raises: caching is an optimisation."""
    try:
        with _CACHE_LOCK:
            _CACHE[_cache_key(receiver, days)] = (time.time(), dict(payload))
            if len(_CACHE) > 512:
                # Bounded on purpose: this is an in-process convenience, not a
                # store, and an unbounded dict keyed by caller input is a leak.
                oldest = sorted(_CACHE.items(), key=lambda kv: kv[1][0])[:128]
                for key, _ in oldest:
                    _CACHE.pop(key, None)
    except Exception:
        pass


def _verdict(read: str, classified: dict, coverage: dict) -> str:
    """One plain sentence a buyer can act on, that never overstates the read.

    Written here rather than in the route so it cannot be softened separately
    from the numbers it is describing.
    """
    if read == "failed":
        return ("Could not read this receiver on-chain, so this report says "
                "nothing about whether it gets paid. Treat it as unknown, not "
                "as empty.")
    if read == "partial":
        return ("The window was not read end to end, so these figures are a "
                "floor, not a total. Silence in the unread part is not evidence "
                "that nobody paid.")
    external = classified.get("external_unique_payers", 0)
    if external == 0:
        return ("Read cleanly, and no distinct paying address was found in this "
                "window. That is a real zero for this window, not a failed read.")
    repeats = len(classified.get("repeat_payers") or [])
    return (f"Read cleanly: {external} distinct paying address(es), "
            f"{repeats} of them paid more than once.")


def build_audit(transfers: List[dict], coverage: Optional[dict], *,
                receiver: str, days: int, now: Optional[datetime] = None,
                failed_reason: str = "") -> dict:
    """Turn raw transfers + coverage into the published report. Pure.

    Kept free of RPC and of Flask so every honesty rule here is testable without
    a network, which is how the `failed` / `partial` / `clean` split gets proven
    rather than asserted.
    """
    from scripts.competitor_recon import classify_transfers

    cov = dict(coverage or {})
    if failed_reason:
        read = "failed"
    elif cov.get("complete") is False:
        read = "partial"
    else:
        read = "clean"

    classified = classify_transfers(transfers or [])
    stamped = (now or datetime.now(timezone.utc)).isoformat()

    return {
        "ok": read != "failed",
        "receiver": receiver,
        "window_days": days,
        "read": read,
        "read_reason": failed_reason or None,
        "checked_at": stamped,
        "coverage": {
            "complete": bool(cov.get("complete")),
            "reason": cov.get("reason"),
            "from_block": cov.get("from_block"),
            "to_block": cov.get("to_block"),
            "requested_blocks": cov.get("requested_blocks"),
            "scanned_blocks": cov.get("scanned_blocks"),
            "failed_ranges": cov.get("failed_ranges"),
            "split_retries": cov.get("split_retries"),
        },
        "verdict": _verdict(read, classified, cov),
        # `classified` is published as-is: it already separates large
        # treasury/exchange flows and reviewer canaries from operator payments,
        # so the headline cannot be inflated by either.
        "payer_analysis": classified,
        "notes": [
            "Only incoming USDC transfers on Base to this exact address are read.",
            "Transfers at or above the large-transfer threshold are counted as "
            "treasury/exchange flows, not as per-call payments.",
            "Known reviewer/verification addresses are counted separately so they "
            "cannot inflate the customer count.",
            "A distinct paying address is not a distinct customer: one operator "
            "can pay from several wallets, and several agents can share one.",
        ],
    }


def audit_receiver(receiver: str, days: int = DEFAULT_AUDIT_DAYS,
                   rpc_url: str = "", usdc_contract: str = "") -> dict:
    """Read the chain and publish an honest audit of `receiver`.

    Never raises for a chain problem: an unreachable RPC is reported as
    `read: "failed"`, because the alternative — an exception, or an empty report
    — would both be read as "this seller has no customers".
    """
    from scripts import competitor_recon as recon

    days = max(MIN_AUDIT_DAYS, min(MAX_AUDIT_DAYS, int(days or DEFAULT_AUDIT_DAYS)))

    if not rpc_url:
        try:
            from config import base_rpc_candidates
            candidates = base_rpc_candidates()
            rpc_url = candidates[0] if candidates else ""
        except Exception:
            rpc_url = ""
    if not rpc_url:
        return build_audit([], None, receiver=receiver, days=days,
                           failed_reason="no_rpc_configured")

    # One URL is enough here: the audit is a read we can retry, and a buyer
    # waiting on a report is better served by an honest failure than by a long
    # hunt through endpoints. `base_rpc_candidates()` remains the source of the
    # primary, so this follows configuration rather than pinning a host.
    #
    # `days` is passed THROUGH to the scanner. It used to stop here: the scanner
    # hardcoded a 7-day window while this function reported whatever it had been
    # asked for, so a report headed "last 30 days" had read 7. The window in the
    # report and the window walked are now the same value, and the coverage block
    # carries lookback_days so the two can be compared rather than trusted.
    stats: dict = {}
    kwargs = {"stats": stats, "days": days}
    if usdc_contract:
        kwargs["usdc_contract"] = usdc_contract
    try:
        transfers = recon.fetch_incoming_transfers(rpc_url, receiver, **kwargs)
    except Exception as exc:
        log.warning("seller audit could not read %s: %s", receiver, type(exc).__name__)
        return build_audit([], stats, receiver=receiver, days=days,
                           failed_reason=f"rpc_read_failed: {type(exc).__name__}")

    return build_audit(transfers, stats, receiver=receiver, days=days)
