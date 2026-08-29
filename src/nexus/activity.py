"""Public activity feed — anonymized proof-of-traction for the viral layer.

Builds a privacy-safe, unauthenticated activity feed from:
  * successful x402 data unlocks (paid-endpoint traffic from the request log)
  * real on-chain USDC unlocks from the sales history (no sender, tx truncated)
  * durable catalog metrics (verified agent payments in 24h)
  * verified Nexus Intelligence signals (gap-analysis summary)

Anonymization is enforced by construction: the builder never receives and
never emits emails, raw wallet addresses, IPs or full tx hashes.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

# Friendly, public-facing labels for recorded request-log endpoint keys.
_SIGNAL_LABELS: Dict[str, str] = {
    "api_stats": "DeFi Market Signal",
    "api_sales": "Market Evaluator Signal",
    "api_bot_status": "Bot Intelligence Signal",
    "api_arb_opportunities": "Arbitrage Opportunity Scan",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _agent_alias(*seed_parts: str) -> str:
    """Deterministic non-reversible alias (e.g. 'Agent #7f3a2b') — no PII."""
    digest = hashlib.sha256("|".join(seed_parts).encode()).hexdigest()[:6]
    return f"Agent #{digest}"


def _short_tx(tx_hash: str) -> str:
    tx = (tx_hash or "").strip()
    return f"{tx[:10]}…" if len(tx) > 12 else tx


def build_activity_feed(
    request_log_provider: Callable[[], List[Dict[str, Any]]],
    sales_history_provider: Callable[[], List[Dict[str, Any]]],
    catalog_metrics_provider: Callable[[], Dict[str, Any]],
    nexus_signals_provider: Callable[[], Dict[str, Any]],
    limit: int = 20,
) -> Dict[str, Any]:
    """Assemble the anonymized public feed. Providers keep main.py decoupled."""
    items: List[Dict[str, Any]] = []

    # 1) Successful x402 data unlocks from the bounded request log.
    unlocks_seen = 0
    for entry in reversed(request_log_provider() or []):
        key = str(entry.get("endpoint", ""))
        label = _SIGNAL_LABELS.get(key)
        if not label or not entry.get("success"):
            continue
        unlocks_seen += 1
        ts = str(entry.get("timestamp", ""))
        items.append(
            {
                "id": f"unlk:{hashlib.sha256((ts + key).encode()).hexdigest()[:10]}",
                "ts": ts,
                "kind": "unlock",
                "text": f"{_agent_alias(ts, key)} unlocked {label} on Base",
                "meta": {"signal": label, "chain": "base"},
            }
        )

    # 2) Real on-chain USDC unlocks — sender never exposed, tx truncated.
    for sale in sales_history_provider() or []:
        ts = str(sale.get("timestamp", ""))
        amount = float(sale.get("amount_usd", 0.0) or 0.0)
        items.append(
            {
                "id": f"sale:{_short_tx(sale.get('tx_hash', ''))}",
                "ts": ts,
                "kind": "on_chain_unlock",
                "text": (
                    f"On-chain payment verified on Base: {amount:.3f} USDC "
                    f"({sale.get('token', 'USDC')}) — tx {_short_tx(sale.get('tx_hash', ''))}"
                ),
                "meta": {"amount_usdc": amount, "chain": "base"},
            }
        )

    # 3) Durable catalog aggregates (verified agent payments, 24h window).
    try:
        metrics = catalog_metrics_provider() or {}
        totals = metrics.get("totals", {})
        if int(totals.get("payments", 0) or 0) > 0 or int(totals.get("clicks", 0) or 0) > 0:
            items.append(
                {
                    "id": "catalog:24h",
                    "ts": _utcnow().isoformat(),
                    "kind": "catalog_totals",
                    "text": (
                        f"Catalog 24h: {int(totals.get('payments', 0) or 0)} verified agent "
                        f"payments across {len(metrics.get('products', []))} agents"
                    ),
                    "meta": {
                        "clicks": int(totals.get("clicks", 0) or 0),
                        "payments": int(totals.get("payments", 0) or 0),
                        "revenue_usd": totals.get("revenue_usd", 0),
                    },
                }
            )
    except Exception:
        pass  # aggregates are best-effort; the feed never fails on them

    # 4) Verified Nexus Intelligence signals (generalized, no internal detail).
    try:
        summary = (nexus_signals_provider() or {}).get("summary", {})
        by_priority = summary.get("by_priority", {})
        high = int(by_priority.get("high", 0) or 0)
        total = int(summary.get("total_briefs", 0) or 0)
        if total:
            items.append(
                {
                    "id": "nexus:signals",
                    "ts": _utcnow().isoformat(),
                    "kind": "nexus_signal",
                    "text": (
                        f"Nexus Engine verified {total} strategic signal(s) "
                        f"({high} high-priority) against live platform data"
                    ),
                    "meta": {"total_briefs": total, "high_priority": high},
                }
            )
    except Exception:
        pass

    items.sort(key=lambda i: i.get("ts", ""), reverse=True)
    items = items[: max(1, int(limit))]

    return {
        "generated_at": _utcnow().isoformat(),
        "chain": "base",
        "anonymized": True,
        "totals": {
            "unlocks_recent": unlocks_seen,
            "on_chain_unlocks": sum(1 for i in items if i["kind"] == "on_chain_unlock"),
            "items": len(items),
        },
        "items": items,
    }
