"""`docs/x402-client-example.js` is the flow developers copy.

The previous version told them, in its header, that "the current server does not
yet verify request-bound payment proofs in the paywall" and that the deployment
was `settlement_status=discovery_only`. Both were false — the paywall has been
verifying and settling for months — and this test USED TO REQUIRE that string,
so it locked the false claim in. A test written to match the code instead of the
truth is worse than no test.

It also described only the legacy rail, which waits 12 confirmations (~24s),
while the standard rail settles in ~2s.
"""
from pathlib import Path

EXAMPLE = Path("docs/x402-client-example.js")


def _example() -> str:
    return EXAMPLE.read_text(encoding="utf-8")


def test_the_example_never_claims_the_paywall_does_not_work():
    """The single most damaging thing this file used to say."""
    example = _example()
    for false_claim in (
        "discovery_only",
        "does not yet verify",
        "settlement_status=discovery_only",
        "discovery-only until facilitator settlement is enabled",
    ):
        assert false_claim not in example, (
            f"the example again tells developers the paywall is not real: "
            f"{false_claim!r}")


def test_the_example_documents_both_rails():
    example = _example()
    for fragment in (
        "PAYMENT-SIGNATURE",        # standard rail credential
        "PAYMENT-REQUIRED",         # standard rail challenge
        "X-Payment-Proof",          # legacy rail credential
        "signTypedData",            # EIP-3009 signing
        "TransferWithAuthorization",
        "writeContract",            # legacy broadcast
        "waitForTransactionReceipt",
        "X402_RAIL",                # the switch between them
    ):
        assert fragment in example, f"the example does not mention {fragment!r}"


def test_the_example_prefers_the_fast_rail_and_says_why():
    """The standard rail is the default; the ~24s legacy wait is stated."""
    example = _example()
    assert 'process.env.X402_RAIL?.trim() || "standard"' in example, (
        "the standard rail must be the default")
    assert "~2 seconds" in example and "~24 seconds" in example, (
        "both rails' real timings must be stated")
    assert "12 confirmations" in example, (
        "the legacy rail's confirmation wait must be stated")


def test_the_example_handles_425_without_paying_twice():
    """425 means settling — re-send the credential, never make a second payment."""
    example = _example()
    assert "settlement_in_flight" in example
    assert "same credential" in example
    assert "one-time-use" in example


def test_the_example_still_refuses_to_pay_on_the_wrong_network():
    example = _example()
    assert "Refusing to pay on a non-Base network" in example or \
        "Refusing to pay on chain" in example
    assert "8453" in example
    assert "Never commit X402_PRIVATE_KEY" in example


def test_the_example_runs_without_a_network_or_a_wallet():
    """It must parse: a syntax error would only surface on a developer's machine."""
    import subprocess
    import sys

    result = subprocess.run(
        ["node", "--check", str(EXAMPLE)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0 and "ENOENT" in (result.stderr or ""):
        import pytest
        pytest.skip("node is not available here")
    assert result.returncode == 0, result.stderr or result.stdout
    del sys
