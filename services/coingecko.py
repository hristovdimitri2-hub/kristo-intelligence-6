"""
CoinGecko price client for Kristo Intelligence v6.

Uses the public CoinGecko API by default. If a Base44 API key is provided,
requests are routed/authenticated per Base44 guidance so the client can
benefit from higher rate limits and unified access. If the Base44 proxy
is unavailable or returns an error, the client transparently falls back
to the public CoinGecko endpoint so prices are always available.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Dict, List, Optional

import requests

log = logging.getLogger("kristo.v6.coingecko")

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

    _price_cache: Dict[tuple[str, ...], dict] = {}
    _cache_lock = threading.RLock()
    _cooldown_until = 0.0
    _cache_ttl_seconds = max(1, int(os.getenv("MARKET_DATA_CACHE_TTL_SECONDS", "900")))
    _stale_ttl_seconds = max(60, int(os.getenv("MARKET_DATA_STALE_TTL_SECONDS", "21600")))
    _max_attempts = max(1, int(os.getenv("COINGECKO_MAX_ATTEMPTS", "2")))
    _backoff_base_seconds = max(0.0, float(os.getenv("COINGECKO_BACKOFF_BASE_SECONDS", "0.25")))
    _backoff_max_seconds = max(
        _backoff_base_seconds,
        float(os.getenv("COINGECKO_BACKOFF_MAX_SECONDS", "2")),
    )
    _cooldown_max_seconds = max(
        _backoff_max_seconds,
        float(os.getenv("COINGECKO_COOLDOWN_MAX_SECONDS", "120")),
    )

    def __init__(self, api_key: str = "", timeout: Optional[int] = None):
        self.api_key = api_key
        self.timeout = timeout or max(1, int(os.getenv("COINGECKO_TIMEOUT_SECONDS", "5")))
        self._session = requests.Session()
        self.last_price_status: dict = {"state": "unavailable", "age_seconds": None}
        # If the Base44 proxy fails once, skip it for the rest of the session.
        self._base44_available = bool(api_key)

    @classmethod
    def _cached_prices(cls, cache_key: tuple[str, ...], *, allow_stale: bool = False):
        with cls._cache_lock:
            entry = cls._price_cache.get(cache_key)
            if not entry:
                return None
            age = max(0, int(time.monotonic() - entry["stored_at"]))
            if age < cls._cache_ttl_seconds or (allow_stale and age < cls._stale_ttl_seconds):
                return dict(entry["data"]), age
        return None

    @classmethod
    def _set_cached_prices(cls, cache_key: tuple[str, ...], data: Dict[str, float | None]) -> None:
        with cls._cache_lock:
            # The agent has a small fixed token set; keeping this bounded also
            # protects long-running workers from arbitrary input growth.
            if cache_key not in cls._price_cache and len(cls._price_cache) >= 32:
                oldest_key = min(cls._price_cache, key=lambda item: cls._price_cache[item]["stored_at"])
                cls._price_cache.pop(oldest_key, None)
            cls._price_cache[cache_key] = {"data": dict(data), "stored_at": time.monotonic()}

    def _public_get_with_backoff(self, path: str, params: dict, headers: dict) -> dict:
        """Bound public API retries and cool down after a 429 response."""
        cls = type(self)
        with cls._cache_lock:
            if time.monotonic() < cls._cooldown_until:
                raise RuntimeError("CoinGecko rate-limit cooldown is active")

        last_error: Optional[Exception] = None
        for attempt in range(cls._max_attempts):
            response = None
            try:
                response = self._session.get(
                    f"{_COINGECKO_PUBLIC}{path}",
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    raise requests.HTTPError("CoinGecko rate limited", response=response)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_error = exc
                status_code = getattr(getattr(exc, "response", response), "status_code", None)
                if status_code == 429:
                    retry_after = (getattr(response, "headers", {}) or {}).get("Retry-After")
                    try:
                        cooldown = min(
                            cls._cooldown_max_seconds,
                            max(cls._backoff_max_seconds, float(retry_after)),
                        )
                    except (TypeError, ValueError):
                        cooldown = cls._backoff_max_seconds
                    with cls._cache_lock:
                        cls._cooldown_until = time.monotonic() + cooldown
                    break
                retryable = status_code == 429 or status_code is None or status_code >= 500
                if not retryable or attempt + 1 >= cls._max_attempts:
                    break
                delay = min(cls._backoff_max_seconds, cls._backoff_base_seconds * (2 ** attempt))
                delay = min(cls._backoff_max_seconds, delay + random.uniform(0, delay * 0.25))
                if delay:
                    time.sleep(delay)

        raise last_error or RuntimeError("CoinGecko request failed")

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
        return self._public_get_with_backoff(path, params, headers)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_prices(self, tokens: List[str]) -> Dict[str, float | None]:
        """
        Return a mapping {token_symbol: usd_price} for the requested tokens.
        Unknown tokens are returned as None.
        """
        cache_key = tuple(sorted(sym.lower() for sym in tokens))
        cached = self._cached_prices(cache_key)
        if cached is not None:
            data, age = cached
            self.last_price_status = {"state": "cached", "age_seconds": age}
            return data

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
            stale = self._cached_prices(cache_key, allow_stale=True)
            if stale is not None:
                data, age = stale
                self.last_price_status = {"state": "stale", "age_seconds": age}
                return data
            self.last_price_status = {"state": "unavailable", "age_seconds": None}
            return {sym: None for sym in tokens}

        result: Dict[str, float | None] = {}
        for sym in tokens:
            cid = symbol_to_id.get(sym.lower())
            if cid and cid in data:
                result[sym] = data[cid].get("usd")
            else:
                result[sym] = None
        self._set_cached_prices(cache_key, result)
        self.last_price_status = {"state": "live", "age_seconds": 0}
        return result

    def get_price(self, token: str) -> float | None:
        """Convenience: single token price."""
        return self.get_prices([token]).get(token.lower())