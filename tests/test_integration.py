import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("KRISTO_ALLOW_MOCK_PAYMENTS", "true")
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    import main
    from integrations.crm_store import CRMStore
    from integrations.stripe_checkout import StripeCheckoutService

    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    monkeypatch.setattr(main, "stripe_checkout", StripeCheckoutService())
    return main.app.test_client()


def test_health_endpoint(client, monkeypatch):
    # Simulate a healthy monitor-only wallet so the test is deterministic
    # and does not depend on live Base RPC connectivity.
    import main

    healthy_wallet_state = {
        "wallet_address": main.X402_RECEIVER_ADDRESS,
        "fee_receiver": main.X402_RECEIVER_ADDRESS,
        "usdc_balance": 0.0,
        "rpc_connected": True,
        "chain_id": 8453,
        "network": "Base Mainnet",
        "receiver_valid": True,
        "rpc_error": None,
        "last_block_checked": 0,
        "last_check_time": None,
    }
    monkeypatch.setattr(main, "_wallet_state", healthy_wallet_state)

    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["database"] == {"backend": "sqlite", "ready": True}
    assert payload["blockchain"]["network"] == "Base Mainnet"
    assert payload["blockchain"]["chain_id"] == 8453
    assert payload["blockchain"]["ready"] is True


def test_health_endpoint_returns_200_when_blockchain_rpc_is_flaky(client, monkeypatch):
    """Regression test (2026-08-24 deploy failure): platform health checks
    must not fail when the public Base RPC is rate-limited (429). The service
    itself is up — only the blockchain monitor is degraded."""
    import main

    degraded_wallet_state = {
        "wallet_address": None,
        "fee_receiver": None,
        "usdc_balance": 0.0,
        "rpc_connected": False,
        "chain_id": None,
        "network": "Base Mainnet",
        "receiver_valid": False,
        "rpc_error": "429 Too Many Requests",
        "last_block_checked": 0,
        "last_check_time": None,
    }
    monkeypatch.setattr(main, "_wallet_state", degraded_wallet_state)

    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["service"] == "up"
    assert payload["status"] == "degraded"
    assert payload["database"]["ready"] is True
    assert payload["blockchain"]["ready"] is False


def test_sentinel_module_configuration_gates():
    """The embedded Sentinel agent must stay silent unless fully configured
    (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID), and must honor SENTINEL_ENABLED=false."""
    from services import sentinel

    # Without chat id → disabled
    monkeypatch_del = pytest.MonkeyPatch()
    monkeypatch_del.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert sentinel.sentinel_enabled() is False
    monkeypatch_del.undo()

    # With both → enabled
    mp = pytest.MonkeyPatch()
    mp.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    mp.setenv("TELEGRAM_CHAT_ID", "456")
    assert sentinel.sentinel_enabled() is True

    # Explicit kill-switch wins
    mp.setenv("SENTINEL_ENABLED", "false")
    assert sentinel.sentinel_enabled() is False
    mp.undo()


def test_sentinel_health_alert_only_on_change(monkeypatch):
    """Alerts fire on transitions only; steady states must stay silent."""
    from services import sentinel

    sent: list[str] = []
    monkeypatch.setattr(sentinel, "_tg_send", lambda text: sent.append(text) or True)

    def fake_get(url, timeout=30):
        class R:
            status_code = 200
            def json(self):
                return {"status": "ok", "blockchain": {"ready": True}}
        return R()

    monkeypatch.setattr(sentinel.requests, "get", fake_get)

    state = {"health": None}
    sentinel._check_health(state)          # baseline — no alert
    assert sent == []
    sentinel._check_health(state)          # still ok — no alert
    assert sent == []

    state["health"] = "down"               # simulate previous down state
    sentinel._check_health(state)          # down -> ok transition → alert
    assert len(sent) == 1
    assert "🟢" in sent[0]


def test_sentinel_revenue_alert_on_payment(monkeypatch):
    """A balance increase must produce exactly one payment alert."""
    from services import sentinel

    sent: list[str] = []
    monkeypatch.setattr(sentinel, "_tg_send", lambda text: sent.append(text) or True)

    balances = iter(["0", "50000"])  # 0.00 → 0.05 USDC (6 decimals)
    monkeypatch.setattr(
        sentinel.requests, "post",
        lambda url, json=None, timeout=30: type("R", (), {
            "json": lambda self: {"result": hex(int(next(balances)))}
        })(),
    )

    state = {"usdc_balance": 0.0}
    sentinel._check_revenue(state)
    assert sent == []                      # baseline
    sentinel._check_revenue(state)
    assert len(sent) == 1
    assert "💰" in sent[0]
    assert state["usdc_balance"] == 0.05


