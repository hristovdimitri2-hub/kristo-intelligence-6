"""THE PHANTOM-PRICE SWEEP — the regression guard for the whole family.

Every price a machine or a human can read must equal X402_PRICE_MAP. This test
exists because the same phantom ($0.05 / $0.10 / "1 free call") has been found
and fixed FOUR separate times in FOUR different places — the storefront, the
API docs, the marketing kit and the landing page — and fixing it by hand each
time is how it kept coming back. Now it is checked mechanically:

  * every publicly SERVED text (landing, llms.txt, openapi, both discovery docs,
    quickstart, dashboard) is fetched through the real app;
  * every money-like number in them must be a price from X402_PRICE_MAP;
  * the six paid routes must each appear with their EXACT price;
  * the live 402 challenge of each route must carry the same atomic amount;
  * a banned list (the old flat prices, the free-tier promise) must not appear;
  * the Telegram VIP button must quote config.KRISTO_VIP_ANALYSIS_PRICE.

Deliberately NOT checked: historical notes that quote the old numbers while
explaining the bug (audit documents, commit messages, code comments). The guard
is about what we SERVE, not about what we remember.
"""
from __future__ import annotations

import json
import os
import re

import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Production semantics: NO free tier. A public text promising a free call is
    # a phantom claim, and this fixture is what makes that checkable.
    monkeypatch.setenv("KRISTO_FREE_TIER_LIMIT", "0")
    import main
    from integrations.dashboard_store import DashboardStore

    # FREE_TIER_LIMIT is evaluated at IMPORT time, so setting the env var is not
    # enough when another test already imported main: patch the value itself, or
    # this test would judge the served texts against a different world than
    # production (which runs with 0).
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0,
                        raising=False)
    monkeypatch.setattr(main, "dashboard_db",
                        DashboardStore(tmp_path / "dashboard_state.db"))
    return main.app.test_client(), main


SERVED_TEXTS = [
    "/",
    "/llms.txt",
    "/openapi.json",
    "/.well-known/x402",
    "/.well-known/x402.json",
    "/api/v1/quickstart",
    "/api/dashboard/data",
]

#: Prices that used to live on our public surfaces and must never come back.
BANNED = [
    (r"\$0\.05", "the old flat $0.05"),
    (r"\$0\.10", "the old flat $0.10"),
    (r"0\.05\s*USDC", "0.05 USDC literal"),
    (r"0\.10\s*USDC", "0.10 USDC literal"),
    (r"\$0\.01\b|0\.01\s*USDC", "the phantom volume 'discount' price"),
    (r"1 free call", "the free-tier promise (production gives none)"),
    (r"first call is free", "the free-tier promise (production gives none)"),
    (r"free call per client", "the free-tier promise (production gives none)"),
]


def _fetched(client):
    out = {}
    for path in SERVED_TEXTS:
        response = client.get(path)
        assert response.status_code == 200, "%s -> %s" % (path,
                                                          response.status_code)
        out[path] = response.get_data(as_text=True)
    return out


def test_no_served_text_quotes_a_price_outside_the_price_map(client):
    """Every money-like number on a public surface must be a real route price."""
    _test_client, main = client
    allowed = {round(float(p), 6) for p in main.X402_PRICE_MAP.values()}
    allowed |= {round(float(p), 6) for p in
                (r["price_usdc"] for r in main.REAL_X402_ROUTES)}
    offenders = []
    for path, body in _fetched(_test_client).items():
        for match in re.finditer(r"\$\s?(0\.\d{2,6})|(0\.\d{2,6})\s*USDC",
                                 body):
            value = float(match.group(1) or match.group(2))
            if round(value, 6) not in allowed:
                snippet = body[max(0, match.start() - 70):match.end() + 40]
                offenders.append((path, value, snippet.replace("\n", " ")[:130]))
    assert not offenders, (
        "a served text quotes a price that is not in X402_PRICE_MAP:\n"
        + "\n".join("  %s: $%s in …%s…" % o for o in offenders))


