#!/usr/bin/env python3
"""
Kristo Intelligence v5 — Live System Test
==========================================

End-to-end automated test that verifies:

  a) Real ETH/USDC price extraction from DEXScreener API (no demo data).
  b) GLM AI model generates a short market bulletin from the live data.
  c) BASE_FEE_RECEIVER points exactly to the bound wallet address:
       0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f

Run:
    python scripts/test_live_system.py

Output:
    PASSED / FAILED in the console.
"""

from __future__ import annotations

import os
import sys
import logging

# ── Ensure project root is on sys.path so `config` and `services` are importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── Load .env if python-dotenv is available (optional, for local testing)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("kristo.test.live_system")

# ── The exact bound address that MUST be used as fallback
BOUND_ADDRESS = "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"


def check_dexscreener_eth_usdc_price() -> dict:
    """
    Test (a): Extract real ETH/USDC price from DEXScreener.
    Returns the price dict. Fails if no price is returned.
    """
    from services.market_data import fetch_eth_usdc_price_dexscreener

    log.info("Test (a): Fetching real ETH/USDC price from DEXScreener...")
    result = fetch_eth_usdc_price_dexscreener()

    price = result.get("price_usd")
    if price is None:
        raise AssertionError(
            "DEXScreener returned no ETH/USDC price — "
            "check network connectivity or API availability."
        )

    log.info("  ✅ ETH/USDC price: $%.4f (dex=%s, liq=$%s)",
             price, result.get("dex"), result.get("liquidity_usd"))
    return result


def check_glm_bulletin(market_data: dict) -> str:
    """
    Test (b): Feed live data to the GLM AI model and generate a short bulletin.
    Returns the bulletin text. Fails if the bulletin is empty.
    """
    from services.ai_engine import generate_market_bulletin

    log.info("Test (b): Generating market bulletin via GLM AI model...")
    bulletin = generate_market_bulletin(market_data)

    if not bulletin or len(bulletin.strip()) < 10:
        raise AssertionError("GLM AI bulletin is empty or too short.")

    log.info("  ✅ Bulletin generated (%d chars): %s",
             len(bulletin), bulletin[:120].replace("\n", " ") + "...")
    return bulletin


def check_base_fee_receiver_address() -> str:
    """
    Test (c): Verify that BASE_FEE_RECEIVER points exactly to the bound address.
    Returns the resolved address. Fails if it doesn't match.
    """
    from config import get_base_fee_receiver, BOUND_BASE_FEE_RECEIVER

    log.info("Test (c): Checking BASE_FEE_RECEIVER address binding...")
    resolved = get_base_fee_receiver()

    # Case-insensitive comparison (Ethereum addresses are case-insensitive
    # for equality, though checksum casing may differ)
    if resolved.lower() != BOUND_ADDRESS.lower():
        raise AssertionError(
            f"BASE_FEE_RECEIVER mismatch!\n"
            f"  Expected: {BOUND_ADDRESS}\n"
            f"  Got:      {resolved}\n"
            f"  Hard fallback in config.py: {BOUND_BASE_FEE_RECEIVER}"
        )

    log.info("  ✅ BASE_FEE_RECEIVER = %s (matches bound address)", resolved)
    return resolved


def main():
    """Run all tests and print PASSED / FAILED."""
    print("\n" + "=" * 70)
    print("  Kristo Intelligence v5 — Live System Test")
    print("=" * 70)

    results = {}

    # ── Test (a): DEXScreener live price ──────────────────────────────────
    try:
        price_data = check_dexscreener_eth_usdc_price()
        results["a_dexscreener_price"] = True
    except Exception as exc:
        log.error("  ❌ Test (a) FAILED: %s", exc)
        results["a_dexscreener_price"] = False
        price_data = None

    # ── Test (b): GLM AI bulletin ──────────────────────────────────────────
    try:
        # Build a minimal market_data dict from the DEXScreener price result
        if price_data and price_data.get("price_usd") is not None:
            market_data = {
                "tokens": {
                    "eth": {
                        "price_usd": price_data.get("price_usd"),
                        "change_24h": None,
                    }
                },
                "fear_greed_index": {"value": None, "classification": None},
                "dex_pairs_base": [
                    {
                        "base_token": "ETH",
                        "dex": price_data.get("dex"),
                        "price_usd": price_data.get("price_usd"),
                        "volume_24h": price_data.get("volume_24h"),
                    }
                ],
            }
        else:
            # Fallback: use the full market snapshot
            from services.market_data import get_market_snapshot
            market_data = get_market_snapshot()

        bulletin = check_glm_bulletin(market_data)
        results["b_glm_bulletin"] = True
    except Exception as exc:
        log.error("  ❌ Test (b) FAILED: %s", exc)
        results["b_glm_bulletin"] = False
        bulletin = None

    # ── Test (c): BASE_FEE_RECEIVER address binding ────────────────────────
    try:
        check_base_fee_receiver_address()
        results["c_fee_receiver"] = True
    except Exception as exc:
        log.error("  ❌ Test (c) FAILED: %s", exc)
        results["c_fee_receiver"] = False

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "-" * 70)
    print("  TEST RESULTS SUMMARY")
    print("-" * 70)
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print("-" * 70)
    if all_passed:
        print("  🎉 OVERALL: ALL TESTS PASSED ✅")
    else:
        print("  ⚠️  OVERALL: SOME TESTS FAILED ❌")
    print("=" * 70 + "\n")

    # Exit code: 0 = success, 1 = failure
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()