# -*- coding: utf-8 -*-
"""vet402's L2 declaration: our 402 must carry the output keys vet402 reads.

vet402's L2 reader (src/lib/observatory/l2-check.ts, function ``catalogOutputOf``)
reads the declaration from the CDP Bazaar row as:

    declaredSchema.properties.output.properties.example

and then takes ``.required`` and ``.properties`` from THAT object. It never reads
``output.required``. With neither, the endpoint reports ``l2_undeclared`` — "the
listing declares no output schema" — and the buyer-facing page keeps it on a
WARN.

Measured on 11.11.2026: our own Bazaar row carried
``output.properties.example = {"type": "object", "description": "Paid JSON
response payload"}`` — no ``required``, no ``properties`` — so the declaration
read as empty and vet402 answered ``l2_undeclared`` for all seven paid routes.

This test pins the reading order, so the next change to the schema cannot
silently reintroduce the empty declaration. It is the same port used by
``_forensics/what_l2_undeclared_wants.py``.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _catalog_output_of(declared_schema):
    """Port of vet402's catalogOutputOf, exactly as it reads the declaration."""
    if not isinstance(declared_schema, dict):
        return {"requiredKeys": [], "exampleProps": None}
    props = declared_schema.get("properties")
    if not isinstance(props, dict):
        return {"requiredKeys": [], "exampleProps": None}
    output = props.get("output")
    if not isinstance(output, dict):
        return {"requiredKeys": [], "exampleProps": None}
    output_props = output.get("properties")
    if not isinstance(output_props, dict):
        return {"requiredKeys": [], "exampleProps": None}
    example = output_props.get("example")
    if not isinstance(example, dict):
        return {"requiredKeys": [], "exampleProps": None}
    example_props = example.get("properties")
    if not isinstance(example_props, dict):
        example_props = None
    required = example.get("required")
    required_keys = [k for k in required if isinstance(k, str)] if isinstance(required, list) else []
    return {"requiredKeys": required_keys, "exampleProps": example_props}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    return main.app.test_client()


def _challenge_for(client, path):
    import main
    main._free_tier_usage["127.0.0.1"] = 999
    r = client.get(path)
    assert r.status_code == 402, f"{path} answered {r.status_code}, expected 402"
    return r.get_json()


def test_every_paid_route_declares_output_keys_vet402_can_read(client):
    """The declaration must not read as empty: that is what l2_undeclared means."""
    import main

    problems = []
    for path in main.X402_PAID_ENDPOINTS:
        body = _challenge_for(client, path)
        schema = ((body.get("extensions") or {}).get("bazaar") or {}).get("schema")
        out = _catalog_output_of(schema)
        if not out["requiredKeys"] and not out["exampleProps"]:
            problems.append(f"{path}: declaration reads as empty")
    assert not problems, "vet402 would report l2_undeclared for: " + "; ".join(problems)


def test_declared_properties_match_the_public_example(client):
    """The declared keys must be the keys the buyer is actually shown.

    A declaration that names keys the example does not have is a lie in the
    other direction; the derived map keeps the two in step by construction.
    """
    import main

    for path in main.X402_PAID_ENDPOINTS:
        body = _challenge_for(client, path)
        bazaar = (body.get("extensions") or {}).get("bazaar") or {}
        example = (((bazaar.get("info") or {}).get("output") or {}).get("example")) or {}
        declared = _catalog_output_of(bazaar.get("schema"))["exampleProps"] or {}
        assert set(declared) == set(example), (
            f"{path}: declared properties {sorted(declared)} != example keys "
            f"{sorted(example)}")


def test_declared_required_keys_are_proven_present_in_the_delivery(client, monkeypatch):
    """`required` may only list keys MEASURED present in a real delivery.

    vet402 reads `.required` from the example object and treats a key missing
    from the body as a mismatch (a BLOCK), so the list may only hold keys we
    have proven. This replaces an earlier blanket "declare no required keys"
    rule: that rule was right about unprovable keys and wrong about provable
    ones — /api/v1/verify-seller returns all nine keys its example names, on a
    cold read and on a cached read alike.
    """
    import main
    import services.seller_audit as sa

    # 1. The declaration must not contradict itself: every required key has to
    #    be one the same example declares as a property.
    declared = {}
    for path in main.X402_PAID_ENDPOINTS:
        body = _challenge_for(client, path)
        schema = ((body.get("extensions") or {}).get("bazaar") or {}).get("schema")
        out = _catalog_output_of(schema)
        props = set(out["exampleProps"] or {})
        assert set(out["requiredKeys"]) <= props, (
            f"{path} requires keys its own example does not declare: "
            f"{sorted(set(out['requiredKeys']) - props)}")
        if out["requiredKeys"]:
            declared[path] = out["requiredKeys"]

    assert declared, "no paid route declares required keys — nothing is proven"

    # 2. Every declared required key must be in the body a paying caller gets.
    #    The chain read is stubbed, so this never touches the network.
    monkeypatch.setattr(sa, "_CACHE", {}, raising=False)
    monkeypatch.setattr(
        sa, "audit_receiver",
        lambda receiver, days=7, **kw: sa.build_audit(
            [{"tx_hash": "0x" + "ab" * 32,
              "payer": "0x1111111111111111111111111111111111111111",
              "amount_usdc": 0.003, "block_number": 1}],
            {"complete": True, "lookback_days": days, "scanned_blocks": 10,
             "failed_ranges": 0, "split_retries": 0},
            receiver=receiver, days=days))
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 2)

    for path, required in declared.items():
        main._free_tier_usage.clear()
        r = client.get(path + "?receiver="
                       "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f")
        assert r.status_code == 200, f"{path} answered {r.status_code}"
        delivered = r.get_json()
        missing = [k for k in required if k not in delivered]
        assert not missing, (
            f"{path} declares {missing} as required but a real delivery lacks "
            f"them — vet402 would BLOCK")


def test_the_402_header_and_body_agree_on_the_declaration(client):
    """The PAYMENT-REQUIRED header is the canonical copy; the body must match it."""
    import base64

    import main

    for path in main.X402_PAID_ENDPOINTS:
        main._free_tier_usage["127.0.0.1"] = 999
        r = client.get(path)
        assert r.status_code == 402
        header = r.headers.get("PAYMENT-REQUIRED")
        assert header, f"{path}: no PAYMENT-REQUIRED header"
        decoded = json.loads(base64.b64decode(header))
        body = r.get_json()
        assert decoded["extensions"] == body["extensions"], (
            f"{path}: header and body disagree on extensions")
        assert _catalog_output_of(decoded["extensions"]["bazaar"]["schema"]) == \
            _catalog_output_of(body["extensions"]["bazaar"]["schema"])
