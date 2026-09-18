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


def test_glama_server_ownership_file_is_served_verbatim(client):
    """Glama's SERVER schema requires exactly ONE key — `maintainers`, the GitHub
    usernames allowed to maintain the server. The connector Glama holds for us is
    `io.github.hristovdimitri2-hub/kristo-intelligence`, so this file is what
    proves the GitHub account may claim it. `/glama.json` serves it verbatim from
    the repo — one source of truth (the file their repo probe reads too).
    """
    _test_client, main = client
    with open(REPO_ROOT + "/glama.json", encoding="utf-8") as handle:
        doc = json.load(handle)

    assert doc["$schema"] == "https://glama.ai/mcp/schemas/server.json"
    assert "hristovdimitri2-hub" in doc["maintainers"], \
        "the repo owner must be in maintainers or the claim cannot be verified"

    served = main.app.test_client().get("/glama.json")
    assert served.status_code == 200, "/glama.json -> %s" % served.status_code
    assert served.get_json() == doc, "/glama.json differs from the file"


def test_glama_connector_claim_is_live_at_the_well_known_path(client):
    """Glama's CONNECTOR http challenge (their claim window, step 2) must be
    served at `/.well-known/glama.json` — the exact URL that window points at —
    carrying the EXACT document it shows. It is pure ownership proof: static, so
    no wallet address, price or endpoint can ever leak through this route.
    """
    _test_client, main = client
    path = REPO_ROOT + "/glama-connector-claim.json"
    with open(path, "rb") as handle:
        raw = handle.read()
    doc = json.loads(raw)

    assert doc == {
        "$schema": "https://glama.ai/mcp/schemas/connector.json",
        "claim": "glama_claim_e-w2Yrd4h6-G4ECF-YRdZ291LHRQ7kpH",
    }, "the claim document must match Glama's window exactly"

    served = main.app.test_client().get("/.well-known/glama.json")
    assert served.status_code == 200, \
        "/.well-known/glama.json -> %s" % served.status_code
    assert served.mimetype == "application/json"
    assert served.get_data() == raw, "the claim must be served verbatim"

    text = raw.decode("utf-8").lower()
    for banned in ("0xd4cda900839c0fed4374ee37ea0db8e4c6fd08f", "payto", "price",
                   "usdc", "onrender"):
        assert banned not in text, "the claim file leaks %r" % banned
def test_the_whale_threshold_is_5m_on_every_public_surface(client):
    """18.09: the owner raised the whale threshold to $5M (at $50k the network-wide
    scan produced ~227k events/day — noise, not whales). Every surface the world
    can read must state the new number and no $50k remnant may survive, which is
    the same class of guard as the price sweep — checked on the SERVED bytes, not
    on the source, so historical comments cannot mask a stale advertisement.
    """
    from integrations import dashboard_store as ds

    assert ds.WHALE_THRESHOLD_DEFAULT == 5_000_000.0
    assert ds.WHALE_RETENTION_DAYS_DEFAULT == 30

    _test_client, main = client
    c = main.app.test_client()
    checked = descriptive = 0
    for path in ("/llms.txt", "/openapi.json", "/.well-known/x402.json",
                 "/.well-known/x402", "/api/mcp/manifest"):
        body = c.get(path).get_data(as_text=True)
        assert "$50k" not in body, "%s still advertises the old $50k threshold" % path
        if "whaleflow" not in body.lower():
            continue
        checked += 1
        if "USDC transfers" in body:          # surfaces that DESCRIBE the route
            descriptive += 1
            assert "$5M" in body, "%s does not state the $5M threshold" % path
    assert checked >= 4, "expected the whale route on at least four surfaces"
    assert descriptive >= 3, "the route description must state the threshold"

    # The paid challenge itself must describe the product the same way.
    challenge = c.get("/api/v1/whaleflow")
    assert challenge.status_code == 402
    text = challenge.get_data(as_text=True)
    assert "$50k" not in text
    assert "$5M" in text, "the 402 challenge does not state the new threshold"

    readme = open(REPO_ROOT + "/README.md", encoding="utf-8").read()
    assert "$50k" not in readme
    assert "≥ $5M" in readme

    # The x402 security blurb must never state ONE flat amount again: the routes
    # cost different prices (0.003 / 0.005) and "send 0.005 USDC" made a buyer
    # overpay on the cheap ones. It now points at the route's own 402 challenge.
    spec = c.get("/openapi.json").get_json()
    blurb = spec["components"]["securitySchemes"]["x402"]["description"]
    assert "402 challenge" in blurb
    assert "send 0.005 USDC" not in blurb
    assert "$%.3f" % min(float(p) for p in
                         __import__("main").X402_PRICE_MAP.values()) in blurb
