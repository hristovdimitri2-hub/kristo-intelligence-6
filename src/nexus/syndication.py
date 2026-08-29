"""Syndication / hook generator — clean text blocks for external posting.

Formats top Nexus insights and the anonymized activity feed into
lightweight, copy-paste-ready text blocks designed for syndication
(newsletters, social posts, agent bulletins). Pure functions, zero
dependencies beyond the standard library — safe to call anywhere.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_HEADER = "Kristo Intelligence — agent activity on Base (x402)"


def _relative_time(ts_iso: str, now: Optional[datetime] = None) -> str:
    """Compact relative time ('2m ago', '3h ago', 'just now')."""
    try:
        ts = datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "recently"
    now = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    seconds = max(0, int((now - ts).total_seconds()))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def format_activity_digest(
    feed: Dict[str, Any], limit: int = 5, now: Optional[datetime] = None
) -> str:
    """Format the anonymized activity feed as a clean syndication text block."""
    items = (feed or {}).get("items", [])[: max(1, int(limit))]
    lines: List[str] = [_HEADER, ""]
    if not items:
        lines.append("• Early phase — be among the first agents to unlock live Base data.")
    else:
        for item in items:
            when = _relative_time(item.get("ts", ""), now=now)
            lines.append(f"• {item['text']} ({when})")
    totals = (feed or {}).get("totals", {})
    lines.append("")
    lines.append(
        f"{int(totals.get('unlocks_recent', 0) or 0)} data unlocks tracked · "
        "pay-per-call via x402 in USDC · https://kristo-intelligence-api.onrender.com"
    )
    return "\n".join(lines)


def format_strategy_hooks(
    strategy: Dict[str, Any], limit: int = 3
) -> List[str]:
    """Top Nexus briefs as single-line hooks, highest priority first."""
    briefs = (strategy or {}).get("briefs", [])[: max(1, int(limit))]
    hooks: List[str] = []
    for brief in briefs:
        priority = str(brief.get("priority", "info")).upper()
        title = str(brief.get("title", "")).strip()
        actions = brief.get("recommended_actions") or []
        first_action = str(actions[0]).strip() if actions else ""
        hook = f"[{priority}] {title}"
        if first_action:
            hook += f" — next step: {first_action}"
        hooks.append(hook)
    return hooks


def build_syndication_pack(
    feed: Dict[str, Any],
    strategy: Dict[str, Any],
    limit: int = 5,
    hooks_limit: int = 3,
) -> Dict[str, Any]:
    """Bundle digest + hooks for automated posting pipelines."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "digest": format_activity_digest(feed, limit=limit),
        "hooks": format_strategy_hooks(strategy, limit=hooks_limit),
        "anonymized": True,
    }
