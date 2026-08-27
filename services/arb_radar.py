"""
Kristo Arb Radar — real-time cross-DEX arbitrage spread detection on Base
==========================================================================
Background service that monitors top Base DEX pairs via DEXScreener,
computes cross-DEX price spreads, and maintains an in-memory list of
arbitrage opportunities. The paid endpoint /api/arb/opportunities serves
this data with zero additional RPC cost per call.

Target buyers: trading bots and arbitrageurs on Base who need actionable
spread data without building their own monitoring infrastructure.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

import requests

from config import KRISTO_ARB_PRICE  # noqa: F401 — re-exported price constant

log = logging.getLogger("kristo.v6.arb_radar")

SCAN_INTERVAL = max(30, int(os.getenv("ARB_SCAN_INTERVAL", "60")))
MIN_LIQUIDITY_USD = float(os.getenv("ARB_MIN_LIQUIDITY", "10000"))
MIN_SPREAD_PCT = float(os.getenv("ARB_MIN_SPREAD", "0.05"))
MAX_OPPORTUNITIES = int(os.getenv("ARB_MAX_OPPORTUNITIES", "20"))

SEARCH_QUERIES = [
    "WETH USDC base",
    "cbBTC USDC base",
    "AERO WETH base",
    "USDC USDT base",
    "DEGEN WETH base",
    "VIRTUAL WETH base",
    "BRETT WETH base",
    "AIXBT WETH base",
]

_lock = threading.Lock()
_opportunities: List[dict] = []
_last_scan: Optional[datetime] = None
_scan_count = 0


def get_opportunities() -> List[dict]:
    """Return the current top arbitrage opportunities (thread-safe copy)."""
    with _lock:
        return list(_opportunities)


def get_scan_info() -> dict:
    """Return metadata about the last scan."""
    with _lock:
        return {
            "last_scan": _last_scan.isoformat() if _last_scan else None,
            "scan_count": _scan_count,
            "opportunity_count": len(_opportunities),
            "scan_interval_seconds": SCAN_INTERVAL,
        }


def _fetch_dexscreener_pairs(query: str) -> List[dict]:
    """Fetch pair data from DEXScreener for a search query."""
    try:
        url = f"https://api.dexscreener.com/latest/dex/search?q={query.replace(' ', '%20')}"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        pairs = data.get("pairs") or []
        result = []
        for p in pairs:
            if p.get("chainId") != "base":
                continue
            liq = (p.get("liquidity") or {}).get("usd", 0)
            if not liq or liq < MIN_LIQUIDITY_USD:
                continue
            result.append(p)
        return result
    except Exception as exc:
        log.warning("DEXScreener fetch failed for '%s': %s", query, exc)
        return []


def _scan_for_arbitrage() -> List[dict]:
    """Scan all monitored pairs and compute cross-DEX spreads."""
    all_opportunities = []

    for query in SEARCH_QUERIES:
        pairs = _fetch_dexscreener_pairs(query)
        if len(pairs) < 2:
            continue

        # Group by base token address to find same pair on different DEXes
        by_token = {}
        for p in pairs:
            base_token = (p.get("baseToken") or {}).get("address", "")
            quote_token = (p.get("quoteToken") or {}).get("address", "")
            if not base_token or not quote_token:
                continue
            key = f"{base_token.lower()}/{quote_token.lower()}"
            price_usd = p.get("priceUsd")
            if not price_usd:
                continue
            by_token.setdefault(key, []).append({
                "dex": p.get("dexId", "unknown"),
                "pair_address": p.get("pairAddress", ""),
                "price_usd": float(price_usd),
                "liquidity_usd": (p.get("liquidity") or {}).get("usd", 0),
                "volume_24h": (p.get("volume") or {}).get("h24", 0),
                "symbol": (p.get("baseToken") or {}).get("symbol", "?"),
                "quote_symbol": (p.get("quoteToken") or {}).get("symbol", "?"),
            })

        # Compute cross-DEX spreads for each token pair
        for pair_key, listings in by_token.items():
            if len(listings) < 2:
                continue

            listings.sort(key=lambda x: x["price_usd"])
            cheapest = listings[0]
            highest = listings[-1]

            if cheapest["price_usd"] <= 0:
                continue

            spread_pct = (
                (highest["price_usd"] - cheapest["price_usd"])
                / cheapest["price_usd"]
            ) * 100

            if spread_pct < MIN_SPREAD_PCT:
                continue

            # Estimate max trade size (limited by lower liquidity side)
            max_liquidity = min(cheapest["liquidity_usd"],
                                highest["liquidity_usd"])
            est_trade_usd = max_liquidity * 0.02  # conservative 2% of pool
            est_profit_usd = est_trade_usd * (spread_pct / 100) * 0.8

            all_opportunities.append({
                "pair": f"{cheapest['symbol']}/{cheapest['quote_symbol']}",
                "buy_dex": cheapest["dex"],
                "sell_dex": highest["dex"],
                "spread_pct": round(spread_pct, 4),
                "buy_price_usd": cheapest["price_usd"],
                "sell_price_usd": highest["price_usd"],
                "est_trade_usd": round(est_trade_usd, 2),
                "est_profit_usd": round(est_profit_usd, 2),
                "liquidity_usd_buy": cheapest["liquidity_usd"],
                "liquidity_usd_sell": highest["liquidity_usd"],
                "pair_buy": cheapest["pair_address"],
                "pair_sell": highest["pair_address"],
                "volume_24h": max(cheapest["volume_24h"],
                                  highest["volume_24h"]),
                "scanned_at": datetime.now(timezone.utc).isoformat(),
            })

    # Sort by estimated profit, keep top N
    all_opportunities.sort(key=lambda x: -x["est_profit_usd"])
    return all_opportunities[:MAX_OPPORTUNITIES]


def arb_radar_loop():
    """Background thread: continuously scan for arbitrage opportunities."""
    global _opportunities, _last_scan, _scan_count
    log.info("Arb Radar thread started (interval=%ds, min_spread=%.2f%%).",
             SCAN_INTERVAL, MIN_SPREAD_PCT)

    while True:
        try:
            opps = _scan_for_arbitrage()
            with _lock:
                _opportunities = opps
                _last_scan = datetime.now(timezone.utc)
                _scan_count += 1
            log.info("Arb Radar scan #%d: %d opportunities found.",
                     _scan_count, len(opps))
        except Exception as exc:
            log.warning("Arb Radar scan failed (non-fatal): %s", exc)
        time.sleep(SCAN_INTERVAL)


def start_arb_radar_thread():
    """Start the Arb Radar daemon thread."""
    threading.Thread(
        target=arb_radar_loop, daemon=True, name="arb-radar"
    ).start()