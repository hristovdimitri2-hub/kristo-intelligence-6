"""
Kristo Intelligence v6 — Central Configuration
================================================

Single source of truth for critical constants (wallet addresses, RPC
endpoints, AI model selection, etc.).  Every module that needs these
values should import them from here rather than re-declaring them.

The Base fee-receiver address is bound as a HARD fallback so that even
if the environment variable is missing or empty, the system always
points to the correct on-chain wallet.
"""

from __future__ import annotations

import os

try:
    from eth_utils import to_checksum_address as _checksum
except ImportError:  # config се чете и извън пълния venv — identity fallback
    def _checksum(address: str) -> str:
        return address

# ── Base network fee receiver (HARD FALLBACK) ──────────────────────────────
# This is the real, bound wallet address that receives the per-request
# micro-fee on Base (the amount comes from BASE_FEE_AMOUNT_USDC below and is
# overridden per route by X402_PRICE_MAP — never a literal in this comment).
# It is used unconditionally when the BASE_FEE_RECEIVER environment variable is
# absent or empty.
# EIP-55 canonical form (19.10): the literal below historically carried a
# mismatched-case register; the BYTES are identical (BaseScan-verified — the
# wallet does not change). Normalising here means every consumer (402 header,
# body mirrors, manifests, tests) inherits ONE spelling.
BOUND_BASE_FEE_RECEIVER = _checksum(
    "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f")


def get_base_fee_receiver() -> str:
    """
    Return the Base fee-receiver address in canonical EIP-55 form.

    Priority:
      1. BASE_FEE_RECEIVER env var (if non-empty)
      2. BOUND_BASE_FEE_RECEIVER hard fallback
    Both paths pass through to_checksum_address so a stale-cased env value
    (e.g. set in Render) can never reintroduce the mismatched register.
    """
    env_val = os.getenv("BASE_FEE_RECEIVER", "").strip()
    raw = env_val if env_val else BOUND_BASE_FEE_RECEIVER
    try:
        return _checksum(raw)
    except Exception:
        return raw


# ── Base network constants ────────────────────────────────────────────────
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
BASE_CHAIN_ID = int(os.getenv("BASE_CHAIN_ID", "8453"))
BASE_USDC_CONTRACT = os.getenv(
    "BASE_USDC_CONTRACT", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
)
BASE_FEE_AMOUNT_USDC = float(os.getenv("BASE_FEE_AMOUNT_USDC", "0.005"))

#: Base RPC endpoints to try IN ORDER when the primary does not answer.
#:
#: Added 06.11 after the payment monitor sat uninitialised for over FIFTEEN hours
#: and never recovered on its own: `_init_wallet` had exactly ONE url to try, so a
#: shared public endpoint that rate-limits (429) took the whole payment-detection
#: layer down with it, roughly 25 retries in a row on the same address. The
#: settlement rail has had a three-deep fallback chain for months; a dependency
#: that the entire inbound-payment path rests on deserves the same treatment.
#:
#: The primary is always BASE_RPC_URL and stays first, so nothing changes for an
#: installation that set only that. Override the tail with BASE_RPC_FALLBACKS
#: (comma-separated); an empty or unset value means the defaults below.
DEFAULT_BASE_RPC_FALLBACKS = (
    "https://base.drpc.org",
    "https://base-rpc.publicnode.com",
    "https://1rpc.io/base",
)


def base_rpc_candidates() -> tuple:
    """Every RPC worth trying: the primary first, then the fallbacks.

    Order-preserving and de-duplicated, so an operator who lists the primary
    again in BASE_RPC_FALLBACKS does not make the monitor dial it twice. Read at
    CALL time rather than import time: the monitor re-initialises on a retry, and
    a rotated endpoint must be picked up without a redeploy.
    """
    raw = os.getenv("BASE_RPC_FALLBACKS", "")
    tail = ([u.strip() for u in raw.split(",") if u.strip()]
            if raw.strip() else list(DEFAULT_BASE_RPC_FALLBACKS))
    out = []
    for url in [BASE_RPC_URL] + tail:
        if url and url not in out:
            out.append(url)
    return tuple(out)


