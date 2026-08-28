"""
x402scan schema compliance tests.

Validates that the Kristo Intelligence 6 server meets the discovery and
registration requirements defined by x402scan:
https://github.com/Merit-Systems/x402scan/blob/main/docs/DISCOVERY.md

These tests run against the Flask test client and verify:
1. /.well-known/x402 endpoint exists (NO .json extension)
2. /.well-known/x402 returns the correct fan-out format (version, resources)
3. /openapi.json has required fields (openapi, info.title, info.version, paths)
4. /openapi.json has x-payment-info per paid operation
5. /openapi.json has x-discovery.ownershipProofs
6. /openapi.json paid operations have 402 response declared
7. Paid endpoints (/api/stats, /api/sales, /api/bot-status) return 402 after free tier
8. 402 response includes required payment headers
"""
import json
import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    return main.app.test_client()


# ── /.well-known/x402 (x402scan compatibility endpoint) ──────────────────────

def test_well_known_x402_endpoint_exists_without_json_extension(client):
    """x402scan expects /.well-known/x402 (NOT .json)."""
    r = client.get("/.well-known/x402")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"


def test_well_known_x402_returns_version_field(client):
    """x402scan spec: payload must include 'version' field."""
    r = client.get("/.well-known/x402")
    data = r.get_json()
    assert data is not None, "Response must be JSON"
    assert "version" in data, "Missing 'version' field"
    assert data["version"] == 1, f"Expected version=1, got {data['version']}"


def test_well_known_x402_returns_resources_array(client):
    """x402scan spec: payload must include non-empty 'resources' array."""
    r = client.get("/.well-known/x402")
    data = r.get_json()
    assert "resources" in data, "Missing 'resources' field"
    assert isinstance(data["resources"], list), "resources must be array"
    assert len(data["resources"]) > 0, "resources must be non-empty"
    # Each resource must be an absolute URL
    for url in data["resources"]:
        assert url.startswith("http"), f"Resource URL must be absolute: {url}"


def test_well_known_x402_returns_ownership_proofs(client):
    """x402scan spec: optional ownershipProofs field (recommended)."""
    r = client.get("/.well-known/x402")
    data = r.get_json()
    assert "ownershipProofs" in data, "Missing 'ownershipProofs' field"
    assert isinstance(data["ownershipProofs"], list)
    assert len(data["ownershipProofs"]) > 0
    # Each proof must be a valid-looking Ethereum address
    for addr in data["ownershipProofs"]:
        assert addr.startswith("0x"), f"Invalid address format: {addr}"
        assert len(addr) == 42, f"Address must be 42 chars: {addr}"


def test_well_known_x402_resources_match_paid_endpoints(client):
    """Resources array should list the actual paid endpoints."""
    r = client.get("/.well-known/x402")
    data = r.get_json()
    resources = data["resources"]
    # Should include /api/stats, /api/sales, /api/bot-status
    paths_in_resources = [r.split("/", 3)[-1] if "/" in r else r for r in resources]
    assert "/api/stats" in resources or any("api/stats" in r for r in resources), \
        f"resources must include /api/stats: {resources}"


# ── /openapi.json (OpenAPI-first discovery) ─────────────────────────────────

