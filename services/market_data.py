"""
Real-time market data integration for Kristo Intelligence v6.

Fetches live data from three public, free API sources:
  * CoinGecko Free API  — token prices, market caps, 24h change
  * DEXScreener API     — on-chain DEX pair data (Base network)
  * Fear & Greed Index  — market sentiment (0-100)

All requests use a short timeout and graceful fallback so the API
never blocks if an upstream source is temporarily unavailable.

TTL caching of 15 minutes ensures we stay well within free API rate
limits while data still refreshes automatically 24/7.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

log = logging.getLogger("kristo.v6.market_data")

# ── API endpoints (all free, no key required) ──────────────────────────────
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DEXSCREENER_BASE = "https://api.dexscreener.com"
FNG_BASE = "https://api.alternative.me"

# Bounded, thread-safe cache. Successful CoinGecko responses are retained
# longer than their fresh TTL so a rate-limited request can return explicitly
# marked stale data instead of pretending the market has no values.
_CACHE: Dict[str, dict] = {}
_CACHE_LOCK = threading.RLock()
_COINGECKO_REFRESH_LOCK = threading.Lock()
_CACHE_TTL = timedelta(seconds=max(1, int(os.getenv("MARKET_DATA_CACHE_TTL_SECONDS", "900"))))
_STALE_CACHE_TTL = timedelta(seconds=max(60, int(os.getenv("MARKET_DATA_STALE_TTL_SECONDS", "21600"))))
_CACHE_MAX_ENTRIES = max(8, int(os.getenv("MARKET_DATA_CACHE_MAX_ENTRIES", "64")))
_COINGECKO_MAX_ATTEMPTS = max(1, int(os.getenv("COINGECKO_MAX_ATTEMPTS", "2")))
_COINGECKO_TIMEOUT_SECONDS = max(1, int(os.getenv("COINGECKO_TIMEOUT_SECONDS", "5")))
_COINGECKO_BACKOFF_BASE_SECONDS = max(0.0, float(os.getenv("COINGECKO_BACKOFF_BASE_SECONDS", "0.25")))
_COINGECKO_BACKOFF_MAX_SECONDS = max(
    _COINGECKO_BACKOFF_BASE_SECONDS,
    float(os.getenv("COINGECKO_BACKOFF_MAX_SECONDS", "2")),
)
_COINGECKO_COOLDOWN_MAX_SECONDS = max(
    _COINGECKO_BACKOFF_MAX_SECONDS,
    float(os.getenv("COINGECKO_COOLDOWN_MAX_SECONDS", "120")),
)
_COINGECKO_COOLDOWN_UNTIL: Optional[datetime] = None
_COINGECKO_STATUS: Dict[str, dict] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cache_entry(key: str) -> Optional[dict]:
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        return dict(entry) if entry else None


def _cache_age_seconds(key: str, now: Optional[datetime] = None) -> Optional[int]:
    entry = _cache_entry(key)
    if not entry:
        return None
    return max(0, int(((now or _now()) - entry["ts"]).total_seconds()))


def _cached(key: str, *, allow_stale: bool = False):
    """Return a fresh cache value, or a bounded stale value when requested."""
    entry = _cache_entry(key)
    if not entry:
        return None

    age = _now() - entry["ts"]
    if age < _CACHE_TTL or (allow_stale and age < _STALE_CACHE_TTL):
        return entry["data"]
    return None


def _set_cache(key: str, data):
    with _CACHE_LOCK:
        if key not in _CACHE and len(_CACHE) >= _CACHE_MAX_ENTRIES:
            oldest_key = min(_CACHE, key=lambda item: _CACHE[item]["ts"])
            _CACHE.pop(oldest_key, None)
        _CACHE[key] = {"ts": _now(), "data": data}


def _set_coingecko_status(key: str, state: str, *, detail: str = "") -> None:
    with _CACHE_LOCK:
        _COINGECKO_STATUS[key] = {
            "state": state,
            "age_seconds": _cache_age_seconds(key),
            "last_success_at": (
                _cache_entry(key)["ts"].isoformat() if _cache_entry(key) else None
            ),
            "detail": detail,
        }


def _retry_after_seconds(response, fallback: float) -> float:
    """Honor a server retry hint without an unbounded cooldown."""
    raw = (getattr(response, "headers", {}) or {}).get("Retry-After")
    try:
        return min(_COINGECKO_COOLDOWN_MAX_SECONDS, max(fallback, float(raw)))
    except (TypeError, ValueError):
        return fallback


def _set_coingecko_cooldown(delay_seconds: float) -> None:
    global _COINGECKO_COOLDOWN_UNTIL
    with _CACHE_LOCK:
        _COINGECKO_COOLDOWN_UNTIL = _now() + timedelta(seconds=delay_seconds)


def _coingecko_cooldown_active() -> bool:
    with _CACHE_LOCK:
        return bool(_COINGECKO_COOLDOWN_UNTIL and _now() < _COINGECKO_COOLDOWN_UNTIL)


def _coingecko_request(cache_key: str, path: str, *, params: Optional[dict] = None) -> Optional[dict]:
    """
    Fetch one CoinGecko resource with cache-first reads and bounded retries.

    A process-wide refresh lock prevents concurrent Telegram/dashboard requests
    from fanning one expired cache entry into a burst of CoinGecko calls.
    """
    cached = _cached(cache_key)
    if cached is not None:
        _set_coingecko_status(cache_key, "cached")
        return cached

    stale = _cached(cache_key, allow_stale=True)
    if _coingecko_cooldown_active():
        if stale is not None:
            _set_coingecko_status(cache_key, "stale", detail="rate-limit cooldown")
            return stale
        _set_coingecko_status(cache_key, "unavailable", detail="rate-limit cooldown")
        return None

    with _COINGECKO_REFRESH_LOCK:
        # Another thread may have refreshed this exact resource while we waited.
        cached = _cached(cache_key)
        if cached is not None:
            _set_coingecko_status(cache_key, "cached")
            return cached

        stale = _cached(cache_key, allow_stale=True)
        if _coingecko_cooldown_active():
            if stale is not None:
                _set_coingecko_status(cache_key, "stale", detail="rate-limit cooldown")
                return stale
            _set_coingecko_status(cache_key, "unavailable", detail="rate-limit cooldown")
            return None

        # When a usable stale snapshot exists, one failed refresh is enough:
        # return it immediately rather than holding a Telegram response open
        # for another network timeout. A cold cache still uses bounded retries.
        attempt_limit = 1 if stale is not None else _COINGECKO_MAX_ATTEMPTS
        last_error = ""
        for attempt in range(attempt_limit):
            response = None
            try:
                response = requests.get(
                    f"{COINGECKO_BASE}{path}",
                    params=params,
                    headers={"accept": "application/json"},
                    timeout=_COINGECKO_TIMEOUT_SECONDS,
                )
                if getattr(response, "status_code", None) == 429:
                    raise requests.HTTPError("CoinGecko rate limited", response=response)
                response.raise_for_status()
                data = response.json()
                _set_cache(cache_key, data)
                _set_coingecko_status(cache_key, "live")
                return data
            except Exception as exc:
                last_error = str(exc)
                status_code = getattr(getattr(exc, "response", response), "status_code", None)
                if status_code == 429:
                    cooldown = _retry_after_seconds(
                        response,
                        _COINGECKO_BACKOFF_MAX_SECONDS,
                    )
                    _set_coingecko_cooldown(cooldown)
                    # A 429 is an explicit instruction to stop requesting.
                    # Returning stale data is both faster for the caller and
                    # avoids extending the provider's throttle window.
                    break
                is_retryable = status_code == 429 or status_code is None or status_code >= 500
                if not is_retryable or attempt + 1 >= attempt_limit:
                    break
                delay = min(
                    _COINGECKO_BACKOFF_MAX_SECONDS,
                    _COINGECKO_BACKOFF_BASE_SECONDS * (2 ** attempt),
                )
                delay = _retry_after_seconds(response, delay)
                # A small bounded jitter keeps multiple workers from retrying in lockstep.
                delay = min(_COINGECKO_BACKOFF_MAX_SECONDS, delay + random.uniform(0, delay * 0.25))
                if delay:
                    time.sleep(delay)

        if stale is not None:
            log.warning("CoinGecko %s failed; serving stale cache: %s", path, last_error)
            _set_coingecko_status(cache_key, "stale", detail="upstream request failed")
            return stale

        log.warning("CoinGecko %s unavailable: %s", path, last_error)
        _set_coingecko_status(cache_key, "unavailable", detail="upstream request failed")
        return None


def get_coingecko_cache_status(cache_keys: Optional[List[str]] = None) -> dict:
    """Return safe freshness metadata for API and dashboard consumers."""
    keys = cache_keys or [key for key in _COINGECKO_STATUS]
    with _CACHE_LOCK:
        now = _now()
        statuses = []
        for key in keys:
            status = _COINGECKO_STATUS.get(key)
            if not status:
                continue
            entry = _CACHE.get(key)
            current = dict(status)
            if entry:
                age_seconds = max(0, int((now - entry["ts"]).total_seconds()))
                current["age_seconds"] = age_seconds
                current["last_success_at"] = entry["ts"].isoformat()
                if age_seconds >= int(_STALE_CACHE_TTL.total_seconds()):
                    current["state"] = "unavailable"
                    current["detail"] = "cached snapshot expired"
                elif age_seconds >= int(_CACHE_TTL.total_seconds()):
                    current["state"] = "stale"
                elif current["state"] == "live" and age_seconds > 0:
                    current["state"] = "cached"
            statuses.append(current)

    if not statuses:
        return {
            "state": "unavailable",
            "age_seconds": None,
            "last_success_at": None,
            "detail": "no successful CoinGecko snapshot yet",
        }

    states = {status["state"] for status in statuses}
    if "unavailable" in states:
        state = "unavailable"
    elif "stale" in states:
        state = "stale"
    elif "cached" in states:
        state = "cached"
    else:
        state = "live"

    ages = [status["age_seconds"] for status in statuses if status["age_seconds"] is not None]
    last_successes = [status["last_success_at"] for status in statuses if status["last_success_at"]]
    details = sorted({status["detail"] for status in statuses if status["detail"]})
    return {
        "state": state,
        "age_seconds": max(ages) if ages else None,
        "last_success_at": min(last_successes) if last_successes else None,
        "detail": "; ".join(details),
    }


# ── CoinGecko: prices + market data ────────────────────────────────────────

# CoinGecko coin IDs for tokens we track
COINGECKO_IDS = {
    "eth": "ethereum",
    "usdc": "usd-coin",
    "degen": "degen-base",
    "brett": "brett-based",
    "aero": "aerodrome-finance",
    "ondo": "ondo-finance",
    "kaito": "kaito",
    "cbeth": "coinbase-wrapped-staked-eth",
}


def fetch_coingecko_prices(tokens: Optional[List[str]] = None) -> Dict[str, dict]:
    """
    Fetch real-time prices and 24h change from CoinGecko Free API.

    Returns: {symbol: {price_usd, market_cap, volume_24h, change_24h}}
    """
    cache_key = f"cg_prices_{','.join(sorted(tokens or []))}"
    tokens = tokens or list(COINGECKO_IDS.keys())
    ids = [COINGECKO_IDS[t] for t in tokens if t in COINGECKO_IDS]
    if not ids:
        return {}

    data = _coingecko_request(
        cache_key,
        "/simple/price",
        params={
            "ids": ",".join(ids),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
        },
    )
    if data is None:
        return {}

    result: Dict[str, dict] = {}
    for sym, cid in COINGECKO_IDS.items():
        if sym not in tokens:
            continue
        if cid in data:
            result[sym] = {
                "price_usd": data[cid].get("usd"),
                "change_24h": data[cid].get("usd_24h_change"),
                "market_cap": data[cid].get("usd_market_cap"),
                "volume_24h": data[cid].get("usd_24h_vol"),
            }
    log.info("CoinGecko prices available for %d tokens (%s)", len(result), get_coingecko_cache_status([cache_key])["state"])
    return result


def fetch_coingecko_trending() -> List[dict]:
    """Fetch trending coins from CoinGecko (free, no key)."""
    data = _coingecko_request("cg_trending", "/search/trending")
    if data is None:
        return []

    coins = []
    for item in (data.get("coins") or [])[:7]:
        coin = item.get("item", {})
        coins.append({
            "id": coin.get("id"),
            "name": coin.get("name"),
            "symbol": coin.get("symbol"),
            "market_cap_rank": coin.get("market_cap_rank"),
            "score": coin.get("score"),
            "thumb": coin.get("thumb"),
        })
    return coins


def fetch_coingecko_global() -> dict:
    """Fetch global crypto market data from CoinGecko."""
    data = _coingecko_request("cg_global", "/global")
    if data is None:
        return {}

    global_data = data.get("data", {})
    return {
        "total_market_cap_usd": global_data.get("total_market_cap", {}).get("usd"),
        "total_volume_24h_usd": global_data.get("total_volume", {}).get("usd"),
        "market_cap_change_24h": global_data.get("market_cap_change_percentage_24h_usd"),
        "btc_dominance": global_data.get("market_cap_percentage", {}).get("btc"),
        "eth_dominance": global_data.get("market_cap_percentage", {}).get("eth"),
        "active_cryptocurrencies": global_data.get("active_cryptocurrencies"),
    }

# ── DEXScreener: on-chain DEX pairs on Base ───────────────────────────────

def fetch_dexscreener_pairs(chain: str = "base", limit: int = 10) -> List[dict]:
    """
    Fetch trending/recent DEX pairs from DEXScreener for the Base network.

    Returns a list of normalized pair dicts.
    """
    cache_key = f"dex_{chain}_{limit}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        # DEXScreener endpoint for trending pairs by chain
        resp = requests.get(
            f"{DEXSCREENER_BASE}/token-pairs/v1/{chain}",
            headers={"accept": "application/json"},
            timeout=10,
        )
        if not resp.ok:
            # Fallback: search for popular Base tokens
            resp = requests.get(
                f"{DEXSCREENER_BASE}/latest/dex/search",
                params={"q": "Base"},
                headers={"accept": "application/json"},
                timeout=10,
            )
        resp.raise_for_status()
        raw = resp.json()

        # Normalize — DEXScreener returns list of pair objects
        pairs_raw = raw if isinstance(raw, list) else raw.get("pairs", [])
        pairs: List[dict] = []
        for p in pairs_raw[:limit]:
            pairs.append({
                "pair_address": p.get("pairAddress"),
                "base_token": p.get("baseToken", {}).get("symbol"),
                "base_token_name": p.get("baseToken", {}).get("name"),
                "quote_token": p.get("quoteToken", {}).get("symbol"),
                "dex": p.get("dexId"),
                "price_usd": p.get("priceUsd"),
                "volume_24h": p.get("volume", {}).get("h24"),
                "liquidity_usd": p.get("liquidity", {}).get("usd"),
                "fdv": p.get("fdv"),
                "pair_created_at": p.get("pairCreatedAt"),
                "url": p.get("url"),
            })
        _set_cache(cache_key, pairs)
        log.info("DEXScreener: %d pairs fetched for %s", len(pairs), chain)
        return pairs
    except Exception as exc:
        log.warning("DEXScreener fetch failed: %s", exc)
        return []


def fetch_dexscreener_token(token_address: str) -> List[dict]:
    """Fetch DEX pairs for a specific token contract address from DEXScreener."""
    cache_key = f"dex_token_{token_address}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            f"{DEXSCREENER_BASE}/tokens/v1/{token_address}",
            headers={"accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()
        pairs = raw if isinstance(raw, list) else raw.get("pairs", [])
        _set_cache(cache_key, pairs[:10])
        return pairs[:10]
    except Exception as exc:
        log.warning("DEXScreener token fetch failed for %s: %s", token_address, exc)
        return []


# ── Fear & Greed Index ─────────────────────────────────────────────────────

def fetch_fear_greed() -> dict:
    """
    Fetch the current Crypto Fear & Greed Index from alternative.me.

    Returns: {value, classification, timestamp}
    """
    cached = _cached("fng")
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            f"{FNG_BASE}/fng/",
            params={"limit": 1},
            headers={"accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        entry = (data.get("data") or [{}])[0]
        result = {
            "value": int(entry["value"]) if entry.get("value") else None,
            "classification": entry.get("value_classification"),
            "timestamp": entry.get("timestamp"),
        }
        _set_cache("fng", result)
        log.info("Fear & Greed Index: %s (%s)", result["value"], result["classification"])
        return result
    except Exception as exc:
        log.warning("Fear & Greed fetch failed: %s", exc)
        return {"value": None, "classification": None, "timestamp": None}


# ── ETH/USDC live price from DEXScreener ────────────────────────────────────

# WETH token contract on Base (used to find ETH/USDC pairs on DEXScreener)
WETH_BASE_CONTRACT = "0x4200000000000000000000000000000000000006"


def fetch_eth_usdc_price_dexscreener() -> dict:
    """
    Fetch the real-time ETH/USDC price directly from DEXScreener.

    Queries the DEXScreener token endpoint for WETH on Base and finds
    the pair with the highest liquidity that quotes ETH against USDC.

    Returns a dict:
      {
        "price_usd": float | None,
        "pair_address": str | None,
        "dex": str | None,
        "liquidity_usd": float | None,
        "volume_24h": float | None,
        "source": "dexscreener"
      }

    NO DEMO DATA — if the API call fails, price_usd is None.
    """
    cache_key = "dex_eth_usdc_live"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    result = {
        "price_usd": None,
        "pair_address": None,
        "dex": None,
        "liquidity_usd": None,
        "volume_24h": None,
        "source": "dexscreener",
    }

    try:
        # DEXScreener v2 endpoint: latest/dex/tokens/{tokenAddress}
        # Returns all DEX pairs for the given token across all chains.
        resp = requests.get(
            f"{DEXSCREENER_BASE}/latest/dex/tokens/{WETH_BASE_CONTRACT}",
            headers={"accept": "application/json"},
            timeout=10,
        )
        if not resp.ok:
            # Fallback: search endpoint
            resp = requests.get(
                f"{DEXSCREENER_BASE}/latest/dex/search",
                params={"q": "WETH USDC Base"},
                headers={"accept": "application/json"},
                timeout=10,
            )
        resp.raise_for_status()
        raw = resp.json()
        # The search endpoint returns {"pairs": [...]}, the tokens endpoint returns a list
        pairs = raw if isinstance(raw, list) else raw.get("pairs", [])

        # Find the best ETH/USDC pair (highest liquidity, quote token = USDC)
        best = None
        best_liq = -1
        for p in pairs:
            quote = (p.get("quoteToken", {}) or {}).get("symbol", "")
            if quote.upper() == "USDC":
                liq = (p.get("liquidity", {}) or {}).get("usd", 0) or 0
                if liq > best_liq:
                    best = p
                    best_liq = liq

        if best:
            result["price_usd"] = float(best["priceUsd"]) if best.get("priceUsd") else None
            result["pair_address"] = best.get("pairAddress")
            result["dex"] = best.get("dexId")
            result["liquidity_usd"] = best_liq
            result["volume_24h"] = (best.get("volume", {}) or {}).get("h24")
            log.info(
                "DEXScreener ETH/USDC: $%s (dex=%s, liq=$%s)",
                result["price_usd"], result["dex"], result["liquidity_usd"],
            )
        else:
            log.warning("DEXScreener: no ETH/USDC pair found for WETH on Base")

    except Exception as exc:
        log.warning("DEXScreener ETH/USDC fetch failed: %s", exc)

    _set_cache(cache_key, result)
    return result


# ── Aggregated snapshot ────────────────────────────────────────────────────

def get_market_snapshot(tokens: Optional[List[str]] = None) -> dict:
    """
    Fetch a complete real-time market snapshot combining all three sources:
      - CoinGecko prices + trending + global
      - DEXScreener Base pairs
      - Fear & Greed Index

    This is the main function called by the API endpoints.
    """
    tokens = tokens or ["eth", "usdc", "degen", "brett", "aero", "ondo", "kaito"]

    prices = fetch_coingecko_prices(tokens)
    trending = fetch_coingecko_trending()
    global_data = fetch_coingecko_global()
    dex_pairs = fetch_dexscreener_pairs(chain="base", limit=10)
    fear_greed = fetch_fear_greed()
    price_cache_key = f"cg_prices_{','.join(sorted(tokens or []))}"
    coingecko_status = get_coingecko_cache_status(
        [price_cache_key, "cg_trending", "cg_global"]
    )

    if coingecko_status["state"] == "stale":
        snapshot_source = "cached_market_data"
    elif coingecko_status["state"] == "unavailable":
        snapshot_source = "degraded_market_data"
    else:
        snapshot_source = "real_api"

    return {
        "source": snapshot_source,
        "timestamp": int(_now().timestamp()),
        "tokens": prices,
        "trending": trending,
        "global_market": global_data,
        "dex_pairs_base": dex_pairs,
        "fear_greed_index": fear_greed,
        "freshness": {
            "coingecko": coingecko_status,
        },
    }