def test_x402_payment_proof_completes_the_handshake(client, monkeypatch):
    """Regression test (2026-08-25): a paying client MUST gain access when
    retrying with the documented X-Payment-Proof header. Before this fix the
    server never read the header — payers stayed locked out."""
    import base64 as b64
    import json as jsonlib
    import main

    # Isolate module-level state so this test cannot pollute other tests.
    monkeypatch.setattr(main, "_sales_history", [])
    monkeypatch.setattr(main, "_verified_payments", set())
    monkeypatch.setattr(main, "_paid_calls_usage", {})
    monkeypatch.setattr(main, "_free_tier_usage", {})
    monkeypatch.setattr(main, "_daily_stats", {})

    # 1st call — free tier
    assert client.get("/api/stats").status_code == 200
    # 2nd call — paywall
    assert client.get("/api/stats").status_code == 402

    # Simulate the background monitor having recorded the on-chain payment.
    payer = "0x" + "ab" * 20
    tx = "0x" + "cd" * 32
    main._record_real_sale(token="USDC", amount_usd=0.05, tx_hash=tx, sender=payer)

    proof = b64.urlsafe_b64encode(jsonlib.dumps({
        "payer": payer, "transaction_hash": tx, "amount_usdc": 0.05,
    }).encode()).decode().rstrip("=")

    # Retry with the proof — access granted
    resp = client.get("/api/stats", headers={"X-Payment-Proof": proof})
    assert resp.status_code == 200
    assert main._paid_calls_usage.get("127.0.0.1", 0) >= 1

    # Replay: the same proof must NOT grant a second call (idempotency).
    # A presented-but-consumed credential is 401 (invalid proof), not 402.
    replay = client.get("/api/stats", headers={"X-Payment-Proof": proof})
    assert replay.status_code == 401
    assert replay.get_json()["error"] == "invalid_payment_proof"


def test_x402_payment_proof_rejects_forged_tx(client, monkeypatch):
    """A proof referencing an unverified transaction must stay locked out —
    the server may not trust client claims without on-chain evidence.
    A presented-but-invalid credential now returns 401 (broken proof),
    distinct from 402 (no proof / payment required)."""
    import base64 as b64
    import json as jsonlib
    import main

    monkeypatch.setattr(main, "_sales_history", [])
    monkeypatch.setattr(main, "_verified_payments", set())
    monkeypatch.setattr(main, "_free_tier_usage", {})
    # Deterministic offline behaviour: on-chain verification fails.
    monkeypatch.setattr(main, "_verify_payment_onchain", lambda *a, **k: None)

    assert client.get("/api/bot-status").status_code == 200   # free tier
    forged_tx = "0x" + "ef" * 32
    proof = b64.urlsafe_b64encode(jsonlib.dumps({
        "payer": "0x" + "11" * 20,
        "transaction_hash": forged_tx,
        "amount_usdc": 0.05,
    }).encode()).decode().rstrip("=")

    # Verification fails (unknown tx) -> 401 invalid proof
    resp = client.get("/api/bot-status", headers={"X-Payment-Proof": proof})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_payment_proof"
    assert "X-Payment-Proof" in resp.get_json()["hint"] or "retry" in resp.get_json()["hint"]


def test_mcp_sse_endpoint_streams_tool_definitions(client):
    """The MCP SSE endpoint lets Claude Desktop / Cursor discover our paid
    tools over the streamable-HTTP transport."""
    resp = client.get("/mcp/sse")
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"

    import json as jsonlib
    stream = resp.get_data(as_text=True)
    # SSE framing present
    assert "event: endpoint" in stream
    assert "event: message" in stream
    # JSON-RPC server info
    assert "kristo-intelligence" in stream
    assert "2024-11-05" in stream
    # Tools advertised with x402 pricing
    assert "get_market_stats" in stream
    assert "get_onchain_sales" in stream
    assert "get_bot_status" in stream
    assert '"price_usdc"' in stream


