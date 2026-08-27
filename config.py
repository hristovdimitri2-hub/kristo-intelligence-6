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

# ── Base network fee receiver (HARD FALLBACK) ──────────────────────────────
# This is the real, bound wallet address that receives the 0.10 USDC
# per-request micro-fee on Base.  It is used unconditionally when the
# BASE_FEE_RECEIVER environment variable is absent or empty.
BOUND_BASE_FEE_RECEIVER = "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"


def get_base_fee_receiver() -> str:
    """
    Return the Base fee-receiver address.

    Priority:
      1. BASE_FEE_RECEIVER env var (if non-empty)
      2. BOUND_BASE_FEE_RECEIVER hard fallback
    """
    env_val = os.getenv("BASE_FEE_RECEIVER", "").strip()
    return env_val if env_val else BOUND_BASE_FEE_RECEIVER


# ── Base network constants ────────────────────────────────────────────────
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
BASE_CHAIN_ID = int(os.getenv("BASE_CHAIN_ID", "8453"))
BASE_USDC_CONTRACT = os.getenv(
    "BASE_USDC_CONTRACT", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
)
BASE_FEE_AMOUNT_USDC = float(os.getenv("BASE_FEE_AMOUNT_USDC", "0.005"))

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
KRISTO_SALES_PRICE = float(os.getenv("KRISTO_SALES_PRICE", "0.05"))        # /api/sales
KRISTO_ARB_PRICE = float(os.getenv("KRISTO_ARB_PRICE", "0.005"))         # /api/arb/opportunities
KRISTO_RUG_PRICE = float(os.getenv("KRISTO_RUG_PRICE", "0.003"))          # rug-risk endpoint
KRISTO_WHALE_PRICE = float(os.getenv("KRISTO_WHALE_PRICE", "0.01"))      # whale activity endpoint