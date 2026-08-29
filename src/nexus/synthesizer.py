"""Strategic Synthesis & Gap Analysis for the Nexus Intelligence Engine.

Turns the cross-referenced intelligence context produced by
:class:`src.nexus.nexus_core.NexusAggregator` into actionable strategic
briefs. The rules are deterministic and run natively in-process — no
external AI/paid dependencies — so brief generation is safe, cheap and
reproducible on the Render free tier.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

# Tunable thresholds (env-overridable for ops without code changes).
MIN_CLICKS_FOR_MONETIZATION_GAP = int(
    os.getenv("KRISTO_NEXUS_MIN_CLICKS_GAP", "3")
)
MAX_REVENUE_CONCENTRATION_SHARE = float(
    os.getenv("KRISTO_NEXUS_MAX_REVENUE_SHARE", "0.80")
)

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class StrategicBrief:
    """One actionable strategic recommendation for the dashboard."""

    id: str
    category: str
    priority: str  # "high" | "medium" | "low"
    title: str
    rationale: str
    recommended_actions: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "priority": self.priority,
            "title": self.title,
            "rationale": self.rationale,
            "recommended_actions": list(self.recommended_actions),
            "evidence": dict(self.evidence),
        }


def _detect_monetization_gaps(context: Dict[str, Any]) -> list:
    """Agents that attract clicks but convert none — paywall/price mismatch."""
    briefs = []
    for agent in context.get("agents", []):
        if agent["clicks_24h"] >= MIN_CLICKS_FOR_MONETIZATION_GAP and agent["payments_24h"] == 0:
            briefs.append(
                StrategicBrief(
                    id=f"monetization_gap:{agent['id']}",
                    category="monetization",
                    priority="high",
                    title=(
                        f"«{agent['name']}» генерира интерес, но нула реализации"
                    ),
                    rationale=(
                        f"{agent['clicks_24h']} клика за 24 ч без нито едно плащане — "
                        "болката, която агентът решава, вероятно не е съобразена с "
                        "цената или 402 challenge текстът не продава стойността."
                    ),
                    recommended_actions=[
                        "Сравни цената на агента с наскоро одобрените research insights "
                        "(дълбочината на данните може да оправдае по-висока цена)",
                        "Препиши 402 challenge описанието около конкретния developer pain point",
                        "Провери дали free tier не покрива целия случай на употреба",
                    ],
                    evidence={
                        "agent_id": agent["id"],
                        "clicks_24h": agent["clicks_24h"],
                        "payments_24h": agent["payments_24h"],
                        "price_usdc": agent["price_usdc"],
                    },
                )
            )
    return briefs


def _detect_discovery_gaps(context: Dict[str, Any]) -> list:
    """Agents nobody discovers — visibility gap in the catalog tail."""
    agents = context.get("agents", [])
    if len(agents) < 3:
        return []
    zero_activity = [a for a in agents if a["clicks_24h"] == 0 and a["payments_24h"] == 0]
    if len(zero_activity) >= max(2, len(agents) // 2):
        briefs = [
            StrategicBrief(
                id="discovery_gap:catalog-wide",
                category="discovery",
                priority="medium",
                title="Каталогът е широко невидим — нито един агент няма активност",
                rationale=(
                    f"{len(zero_activity)} от {len(agents)} агенти имат нулеви клика и "
                    "плащания за 24 ч — проблемът е в дистрибуцията, не в отделния SKU."
                ),
                recommended_actions=[
                    "Регистрирай каталога в x402scan / agentcash / PayAPI маркетплейси",
                    "Обнови /.well-known/x402.json и agents.json манифестите",
                    "Публикувай llms.txt анкер в developer общности (pain-point постове)",
                ],
                evidence={"agents_without_activity": [a["id"] for a in zero_activity]},
            )
        ]
        return briefs
    return [
        StrategicBrief(
            id=f"discovery_gap:{agent['id']}",
            category="discovery",
            priority="low",
            title=f"«{agent['name']}» без никаква активност — тежка дълга опашка",
            rationale=(
                f"Агентът е rank {agent['popularity_rank']} в каталога без кликове за 24 ч — "
                "продуктът е невидим за агентите, които биха го платили."
            ),
            recommended_actions=[
                "Добави агента в MCP manifest описанието с конкретен use-case",
                "Обвържи агента с подходящ research insight в бюлетината",
            ],
            evidence={
                "agent_id": agent["id"],
                "popularity_rank": agent["popularity_rank"],
            },
        )
        for agent in zero_activity[:3]
    ]


def _detect_funnel_gaps(context: Dict[str, Any]) -> list:
    """Captured leads that never convert — follow-up/checkout gap."""
    funnel = context.get("funnel", {})
    leads_total = int(funnel.get("leads_total", 0) or 0)
    paid_count = int(funnel.get("paid_count", 0) or 0)
    if leads_total == 0 or paid_count > 0:
        return []
    return [
        StrategicBrief(
            id="funnel:followup-gap",
            category="funnel",
            priority="high",
            title="Лийдове без нито една конверсия — следване/checkout пауза",
            rationale=(
                f"{leads_total} лийда в CRM с 0 платени — финалният CTA или "
                "checkout връзката не довършват цикъла."
            ),
            recommended_actions=[
                "Изпрати ръчен follow-up с директен checkout линк на топ лийдовете",
                "Провери дали Stripe checkout сесиите не връщат 503 (fail-closed)",
                "Тествай чекаут пътя до реално плащане с mock guard изключен",
            ],
            evidence={
                "leads_total": leads_total,
                "paid_count": paid_count,
                "conversion_rate": funnel.get("conversion_rate", 0.0),
            },
        )
    ]


def _detect_research_productization(context: Dict[str, Any]) -> list:
    """Approved research insights not yet productized as micro-API endpoints."""
    research = context.get("research", {})
    approved = int(research.get("approved", 0) or 0)
    if approved == 0:
        return []
    existing_ids = {a["id"] for a in context.get("agents", [])}
    return [
        StrategicBrief(
            id="research:productization",
            category="product",
            priority="medium",
            title=f"{approved} одобрени research insights чакат продуктизация",
            rationale=(
                "Одобрените insights са готова суровина за нови платени micro-API "
                "крайни точки — точно това търсят агентите, които вече идентифицирахме."
            ),
            recommended_actions=[
                "Картирай всеки APPROVED insight към нов каталожен агент с цена от съответния tier",
                "Ако insight-ът дублира съществуващ агент, обнови неговото описание с данните",
                f"Съществуващи агенти, с които да се избегне дублиране: {len(existing_ids)}",
            ],
            evidence={
                "approved_insights": approved,
                "recent_titles": research.get("recent_titles", []),
            },
        )
    ]


def _detect_revenue_concentration(context: Dict[str, Any]) -> list:
    """Revenue concentrated in one SKU while other agents also convert."""
    agents = [a for a in context.get("agents", []) if a["revenue_24h"] > 0]
    if len(agents) < 2:
        return []
    total_revenue = sum(a["revenue_24h"] for a in agents)
    top = max(agents, key=lambda a: a["revenue_24h"])
    share = top["revenue_24h"] / total_revenue if total_revenue else 0.0
    if share < MAX_REVENUE_CONCENTRATION_SHARE:
        return []
    return [
        StrategicBrief(
            id=f"risk:revenue-concentration:{top['id']}",
            category="risk",
            priority="low",
            title=f"Приходите са концентрирани в «{top['name']}» ({share:.0%})",
            rationale=(
                f"Един SKU носи {share:.0%} от 24-часовия приход — един ценови "
                "излишък може да убие целия revenue поток."
            ),
            recommended_actions=[
                "А/B тествай ценови tier на втория по приходи агент",
                "Промоцирай complementary SKU в бюлетината на top агента",
            ],
            evidence={
                "top_agent": top["id"],
                "revenue_share": round(share, 4),
                "total_revenue_24h_usd": total_revenue,
            },
        )
    ]


class StrategicSynthesizer:
    """Rule-based synthesis: context in, deduplicated prioritized briefs out."""

    RULES = (
        _detect_monetization_gaps,
        _detect_funnel_gaps,
        _detect_research_productization,
        _detect_discovery_gaps,
        _detect_revenue_concentration,
    )

    def synthesize(self, context: Dict[str, Any]) -> Dict[str, Any]:
        briefs: List[StrategicBrief] = []
        seen: set = set()
        for rule in self.RULES:
            try:
                for brief in rule(context):
                    if brief.id not in seen:
                        seen.add(brief.id)
                        briefs.append(brief)
            except Exception:  # a broken rule never breaks the endpoint
                continue

        briefs.sort(key=lambda b: _PRIORITY_ORDER.get(b.priority, 9))
        by_priority = {p: 0 for p in ("high", "medium", "low")}
        for brief in briefs:
            by_priority[brief.priority] = by_priority.get(brief.priority, 0) + 1

        return {
            "summary": {
                "total_briefs": len(briefs),
                "by_priority": by_priority,
                "top_priority": briefs[0].priority if briefs else None,
                "categories": sorted({b.category for b in briefs}),
            },
            "briefs": [b.to_dict() for b in briefs],
        }