def test_no_served_text_revives_a_banned_phantom_string(client):
    """The exact old strings, banned outright."""
    _test_client, _main = client
    offenders = []
    for path, body in _fetched(_test_client).items():
        for pattern, label in BANNED:
            for match in re.finditer(pattern, body, re.I):
                snippet = body[max(0, match.start() - 60):match.end() + 60]
                offenders.append((path, label, snippet.replace("\n", " ")[:120]))
    assert not offenders, "banned phantom text is being served:\n" + "\n".join(
        "  %s: %s in …%s…" % o for o in offenders)


def test_every_paid_route_appears_with_its_exact_price(client):
    """All six routes, each with its own price — in the docs that list prices."""
    _test_client, main = client
    expected = {r["endpoint"]: round(float(r["price_usdc"]), 6)
                for r in main.REAL_X402_ROUTES}
    assert len(expected) == 6, "the live set is six routes"

    served = _fetched(_test_client)
    llms = served["/llms.txt"]
    for endpoint, price in expected.items():
        assert endpoint in llms, "llms.txt does not list %s" % endpoint
        line = [line for line in llms.splitlines() if endpoint in line][0]
        assert "$%.3f" % price in line, \
            "llms.txt lists %s without its price: %s" % (endpoint, line)

    discovery = json.loads(served["/.well-known/x402.json"])
    by_endpoint = {a["endpoint"]: round(float(a["price_usdc"]), 6)
                   for a in discovery.get("agents", [])}
    assert by_endpoint == expected

    landing = served["/"]
    for endpoint, price in expected.items():
        assert endpoint in landing, "landing page omits %s" % endpoint
    for price in sorted(set(expected.values())):
        assert "$%.3f" % price in landing, \
            "landing page never shows the real price $%.3f" % price

    spec = json.loads(served["/openapi.json"])
    for endpoint, price in expected.items():
        op = ((spec.get("paths") or {}).get(endpoint) or {}).get("get") or {}
        info = op.get("x-payment-info") or {}
        assert ((info.get("price") or {}).get("amount") == "%.3f" % price), \
            "%s: openapi price differs" % endpoint
        assert info.get("protocols") == [{"x402": {}}], \
            "%s: x402scan needs protocols == [{'x402': {}}]" % endpoint


def test_the_live_402_challenge_matches_the_price_map(client):
    """The challenge IS the price a paying agent sees — atomic units included."""
    _test_client, main = client
    for route in main.REAL_X402_ROUTES:
        endpoint = route["endpoint"]
        price = round(float(main.X402_PRICE_MAP[endpoint]), 6)
        response = _test_client.get(endpoint)
        assert response.status_code == 402, endpoint
        accepts = response.get_json()["accepts"]
        assert len(accepts) == 1
        assert int(accepts[0]["amount"]) == round(price * 1_000_000), \
            "%s: the 402 asks %s but the map says %s" % (
                endpoint, accepts[0]["amount"], price)
        assert accepts[0]["payTo"].lower() == main.X402_RECEIVER_ADDRESS.lower()


def test_the_telegram_vip_button_quotes_the_config_price(client):
    """The bot's own product price comes from config, not from a literal."""
    _test_client, main = client
    from config import KRISTO_VIP_ANALYSIS_PRICE
    from services import telegram_sales

    assert telegram_sales.VIP_PRICE_USDC == KRISTO_VIP_ANALYSIS_PRICE
    keyboard = telegram_sales._build_vip_inline_keyboard()
    labels = [b["text"] for row in keyboard["inline_keyboard"] for b in row]
    amounts = [float(m) for label in labels
               for m in re.findall(r"0\.\d{2}", label)]
    for amount in amounts:
        assert amount == round(KRISTO_VIP_ANALYSIS_PRICE, 2), \
            "a VIP button quotes %s while config says %s" % (
                amount, KRISTO_VIP_ANALYSIS_PRICE)
    payment = telegram_sales.generate_payment_link()
    assert round(float(payment["amount_usdc"]), 6) == \
        round(KRISTO_VIP_ANALYSIS_PRICE, 6)


