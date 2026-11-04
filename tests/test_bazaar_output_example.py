# -*- coding: utf-8 -*-
"""Bazaar `info.output` — every paid route declares one, and it conforms.

History, because it is the point of this file:
  * 18.10.2026 — the CDP validator reported `bazaar.info.output` missing. The
    fix added `output.example` to the three routes that had a sample, and left
    the other three with no output block at all.
  * 04.11.2026 — the Coinbase Bazaar validator at agentic.market/validate
    answered "Found on Bazaar" and listed our endpoint, yet
    api.agentic.market/v1/services still showed `description: ""`,
    `category: ""`, `enriched: false`, and /v1/services/search returned
    nothing for any spelling of our name.

Reading specs/extensions/bazaar.md from coinbase/x402 explains it. The
`info.output` object is OPTIONAL, but its `type` field is marked
"Required: Yes", and every schema example in the spec carries
`"required": ["type"]` on the output object. Three of our routes published an
output with no `type`; our copy of the schema omitted both the `type` property
and the `required` list, so our declaration validated against our own looser
schema while failing the canonical one.

The previous guard is why this survived: it checked that the SCHEMA exposed
`example`, never that `info.output` existed or carried the required `type`.
A guard aimed at the neighbouring property passes for the wrong reason.

These tests are derived from main.X402_PAID_ENDPOINTS, so a seventh paid route
cannot be added without an output declaration.
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
    # Exhaust free tier → every paid route answers 402 (the challenge body).
    main._free_tier_usage["127.0.0.1"] = 999
    yield main.app.test_client()
    main._free_tier_usage.clear()


def _info_for(client, path):
    r = client.get(path)
    assert r.status_code == 402, f"{path} did not answer 402: {r.status_code}"
    return r.get_json()["extensions"]["bazaar"]["info"]


# ── 1. the rule: every paid route declares output.type ───────────────────────

def test_every_paid_route_declares_a_conformant_bazaar_output(client):
    """bazaar.md: output.type is Required=Yes whenever info.output is present.

    This is the test that would have caught the 04.11 defect. It iterates the
    canonical endpoint set instead of naming routes, so the rule cannot be
    satisfied for six routes and quietly missed for a seventh.
    """
    import main
    assert main.X402_PAID_ENDPOINTS, "canonical paid-route set is empty"
    for path in sorted(main.X402_PAID_ENDPOINTS):
        info = _info_for(client, path)
        assert "output" in info, f"{path}: info.output missing entirely"
        out = info["output"]
        assert isinstance(out, dict), f"{path}: info.output is not an object"
        assert out.get("type") == "json", (
            f"{path}: info.output.type={out.get('type')!r} — the spec requires "
            'a content type such as "json"')
        example = out.get("example")
        assert isinstance(example, dict) and example, (
            f"{path}: info.output.example missing or empty")


def test_output_examples_cover_exactly_the_paid_routes():
    """The hand-written example map and the canonical set must not drift."""
    import main
    assert set(main._BAZAAR_OUTPUT_EXAMPLES) == set(main.X402_PAID_ENDPOINTS), (
        "examples map and X402_PAID_ENDPOINTS disagree: "
        f"only in map={sorted(set(main._BAZAAR_OUTPUT_EXAMPLES) - set(main.X402_PAID_ENDPOINTS))}, "
        f"only in set={sorted(set(main.X402_PAID_ENDPOINTS) - set(main._BAZAAR_OUTPUT_EXAMPLES))}")


# ── 2. the declaration must satisfy the schema we publish ourselves ──────────

def test_published_info_satisfies_the_published_schema(client):
    """Our schema lists output.type in `required`; our info must carry it.

    A schema that requires a field the declaration omits is worse than no
    schema: it is a written claim the code does not honour.
    """
    import main
    for path in sorted(main.X402_PAID_ENDPOINTS):
        body = client.get(path).get_json()
        bazaar = body["extensions"]["bazaar"]
        schema = bazaar["schema"]
        required = (schema.get("properties", {}).get("output", {})
                    or {}).get("required") or []
        if "type" not in required:
            continue  # nothing claimed, nothing to honour
        out = bazaar["info"].get("output") or {}
        assert out.get("type"), (
            f"{path}: schema requires output.type but info.output has no type")


# ── 3. the examples are PUBLIC — they must not widen the public surface ──────

def test_public_output_examples_do_not_leak_internal_addresses():
    """These examples ride in every unpaid 402, so they are world-readable.

    /api/sales and /api/bot-status both return wallet material to a paying
    caller. The example for a public challenge must not, and the receiver
    address is already published once as accepts[0].payTo (F-26/F-27 rule:
    do not repeat an internal address into a second public place).
    """
    import main
    blob = json.dumps(main._BAZAAR_OUTPUT_EXAMPLES).lower()
    for forbidden in ("wallet_address", "usdc_balance", "receiver_address",
                      "private_key", "0xd4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"):
        assert forbidden not in blob, f"public example leaks {forbidden!r}"


# ── 4. the spec's own limits on resource service metadata ────────────────────

def test_resource_service_metadata_respects_spec_limits(client):
    """bazaar.md validation rules, enforced so a future edit cannot breach them.

    serviceName: printable ASCII, length <= 32.
    tags: at most 5 entries, each printable ASCII, length <= 32, deduplicated.
    iconUrl: absolute http(s), length <= 2048, no userinfo, not an IP literal.
    """
    import main
    body = client.get("/api/stats").get_json()
    res = body["resource"]

    name = res["serviceName"]
    assert len(name) <= 32, f"serviceName is {len(name)} chars (max 32)"
    assert all(" " <= ch <= "~" for ch in name), "serviceName must be printable ASCII"

    tags = res["tags"]
    assert len(tags) <= 5, f"{len(tags)} tags (max 5)"
    assert len({t.lower() for t in tags}) == len(tags), "tags must be unique"
    for tag in tags:
        assert len(tag) <= 32, f"tag {tag!r} is {len(tag)} chars (max 32)"
        assert all(" " <= ch <= "~" for ch in tag), f"tag {tag!r} not printable ASCII"

    icon = res["iconUrl"]
    assert len(icon) <= 2048
    assert icon.startswith(("http://", "https://"))
    assert "@" not in icon.split("//", 1)[1].split("/", 1)[0], "iconUrl has userinfo"


# ── 5. per-route example shapes mirror the live handlers ─────────────────────

def test_whaleflow_output_example_mirrors_the_handler(client):
    example = _info_for(client, "/api/v1/whaleflow")["output"]["example"]
    for key in ("state", "whales", "threshold_usdc", "source"):
        assert key in example, key


def test_signal_output_example_mirrors_the_handler(client):
    example = _info_for(client, "/api/v1/signal")["output"]["example"]
    for key in ("generated_at", "signals"):
        assert key in example, key


def test_stats_output_example_mirrors_the_handler(client):
    example = _info_for(client, "/api/stats")["output"]["example"]
    for key in ("today", "requests_today", "top_paths"):
        assert key in example, key


def test_arb_opportunities_output_example_mirrors_the_handler(client):
    """The three routes that carried no output at all until 04.11."""
    example = _info_for(client, "/api/arb/opportunities")["output"]["example"]
    for key in ("opportunities", "count", "source"):
        assert key in example, key
    row = example["opportunities"][0]
    for key in ("pair", "buy_dex", "sell_dex", "spread_pct", "est_profit_usd"):
        assert key in row, key


def test_sales_output_example_mirrors_the_handler(client):
    example = _info_for(client, "/api/sales")["output"]["example"]
    for key in ("total_volume_usd", "total_sales", "by_token", "history", "source"):
        assert key in example, key


def test_bot_status_output_example_mirrors_the_handler(client):
    example = _info_for(client, "/api/bot-status")["output"]["example"]
    for key in ("telegram_bot_running", "last_heartbeat", "commands_processed"):
        assert key in example, key


def test_input_declaration_is_unchanged(client):
    """Regression guard: the declared input stays an explicit empty query map.

    All six paid GET routes read no request.args; an undeclared input reads as
    "may need params", which is the x402 Doctor bazaar-input finding.
    """
    for path in ("/api/v1/whaleflow", "/api/arb/opportunities", "/api/sales"):
        info = _info_for(client, path)
        assert info["input"] == {"type": "http", "method": "GET",
                                 "queryParams": {}}
