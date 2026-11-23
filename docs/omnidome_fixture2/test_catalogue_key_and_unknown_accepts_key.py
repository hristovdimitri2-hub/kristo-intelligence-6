#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kristo Intelligence
#
# This file is MIT-licensed: run it, copy it, change it, ship it. The line
# "Production source this was extracted from (MIT)" further down is the licence
# of the code this was extracted FROM; this block is the licence of the file
# itself, so a stranger who runs it does not have to guess.

"""Catalogue identity: the key that gets published, and the row that vanishes.

FIXTURE 2 for OmniDome Agent Commons (issue #3, "catalogue identity").
Single file, standard library only, no network, no wallet, no keys, and no paid
request of any kind. Every host, address and identifier below is synthetic.

WHAT THIS IS
------------
A redacted extraction of the decision points in the Kristo Intelligence
production code that decide whether a discovery listing appears at all, with the
transport removed. It is not the production code: it is the decision table those
files implement, pinned so that a stranger can run it and see the rules.

Production source this was extracted from (MIT):

    commit  ee80a5dd7b178a2e120ea7b784ce76dea20ab5b9
    blob    app/blueprints/discovery.py   60ed342f01891eb25900dab34001268ae94743ca
    blob    services/connectors.py        ba69d51a84a05f5cd557e15c35904dbaf604daca
    blob    scripts/validate_preview.py   60b93c04504eb0d8ab3767a0fade8a1a93eb2736

    the published key            app/blueprints/discovery.py:2364-2409
    _retype_bazaar_for_mcp       app/blueprints/discovery.py:2012
    the requirements pre-check   services/connectors.py:292-293, 489-520
    /validate preview            scripts/validate_preview.py:45

WHAT IT PINS
------------
1. The catalogue builds the `#<toolName>` fragment ITSELF, from the tool name.
   It does not look at whether the URL it was handed already ends with that
   fragment. A seller that pre-builds the fragment gets it twice, so the
   published key is not the string that was declared.
2. The published key must carry the tool name EXACTLY ONCE. The tool identity
   travels in `extensions.bazaar.info.input.toolName`, which is where both
   catalogues read it from; the fragment in the URL is therefore redundant, and
   harmful precisely because the catalogue adds its own.
3. An unsupported key inside `accepts[0]` is refused LOUDLY. The failure this
   pins is not a refusal. Measured on 16.11.2026: a row was accepted, settled
   eight times across two rounds, and never appeared anywhere, with no error
   returned to anyone.
4. A catalogue row is a DECLARATION, not a receipt. Presence in an index is not
   evidence that anybody paid, and a usage count is evidence only when it is
   derived from settlements.
5. `POST /platform/v2/x402/validate` is HTTP-shaped. For MCP resources it
   reports `returns_402: failed` with a null extension IDENTICALLY whether the
   resource is listed or not, so a failed verdict there is not MCP
   ineligibility - and a valid one is not a promise that a payment will settle.

WHAT THIS IS NOT
----------------
It does not reproduce either catalogue. It pins the RULE we settled on after
measuring them, so that a reader can see the rule and disagree with it.

RUN IT
------
    python3 test_catalogue_key_and_unknown_accepts_key.py
    python3 test_catalogue_key_and_unknown_accepts_key.py --json
    pytest -q test_catalogue_key_and_unknown_accepts_key.py

Exit code 0 means every assertion held. No dependency is installed and no
network call is made.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ── The identity a seller declares, and the one that gets published ───────
#: The MCP endpoint, bare. Synthetic host.
MCP_URL = "https://mcp.example.test/mcp"

#: The tool the seller is declaring. Synthetic.
TOOL_NAME = "get_whale_flow"

#: A second tool, to show that the rule is not a string match on one name.
OTHER_TOOL = "get_trading_signal"


def catalogue_key(declared_url: str, tool_name: str) -> str:
    """The key the catalogue publishes, built the way the catalogue builds it.

    Measured against CDP's own MCP rows: the fragment is `<endpoint>#<toolName>`
    and the catalogue derives it from the tool name. It performs no check on the
    URL it was handed, so the append is unconditional.
    """
    return "%s#%s" % (declared_url, tool_name)


def declare(declared_url: str, tool_name: str) -> str:
    """What a seller SHOULD declare: the bare endpoint, with no fragment.

    The tool name is not lost by removing it - it travels in
    `extensions.bazaar.info.input.toolName`, which both catalogues read. PayAPI
    additionally stores `resource=/mcp` beside a separate `toolName`, so the
    bare form is the correct one for both.
    """
    return declared_url.split("#", 1)[0]


def published_key(declared_url: str, tool_name: str) -> str:
    """The published key once the declaration is normalised.

    That is the contract this fixture pins: whatever the seller declares, the
    key the catalogue stores carries the tool name exactly once.
    """
    return catalogue_key(declare(declared_url, tool_name), tool_name)


def tool_fragments(key: str, tool_name: str) -> int:
    """How many times the tool name appears as a fragment in a published key."""
    return key.count("#" + tool_name)


# ── Rule 2: an unsupported accepts key is a refusal, never a silent drop ──
#: The keys a facilitator's `accepts[0]` may carry.
KNOWN_ACCEPT_KEYS = frozenset({
    "scheme",
    "network",
    "maxAmountRequired",
    "resource",
    "description",
    "mimeType",
    "payTo",
    "maxTimeoutSeconds",
    "asset",
    "extra",
})

#: The only keys allowed inside `accepts[0].extra`. This is the EIP-712 domain
#: a client needs to sign: the token name and its version, nothing else.
KNOWN_EXTRA_KEYS = frozenset({"name", "version"})


def unsupported_keys(accepts: Any) -> List[str]:
    """Every key a strict reader does not recognise, with its location.

    Empty means "publishable". Anything else is a declaration error the SELLER
    made, and it is named here rather than swallowed.
    """
    if not isinstance(accepts, dict):
        return ["accepts_not_an_object"]

    bad: List[str] = []
    for key in sorted(accepts):
        if key not in KNOWN_ACCEPT_KEYS:
            bad.append("accepts.%s" % key)

    extra = accepts.get("extra")
    if extra is not None:
        if not isinstance(extra, dict):
            bad.append("accepts.extra_not_an_object")
        else:
            for key in sorted(extra):
                if key not in KNOWN_EXTRA_KEYS:
                    bad.append("accepts.extra.%s" % key)
    return bad


@dataclass
class PublishOutcome:
    """What happened to one attempted listing."""

    published: bool
    key: Optional[str]
    reasons: List[str] = field(default_factory=list)
    #: The failure mode this fixture exists to make impossible: accepted,
    #: settled, and never listed, with nothing reported.
    silently_voided: bool = False


def publish(declared_url: str, tool_name: str, accepts: Any) -> PublishOutcome:
    """Validate the requirements, then publish or refuse - never neither."""
    bad = unsupported_keys(accepts)
    if bad:
        return PublishOutcome(
            published=False,
            key=None,
            reasons=["unsupported_field:" + b for b in bad],
            silently_voided=False,
        )
    return PublishOutcome(
        published=True,
        key=published_key(declared_url, tool_name),
        reasons=[],
    )


def accepts_fixture(with_helper_keys: bool = False) -> Dict[str, Any]:
    """A spec-legal `accepts[0]`, optionally carrying the two helper keys.

    `extra_name` / `extra_version` are OURS. They exist so the server's own
    EIP-712 pre-check can pin the domain. They appear in no facilitator schema.
    """
    accepts: Dict[str, Any] = {
        "scheme": "exact",
        "network": "eip155:8453",
        "maxAmountRequired": "50000",
        "resource": MCP_URL,
        "description": "One tool call, paid per call.",
        "mimeType": "application/json",
        "payTo": "0x00000000000000000000000000000000000000a1",
        "maxTimeoutSeconds": 60,
        "asset": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "extra": {"name": "USD Coin", "version": "2"},
    }
    if with_helper_keys:
        accepts["extra_name"] = "kristo-precheck"
        accepts["extra_version"] = "1"
    return accepts


# ── Rule 4: a row is a declaration; only settlements are evidence ─────────
@dataclass
class ListingEvidence:
    """What a catalogue row does and does not establish.

    `listed` says only that a declaration was accepted and published. The
    numbers say what settlements showed, and where they came from.
    """

    listed: bool
    source: str = "none"                    # "none" | "declaration" | "settlement"
    settlements_30d: Optional[int] = None
    unique_payers_30d: Optional[int] = None

    @property
    def proves_paid_usage(self) -> bool:
        """A listing is not a receipt.

        True only when a positive count came from observed settlements. A zero
        is not proof either: it is the absence of the thing, not evidence of it.
        """
        return (
            self.source == "settlement"
            and isinstance(self.settlements_30d, int)
            and self.settlements_30d > 0
        )

    @property
    def claimable(self) -> str:
        """The strongest sentence this row supports, and no stronger."""
        if self.proves_paid_usage:
            return ("listed and settled: %d settlement(s) from %s payer(s) in 30d"
                    % (self.settlements_30d, self.unique_payers_30d))
        if self.listed:
            return "listed; no settlement evidence"
        return "not listed"


# ── Rule 5: /validate is HTTP-shaped ──────────────────────────────────────
def validate_says_indexable(response: Any) -> bool:
    """What `/validate` alone would suggest about a resource.

    Deliberately NOT an eligibility test. See the test below for why.
    """
    if not isinstance(response, dict):
        return False
    if str(response.get("returns_402") or "").strip().lower() == "failed":
        return False
    return bool(response.get("bazaarExtension"))


# ── Tests ─────────────────────────────────────────────────────────────────
def test_the_catalogue_builds_the_fragment_itself():
    """Assertion 1a: the bare endpoint is the declaration that works.

    The peer that settled the mechanism declares the bare URL and the catalogue
    stores the fragment:

        declared   https://mcp.example.test/mcp
        published  https://mcp.example.test/mcp#get_whale_flow
    """
    key = catalogue_key(MCP_URL, TOOL_NAME)
    assert key == MCP_URL + "#" + TOOL_NAME, key
    assert tool_fragments(key, TOOL_NAME) == 1, key


def test_a_prebuilt_fragment_is_doubled_by_the_catalogue():
    """Assertion 1b: the declared identity is not the published identity.

    This is the measured defect. We used to declare the form the catalogue
    STORES, and the catalogue appended its own fragment on top:

        declared   .../mcp#get_whale_flow
        published  .../mcp#get_whale_flow#get_whale_flow
    """
    declared = MCP_URL + "#" + TOOL_NAME
    doubled = catalogue_key(declared, TOOL_NAME)
    assert doubled == MCP_URL + "#" + TOOL_NAME + "#" + TOOL_NAME, doubled
    assert tool_fragments(doubled, TOOL_NAME) == 2, doubled
    # And the published key is therefore not the string that was declared.
    assert doubled != declared, "the pre-built fragment happened to survive"


def test_the_published_key_carries_the_tool_name_exactly_once():
    """Assertion 2: exactly-once, whichever form the seller declares.

    Both declaration forms normalise to the same key, so a seller who has
    already shipped the wrong form does not have to re-register - and a seller
    who has not cannot get it wrong.
    """
    for declared in (MCP_URL,
                     MCP_URL + "#" + TOOL_NAME,
                     MCP_URL + "#" + TOOL_NAME + "#" + TOOL_NAME):
        key = published_key(declared, TOOL_NAME)
        assert tool_fragments(key, TOOL_NAME) == 1, (declared, key)
        assert key == MCP_URL + "#" + TOOL_NAME, (declared, key)

        # A different tool name on the same endpoint is a different key, so the
        # rule is not "strip anything after a hash".
        other = published_key(declared, OTHER_TOOL)
        assert tool_fragments(other, OTHER_TOOL) == 1, other
        assert key != other, "two tools collapsed onto one published key"


def test_the_tool_name_survives_removal_from_the_url():
    """Assertion 2b: removing the fragment loses nothing.

    The identity travels in the bazaar extension, which is where both
    catalogues read it from, so the URL fragment is redundant.
    """
    extensions = {
        "bazaar": {
            "info": {
                "input": {"type": "mcp", "toolName": TOOL_NAME,
                          "transport": "streamable-http"},
            }
        }
    }
    url = declare(MCP_URL + "#" + TOOL_NAME, TOOL_NAME)
    assert "#" not in url, url
    assert extensions["bazaar"]["info"]["input"]["toolName"] == TOOL_NAME


def test_an_unknown_accepts_key_is_refused_loudly_not_dropped():
    """Assertion 3a: the two helper keys are named in the refusal.

    Measured on 16.11.2026: with these two keys present, /api/stats settled
    eight times across two rounds and was never listed. The settlement
    succeeded, so the client saw a transaction and nothing was reported as
    wrong. Removing the two keys, with the spec-legal `description` and
    `mimeType` still present, listed within 45 seconds.
    """
    outcome = publish(MCP_URL, TOOL_NAME, accepts_fixture(with_helper_keys=True))
    assert outcome.published is False, "a listing with unsupported keys published"
    assert outcome.silently_voided is False, "the row vanished without a reason"
    assert "unsupported_field:accepts.extra_name" in outcome.reasons, outcome.reasons
    assert "unsupported_field:accepts.extra_version" in outcome.reasons, outcome.reasons
    assert outcome.key is None, "a key was published for a refused listing"


def test_the_spec_legal_form_publishes():
    """Assertion 3b: without the helper keys, the same declaration publishes."""
    outcome = publish(MCP_URL, TOOL_NAME, accepts_fixture(with_helper_keys=False))
    assert outcome.published is True, outcome.reasons
    assert outcome.reasons == [], outcome.reasons
    assert outcome.key == MCP_URL + "#" + TOOL_NAME, outcome.key


def test_an_unknown_extra_key_is_located_precisely():
    """Assertion 3c: the refusal says WHERE, not just that something is wrong."""
    accepts = accepts_fixture()
    accepts["extra"] = {"name": "USD Coin", "version": "2", "chainId": 8453}
    accepts["resource_object"] = {"url": MCP_URL}
    bad = unsupported_keys(accepts)
    assert "accepts.extra.chainId" in bad, bad
    assert "accepts.resource_object" in bad, bad
    assert "accepts.extra.name" not in bad, bad
    assert "accepts.scheme" not in bad, bad


def test_a_listing_is_not_a_receipt():
    """Assertion 4: discoverability alone never proves paid usage.

    Three rows that all look identical in a catalogue. Only the third supports
    a claim about payment, and it supports it because of the settlements, not
    because of the row.
    """
    listed_no_numbers = ListingEvidence(listed=True)
    assert listed_no_numbers.proves_paid_usage is False
    assert listed_no_numbers.claimable == "listed; no settlement evidence"

    listed_zero = ListingEvidence(listed=True, source="settlement",
                                  settlements_30d=0, unique_payers_30d=0)
    assert listed_zero.proves_paid_usage is False, "a zero was read as proof"

    declared_only = ListingEvidence(listed=True, source="declaration")
    assert declared_only.proves_paid_usage is False

    really_paid = ListingEvidence(listed=True, source="settlement",
                                  settlements_30d=12, unique_payers_30d=9)
    assert really_paid.proves_paid_usage is True
    assert "12 settlement(s)" in really_paid.claimable, really_paid.claimable


def test_validate_is_http_shaped_and_proves_neither_listing_nor_settlement():
    """Assertion 5: a failed /validate verdict is not MCP ineligibility.

    Measured: for MCP resources, /validate returns `returns_402: failed` and a
    null `bazaarExtension` identically whether the resource is listed or not.
    The endpoint is HTTP-shaped. So the two responses below are byte-identical
    while one resource is listed and the other is not - which means this
    function can never be the MCP eligibility test.
    """
    listed_mcp = {"returns_402": "failed", "bazaarExtension": None}
    unlisted_mcp = {"returns_402": "failed", "bazaarExtension": None}

    assert listed_mcp == unlisted_mcp, "the two responses are distinguishable"
    assert validate_says_indexable(listed_mcp) is False
    assert validate_says_indexable(unlisted_mcp) is False

    # The listed one is listed despite the failed verdict.
    evidence = ListingEvidence(listed=True, source="settlement",
                               settlements_30d=3, unique_payers_30d=2)
    assert evidence.listed is True and evidence.proves_paid_usage is True

    # And a green verdict is not a payment either: /validate is not /settle, so
    # a valid preview plus a published row still supports no claim about money.
    valid = {"returns_402": "ok", "bazaarExtension": {"info": {}}}
    assert validate_says_indexable(valid) is True
    previewed = ListingEvidence(listed=True, source="declaration")
    assert previewed.proves_paid_usage is False, "a valid preview was read as payment"


# ── Synthetic input / expected output, as JSON ────────────────────────────
def fixture() -> Dict[str, Any]:
    """The cases a reader can diff without reading the code."""
    return {
        "synthetic_input": {
            "mcp_url": MCP_URL,
            "tool_name": TOOL_NAME,
            "declarations": [
                {"declared": MCP_URL, "label": "bare (correct)"},
                {"declared": MCP_URL + "#" + TOOL_NAME,
                 "label": "pre-built fragment (the measured defect)"},
            ],
            "accepts": {
                "spec_legal": accepts_fixture(with_helper_keys=False),
                "with_our_helper_keys": accepts_fixture(with_helper_keys=True),
            },
        },
        "expected_output": {
            "published_key": MCP_URL + "#" + TOOL_NAME,
            "tool_fragments_in_published_key": 1,
            "tool_fragments_if_prebuilt": 2,
            "publish": {
                "spec_legal": {"published": True, "key": MCP_URL + "#" + TOOL_NAME},
                "with_our_helper_keys": {
                    "published": False,
                    "reasons": ["unsupported_field:accepts.extra_name",
                                "unsupported_field:accepts.extra_version"],
                    "silently_voided": False,
                },
            },
            "listing_is_not_a_receipt": {
                "listed_without_settlement_source": {"proves_paid_usage": False},
                "listed_with_zero_settlements": {"proves_paid_usage": False},
                "listed_with_settlements": {"proves_paid_usage": True},
            },
            "validate_for_mcp": {"returns_402": "failed", "bazaarExtension": None,
                                 "identical_when_listed": True},
        },
    }


# ── Runner: works with or without pytest ──────────────────────────────────
def _tests() -> List[Tuple[str, Any]]:
    return sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    )


def run_all() -> int:
    failures = 0
    tests = _tests()
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures += 1
            print("FAIL  %s  %s" % (name, exc))
        else:
            print("PASS  %s" % name)
    print("\n%d passed, %d failed" % (len(tests) - failures, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(fixture(), indent=2))
        sys.exit(0)
    sys.exit(run_all())
