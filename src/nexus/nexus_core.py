"""Nexus Aggregator — collects and cross-references autonomous intelligence.

Pulse sources are pluggable feeders of "intelligence items"; the built-in
adapters read the durable stores the application already maintains (x402
agent-catalog metrics, sales funnel, research insights — the database where
x402-pulse style collectors land their processed items). Custom collectors
(a future ``x402-pulse`` scraper module, for example) attach via
:meth:`NexusAggregator.register_source` without touching the synthesis rules.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("kristo.v6.nexus.core")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PulseSource:
    """Protocol/base class for intelligence feeders (x402-pulse adapters).

    Subclasses set :attr:`name` and implement :meth:`collect`, returning a
    list of plain-dict items:
    ``{"kind": str, "ref_id": str, "title": str, "metrics": dict}``.
    """

    name: str = "pulse-source"

    def collect(self) -> List[Dict[str, Any]]:
        raise NotImplementedError


class CatalogPulseSource(PulseSource):
    """x402 agent-catalog performance as per-agent intelligence items."""

    name = "x402-catalog"

    def __init__(self, store_provider: Callable[[], Any]):
        self._store_provider = store_provider

    def collect(self) -> List[Dict[str, Any]]:
        store = self._store_provider()
        metrics = store.get_metrics_24h()
        items: List[Dict[str, Any]] = []
        for product in metrics.get("products", []):
            items.append(
                {
                    "kind": "agent_performance",
                    "ref_id": product.get("id", ""),
                    "title": product.get("name", product.get("id", "")),
                    "metrics": {
                        "price_usdc": product.get("price_usdc") or product.get("price_x402"),
                        "clicks_24h": int(product.get("clicks_24h", 0) or 0),
                        "calls_24h": int(product.get("calls_24h", 0) or 0),
                        "hits_24h": int(product.get("hits_24h", 0) or 0),
                        "payments_24h": int(product.get("payments_24h", 0) or 0),
                        "revenue_24h": float(product.get("revenue_24h", 0.0) or 0.0),
                        "popularity_rank": int(product.get("popularity_rank", 0) or 0),
                    },
                }
            )
        totals = metrics.get("totals", {})
        if totals:
            items.append(
                {
                    "kind": "catalog_totals",
                    "ref_id": "catalog-24h",
                    "title": "Catalog 24h totals",
                    "metrics": {
                        k: totals.get(k, 0)
                        for k in ("clicks", "calls", "hits", "payments", "sales", "revenue_usd")
                    },
                }
            )
        return items


class FunnelPulseSource(PulseSource):
    """Sales-funnel intelligence from the CRM store (leads, pipeline, paid)."""

    name = "sales-funnel"

    def __init__(self, store_provider: Callable[[], Any]):
        self._store_provider = store_provider

    def collect(self) -> List[Dict[str, Any]]:
        store = self._store_provider()
        pipeline = store.get_sales_pipeline()
        statuses = store.count_by_status()
        leads = store.get_all()
        paid = sum(1 for lead in leads if str(lead.get("status", "")).upper() == "PAID")
        return [
            {
                "kind": "funnel_snapshot",
                "ref_id": "sales-pipeline",
                "title": "Sales pipeline snapshot",
                "metrics": {
                    "pipeline": dict(pipeline),
                    "statuses": dict(statuses),
                    "leads_total": len(leads),
                    "paid_count": paid,
                    "conversion_rate": round(
                        (paid / len(leads) * 100) if leads else 0.0, 2
                    ),
                },
            }
        ]


class ResearchPulseSource(PulseSource):
    """Processed intelligence items from the durable research-insights store."""

    name = "research-intel"

    def __init__(self, store_provider: Callable[[], Any], limit: int = 50):
        self._store_provider = store_provider
        self._limit = max(1, min(int(limit), 200))

    def collect(self) -> List[Dict[str, Any]]:
        store = self._store_provider()
        items: List[Dict[str, Any]] = []
        for insight in store.list_insights(limit=self._limit):
            items.append(
                {
                    "kind": "research_insight",
                    "ref_id": insight.get("id", ""),
                    "title": insight.get("title", ""),
                    "metrics": {
                        "status": insight.get("status", ""),
                        "source": insight.get("source", ""),
                        "actionable_summary": insight.get("actionable_summary", ""),
                    },
                }
            )
        return items


class NexusAggregator:
    """Aggregates every registered pulse source into one intelligence snapshot."""

    def __init__(
        self,
        project_params_provider: Callable[[], Dict[str, Any]],
        sources: Optional[List[PulseSource]] = None,
    ):
        self._params_provider = project_params_provider
        self._sources: List[PulseSource] = list(sources or [])
        self._lock = threading.Lock()

    def register_source(self, source: PulseSource) -> None:
        """Attach an additional intelligence feeder (e.g. an x402-pulse scraper)."""
        with self._lock:
            if source.name not in {s.name for s in self._sources}:
                self._sources.append(source)

    def collect(self) -> Dict[str, Any]:
        """Collect items from all sources. A failing source never breaks the loop."""
        items: List[Dict[str, Any]] = []
        source_reports: List[Dict[str, Any]] = []
        for source in self._sources:
            try:
                collected = source.collect() or []
                items.extend(collected)
                source_reports.append(
                    {"name": source.name, "status": "ok", "items": len(collected)}
                )
            except Exception as exc:  # resilient: one dead source never kills the loop
                log.warning("Nexus pulse source %s failed: %s", source.name, exc)
                source_reports.append(
                    {"name": source.name, "status": "error", "error": str(exc)[:200]}
                )
        return {
            "generated_at": _utcnow_iso(),
            "items": items,
            "sources": source_reports,
        }

    def cross_reference(self, collected: Dict[str, Any]) -> Dict[str, Any]:
        """Merge raw intelligence with the live project parameters into one context."""
        items = collected.get("items", [])
        params = self._params_provider() or {}

        agents: List[Dict[str, Any]] = []
        funnel: Dict[str, Any] = {}
        catalog_totals: Dict[str, Any] = {}
        for item in items:
            kind = item.get("kind")
            if kind == "agent_performance":
                metrics = item.get("metrics", {})
                clicks = int(metrics.get("clicks_24h", 0) or 0)
                payments = int(metrics.get("payments_24h", 0) or 0)
                agents.append(
                    {
                        "id": item.get("ref_id", ""),
                        "name": item.get("title", ""),
                        "price_usdc": metrics.get("price_usdc"),
                        "clicks_24h": clicks,
                        "calls_24h": int(metrics.get("calls_24h", 0) or 0),
                        "payments_24h": payments,
                        "revenue_24h": float(metrics.get("revenue_24h", 0.0) or 0.0),
                        "popularity_rank": int(metrics.get("popularity_rank", 0) or 0),
                        "conversion_rate_24h": round(
                            (payments / clicks * 100) if clicks else 0.0, 2
                        ),
                    }
                )
            elif kind == "funnel_snapshot":
                funnel = dict(item.get("metrics", {}))
            elif kind == "catalog_totals":
                catalog_totals = dict(item.get("metrics", {}))

        agents.sort(key=lambda a: (a["popularity_rank"] or 10**6, a["id"]))

        research_items = [i for i in items if i.get("kind") == "research_insight"]
        research = {
            "total": len(research_items),
            "pending": sum(
                1
                for i in research_items
                if str(i.get("metrics", {}).get("status", "")).upper() == "PENDING"
            ),
            "approved": sum(
                1
                for i in research_items
                if str(i.get("metrics", {}).get("status", "")).upper() == "APPROVED"
            ),
            "recent_titles": [i.get("title", "") for i in research_items[:5]],
        }

        return {
            "generated_at": collected.get("generated_at", _utcnow_iso()),
            "sources": collected.get("sources", []),
            "project": params,
            "agents": agents,
            "funnel": funnel,
            "research": research,
            "catalog_totals": catalog_totals,
        }


class NexusEngine:
    """The unified loop: aggregate -> cross-reference -> synthesize (TTL cached).

    Built on-demand per request behind a short TTL cache so reads stay
    responsive without background threads, external paid dependencies or
    spam automations.
    """

    CACHE_TTL_SECONDS = 60

    def __init__(self, aggregator: NexusAggregator, synthesizer: Any):
        self._aggregator = aggregator
        self._synthesizer = synthesizer
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_at = 0.0
        self._lock = threading.Lock()

    def invalidate(self) -> None:
        """Drop the cached strategy snapshot (next build re-reads the stores)."""
        with self._lock:
            self._cache = None
            self._cache_at = 0.0

    def build_strategy(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Run the full autonomous loop once and return the strategy payload."""
        now = time.time()
        with self._lock:
            if (
                not force_refresh
                and self._cache is not None
                and now - self._cache_at < self.CACHE_TTL_SECONDS
            ):
                return self._cache

        collected = self._aggregator.collect()
        context = self._aggregator.cross_reference(collected)
        synthesis = self._synthesizer.synthesize(context)
        payload = {
            "generated_at": context.get("generated_at"),
            "summary": synthesis.get("summary", {}),
            "briefs": synthesis.get("briefs", []),
            "context": {
                "project": context.get("project", {}),
                "funnel": context.get("funnel", {}),
                "agents": context.get("agents", []),
                "research": context.get("research", {}),
                "catalog_totals": context.get("catalog_totals", {}),
                "sources": context.get("sources", []),
            },
        }
        with self._lock:
            self._cache = payload
            self._cache_at = now
        return payload