def test_mcp_info_endpoint(client):
    """Human/machine summary pointing at the SSE transport."""
    resp = client.get("/mcp")
    assert resp.status_code == 200
    b = resp.get_json()
    assert b["mcp"]["transport"] == "sse"
    assert b["mcp"]["sse_endpoint"].endswith("/mcp/sse")
    assert "Claude Desktop" in b["clients"]


def test_x402_response_documents_proof_header(client, monkeypatch):
    """The 402 response must tell bots HOW to retry (machine-readable)."""
    import main
    monkeypatch.setattr(main, "_free_tier_usage", {"127.0.0.1": 99})  # exhausted

    resp = client.get("/api/sales")             # immediately 402
    assert resp.status_code == 402
    body = resp.get_json()
    assert body["payment_proof"]["header"] == "X-Payment-Proof"
    assert "transaction_hash" in body["payment_proof"]["format"]


def test_x402_response_is_self_contained_for_llm_agents(client, monkeypatch):
    """Canonical x402_* fields: an LLM receiving ONLY the 402 body must be
    able to construct the payment and the retry request — no docs needed."""
    import main
    from config import BOUND_BASE_FEE_RECEIVER
    monkeypatch.setattr(main, "_free_tier_usage", {"127.0.0.1": 99})

    resp = client.get("/api/sales")
    assert resp.status_code == 402
    b = resp.get_json()
    assert b["x402_network"] == "base-mainnet"
    assert b["x402_chain_id"] == 8453
    assert b["x402_token"] == "USDC"
    assert b["x402_token_contract"].startswith("0x")
    assert float(b["x402_amount"]) > 0
    assert b["x402_recipient"] == BOUND_BASE_FEE_RECEIVER
    # accepts is now the canonical x402 v2 payment requirements array
    acc = b["x402_accepts"]
    assert isinstance(acc, list) and acc
    assert acc[0]["scheme"] == "exact"
    assert acc[0]["network"] == "eip155:8453"
    assert acc[0]["amount"].isdigit()
    assert "X-Payment-Proof" in b["x402_retry_instructions"]
    assert "x402_recipient" in b["x402_retry_instructions"]


def test_client_ip_resolution_via_render_proxy(client, monkeypatch):
    """Free tier must be counted per REAL client IP, not per rotating Render
    proxy IP. Two calls through different private proxies from the same
    client must share one free call."""
    import main
    monkeypatch.setattr(main, "_free_tier_usage", {})

    # Call 1 through Render proxy A — free tier for the real client
    r1 = client.get("/api/stats",
                    headers={"X-Forwarded-For": "203.0.113.7"},
                    environ_base={"REMOTE_ADDR": "10.197.24.22"})
    assert r1.status_code == 200

    # Call 2 through a DIFFERENT Render proxy IP — same real client → 402
    r2 = client.get("/api/stats",
                    headers={"X-Forwarded-For": "203.0.113.7"},
                    environ_base={"REMOTE_ADDR": "10.195.90.118"})
    assert r2.status_code == 402


def test_client_ip_resolution_rejects_spoofed_xff_prefix(client, monkeypatch):
    """A client may PREPEND fake entries to X-Forwarded-For; the server must
    resolve to the last PUBLIC entry (appended by the trusted proxy)."""
    import main
    monkeypatch.setattr(main, "_free_tier_usage", {})

    # Client spoofs "1.2.3.4" first, proxy appends real IP "198.51.100.9"
    r1 = client.get("/api/stats",
                    headers={"X-Forwarded-For": "1.2.3.4, 198.51.100.9"},
                    environ_base={"REMOTE_ADDR": "10.197.204.138"})
    assert r1.status_code == 200
    # Same spoof + same real client → still one identity → 402
    r2 = client.get("/api/stats",
                    headers={"X-Forwarded-For": "1.2.3.4, 198.51.100.9"},
                    environ_base={"REMOTE_ADDR": "10.197.204.138"})
    assert r2.status_code == 402
    # Rotating the SPOOFED prefix must not grant a new free call
    r3 = client.get("/api/stats",
                    headers={"X-Forwarded-For": "9.9.9.9, 198.51.100.9"},
                    environ_base={"REMOTE_ADDR": "10.197.204.138"})
    assert r3.status_code == 402


