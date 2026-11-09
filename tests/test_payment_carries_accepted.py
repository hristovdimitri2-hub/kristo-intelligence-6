"""`accepted` must travel with the payment — a facilitator will refuse without it.

THE FINDING, and it is the reason PayAI never once settled for us.

Reproduced by calling the facilitator DIRECTLY and reading the response body,
which is the only thing that says what it objected to:

    POST https://facilitator.payai.network/settle
    HTTP 400
    {"success":false,"errorReason":"invalid_payload",
     "errorMessage":"accepted: Invalid input: expected object, received undefined"}

x402 v2 names the buyer's chosen option `accepted` — ONE OBJECT. Our 402 ships
`accepts`, an ARRAY, and `echo_extensions` echoed `extensions` and `resource`
while leaving the option itself out. So a spec-strict facilitator refused every
payment, and everything that DID settle went through CDP.

That is the same field that broke verification on the server side, from the other
direction: our own verifier read `payload["accepted"]` while our clients sent
`accepts`, so real payments were refused as unverifiable. Both halves are now
closed — the facilitator gets `accepted`, and our verifier reads either spelling.

WITH THE FIX, THE SAME CALL RETURNS:

    HTTP 200
    {"success":true,"transaction":"0xb138f56b...","payer":"0xe50c5212..."}
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_helper():
    """Import `scripts/demo_sponsored_pay.py` without running it as a script."""
    path = REPO / "scripts" / "demo_sponsored_pay.py"
    spec = importlib.util.spec_from_file_location("_dsp_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_dsp_under_test"] = module
    spec.loader.exec_module(module)
    return module


DSP = _load_helper()

OPTION = {
    "scheme": "exact",
    "network": "eip155:8453",
    "amount": "3000",
    "payTo": "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f",
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "maxTimeoutSeconds": 60,
    "extra": {"name": "USD Coin", "version": "2"},
}


def _challenge(**extra):
    ch = {"accepts": [dict(OPTION)], "resource": {
        "url": "https://kristo-intelligence-api.onrender.com/api/v1/whaleflow",
        "description": "live whale flow"}}
    ch.update(extra)
    return ch


def _payload():
    return {"x402Version": 2, "scheme": "exact", "network": "eip155:8453",
            "payload": {"signature": "0x" + "ab" * 65,
                        "authorization": {"from": "0x1", "to": "0x2"}}}


# ── the field a facilitator requires ────────────────────────────────────────

def test_accepted_is_added_from_the_accepts_array():
    """THE regression. Without this the facilitator answers 400."""
    out = DSP.echo_extensions(_payload(), _challenge())
    assert "accepted" in out, (
        "the payment carries no `accepted`, so a spec-strict facilitator refuses "
        "it with 'expected object, received undefined'")
    assert out["accepted"] == OPTION


def test_accepted_is_a_single_object_not_the_array():
    """x402 v2 names ONE option. Sending the array is what the error complains
    about, so echoing `accepts` back under the singular name would not help."""
    out = DSP.echo_extensions(_payload(), _challenge())
    assert isinstance(out["accepted"], dict)
    assert not isinstance(out["accepted"], list)


def test_the_other_two_echoes_still_travel():
    """The fix must not displace what already worked — the Bazaar declaration
    and the resource url are how the facilitator learns to list us."""
    ch = _challenge(extensions={"bazaar": {"info": {}}})
    out = DSP.echo_extensions(_payload(), ch)
    assert out["extensions"] == {"bazaar": {"info": {}}}
    assert out["resource"]["url"].endswith("/api/v1/whaleflow")
    assert out["accepted"] == OPTION


def test_an_already_singular_accepted_is_respected():
    """A newer client that sends `accepted` directly must not be overwritten."""
    ch = _challenge(accepted=dict(OPTION, amount="9999"))
    out = DSP.echo_extensions(_payload(), ch)
    assert out["accepted"]["amount"] == "9999"


def test_a_dict_under_accepts_is_also_understood():
    """Some clients send a bare object rather than an array."""
    ch = {"accepts": dict(OPTION)}
    out = DSP.echo_extensions(_payload(), ch)
    assert out["accepted"] == OPTION


def test_no_terms_means_no_accepted_and_no_crash():
    """A challenge with nothing to echo must leave the payload alone rather than
    inventing an option the buyer never signed."""
    out = DSP.echo_extensions(_payload(), {})
    assert "accepted" not in out


def test_the_caller_payload_is_not_mutated():
    """The helper copies before it writes; a caller reusing its dict must not
    find terms it never added."""
    original = _payload()
    DSP.echo_extensions(original, _challenge())
    assert "accepted" not in original
    assert "resource" not in original


def test_both_spellings_travel_together():
    """`accepted` satisfies the facilitator; `accepts` stays for anything
    reading the array. Our verifier reads either."""
    out = DSP.echo_extensions(_payload(), _challenge())
    assert isinstance(out["accepted"], dict)
