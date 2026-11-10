# -*- coding: utf-8 -*-
"""The listing must say WHEN to call it, and must not lose the payment.

WHY THIS FILE EXISTS. The CDP discovery docs list what qualifies an endpoint
for curation — the tier that is actually distributed to buyers — and one of the
five requirements is metadata, not code:

    "Agent-ready metadata: Complete input schema; a description that tells an
     agent *when* to use the endpoint; per-call pricing, supported networks,
     and documented error responses."
    -- docs.cdp.coinbase.com/x402/seller/get-discovered

Measured against the whole Bazaar on 2026-11-10: 9.3% of 33,392 listed rows
carry a "when to use" line. All 19 of our rows but two did not — we were in the
90.7% that describes the product and never says when it is worth buying. Worse,
the same docs say the description is a ranking input:

    "Description. Write a natural-language description of what the endpoint
     does and when to call it. Bare endpoint names and placeholder text score
     zero on metadata quality."

And the same field carries a hard cap, breach of which costs the money, not
just the position:

    "Keep it to 500 characters or fewer, because the CDP Facilitator rejects
     verify and settle requests whose description exceeds that limit."

Three guards, then: the trigger is present, the cap is respected, and the text
describes rather than instructs (the metadata content policy screens for text
"that could instruct an agent instead of describing the endpoint").
"""
from __future__ import annotations

import re

import pytest

#: The documented maximum. Over it, verify AND settle are rejected.
DESC_CAP = 500

#: What "says when to use it" looks like in our own copy.
#:
#: Deliberately a vocabulary rather than one blessed sentence: the property is
#: "names the situation that makes the call worth making", and there is more
#: than one honest way to say that. A new shape here should be ADDED to the
#: alternation, not worked around by rewording the product copy.
WHEN_TRIGGERS = re.compile(
    r"\b(useful|relevant|worth reading|worth calling|worth paying|"
    r"fits an agent|matters)\b[^.]{0,120}?\b(when|before|at the start)\b"
    r"|\bwhen (an agent|you|a trader|the caller|the engine)\b"
    r"|\bbefore (you pay|paying|opening|acting|sending|deciding)\b"
    r"|\banswers (the|a) question\b"
    r"|\bis the question\b",
    re.I,
)

#: A smoke test for the content policy, NOT the policy itself. The Bazaar
#: screens metadata for text that could be read as an instruction to an agent;
#: these are the shapes that most obviously read that way. A rewrite that says
#: "Call this endpoint and send your payment now" would be caught here; a
#: subtler instruction would not, and no regex settles that.
INSTRUCTION_SHAPES = re.compile(
    r"(ignore (all )?(previous|prior|above))"
    r"|(you must)"
    r"|(^|[.!?]\s)(call|send|pay|use|execute|run|invoke|do not|don't)\b",
    re.I,
)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    return main.app.test_client()


def _paid_paths():
    import main
    # Canonical routes AND their alias spellings: an alias is a paid route in
    # every sense, and it is the spelling the catalogue actually returns.
    return sorted(main.X402_PAID_ENDPOINTS)


def _served_description(client, path):
    import main
    main._free_tier_usage["127.0.0.1"] = 999   # exhaust the free tier
    r = client.get(path)
    assert r.status_code == 402, f"{path} should demand payment, got {r.status_code}"
    return r.get_json()["resource"]["description"]


def test_there_are_twelve_paid_paths_to_check(client):
    """If this number changes, the three guards below changed meaning too."""
    assert len(_paid_paths()) == 12, _paid_paths()


def test_every_paid_listing_says_when_to_use_it(client):
    """The requirement most sellers skip, enforced on every route we sell."""
    missing = []
    for path in _paid_paths():
        desc = _served_description(client, path)
        if not WHEN_TRIGGERS.search(desc):
            missing.append((path, desc))
    assert missing == [], (
        "these listings never say when the call is worth making, which is an "
        "explicit curation requirement and a ranking input:\n"
        + "\n".join("  %s: %r" % (p, d) for p, d in missing))


