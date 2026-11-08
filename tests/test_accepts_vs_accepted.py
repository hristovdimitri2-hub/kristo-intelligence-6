"""A payment option must be found under EITHER spelling of its key.

THE BUG, found on the live rail on 08.11.2026. The x402 v2 spec calls the chosen
option `accepted` (one object); this code read exactly that. But clients echo what
the 402 GAVE them, and our 402 ships `accepts` — an ARRAY. So `accepted` came back
empty, `verifyingContract` became None, and EIP-712 recovery failed on every
genuine payment:

    local_eip712_recovery_failed: ValueError: Missing value for field
    `verifyingContract` of type `address`

The refusal was recorded honestly as a 401 — which is exactly why it went unseen:
the dashboard showed `credentials_today: 8`, eight buyers presenting credentials
and being refused, and nothing anywhere said the reason was a field name.
"""

from services import connectors


OPTION = {"asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
          "network": "eip155:8453", "payTo": "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f",
          "amount": "3000", "scheme": "exact",
          "extra": {"name": "USD Coin", "version": "2"}}


def test_the_spec_spelling_is_used():
    assert connectors._accepted_option({"accepted": OPTION}) == OPTION


def test_our_own_402_spelling_is_also_used():
    """The one that was broken: a client echoing back the array we sent."""
    assert connectors._accepted_option({"accepts": [OPTION]}) == OPTION


def test_a_bare_object_under_accepts_is_accepted():
    assert connectors._accepted_option({"accepts": OPTION}) == OPTION


def test_neither_spelling_yields_an_empty_dict_not_an_exception():
    """So the caller fails with a REASON, never with a crash."""
    assert connectors._accepted_option({}) == {}
    assert connectors._accepted_option({"accepts": []}) == {}
    assert connectors._accepted_option({"accepted": None}) == {}


def test_the_first_option_wins():
    """One option was offered, so the first is the one accepted."""
    other = dict(OPTION, amount="9999")
    assert connectors._accepted_option({"accepts": [OPTION, other]}) == OPTION


def test_merged_requirements_honours_the_clients_values():
    """The signature is over the BUYER's values, so settlement must carry them."""
    server = {"amount": "3000", "payTo": "0xserver", "scheme": "exact",
              "asset": "0xasset", "network": "eip155:8453"}
    client = dict(OPTION, amount="3000")
    merged = connectors._merged_requirements({"accepts": [client]}, server)
    assert merged["payTo"] == client["payTo"], (
        "settlement carried the server's payTo instead of the buyer's")
    assert merged["asset"] == client["asset"]


def test_merged_requirements_still_falls_back_to_the_server():
    """No client echo at all must not leave the request without requirements."""
    server = {"amount": "3000", "payTo": "0xserver"}
    merged = connectors._merged_requirements({}, server)
    assert merged == server