def test_client_ip_resolution_walks_back_past_private_hops(client, monkeypatch):
    """With multiple proxy hops the XFF chain may end with private IPs;
    resolution must walk back to the last public (client) address."""
    import main
    monkeypatch.setattr(main, "_free_tier_usage", {})

    r1 = client.get("/api/stats",
                    headers={"X-Forwarded-For": "203.0.113.5, 10.1.2.3"},
                    environ_base={"REMOTE_ADDR": "10.0.0.5"})
    assert r1.status_code == 200
    # The same client through another hop tail → same identity → 402
    r2 = client.get("/api/stats",
                    headers={"X-Forwarded-For": "203.0.113.5, 10.9.9.9"},
                    environ_base={"REMOTE_ADDR": "10.0.0.6"})
    assert r2.status_code == 402


def test_ai_plugin_json_discovery_manifest(client):
    """OpenAI ai-plugin.json — the classic plugin discovery format that
    agent scanners crawl for."""
    resp = client.get("/.well-known/ai-plugin.json")
    assert resp.status_code == 200
    b = resp.get_json()
    assert b["schema_version"] == "v1"
    assert b["name_for_model"] == "kristo_intelligence"
    assert b["api"]["type"] == "openapi"
    assert b["api"]["url"].endswith("/openapi.json")
    assert b["auth"]["type"] == "none"
    # The x402 payment block lets scanners price the service immediately.
    assert b["x402_payment"]["chain_id"] == 8453
    assert b["x402_payment"]["receiver_address"].startswith("0x")
    assert b["x402_payment"]["price_per_call_usdc"] > 0


def test_landing_page_shows_the_payment_flow(client):
    """The landing page must demo the 402 -> pay -> 200 handshake."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "402" in html
    assert "X-Payment-Proof" in html
    assert "200 OK" in html
    assert "api/stats" in html          # copy-paste curl example
    assert "No API keys" in html


def test_strict_x402_mode_first_call_requires_payment(client, monkeypatch):
    """Strict x402 semantics (KRISTO_FREE_TIER_LIMIT=0): the FIRST unpaid
    request must return the canonical 402 challenge — required by x402
    marketplaces/verifiers (PayAPI.market)."""
    import main
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})

    resp = client.get("/api/stats")
    assert resp.status_code == 402
    b = resp.get_json()
    assert b["error"] == "payment_required"
    # accepts[] must carry canonical x402 v2 payment requirements for
    # marketplace verifiers (x402scan v2 schema: CAIP-2 network + atomic units)
    for acc in (b["accepts"], b["accepts[]"], b["x402_accepts"]):
        assert isinstance(acc, list) and acc, "accepts must be a non-empty array"
        req = acc[0]
        assert req["scheme"] == "exact"
        assert req["network"] == "eip155:8453", \
            "v2 network must be CAIP-2 form (eip155:8453 = Base)"
        assert isinstance(req["amount"], str) and req["amount"].isdigit(), \
            "amount must be atomic units (0.005 USDC -> '5000')"
        assert int(req["amount"]) == int(round(float(b["x402_amount"]) * 1_000_000))
        assert req["payTo"] == b["x402_recipient"]
        assert req["asset"].startswith("0x")
        assert isinstance(req["maxTimeoutSeconds"], int)
    # v2 top-level resource + bazaar extensions make the route invocable
    assert b["resource"]["url"].startswith("http")
    assert b["extensions"]["bazaar"]["info"]["input"]["method"] in ("GET", "POST")
    # WWW-Authenticate header per 402 conventions
    assert "x402" in resp.headers.get("WWW-Authenticate", "")


def test_public_dashboard_stats_are_free_and_use_official_catalog(client):
    response = client.get("/api/dashboard-stats")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["products_summary"]["total_products"] == 8
    assert len(payload["products"]) == 8
    assert "recent_requests" not in payload
    assert all(0.001 <= product["price_usdc"] <= 0.25 for product in payload["products"])
    assert payload["total_volume_usd"] == 0.0
    assert payload["total_sales"] == 0
    assert "telegram_bot_running" in payload


def test_lead_capture_and_checkout(client):
    lead = client.post(
        "/api/leads",
        json={
            "email": "integration@example.com",
            "source": "test",
            "campaign": "integration",
        },
    )
    assert lead.status_code == 200
    assert lead.get_json()["ok"] is True

    checkout = client.post(
        "/api/checkout",
        json={"email": "integration@example.com", "plan": "pro"},
    )
    assert checkout.status_code == 200
    payload = checkout.get_json()
    assert payload["ok"] is True
    assert payload["plan"] == "Pro"
    assert payload["payment_session"]["provider"] in {"mock", "mock_fallback", "stripe"}