def test_no_listing_description_can_lose_a_payment_on_length(client):
    """>500 characters makes the facilitator reject verify AND settle.

    That is not a listing penalty: the buyer's payment is refused, so the
    defect costs the sale itself. A cap enforced only at publish time is not
    enforced — this reads what the 402 actually serves.
    """
    over = []
    for path in _paid_paths():
        desc = _served_description(client, path)
        if len(desc) > DESC_CAP:
            over.append((path, len(desc)))
    assert over == [], (
        "the facilitator rejects verify and settle above %d characters: %r"
        % (DESC_CAP, over))


def test_no_listing_reads_as_an_instruction_to_the_agent(client):
    """The metadata content policy: describe the endpoint, do not direct it."""
    offenders = []
    for path in _paid_paths():
        desc = _served_description(client, path)
        m = INSTRUCTION_SHAPES.search(desc)
        if m:
            offenders.append((path, m.group(0)))
    assert offenders == [], (
        "the Bazaar screens out metadata that reads as an instruction to an "
        "agent rather than a description of the endpoint: %r" % (offenders,))


def test_the_icon_is_one_url_in_one_format_on_every_surface(client):
    """A2A card and the x402 challenge must not disagree about the icon.

    They were two hand-written "/static/icons/kristo.svg" strings, which is how
    one surface gets fixed and the other stays wrong.
    """
    import main
    main._free_tier_usage["127.0.0.1"] = 999
    challenge = client.get("/api/stats")
    assert challenge.status_code == 402
    icon_402 = challenge.get_json()["resource"]["iconUrl"]

    card = client.get("/.well-known/agent-card.json")
    assert card.status_code == 200
    icon_card = card.get_json()["iconUrl"]

    tail_402 = icon_402.split("/", 3)[-1]
    tail_card = icon_card.split("/", 3)[-1]
    assert tail_402 == tail_card == main.X402_ICON_PATH.lstrip("/"), (
        "the challenge says %r and the agent card says %r"
        % (icon_402, icon_card))


def test_the_icon_asset_is_a_real_square_png():
    """Read the PNG's own header — stdlib only, so this guard always runs.

    A directory renders the icon in a card, so a wrong aspect ratio or a
    thumbnail-sized asset is a listing that looks broken. Pillow is needed to
    GENERATE the file, not to check it, and a guard that skips is a guard that
    did not run.
    """
    from pathlib import Path
    import struct

    blob = (Path(__file__).resolve().parents[1]
            / "static" / "icons" / "kristo.png").read_bytes()
    assert blob[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    assert blob[12:16] == b"IHDR", "the first chunk is not IHDR"
    width, height = struct.unpack(">II", blob[16:24])
    assert width == height, "a card icon must be square, got %dx%d" % (width, height)
    assert width >= 256, "too small for a directory card: %dpx" % width


def test_the_icon_generator_matches_the_served_asset():
    """The PNG is generated by a script, so it must BE that script's output.

    A committed binary with no generator is an asset nobody can change; a
    generator whose output was hand-edited is worse. Skipped without Pillow,
    because Pillow is a build-time tool here and the header check above covers
    the properties that matter at run time.
    """
    from pathlib import Path
    import io
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    try:
        import make_brand_icon
    except ImportError:  # pragma: no cover
        pytest.skip("icon generator not importable")
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        pytest.skip("Pillow is only needed to REGENERATE the icon, not to serve it")

    buf = io.BytesIO()
    make_brand_icon.render().save(buf, format="PNG", optimize=True)
    on_disk = (root / "static" / "icons" / "kristo.png").read_bytes()
    assert buf.getvalue() == on_disk, (
        "static/icons/kristo.png is not what scripts/make_brand_icon.py renders "
        "— re-run the generator")