# ── The files we hand to REGISTRIES: same guard, no second price source ─────

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLISHER_KEY = "io.modelcontextprotocol.registry/publisher-provided"
LIVE_BASE = "https://kristo-intelligence-api.onrender.com"


def test_the_registry_server_json_is_generated_from_the_price_map(client):
    """`server.json` goes to the OFFICIAL MCP Registry, where it replaces an entry
    (published 05.08) that still advertises the legacy product: a Vercel endpoint
    answering 405 to `initialize`, 15 tools and $0.10/call. That drift happened
    because the numbers were typed by hand — so this test pins every one of them
    to X402_PRICE_MAP, and pins the schema's own limits too (a 320-character
    description looks fine and would be REJECTED: `description` maxLength is 100).
    """
    _test_client, main = client
    with open(REPO_ROOT + "/server.json", encoding="utf-8") as handle:
        raw = handle.read()
    doc = json.loads(raw)

    # the schema's required fields, in the authenticated GitHub namespace
    assert doc["name"] == "io.github.hristovdimitri2-hub/kristo-intelligence"
    assert re.fullmatch(r"\d+\.\d+\.\d+", doc["version"]), "semver, never a range"
    assert 1 <= len(doc["description"]) <= 100
    assert 1 <= len(doc["title"]) <= 100
    assert len(doc["name"]) <= 200

    # the remote must point at OUR live MCP endpoint
    remotes = {r["type"]: r["url"] for r in doc["remotes"]}
    assert remotes["streamable-http"] == LIVE_BASE + "/mcp"
    assert remotes["sse"] == LIVE_BASE + "/mcp/sse"
    assert "vercel" not in raw.lower(), "the dead legacy endpoint must not return"

    # EVERY price comes from the map
    meta = doc["_meta"][PUBLISHER_KEY]
    published = {row["endpoint"]: round(float(row["price_usd"]), 6)
                 for row in meta["paid_endpoints"]}
    expected = {endpoint: round(float(price), 6)
                for endpoint, price in main.X402_PRICE_MAP.items()}
    assert published == expected, "server.json prices drifted from X402_PRICE_MAP"
    assert meta["pricing"]["min_usd"] == min(expected.values())
    assert meta["pricing"]["max_usd"] == max(expected.values())

    # the tools it advertises are the tools we SERVE, at their route's price
    from app.blueprints.discovery import _mcp_tools
    served = {tool["name"]: "/" + (tool["x402"]["endpoint"]
                                   .split(LIVE_BASE, 1)[-1].lstrip("/"))
              for tool in _mcp_tools(LIVE_BASE)}
    listed = {row["name"]: row["endpoint"] for row in meta["tools"]}
    assert listed == served, "server.json tools differ from the served /mcp tools"
    for row in meta["tools"]:
        assert round(float(row["price_usd"]), 6) == expected[row["endpoint"]], \
            "%s: tool price is not the route price" % row["name"]


def test_glama_json_is_the_documented_ownership_file(client):
    """Glama's own schema requires exactly ONE key — `maintainers`, the GitHub
    usernames allowed to maintain the server. The connector Glama holds for us is
    `io.github.hristovdimitri2-hub/kristo-intelligence`, currently Unhealthy with
    an EMPTY health-check URL and the legacy repo, so this file is what proves the
    GitHub account may claim it. It is served verbatim from both paths a probe may
    look at, and the file stays the single source of truth.
    """
    _test_client, main = client
    with open(REPO_ROOT + "/glama.json", encoding="utf-8") as handle:
        doc = json.load(handle)

    assert doc["$schema"] == "https://glama.ai/mcp/schemas/server.json"
    assert "hristovdimitri2-hub" in doc["maintainers"], \
        "the repo owner must be in maintainers or the claim cannot be verified"

    for path in ("/glama.json", "/.well-known/glama.json"):
        served = main.app.test_client().get(path)
        assert served.status_code == 200, "%s -> %s" % (path, served.status_code)
        assert served.get_json() == doc, "%s differs from the file" % path