"""
CoinGecko price client for Kristo Intelligence v5.

Uses the public CoinGecko API by default. If a Base44 API key is provided,
requests are routed/authenticated per Base44 guidance so the client can
benefit from higher rate limits and unified access. If the Base44 proxy
is unavailable or returns an error, the client transparently falls back
to the public CoinGecko endpoint so prices are always available.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List

import requests

log = logging.getLogger("kristo.v5.coingecko")

# Base44-guided token list (CoinGecko ids).
SUPPORTED_TOKENS = {
    "eth": "ethereum",
    "ondo": "ondo-finance",
    "kaito": "kaito",
    "degen": "degen-base",
}

_COINGECKO_PUBLIC = "https://api.coingecko.com/api/v3"
_BASE44_PROXY = os.getenv("BASE44_API_BASE", "https://api.base44.com")


class CoinGeckoClient:
    """Thin, resilient CoinGecko client with Base44 proxy + public fallback."""

    def __init__(self, api_key: str = "", timeout: int = 15):
        self.api_key = api_key
        self.timeout = timeout
        self._session = requests.Session()
        # If the Base44 proxy fails once, skip it for the rest of the session.
        self._base44_available = bool(api_key)

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------
    def _get(self, path: str, params: dict | None = None) -> dict:
        params = params or {}
        headers = {"accept": "application/json"}

        # Try Base44 proxy first if a key is configured and it's still available.
        if self.api_key and self._base44_available:
            url = f"{_BASE44_PROXY}/coingecko{path}"
            headers["Authorization"] = f"Bearer {self.api_key}"
            try:
                resp = self._session.get(url, params=params, headers=headers, timeout=self.timeout)
                if resp.ok:
                    return resp.json()
                # 404 / 401 / 403 -> proxy endpoint not available; fall back.
                log.debug("Base44 proxy returned %s — falling back to public API.", resp.status_code)
                self._base44_available = False
            except Exception as exc:
                log.debug("Base44 proxy request failed (%s) — falling back to public API.", exc)
                self._base44_available = False

        # Public CoinGecko fallback (always works without a key).
        url = f"{_COINGECKO_PUBLIC}{path}"
        # Optional: attach CoinGecko demo/pro key if set separately.
        cg_key = os.getenv("COINGECKO_API_KEY", "").strip()
        if cg_key:
            headers["x-cg-demo-api-key"] = cg_key
        resp = self._session.get(url, params=params, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_prices(self, tokens: List[str]) -> Dict[str, float | None]:
        """
        Return a mapping {token_symbol: usd_price} for the requested tokens.
        Unknown tokens are returned as None.
        """
        ids = []
        symbol_to_id = {}
        for sym in tokens:
            cid = SUPPORTED_TOKENS.get(sym.lower())
            if cid:
                ids.append(cid)
                symbol_to_id[sym.lower()] = cid

        if not ids:
            return {sym: None for sym in tokens}

        try:
            data = self._get(
                "/simple/price",
                params={"ids": ",".join(ids), "vs_currencies": "usd"},
            )
        except Exception as exc:
            log.error("CoinGecko request failed: %s", exc)
            return {sym: None for sym in tokens}

        result: Dict[str, float | None] = {}
        for sym in tokens:
            cid = symbol_to_id.get(sym.lower())
            if cid and cid in data:
                result[sym] = data[cid].get("usd")
            else:
                result[sym] = None
        return result

    def get_price(self, token: str) -> float | None:
        """Convenience: single token price."""
        return self.get_prices([token]).get(token.lower())