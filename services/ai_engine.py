"""
GLM AI Engine — Market Analysis Generator
==========================================

Uses the GLM model (Zhipu AI / BigModel) to generate concise market
bulletins from real-time price data.

The GLM API is OpenAI-compatible (chat/completions endpoint), so we
use plain `requests` — no heavy SDK dependency required.

If GLM_API_KEY is not configured, a deterministic offline fallback
bulletin is generated so the system never blocks.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from config import GLM_API_BASE, GLM_API_KEY, GLM_MODEL

log = logging.getLogger("kristo.v6.ai_engine")


def generate_market_bulletin(market_data: dict) -> str:
    """
    Generate a short market bulletin using the GLM model.

    Parameters
    ----------
    market_data : dict
        Real-time market data (prices, changes, fear & greed, etc.)
        as returned by `services.market_data`.

    Returns
    -------
    str
        A concise market analysis bulletin (2-4 sentences).
    """
    # Build a compact prompt from the market data
    tokens = market_data.get("tokens", {}) or {}
    eth = tokens.get("eth", {})
    eth_price = eth.get("price_usd")
    eth_change = eth.get("change_24h")

    fng = market_data.get("fear_greed_index", {}) or {}
    fng_value = fng.get("value")
    fng_class = fng.get("classification")

    dex_pairs = market_data.get("dex_pairs_base", []) or []
    top_pair = dex_pairs[0] if dex_pairs else {}

    prompt_data = (
        f"ETH price: ${eth_price} (24h change: {eth_change}%)\n"
        f"Fear & Greed Index: {fng_value} ({fng_class})\n"
        f"Top Base DEX pair: {top_pair.get('base_token', 'N/A')} "
        f"on {top_pair.get('dex', 'N/A')} — "
        f"price ${top_pair.get('price_usd', 'N/A')}, "
        f"24h vol ${top_pair.get('volume_24h', 'N/A')}\n"
    )

    # ── Try GLM API ──────────────────────────────────────────────────────
    if GLM_API_KEY:
        try:
            return _call_glm(prompt_data)
        except Exception as exc:
            log.warning("GLM API call failed, using offline fallback: %s", exc)

    # ── Offline fallback (deterministic, no demo data) ───────────────────
    return _offline_bulletin(eth_price, eth_change, fng_value, fng_class)


def _call_glm(prompt_data: str) -> str:
    """Call the GLM chat/completions API and return the generated text."""
    system_msg = (
        "Ти си финансов анализатор. Генерирай кратък пазарен бюлетин "
        "(2-4 изречения) на български въз основа на подадените реални "
        "пазарни данни. Не използвай демо данни."
    )
    user_msg = f"Реални пазарни данни:\n{prompt_data}\nГенерирай бюлетин:"

    resp = requests.post(
        f"{GLM_API_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {GLM_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GLM_MODEL,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.7,
            "max_tokens": 300,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()
    log.info("GLM bulletin generated (model=%s, %d chars)", GLM_MODEL, len(content))
    return content


def _offline_bulletin(eth_price, eth_change, fng_value, fng_class) -> str:
    """Deterministic fallback bulletin when GLM API is unavailable."""
    eth_str = f"${eth_price:,.2f}" if eth_price is not None else "N/A"
    change_str = f"{eth_change:+.2f}%" if eth_change is not None else "N/A"
    fng_str = f"{fng_value} ({fng_class})" if fng_value is not None else "N/A"

    return (
        f"📊 Пазарен бюлетин (офлайн резерв): ETH се търгува на {eth_str} "
        f"с 24ч промяна {change_str}. Индексът Fear & Greed е {fng_str}. "
        f"Данните са реални, но GLM AI моделът не е наличен в момента."
    )