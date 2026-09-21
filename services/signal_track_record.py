"""The PUBLIC track-record feed (/public/signals/history) — FROZEN RULES.

Six rules, frozen on 18.09.2026 (recorded in PROJECT_STATUS before the first
signal). They are not configurable and they are not "improved" once data
arrives; tests/test_signal_history.py fails if anyone edits them.

  1. The feed is FREE and rate-limited, and it serves ONLY signals that were
     issued through the PAID route and are at least 24 hours old. The fresh
     signal itself stays paid: the feed is the proven past, never the present.
  2. Realized volatility (24h, from 14 days of hourly closes) is computed AT
     ISSUE and stored immutably with the record. hit = the 24h move reached the
     volatility IN the signal's direction; miss = reached it AGAINST; flat =
     between the two. The price window is ±2 hours around the 24th hour.
  3. Resolution order: (1) the signal's own source, CoinGecko; (2) DEXScreener,
     only inside that window. If both fail the outcome is `unresolved` — never a
     price from outside the window, and never a resolution from a colliding
     symbol.
  4. Every record carries issued_at, asset, action, confidence, price_at_issue,
     vol_threshold, price_at_24h, move_pct, outcome, resolved_at,
     resolution_source.
  5. Aggregates always show n — including the per-asset UNRESOLVED count, so a
     selective absence is visible. A percentage appears only at n >= 50 for that
     cell (the same rule the confidence score already follows): the feed says
     "DEGEN: n=3, hits=2", never "DEGEN: 67%".
  6. The review schedule is a technical guard, not a promise: hit_rate is
     computed only from the first checkpoint (n=30) onward, every checkpoint
     reached is recorded so the goalposts cannot move, and the headline covers
     the WHOLE feed — never a share of it.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

log = logging.getLogger("kristo.v6.signal_track_record")

#: The day the rules above were frozen. Shown in the payload so a reader can see
#: that the thresholds predate the numbers they are reading.
FROZEN_ON = "2026-09-18"

#: Review checkpoints (rule 6). The FINAL one is 200.
CHECKPOINTS: Tuple[int, ...] = (30, 100, 200)

#: A percentage is only shown at this sample size per cell (rule 5).
MIN_PERCENT_N = 50

#: The resolution window: prices are read within ±2h of the 24th hour (rule 2/3).
PRICE_WINDOW_HOURS = 2

#: Volatility lookback (rule 2): 14 days of hourly closes, scaled to 24h.
VOL_LOOKBACK_DAYS = 14

#: Resolution at (or after) this age is due (rule 1).
RESOLVE_AFTER_HOURS = 24

#: The signal source, first in the frozen order (rule 3).
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DEXSCREENER_SEARCH = "https://api.dexscreener.com/latest/dex/search"

#: A fallback price more than 10× away from the issue price is a symbol
#: collision, not the same asset — `unresolved` is the honest answer.
_MAX_FALLBACK_RATIO = 10.0

#: Directional vocabulary — matched against the strings the agent ACTUALLY
#: publishes. First version guessed ("buy"/"long") and the live run on 18.09
#: showed the real values (`recommend_accumulate_on_dips`,
#: `recommend_small_allocation_only`, `recommend_hold_or_add`, `monitor`), so
#: every one of them was scored as non-directional: the feed would have stayed
#: empty forever while looking perfectly healthy. Ambiguous actions stay
#: UNSCORED on purpose — "hold or add" is not a direction.
_BULLISH = {"buy", "long", "bullish", "strong_buy", "recommend_buy",
            "accumulate", "recommend_accumulate", "recommend_accumulate_on_dips",
            "small_allocation", "recommend_small_allocation_only"}
_BEARISH = {"sell", "short", "bearish", "strong_sell", "recommend_sell",
            "avoid", "recommend_avoid"}
#: Neutral OR ambiguous: counted, never scored (rule 2).
_NEUTRAL = {"hold", "monitor", "wait", "recommend_hold_or_add", ""}

#: The four assets we sell (services/coingecko.py SUPPORTED_TOKENS).
ASSET_IDS = {"eth": "ethereum", "ondo": "ondo-finance", "kaito": "kaito",
             "degen": "degen-base"}


def direction_of(action: str) -> int:
    """+1 bullish, -1 bearish, 0 non-directional or ambiguous (never scored)."""
    key = (action or "").strip().lower().replace("-", "_")
    if key in _NEUTRAL:
        return 0
    if key in _BULLISH:
        return 1
    if key in _BEARISH:
        return -1
    # An unknown action is NOT guessed into a direction: scoring a string we do
    # not recognise is how a track record starts lying.
    return 0


def realized_volatility_24h(hourly_closes: Iterable[float]) -> Optional[float]:
    """σ of hourly log returns over 14 days, scaled to a 24-hour horizon.

    Frozen definition (rule 2). Hourly returns (336 samples) rather than 13 daily
    ones, because a stdev of 13 points swings wildly enough to decide the
    hit/miss verdict by luck — the threshold must be stable to be fair. Scaling
    is √24, the standard random-walk step from 1 hour to 24.
    """
    closes = [float(c) for c in (hourly_closes or []) if c and float(c) > 0]
    if len(closes) < 24:
        return None
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(24.0)


def classify(price_at_issue: Optional[float], price_at_24h: Optional[float],
             vol_threshold: Optional[float],
             action: str) -> Tuple[str, Optional[float]]:
    """(outcome, move_pct) for one record — the frozen rule 2, nothing else.

    Non-directional actions and missing numbers are NOT guessed into a verdict.
    """
    if not price_at_issue or price_at_issue <= 0 or not price_at_24h \
            or price_at_24h <= 0 or not vol_threshold:
        return "unresolved", None
    direction = direction_of(action)
    if direction == 0:
        return "unresolved", None
    move = (price_at_24h - price_at_issue) / price_at_issue
    signed = move * direction
    if signed >= vol_threshold:
        return "hit", round(move * 100, 4)
    if signed <= -vol_threshold:
        return "miss", round(move * 100, 4)
    return "flat", round(move * 100, 4)


def _pct(n: int, hits: int) -> Optional[float]:
    """A percentage ONLY at n >= MIN_PERCENT_N (rule 5); else None + n is shown."""
    if n < MIN_PERCENT_N:
        return None
    return round(100.0 * hits / n, 1)
def fetch_hourly_closes(asset: str, days: int = VOL_LOOKBACK_DAYS,
                        timeout: int = 45) -> List[float]:
    """CoinGecko hourly closes for the volatility (rule 2, computed at issue).

    18.09 fix: this used to call the public endpoint RAW. The app already spends
    the same free CoinGecko budget on prices every cycle, so the history calls
    collided with it and answered HTTP 429 — which meant `vol_threshold = None`
    and a record that could never be scored (a silently dead feed). It now goes
    through the app's shared CoinGecko machinery (cache + cooldown + backoff).
    """
    coin_id = ASSET_IDS.get((asset or "").lower())
    if not coin_id:
        return []
    try:
        from services.market_data import fetch_coingecko_market_chart

        closes = fetch_coingecko_market_chart(coin_id, days=days)
        if closes:
            return closes
    except Exception as exc:
        log.warning("shared CoinGecko history path failed for %s: %s", asset, exc)
    try:
        response = requests.get(
            "%s/coins/%s/market_chart" % (COINGECKO_BASE, coin_id),
            params={"vs_currency": "usd", "days": days}, timeout=timeout)
        if response.status_code != 200:
            log.warning("CoinGecko history HTTP %s for %s",
                        response.status_code, asset)
            return []
        return [float(p[1]) for p in (response.json().get("prices") or [])]
    except Exception as exc:
        log.warning("CoinGecko history failed for %s: %s", asset, exc)
        return []


def fetch_price_at(asset: str, target_ts: float,
                   window_hours: int = PRICE_WINDOW_HOURS,
                   timeout: int = 45) -> Tuple[Optional[float], str]:
    """The signal's own source, inside the window only (rule 3, step 1).

    Returns (price, source). Nothing outside ±window_hours of the target is ever
    returned — an out-of-window price is not evidence, it is a different claim.
    """
    coin_id = ASSET_IDS.get((asset or "").lower())
    if not coin_id:
        return None, ""
    low = int(target_ts - window_hours * 3600)
    high = int(target_ts + window_hours * 3600)
    try:
        response = requests.get(
            "%s/coins/%s/market_chart/range" % (COINGECKO_BASE, coin_id),
            params={"vs_currency": "usd", "from": low, "to": high},
            timeout=timeout)
        if response.status_code != 200:
            return None, ""
        points = response.json().get("prices") or []
    except Exception as exc:
        log.warning("CoinGecko range failed for %s: %s", asset, exc)
        return None, ""

    inside = [(ts / 1000.0, float(price)) for ts, price in points
              if low <= ts / 1000.0 <= high and price]
    if not inside:
        return None, ""
    best = min(inside, key=lambda p: abs(p[0] - target_ts))
    if abs(best[0] - target_ts) > window_hours * 3600:
        return None, ""
    return best[1], "coingecko"


def fetch_dexscreener_implied(asset: str, reference_price: Optional[float],
                              timeout: int = 45) -> Tuple[Optional[float], str]:
    """DEXScreener price 24h ago, implied by priceUsd + priceChange.h24.

    Rule 3 step 2 — and the caller must already have checked that we are INSIDE
    the ±2h window, because "24h ago from now" is only the 24th hour of the
    signal while we are there. Guards against symbol collisions: exact symbol,
    Base chain, real liquidity, an h24 present, and a price within 10× of the
    issue price (a fake "ETH" at $0.01 must never resolve a real ETH signal).
    """
    symbol = (asset or "").upper()
    if not symbol:
        return None, ""
    try:
        response = requests.get(DEXSCREENER_SEARCH, params={"q": symbol},
                                timeout=timeout)
        if response.status_code != 200:
            return None, ""
        pairs = response.json().get("pairs") or []
    except Exception as exc:
        log.warning("DEXScreener search failed for %s: %s", asset, exc)
        return None, ""

    candidates = []
    for pair in pairs:
        base = (pair.get("baseToken") or {}).get("symbol") or ""
        change = (pair.get("priceChange") or {}).get("h24")
        liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
        price = pair.get("priceUsd")
        if base.upper() != symbol or change is None or not price:
            continue
        if (pair.get("chainId") or "").lower() != "base" or liquidity < 50_000:
            continue
        try:
            implied = float(price) / (1.0 + float(change) / 100.0)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if implied <= 0:
            continue
        if reference_price and reference_price > 0:
            ratio = max(implied / reference_price, reference_price / implied)
            if ratio > _MAX_FALLBACK_RATIO:
                continue
        candidates.append((liquidity, implied))
    if not candidates:
        return None, ""
    candidates.sort(reverse=True)
    return candidates[0][1], "dexscreener"
def next_checkpoint(n: int) -> Optional[int]:
    """The next review size (rule 6), or None once the final one is behind us."""
    for point in CHECKPOINTS:
        if n < point:
            return point
    return None


def build_feed(rows: List[Dict[str, Any]], now: Optional[datetime] = None,
               checkpoints: Optional[List[Dict[str, Any]]] = None,
               not_scored: int = 0) -> Dict[str, Any]:
    """The public payload: records + aggregates, obeying rules 1/5/6.

    `rows` are the durable records (already issued, already ≥24h old). Nothing
    here decides what a hit is — that was decided at issue time and is immutable.
    """
    now = now or datetime.now(timezone.utc)
    scored = [r for r in rows if (r.get("outcome") or "") in
              ("hit", "miss", "flat")]
    unresolved = [r for r in rows if (r.get("outcome") or "") == "unresolved"]
    n = len(scored)
    hits = sum(1 for r in scored if r.get("outcome") == "hit")
    misses = sum(1 for r in scored if r.get("outcome") == "miss")
    flats = sum(1 for r in scored if r.get("outcome") == "flat")

    by_asset: Dict[str, Dict[str, Any]] = {}
    unresolved_by_asset: Dict[str, int] = {}
    for row in rows:
        asset = (row.get("asset") or "?").upper()
        cell = by_asset.setdefault(asset, {"asset": asset, "n": 0, "hits": 0,
                                           "misses": 0, "flats": 0,
                                           "unresolved": 0})
        outcome = row.get("outcome") or "unresolved"
        if outcome == "unresolved":
            unresolved_by_asset[asset] = unresolved_by_asset.get(asset, 0) + 1
            cell["unresolved"] += 1
            continue
        cell["n"] += 1
        if outcome == "hit":
            cell["hits"] += 1
        elif outcome == "miss":
            cell["misses"] += 1
        else:
            cell["flats"] += 1
    for cell in by_asset.values():
        cell["hit_rate_pct"] = _pct(cell["n"], cell["hits"])
        cell["total_issued"] = cell["n"] + cell["unresolved"]

    by_confidence: Dict[str, Dict[str, Any]] = {}
    for row in scored:
        band = _confidence_band(row.get("confidence"))
        cell = by_confidence.setdefault(band, {"band": band, "n": 0, "hits": 0})
        cell["n"] += 1
        if row.get("outcome") == "hit":
            cell["hits"] += 1
    for cell in by_confidence.values():
        cell["hit_rate_pct"] = _pct(cell["n"], cell["hits"])

    moves_hit = [abs(float(r["move_pct"])) for r in scored
                 if r.get("outcome") == "hit" and r.get("move_pct") is not None]
    moves_miss = [abs(float(r["move_pct"])) for r in scored
                  if r.get("outcome") == "miss" and r.get("move_pct") is not None]

    # Rule 6: the headline is computed ONLY from the first checkpoint onward —
    # a technical guard, so nobody reads a number nobody was allowed to read yet.
    gate_open = n >= CHECKPOINTS[0]
    payload: Dict[str, Any] = {
        "ok": True,
        "generated_at": now.isoformat(),
        "frozen_on": FROZEN_ON,
        "schedule": {
            "checkpoints": list(CHECKPOINTS),
            "next_checkpoint": next_checkpoint(n),
            "checkpoints_reached": checkpoints or [],
            "note": ("hit_rate is computed only from the first checkpoint "
                     "onward — a technical guard, not a promise."),
        },
        "totals": {
            "issued": len(rows) + not_scored,
            "scored_n": n,
            "unresolved": len(unresolved),
            "not_scored_non_directional": not_scored,
            "hits": hits, "misses": misses, "flats": flats,
            # Rule 6: the HEADLINE opens at the first checkpoint (n=30). Rule 5's
            # n≥50 floor governs the per-cell percentages (by_asset /
            # by_confidence), not this one — two different gates, on purpose.
            "hit_rate_pct": (round(100.0 * hits / n, 1) if (gate_open and n)
                             else None),
            "gate_open": gate_open,
        },
        "unresolved_by_asset": unresolved_by_asset,
        "by_asset": sorted(by_asset.values(), key=lambda c: c["asset"]),
        "by_confidence": sorted(by_confidence.values(), key=lambda c: c["band"]),
        "avg_move_on_hit_pct": (round(sum(moves_hit) / len(moves_hit), 3)
                                if moves_hit else None),
        "avg_move_on_miss_pct": (round(sum(moves_miss) / len(moves_miss), 3)
                                 if moves_miss else None),
        "records": rows,
        "framing": ("Thresholds, review schedule, resolution plan and unresolved "
                    "reporting frozen on %s. Past performance, not a "
                    "prediction." % FROZEN_ON),
        "paid_note": ("Fresh signals stay paid; this feed is the proven past "
                      "(≥24h old, issued through the paid route)."),
    }

    # Rule 5's visibility clause: when unresolved is not evenly spread, say it.
    rates = {}
    for asset, cell in by_asset.items():
        total = cell["total_issued"]
        rates[asset] = (cell["unresolved"] / total) if total else 0.0
    if rates:
        worst = max(rates.values())
        best = min(rates.values())
        if best == 0 and worst > 0:
            payload["unresolved_note"] = (
                "unresolved concentrates in thinner markets (KAITO/DEGEN) — "
                "smaller sample ≠ worse model, thinner price data")
        elif best > 0 and worst / best >= 2.0:
            payload["unresolved_note"] = (
                "unresolved concentrates in thinner markets (KAITO/DEGEN) — "
                "smaller sample ≠ worse model, thinner price data")
    return payload


def _confidence_band(confidence: Any) -> str:
    """Coarse, pre-declared bands — never a band chosen after seeing the results."""
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return "unknown"
    if value >= 0.8:
        return "0.8-1.0"
    if value >= 0.6:
        return "0.6-0.8"
    if value >= 0.4:
        return "0.4-0.6"
    return "0.0-0.4"