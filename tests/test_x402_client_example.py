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


# ── The unit trap (F-18) ────────────────────────────────────────────────────
#
# `payment.amount_usdc` is ATOMIC on the live API: a $0.005 call arrives as
# 5000. The field was decimal in an earlier release and main.py annotates the
# change ("atomic units, as in accepts (was decimal)"). The original example
# ran parseUnits(String(payment.amount_usdc), 6) on it, i.e. told the wallet to
# transfer 5000 USDC for a $0.005 call. The server compares the decoded on-chain
# amount with `>=`, so it would have ACCEPTED that transfer and kept the money.

def _example_code() -> str:
    """The example's CODE, with comment lines removed.

    The file documents the old bug in its comments, so a plain substring check
    over the whole file matches the WARNING rather than the mistake. Assertions
    about behaviour have to look at code.
    """
    kept = []
    for line in _example().splitlines():
        if line.strip().startswith(("*", "//", "/*")):
            continue
        kept.append(line)
    return "\n".join(kept)


def test_the_example_never_multiplies_an_already_atomic_amount():
    code = _example_code()
    for wrong in (
        "parseUnits(String(payment.amount_usdc)",
        "parseUnits(payment.amount_usdc",
        "parseUnits(String(amount_usdc)",
    ):
        assert wrong not in code, (
            f"the example re-scales an atomic amount again: {wrong!r} — that "
            "instructs the wallet to send 1000000x the price")


def test_the_example_carries_the_atomic_value_straight_to_the_chain():
    example = _example()
    assert "BigInt(amountAtomic)" in example, (
        "the transfer must use the atomic value as-is")
    assert "function toAtomicString" in example, (
        "the unit decision must be explicit, not implicit")


def test_the_example_refuses_to_overstate_a_price():
    """Understating costs a rejected call; overstating costs the balance."""
    example = _example()
    assert "the smaller one" in example or "the smaller" in example, (
        "the tie-break direction must be documented, not left to chance")


def test_the_example_accepts_the_canonical_caip2_network():
    """The live challenge says eip155:8453; an earlier version demanded "base"
    and therefore threw before the legacy rail could ever pay."""
    example = _example()
    assert "isBaseNetwork" in example
    assert "eip155:8453" in example
    assert 'payment.network !== "base"' not in example, (
        "the CAIP-2 spelling must not be rejected")


def test_the_example_says_the_proof_amount_is_ignored():
    example = _example()
    assert "IGNORES amount_usdc" in example, (
        "the reader must know the claimed amount is not what is verified")