# ── OpenAI-compatible AI Engine configuration ─────────────────────────────
# OpenRouter is the default provider; GLM remains supported through the
# existing GLM_* variables for backwards compatibility.
GLM_API_BASE = os.getenv("GLM_API_BASE", "https://openrouter.ai/api/v1")
GLM_API_KEY = os.getenv("GLM_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
GLM_MODEL = os.getenv("GLM_MODEL", "openai/gpt-4o-mini")


# ── x402 Product Prices ───────────────────────────────────────────────────
# Single source of pricing truth for all endpoints.
# These defaults can be overridden via environment variables.
KRISTO_STATS_PRICE = float(os.getenv("KRISTO_STATS_PRICE", "0.005"))       # /api/stats
KRISTO_SALES_PRICE = float(os.getenv("KRISTO_SALES_PRICE", "0.005"))       # /api/sales
KRISTO_ARB_PRICE = float(os.getenv("KRISTO_ARB_PRICE", "0.005"))         # /api/arb/opportunities
KRISTO_RUG_PRICE = float(os.getenv("KRISTO_RUG_PRICE", "0.003"))          # rug-risk endpoint
KRISTO_WHALE_PRICE = float(os.getenv("KRISTO_WHALE_PRICE", "0.01"))      # whale activity endpoint
KRISTO_SIGNAL_PRICE = float(os.getenv("KRISTO_SIGNAL_PRICE", "0.003"))   # /api/v1/signal
# Whale flow feed (built 09.09 per docs/WHALE_FLOW_SPEC.md — owner-approved).
# Kept at the canary-proven price tier. Existing prices are NOT touched.
KRISTO_WHALEFLOW_PRICE = float(os.getenv("KRISTO_WHALEFLOW_PRICE", "0.003"))

# ── Seller verification: the first product priced above $1 ────────────────
# This is the arbitrary-receiver audit. It reads the chain for ANY address a
# caller names, so unlike every route above it is not a cached lookup: a 7-day
# window is thousands of adaptive eth_getLogs chunks, and the price has to cover
# real RPC work.
#
# $1.00 is not a guess. A census of 143.8M x402 settlements (Zenodo
# 10.5281/zenodo.22726373, "Sub-Dollar Machine Commerce") puts the volume-weighted
# average payment at $0.27, and finds that payments of $1 or more carry 72.5% of
# all value from under 8% of the traffic: the sub-dollar tier is where our
# existing $0.003-$0.005 routes live, and the top 1% of merchants take 93.0% of
# revenue. Pricing this at $0.003 would put us below the median list price of
# $0.01 while doing the most expensive work we offer.
#
# It also prices in the abuse the free surface is deliberately shaped to avoid.
# Owners' reasoning for fixing the free audit to our own receiver was that an
# open one would let a single caller aim it at 1000 addresses and burn the RPC.
# At $1.00 that caller pays $1000 to do it, which is a deterrent; at a cent it
# is an invitation.
#
# Overridable like every other price, and it does not touch an existing one.
KRISTO_VERIFY_SELLER_PRICE = float(
    os.getenv("KRISTO_VERIFY_SELLER_PRICE", "1.00"))     # /api/v1/verify-seller

# ── Human products (NOT x402 routes) ──────────────────────────────────────
# The Telegram VIP-analysis unlock is paid in USDC like a route but is a HUMAN
# product, so it is deliberately NOT in X402_PRICE_MAP. It lives here anyway so
# the bot's button and message can never quote a number of their own.
KRISTO_VIP_ANALYSIS_PRICE = float(
    os.getenv("KRISTO_VIP_ANALYSIS_PRICE", "0.10"))          # Telegram VIP unlock