"""
DeFi signal generator for Kristo Intelligence v5.

Base44-guided signal set covering:
  * ETH   — Ethereum core
  * ONDO  — RWA / tokenized treasuries
  * KAITO — info-financial / attention-weighted AI
  * DEGEN — Base-native social/meme

Each signal carries a directional bias, confidence, and a short rationale
aligned with Base44 guidance.
"""

from __future__ import annotations

import logging
from typing import Dict, List

log = logging.getLogger("kristo.v5.defi")

# Base44-guided baseline signals. These are static defaults that can be
# enriched by live CoinGecko prices and Base44 API data at runtime.
_BASE44_SIGNALS: Dict[str, dict] = {
    "eth": {
        "symbol": "ETH",
        "bias": "BULLISH",
        "confidence": 0.78,
        "narrative": "Core L1 / gas asset on Base; staking yield + L2 adoption.",
        "action": "accumulate_on_dips",
    },
    "ondo": {
        "symbol": "ONDO",
        "bias": "BULLISH",
        "confidence": 0.72,
        "narrative": "RWA leader; tokenized treasuries gaining institutional flow.",
        "action": "hold_or_add",
    },
    "kaito": {
        "symbol": "KAITO",
        "bias": "NEUTRAL-BULLISH",
        "confidence": 0.61,
        "narrative": "Info-financial AI / attention-weighted indexing; watch liquidity.",
        "action": "monitor",
    },
    "degen": {
        "symbol": "DEGEN",
        "bias": "SPECULATIVE",
        "confidence": 0.45,
        "narrative": "Base-native social token; high volatility, size small.",
        "action": "small_allocation_only",
    },
}


class DeFiSignalGenerator:
    """Generates DeFi trading signals, optionally enriched via Base44."""

    def __init__(self, api_key: str = "", tokens: List[str] | None = None):
        self.api_key = api_key
        self.tokens = tokens or ["eth", "ondo", "kaito", "degen"]

    def generate_signals(self) -> Dict[str, dict]:
        """
        Return a dict {token: signal_dict}. If a Base44 API key is configured,
        we attempt to enrich each signal with live metadata; on any failure
        we gracefully fall back to the Base44-guided baseline.
        """
        signals: Dict[str, dict] = {}
        for tok in self.tokens:
            base = _BASE44_SIGNALS.get(tok.lower())
            if base is None:
                log.warning("No Base44 baseline signal for %s — skipping.", tok)
                continue
            enriched = dict(base)
            if self.api_key:
                enriched = self._enrich_from_base44(tok, enriched)
            signals[tok.lower()] = enriched
        return signals

    # ------------------------------------------------------------------
    # Base44 enrichment (best-effort)
    # ------------------------------------------------------------------
    def _enrich_from_base44(self, token: str, signal: dict) -> dict:
        try:
            import requests
            base = __import__("os").getenv("BASE44_API_BASE", "https://api.base44.com")
            url = f"{base}/defi/signals/{token.lower()}"
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=15,
            )
            if resp.ok:
                data = resp.json()
                # Merge any returned fields, but keep our schema stable.
                if isinstance(data, dict):
                    for k in ("confidence", "bias", "narrative", "action"):
                        if k in data:
                            signal[k] = data[k]
                    signal["source"] = "base44-live"
                return signal
            log.debug("Base44 enrichment for %s returned %s", token, resp.status_code)
        except Exception as exc:
            log.debug("Base44 enrichment failed for %s: %s", token, exc)
        signal["source"] = "base44-baseline"
        return signal