def test_the_registry_generator_takes_a_version_and_refuses_ranges(client):
    """Publishing the NEXT version must not require a code edit (`--version 6.0.1`),
    and a typo must be caught HERE rather than by `mcp-publisher publish` — the
    registry rejects version ranges outright ("^1.2.3", "~1.2.3", ">=1.2.3", "1.x").
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_registry_server_json",
        os.path.join(REPO_ROOT, "scripts", "build_registry_server_json.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.build()["version"] == module.VERSION == "6.0.0"
    bumped = module.build("6.0.1")
    assert bumped["version"] == "6.0.1"
    assert module.validate(bumped) == [], module.validate(bumped)
    # the bump changes ONLY the version — prices, remotes and tools are the same
    assert {k: v for k, v in bumped.items() if k != "version"} == \
        {k: v for k, v in module.build().items() if k != "version"}

    for bad in ("^6.0.0", "~6.0.0", ">=6.0.0", "6.x", "6.0", ""):
        problems = module.validate(dict(bumped, version=bad))
        assert any("version" in p for p in problems), (bad, problems)


# ── VIP flow: the button a REAL buyer taps (18.09) ──────────────────────────

def test_the_vip_payment_payload_has_no_fabricated_link():
    """The owner, testing as a buyer, tapped "VIP анализ 0.10 USDC" and hit
    DNS_PROBE_FINISHED_NXDOMAIN: the payload carried
    `https://wallet.pay/base/<USDC>/transfer?address=…&uint256=…` — an EIP-681
    URI body with an invented HTTPS host glued on. No such product exists, and no
    HTTPS wallet-transfer URL exists either. The link is gone; what a buyer needs
    is the amount, the address, and a way to VERIFY the address — and the
    instructions must not promise what the code does not do.
    """
    import services.telegram_sales as telegram_sales

    payment = telegram_sales.generate_payment_link()
    assert "deep_link" not in payment, "the fabricated deep link came back"
    assert "wallet.pay" not in repr(payment)
    assert payment["explorer_link"] == (
        "https://basescan.org/address/" + payment["receiver_address"])

    instructions = payment["instructions"]
    assert "on-chain монитор" in instructions      # what actually detects it
    assert "tx хеша" in instructions               # the claim path, now real
    assert "x402 автоматично" not in instructions  # x402 never watched this
    assert "натиснете бутона отново" not in instructions   # tapping again only
    #                                                        re-sent this text


def test_the_vip_button_reply_has_no_dead_link(monkeypatch):
    """The exact message behind the button: no dead host, a link that exists."""
    import services.telegram_sales as telegram_sales

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    sent = {}

    def _capture(token, chat_id, text, **kwargs):
        sent["chat_id"], sent["text"] = str(chat_id), text
        return {"ok": True}

    monkeypatch.setattr(telegram_sales, "_send_text", _capture)
    telegram_sales.handle_callback_query("unlock_vip_analysis", "123", 7)

    assert "wallet.pay" not in sent["text"]
    assert "basescan.org/address/" in sent["text"]
    assert "Инструкции за плащане" in sent["text"]
    # Every link in the message must be one we can stand behind.
    for url in re.findall(r"https?://[^\s`)]+", sent["text"]):
        assert url.startswith("https://basescan.org/"), url



def test_a_buyer_can_claim_with_a_tx_hash(client, monkeypatch):
    """Step 4 of the instructions is now real. Before this, a pasted tx hash got
    "Не разпознах командата" — a dead end for someone who had just sent money.
    The hash is checked against the durable sales record and a human is told; the
    code is NOT auto-issued, because a tx hash is public and the first claimer
    could be a stranger."""
    from datetime import datetime, timezone

    import services.telegram_sales as telegram_sales

    _test_client, main = client
    tx = "0x" + "ab" * 32
    assert main.dashboard_db.record_sale(
        tx_hash=tx, amount_usdc=0.10, sender="0x" + "cd" * 20, block_number=123,
        ts=datetime.now(timezone.utc), source="live")

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@somechannel")
    monkeypatch.delenv("TELEGRAM_VIP_CHAT_ID", raising=False)
    sends = []
    monkeypatch.setattr(
        telegram_sales, "_send_text",
        lambda token, chat_id, text, **kw: sends.append((str(chat_id), text))
        or {"ok": True})

    result = telegram_sales.process_webhook_update(
        {"message": {"chat": {"id": 555}, "text": "Платих: " + tx}})
    assert result["type"] == "vip_claim" and result["found"] is True

    buyer = [text for chat, text in sends if chat == "555"][0]
    assert "Заявка за VIP покана" in buyer and "0.10" in buyer
    owner = [text for chat, text in sends if chat == "@somechannel"][0]
    assert tx in owner and "Заявка" in owner


def test_a_random_message_is_still_not_a_claim(client, monkeypatch):
    """Only a real tx hash triggers the claim path — everything else keeps the
    ordinary "unknown command" reply (no accidental VIP for chit-chat)."""
    import services.telegram_sales as telegram_sales

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    sends = []
    monkeypatch.setattr(
        telegram_sales, "_send_text",
        lambda token, chat_id, text, **kw: sends.append(text) or {"ok": True})

    result = telegram_sales.process_webhook_update(
        {"message": {"chat": {"id": 555}, "text": "здравейте"}})
    assert result["type"] == "unknown_command"
    assert "Не разпознах командата" in sends[-1]



def test_the_vip_invite_code_is_never_posted_to_a_public_chat(monkeypatch):
    """OUR channel @Kristointeligent is public and TELEGRAM_VIP_CHAT_ID is unset,
    so the invite code — the product itself — was posted to the world along with
    the payer's wallet. The code may only travel to an explicitly configured VIP
    chat; the channel gets a redacted receipt."""
    import requests

    import main

    posted = []

    class _Resp:
        status_code = 200

    def _fake_post(url, json=None, timeout=None, **kwargs):
        posted.append(json)
        return _Resp()

    monkeypatch.setattr(requests, "post", _fake_post)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@Kristointeligent")
    monkeypatch.delenv("TELEGRAM_VIP_CHAT_ID", raising=False)

    wallet = "0x" + "ab" * 20
    main._send_telegram_vip_notification(wallet, "KRI-VIP-DEADBEEF",
                                         "0x" + "cd" * 32)
    assert posted, "the owner still needs to hear about a payment"
    public = posted[-1]
    assert public["chat_id"] == "@Kristointeligent"
    assert "KRI-VIP-DEADBEEF" not in public["text"]
    assert wallet not in public["text"]          # only a truncated form

    monkeypatch.setenv("TELEGRAM_VIP_CHAT_ID", "987654")
    main._send_telegram_vip_notification(wallet, "KRI-VIP-DEADBEEF",
                                         "0x" + "cd" * 32)
    private = posted[-1]
    assert private["chat_id"] == "987654"
    assert "KRI-VIP-DEADBEEF" in private["text"]
