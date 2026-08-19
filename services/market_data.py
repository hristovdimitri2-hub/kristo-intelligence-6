"""
Real-time market data integration for Kristo Intelligence v5.

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
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

log = logging.getLogger("kristo.v5.market_data")

# ── API endpoints (all free, no key required) ──────────────────────────────
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DEXSCREENER_BASE = "https://api.dexscreener.com"
FNG_BASE = "https://api.alternative.me"

# Simple in-memory cache with 15-minute TTL (datetime-based)
_CACHE: Dict[str, dict] = {}
_CACHE_TTL = timedelta(minutes=15)


def _cached(key: str):
    """Return cached value if still valid, else None."""
    entry = _CACHE.get(key)
    if entry and (datetime.now(timezone.utc) - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None


def _set_cache(key: str, data):
    _CACHE[key] = {"ts": datetime.now(timezone.utc), "data": data}


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
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    tokens = tokens or list(COINGECKO_IDS.keys())
    ids = [COINGECKO_IDS[t] for t in tokens if t in COINGECKO_IDS]
    if not ids:
        return {}

    try:
        resp = requests.get(
            f"{COINGECKO_BASE}/simple/price",
            params={
                "ids": ",".join(ids),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
            },
            headers={"accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

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
        _set_cache(cache_key, result)
        log.info("CoinGecko prices fetched for %d tokens", len(result))
        return result
    except Exception as exc:
        log.warning("CoinGecko price fetch failed: %s", exc)
        return {}


def fetch_coingecko_trending() -> List[dict]:
    """Fetch trending coins from CoinGecko (free, no key)."""
    cached = _cached("cg_trending")
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            f"{COINGECKO_BASE}/search/trending",
            headers={"accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
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
        _set_cache("cg_trending", coins)
        log.info("CoinGecko trending: %d coins", len(coins))
        return coins
    except Exception as exc:
        log.warning("CoinGecko trending fetch failed: %s", exc)
        return []


def fetch_coingecko_global() -> dict:
    """Fetch global crypto market data from CoinGecko."""
    cached = _cached("cg_global")
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            f"{COINGECKO_BASE}/global",
            headers={"accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        result = {
            "total_market_cap_usd": data.get("total_market_cap", {}).get("usd"),
            "total_volume_24h_usd": data.get("total_volume", {}).get("usd"),
            "market_cap_change_24h": data.get("market_cap_change_percentage_24h_usd"),
            "btc_dominance": data.get("market_cap_percentage", {}).get("btc"),
            "eth_dominance": data.get("market_cap_percentage", {}).get("eth"),
            "active_cryptocurrencies": data.get("active_cryptocurrencies"),
        }
        _set_cache("cg_global", result)
        log.info("CoinGecko global data fetched")
        return result
    except Exception as exc:
        log.warning("CoinGecko global fetch failed: %s", exc)
        return {}


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

    return {
        "source": "real_api",
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
        "tokens": prices,
        "trending": trending,
        "global_market": global_data,
        "dex_pairs_base": dex_pairs,
        "fear_greed_index": fear_greed,
    }