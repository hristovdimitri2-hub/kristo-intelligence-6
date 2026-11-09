"""The facilitator chain must not be a single point of failure.

WHY THIS EXISTS, and it is a scheduled risk rather than a hypothetical one.

CDP's status feed carries:

    Scheduled System Maintenance — November 14
    Nov 14, 10:00 - 18:00 PST
    some users may experience degraded performance across multiple products

That is up to FOUR HOURS in which CDP — the facilitator our settlements prefer —
may not answer. Until 09.11 the fallback behind it did not work at all, so a CDP
outage meant no payments, full stop.

The reason it did not work, measured by calling PayAI directly and reading the body:

    HTTP 400
    {"errorReason":"invalid_payload",
     "errorMessage":"accepted: Invalid input: expected object, received undefined"}

x402 v2 names the chosen option `accepted` — ONE OBJECT. Our 402 ships `accepts`,
an ARRAY. CDP tolerates the array; PayAI does not. So the chain was only a fallback
for clients that spell the field the spec way, and everyone else — including agents
echoing our own 402 verbatim — had exactly ONE usable facilitator.

`_with_accepted` fills the field in from terms the SERVER itself offered. That is
reconstruction, not falsification: the server built the 402, so it knows which
options it gave, and `accepted` records which one was taken.
"""

from services import connectors

OPTION = {
    "scheme": "exact",
    "network": "eip155:8453",
    "amount": "3000",
    "payTo": "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f",
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "maxTimeoutSeconds": 60,
    "extra": {"name": "USD Coin", "version": "2"},
}


def test_the_array_spelling_gets_an_accepted_filled_in():
    """THE point. A client echoing our own 402 sends `accepts`; without this it
    can only be settled by the lenient facilitator."""
    out = connectors._with_accepted({"accepts": [dict(OPTION)]}, {})
    assert out.get("accepted") == OPTION


def test_a_client_that_already_sent_accepted_keeps_its_own():
    """The buyer's answer wins, byte for byte. A server that overwrote it would be
    deciding which option was taken rather than recording it."""
    sent = {"accepted": {"amount": "9999", "scheme": "exact"}}
    out = connectors._with_accepted(dict(sent, accepts=[dict(OPTION)]), {})
    assert out["accepted"] == {"amount": "9999", "scheme": "exact"}


def test_a_payload_with_no_terms_is_left_alone():
    """Nothing to reconstruct, so nothing is invented — an `accepted` conjured
    from nothing would describe an option the buyer never signed."""
    assert "accepted" not in connectors._with_accepted({"accepts": []}, {})
    assert connectors._with_accepted({}, {}) == {}


def test_none_survives():
    """The caller indexes into this; returning a dict here would move the failure
    rather than prevent it."""
    assert connectors._with_accepted(None, {}) is None


def test_the_callers_payload_is_not_mutated():
    """The decoded payload is used elsewhere in the same call, and a helper that
    wrote into it would change the buyer's record under them."""
    original = {"accepts": [dict(OPTION)]}
    connectors._with_accepted(original, {})
    assert "accepted" not in original


def test_the_filled_option_is_the_signed_one():
    """It must be the option the buyer's signature covers, which is the one merged
    into `paymentRequirements` — not some other entry of the array."""
    chosen = dict(OPTION, amount="7000")
    payload = {"accepts": [dict(OPTION), chosen]}
    out = connectors._with_accepted(payload, {})
    # `_accepted_option` takes the first, and that is what the client signed over
    # when it echoed our single-option 402.
    assert out["accepted"] == connectors._accepted_option(payload)


def test_the_normalisation_runs_before_the_chain():
    """Structural: a normalisation defined and never called fixes nothing."""
    from pathlib import Path

    src = (Path(connectors.__file__)).read_text(encoding="utf-8")
    body = src[src.index("def settle_standard_payment"):]
    assert "_with_accepted(payload" in body, (
        "settle_standard_payment does not normalise the payload, so every "
        "facilitator behind the first is unusable for a client that sends the "
        "array spelling")
