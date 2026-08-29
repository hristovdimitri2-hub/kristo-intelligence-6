"""Regression tests for the Viral & Chain-Reaction Distribution Layer.

Covers:
  * GET /api/public/activity — unauthenticated JSON/HTML/text feed,
    anonymization enforced (no emails, raw wallets or full tx hashes)
  * GET /.well-known/kristo-agent.json + /api/agent-manifest — endpoints,
    USDC pricing, payment flow, agent catalog
  * syndication hook generator (digest + strategy hooks, no PII)
"""

import pytest


@pytest.fixture()
def viral_env(monkeypatch, tmp_path):
    """Isolated app + fresh durable stores; feed data seeded via main globals."""
    monkeypatch.setenv("ADMIN_API_TOKEN", "viral-admin-token")
    monkeypatch.setenv("SESSION_SECRET", "viral-session-secret")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import main
    from integrations.catalog_store import create_catalog_store
    from integrations.crm_store import CRMStore
    from integrations.research_store import ResearchInsightStore
    from src.nexus import mount_nexus_engine

    monkeypatch.setattr(main, "catalog_store", create_catalog_store(tmp_path / "catalog.db"))
    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    monkeypatch.setattr(main, "research_store", ResearchInsightStore(tmp_path / "research.db"))

    mount_nexus_engine(main.app, force_rebuild=True)

    main._request_log.clear()
    main._sales_history.clear()
    main._sales_history.append(
        {
            "timestamp": "2026-08-29T12:00:00+00:00",
            "token": "USDC",
            "amount_usd": 0.005,
            "tx_hash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "sender": "0xSENDERWALLET0000000000000000000000000001",
            "block_number": 49_500_000,
            "status": "confirmed",
        }
    )
    main._request_log.append(
        {
            "timestamp": "2026-08-29T12:05:00+00:00",
            "endpoint": "api_stats",
            "success": True,
        }
    )

    yield main, main.app.test_client()

    main._request_log.clear()
    main._sales_history.clear()


def test_public_activity_requires_no_auth(viral_env):
    _, client = viral_env
    response = client.get("/api/public/activity")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["anonymized"] is True
    assert payload["chain"] == "base"
    assert payload["totals"]["items"] == len(payload["items"])
    kinds = {item["kind"] for item in payload["items"]}
    assert "unlock" in kinds
    assert "on_chain_unlock" in kinds


def test_public_activity_never_leaks_pii(viral_env):
    _, client = viral_env
    body = client.get("/api/public/activity").get_data(as_text=True)
    assert "0xSENDERWALLET" not in body  # sender never exposed
    assert "abcdef1234567890abcdef1234567890abcdef1234567890" not in body  # no full tx
    assert "unlocked DeFi Market Signal on Base" in body
    assert "On-chain payment verified on Base: 0.005 USDC" in body


def test_public_activity_html_and_text_formats(viral_env):
    _, client = viral_env
    html = client.get("/api/public/activity?format=html")
    assert html.status_code == 200
    assert "text/html" in html.content_type
    assert "Live Agent Activity".encode() in html.data
    assert "Anonymized proof-of-traction" in html.get_data(as_text=True)

    text = client.get("/api/public/activity?format=text")
    assert text.status_code == 200
    assert "text/plain" in text.content_type
    assert "Kristo Intelligence — agent activity on Base (x402)" in text.get_data(as_text=True)


def test_agent_manifest_exposes_pricing_and_flow(viral_env):
    _, client = viral_env
    response = client.get("/.well-known/kristo-agent.json")
    assert response.status_code == 200
    manifest = response.get_json()
    assert manifest["ok"] is True
    assert manifest["protocol"]["network"] == "base"
    assert manifest["protocol"]["chain_id"] == 8453
    assert manifest["protocol"]["asset"] == "USDC"
    assert manifest["protocol"]["receiver"].startswith("0x")
    assert manifest["free_tier"]["requests_per_client"] >= 0
    assert len(manifest["payment_flow"]) == 4

    paths = {e["path"] for e in manifest["endpoints"]}
    assert "/api/stats" in paths and "/api/sales" in paths
    stats = next(e for e in manifest["endpoints"] if e["path"] == "/api/stats")
    assert stats["price_usdc"] > 0
    assert stats["price_raw"] == str(int(round(stats["price_usdc"] * 1_000_000)))
    assert manifest["agent_catalog"]  # 8 seeded agents


def test_agent_manifest_alias_route_matches(viral_env):
    _, client = viral_env
    canonical = client.get("/.well-known/kristo-agent.json").get_json()
    alias = client.get("/api/agent-manifest").get_json()
    assert alias == canonical


def test_syndication_pack_structure_and_no_pii(viral_env):
    from src.nexus.syndication import build_syndication_pack

    _, client = viral_env
    feed = client.get("/api/public/activity").get_json()
    strategy = client.get(
        "/api/nexus/strategy", headers={"X-Admin-Token": "viral-admin-token"}
    ).get_json()

    pack = build_syndication_pack(feed, strategy)
    assert pack["anonymized"] is True
    assert pack["generated_at"]
    digest = pack["digest"]
    assert digest.startswith("Kristo Intelligence — agent activity on Base (x402)")
    assert "unlocked DeFi Market Signal on Base" in digest
    assert "0xSENDERWALLET" not in digest
    assert isinstance(pack["hooks"], list)
    assert all(isinstance(hook, str) and hook for hook in pack["hooks"])


def test_strategy_hooks_prioritize_and_format(viral_env):
    from src.nexus.syndication import format_strategy_hooks

    strategy = {
        "briefs": [
            {
                "priority": "high",
                "title": "«Demo Agent» генерира интерес, но нула реализации",
                "recommended_actions": ["Препиши 402 challenge описанието"],
            },
            {
                "priority": "low",
                "title": "Приходите са концентрирани",
                "recommended_actions": [],
            },
        ]
    }
    hooks = format_strategy_hooks(strategy, limit=2)
    assert len(hooks) == 2
    assert hooks[0].startswith("[HIGH]")
    assert "next step: Препиши 402 challenge описанието" in hooks[0]
    assert hooks[1].startswith("[LOW]")


def test_syndication_relative_times(viral_env):
    from datetime import datetime, timedelta, timezone
    from src.nexus.syndication import _relative_time

    now = datetime(2026, 8, 29, 12, 10, tzinfo=timezone.utc)
    assert _relative_time("2026-08-29T12:09:30+00:00", now=now) == "30s ago"
    assert _relative_time("2026-08-29T12:00:00+00:00", now=now) == "10m ago"
    assert _relative_time("2026-08-29T09:00:00+00:00", now=now) == "3h ago"
    assert _relative_time("2026-08-28T10:00:00+00:00", now=now) == "1d ago"
    assert _relative_time("not-a-date", now=now) == "recently"


def test_public_activity_rate_limit_scope_registered(viral_env):
    import main

    assert "public_activity" in main._RATE_LIMIT_DEFAULTS
    max_requests, window = main._RATE_LIMIT_DEFAULTS["public_activity"]
    assert max_requests > 0 and window > 0