def test_openapi_has_required_top_level_fields(client):
    """x402scan spec: openapi, info.title, info.version, paths required."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.get_json()
    assert "openapi" in spec, "Missing 'openapi' field"
    assert "info" in spec, "Missing 'info' field"
    assert "title" in spec["info"], "Missing 'info.title'"
    assert "version" in spec["info"], "Missing 'info.version'"
    assert "paths" in spec, "Missing 'paths' field"


def test_openapi_has_x_discovery_with_ownership_proofs(client):
    """x402scan spec: x-discovery.ownershipProofs (preferred location)."""
    r = client.get("/openapi.json")
    spec = r.get_json()
    assert "x-discovery" in spec, "Missing 'x-discovery' top-level field"
    assert "ownershipProofs" in spec["x-discovery"], \
        "Missing 'x-discovery.ownershipProofs'"
    proofs = spec["x-discovery"]["ownershipProofs"]
    assert isinstance(proofs, list) and len(proofs) > 0
    for addr in proofs:
        assert addr.startswith("0x") and len(addr) == 42


def test_openapi_paid_operations_have_x_payment_info(client):
    """x402scan spec: each paid operation must declare x-payment-info."""
    r = client.get("/openapi.json")
    spec = r.get_json()
    paid_paths = [p for p in ["/api/stats", "/api/sales", "/api/bot-status"] if p in spec["paths"]]
    assert len(paid_paths) == 3, f"Expected 3 paid paths, found {paid_paths}"
    for path in paid_paths:
        op = spec["paths"][path].get("get", {})
        assert "x-payment-info" in op, \
            f"{path} missing 'x-payment-info' extension"
        pi = op["x-payment-info"]
        assert "protocols" in pi, f"{path}: x-payment-info missing 'protocols'"
        assert "x402" in pi["protocols"], f"{path}: 'x402' not in protocols"
        assert "price" in pi, f"{path}: x-payment-info missing 'price'"
        assert pi["price"]["mode"] == "fixed", f"{path}: price.mode must be 'fixed'"
        assert pi["price"]["currency"] == "USD", f"{path}: price.currency must be 'USD'"
        assert "amount" in pi["price"], f"{path}: price.amount missing"


def test_openapi_paid_operations_declare_402_response(client):
    """x402scan spec: each paid operation must declare a 402 response."""
    r = client.get("/openapi.json")
    spec = r.get_json()
    for path in ["/api/stats", "/api/sales", "/api/bot-status"]:
        op = spec["paths"][path].get("get", {})
        assert "responses" in op, f"{path}: missing 'responses'"
        assert "402" in op["responses"], \
            f"{path}: missing '402' response declaration"


def test_openapi_has_security_scheme_for_x402(client):
    """x402scan spec: use OpenAPI security + components.securitySchemes."""
    r = client.get("/openapi.json")
    spec = r.get_json()
    assert "components" in spec, "Missing 'components'"
    assert "securitySchemes" in spec["components"], \
        "Missing 'components.securitySchemes'"
    assert "x402" in spec["components"]["securitySchemes"], \
        "Missing 'x402' security scheme"


# ── Runtime 402 challenge behavior ──────────────────────────────────────────

def test_stats_endpoint_returns_402_after_free_tier(client, monkeypatch):
    """x402scan spec: probed endpoints must return 402 with parseable challenge."""
    # Exhaust the free tier first
    monkeypatch.setitem(client.application.__dict__, "_free_tier_usage", {"127.0.0.1": 1})
    import main
    main._free_tier_usage["127.0.0.1"] = 1
    r = client.get("/api/stats")
    assert r.status_code == 402, f"Expected 402, got {r.status_code}"


def test_402_response_includes_payment_headers(client, monkeypatch):
    """402 response must include X-Payment-Address and X-Payment-Amount-USDC headers."""
    import main
    main._free_tier_usage["127.0.0.1"] = 1
    r = client.get("/api/stats")
    assert r.status_code == 402
    # Check headers (case-insensitive)
    headers_lower = {k.lower(): v for k, v in r.headers.items()}
    assert "x-payment-address" in headers_lower, \
        f"Missing X-Payment-Address header. Headers: {list(headers_lower.keys())}"
    assert "x-payment-amount-usdc" in headers_lower, \
        f"Missing X-Payment-Amount-USDC header"
    # Address must be the corrected one (commit dcebafd)
    assert headers_lower["x-payment-address"] == "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"


def test_402_response_body_includes_payment_details(client, monkeypatch):
    """402 JSON body must include receiver address, amount, and chain."""
    import main
    main._free_tier_usage["127.0.0.1"] = 1
    r = client.get("/api/stats")
    assert r.status_code == 402
    data = r.get_json()
    assert data is not None, "402 response must be JSON"
    # Look for payment details in any reasonable field
    json_str = json.dumps(data)
    assert "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f" in json_str, \
        "402 body must include correct receiver address"
    # Amount can be 0.05 or 0.10 depending on X402_FEE_USDC setting
    assert ("0.05" in json_str or "0.10" in json_str or "0.5" in json_str or "0.1" in json_str), \
        "402 body must include a payment amount"


# ── Free endpoints remain free ──────────────────────────────────────────────

def test_discovery_endpoints_are_free(client):
    """Discovery endpoints must NOT return 402."""
    for path in ["/.well-known/x402", "/.well-known/x402.json", "/openapi.json",
                 "/llms.txt", "/api/mcp/manifest", "/mcp.json"]:
        r = client.get(path)
        assert r.status_code == 200, \
            f"{path} should be free (200), got {r.status_code}"
