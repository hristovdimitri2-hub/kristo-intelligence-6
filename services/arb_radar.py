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

from config import BASE_RPC_URL, KRISTO_ARB_PRICE  # noqa: F401 — price + RPC re-exports

log = logging.getLogger("kristo.v6.arb_radar")

SCAN_INTERVAL = max(30, int(os.getenv("ARB_SCAN_INTERVAL", "60")))
MIN_LIQUIDITY_USD = float(os.getenv("ARB_MIN_LIQUIDITY", "10000"))
MIN_SPREAD_PCT = float(os.getenv("ARB_MIN_SPREAD", "0.05"))
MAX_OPPORTUNITIES = int(os.getenv("ARB_MAX_OPPORTUNITIES", "20"))

# ── Net Edge (plan Product 1: est_profit_usd = "нет след газ") ──────────────
# Gas for a full round trip (2 swaps ≈ 300k gas) expressed in USDC.
# Default 0.10 = conservative typical Base conditions (~0.1 gwei × 300k gas
# × ~$3.5k ETH); override for spikes (e.g. ARB_GAS_COST_USDC=1.00).
GAS_COST_USDC = float(os.getenv("ARB_GAS_COST_USDC", "0.10"))
# Plan filter: keep the opportunity only if gross profit > gas × 3.
GAS_SAFETY_MULT = float(os.getenv("ARB_GAS_SAFETY_MULT", "3"))
# Base block time used to convert wall-clock age → data_age_blocks (no RPC
# on the serve path — the endpoint stays zero-RPC-per-call).
BASE_BLOCK_TIME_SECONDS = 2.0

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
_last_block: Optional[int] = None  # Base block at last scan (plan: block_number)


def get_opportunities() -> List[dict]:
    """Return the current top arbitrage opportunities (thread-safe copy).

    Each row carries the plan's transparency fields: `block_number` (Base
    block at scan time) and `data_age_blocks` (estimated from wall-clock
    age at 2 s/block — zero RPC on the serve path).
    """
    now = datetime.now(timezone.utc)
    with _lock:
        rows = [dict(o) for o in _opportunities]
    for row in rows:
        try:
            scanned = datetime.fromisoformat(row["scanned_at"])
            age_s = max(0.0, (now - scanned).total_seconds())
            row["data_age_blocks"] = int(age_s / BASE_BLOCK_TIME_SECONDS)
        except Exception:
            row["data_age_blocks"] = None
    return rows


def get_scan_info() -> dict:
    """Return metadata about the last scan."""
    with _lock:
        return {
            "last_scan": _last_scan.isoformat() if _last_scan else None,
            "scan_count": _scan_count,
            "opportunity_count": len(_opportunities),
            "scan_interval_seconds": SCAN_INTERVAL,
            "block_number": _last_block,
            "gas_cost_usdc": GAS_COST_USDC,
            "gas_safety_multiplier": GAS_SAFETY_MULT,
        }


def _fetch_base_block() -> Optional[int]:
    """Latest Base block number (one RPC per scan, never per request).

    Best-effort: on any failure returns None and the transparency field
    degrades to `block_number: null` instead of failing the scan.
    """
    try:
        resp = requests.post(
            BASE_RPC_URL,
            json={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber",
                  "params": []},
            timeout=10,
        )
        if resp.status_code == 200:
            return int(resp.json().get("result", "0x0"), 16)
    except Exception as exc:
        log.debug("Base block fetch failed (non-fatal): %s", exc)
    return None


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
    # One eth_blockNumber per scan feeds the plan's `block_number` field;
    # failure degrades to null without stopping the scan.
    scan_block = _fetch_base_block()

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

            # ── Net Edge (plan: "филтрирай spread > газ×3") ────────────────
            # Gross = trade × spread; the opportunity must clear gas×3,
            # otherwise the spread is noise a bot would lose money on.
            gross_profit_usd = est_trade_usd * (spread_pct / 100)
            # FIX #8: Use < instead of <= to include opportunities exactly at threshold
            if gross_profit_usd < GAS_COST_USDC * GAS_SAFETY_MULT:
                continue
            # est_profit_usd = NET after gas ("нет след газ", plan Product 1).
            est_profit_usd = gross_profit_usd - GAS_COST_USDC

            all_opportunities.append({
                "pair": f"{cheapest['symbol']}/{cheapest['quote_symbol']}",
                "buy_dex": cheapest["dex"],
                "sell_dex": highest["dex"],
                "spread_pct": round(spread_pct, 4),
                "buy_price_usd": cheapest["price_usd"],
                "sell_price_usd": highest["price_usd"],
                "est_trade_usd": round(est_trade_usd, 2),
                "est_profit_usd": round(est_profit_usd, 2),
                "gas_cost_usdc": GAS_COST_USDC,
                "liquidity_usd_buy": cheapest["liquidity_usd"],
                "liquidity_usd_sell": highest["liquidity_usd"],
                "pair_buy": cheapest["pair_address"],
                "pair_sell": highest["pair_address"],
                "volume_24h": max(cheapest["volume_24h"],
                                  highest["volume_24h"]),
                "block_number": scan_block,
                "scanned_at": datetime.now(timezone.utc).isoformat(),
            })

    # Sort by estimated profit, keep top N
    all_opportunities.sort(key=lambda x: -x["est_profit_usd"])
    return all_opportunities[:MAX_OPPORTUNITIES]


def arb_radar_loop():
    """Background thread: continuously scan for arbitrage opportunities."""
    global _opportunities, _last_scan, _scan_count, _last_block
    log.info("Arb Radar thread started (interval=%ds, min_spread=%.2f%%, "
             "gas=%.2f USDC, min gross=gas×%d).",
             SCAN_INTERVAL, MIN_SPREAD_PCT, GAS_COST_USDC, GAS_SAFETY_MULT)

    while True:
        try:
            opps = _scan_for_arbitrage()
            with _lock:
                _opportunities = opps
                _last_scan = datetime.now(timezone.utc)
                _scan_count += 1
                _last_block = opps[0]["block_number"] if opps else None
            log.info("Arb Radar scan #%d: %d opportunities found (block=%s).",
                     _scan_count, len(opps),
                     opps[0]["block_number"] if opps else "?")
        except Exception as exc:
            log.warning("Arb Radar scan failed (non-fatal): %s", exc)
        time.sleep(SCAN_INTERVAL)


def start_arb_radar_thread():
    """Start the Arb Radar daemon thread."""
    threading.Thread(
        target=arb_radar_loop, daemon=True, name="arb-radar"
    ).start()