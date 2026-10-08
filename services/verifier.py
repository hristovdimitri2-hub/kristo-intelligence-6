# -*- coding: utf-8 -*-
"""
Phase 1 rule-based value checker — модел „никой не лъже" (07.10.2026).

Преди доставка на платен сигнал числата му (`price_usd`) се кръстосват ПО ДВА
НЕЗАВИСИМИ ИЗТОЧНИКА: CoinGecko (публичен API) × DexScreener (DEX търсене,
Base chain, реална ликвидност). Правилата (docs/VERIFIER_RESEARCH.md, Фаза 1):

  verified   — и двата източника дават цена и разминаването е ≤ TOLERANCE_PCT
               → сигналът минава и се доставя;
  rejected   — източниците се разминават ИЛИ един от тях няма цена
               → „сигналът не минава": НЕ влиза в signals[], но се връща в
               rejected_signals[] (двете цени, diff_pct, причина) и се логва
               (за да се вижда дали някой агент редовно лъже);
  unverified — проверката падна (транспортна грешка/изключение)
               → fail-open: платеният сигнал СЕ ДОСТАВЯ (парите са факт),
               но е бележен като непроверен в scan_info.

Кодът тук НЕ блокира доставката при своя собствена повреда — целият поток е
обгърнат с try/except и в main._verify_signal_values (двоен fail-open).
LLM проверка = Фаза 2, изрично НЕ е включена тук.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import requests

log = logging.getLogger("kristo.v6.verifier")

DEXSCREENER_SEARCH = "https://api.dexscreener.com/latest/dex/search"

# Допустимо разминаване между двата източника (± %); 2% по препоръката от
# проучването — конфигурируемо без код.
TOLERANCE_PCT = max(0.05, float(os.getenv("VERIFIER_TOLERANCE_PCT", "2.0")))
SOURCE_TIMEOUT_SECONDS = max(1, int(os.getenv("VERIFIER_SOURCE_TIMEOUT", "5")))
# DexScreener няма нашия кеш — кратък TTL, за да не наливаме заявки при
# заявка към платения route на всеки клик.
_DEX_CACHE_TTL_SECONDS = max(1, int(os.getenv("VERIFIER_DEX_CACHE_TTL", "60")))
_DEX_MIN_LIQUIDITY_USD = 50_000.0

_dex_cache: dict = {}
_dex_cache_lock = threading.RLock()


# ── източници ───────────────────────────────────────────────────────────────

def _coingecko_source(symbols: List[str]) -> dict:
    """{SYMBOL: (price_usd | None, 'ok' | 'missing' | 'error')} — една заявка."""
    from services.coingecko import CoinGeckoClient

    out = {s: (None, "error") for s in symbols}
    try:
        client = CoinGeckoClient(api_key=os.getenv("BASE44_API_KEY", ""))
        prices = client.get_prices([s.lower() for s in symbols]) or {}
    except Exception as exc:  # целият feed падна → error (fail-open по-нагоре)
        log.warning("value_check: CoinGecko source error (%s: %s)",
                    type(exc).__name__, exc)
        return out
    for s in symbols:
        price = prices.get(s.lower(), prices.get(s))
        if price:
            out[s] = (float(price), "ok")
        else:
            out[s] = (None, "missing")
    return out


def _dexscreener_source(symbol: str, reference_price: Optional[float]) -> tuple:
    """(price_usd | None, 'ok' | 'missing' | 'error') за ЕДИН символ.

    Същите гвардове като signal_track_record: точен символ, Base chain,
    реална ликвидност и цена в разумна близост до познатата (фалшива „ETH"
    на $0.01 не бива да потвърждава истинска ETH цена).
    """
    sym = (symbol or "").upper()
    if not sym:
        return None, "missing"
    with _dex_cache_lock:
        cached = _dex_cache.get(sym)
        if cached and time.monotonic() - cached[1] < _DEX_CACHE_TTL_SECONDS:
            return cached[0], cached[2]

    price, outcome = None, "missing"
    try:
        response = requests.get(DEXSCREENER_SEARCH, params={"q": sym},
                                timeout=SOURCE_TIMEOUT_SECONDS)
        if response.status_code != 200:
            price, outcome = None, "error"
        else:
            pairs = response.json().get("pairs") or []
            candidates = []
            for pair in pairs:
                base = (pair.get("baseToken") or {}).get("symbol") or ""
                liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
                raw_price = pair.get("priceUsd")
                if base.upper() != sym or not raw_price:
                    continue
                if (pair.get("chainId") or "").lower() != "base":
                    continue
                if liquidity < _DEX_MIN_LIQUIDITY_USD:
                    continue
                try:
                    value = float(raw_price)
                except (TypeError, ValueError):
                    continue
                if value <= 0:
                    continue
                if reference_price and reference_price > 0:
                    ratio = max(value / reference_price, reference_price / value)
                    if ratio > 10:   # фалшив символ — същият праг като track record
                        continue
                candidates.append((liquidity, value))
            if candidates:
                candidates.sort(reverse=True)
                price, outcome = candidates[0][1], "ok"
    except Exception as exc:  # транспорт/decode → проверката падна
        log.warning("value_check: DexScreener source error for %s (%s: %s)",
                    sym, type(exc).__name__, exc)
        price, outcome = None, "error"

    if outcome == "ok":
        with _dex_cache_lock:
            _dex_cache[sym] = (price, time.monotonic(), "ok")
    return price, outcome

# ── вердикт на сигнал ───────────────────────────────────────────────────────

def _verdict(signal_price: float, cg: tuple, ds: tuple) -> Tuple[str, str, dict]:
    """(verdict, reason, detail) — виж модулния докстринг за семантиката."""
    cg_price, cg_out = cg
    ds_price, ds_out = ds
    detail = {"signal_price_usd": round(signal_price, 8),
              "coingecko_usd": cg_price, "dexscreener_usd": ds_price}
    if cg_out == "error" or ds_out == "error":
        reason = "source_error:" + ",".join(
            name for name, out in (("coingecko", cg_out), ("dexscreener", ds_out))
            if out == "error")
        return "unverified", reason, detail
    if cg_out == "missing" or ds_out == "missing":
        reason = "source_missing:" + ",".join(
            name for name, out in (("coingecko", cg_out), ("dexscreener", ds_out))
            if out == "missing")
        return "rejected", reason, detail
    diff_pct = abs(cg_price - ds_price) / max(cg_price, ds_price) * 100.0
    detail["diff_pct"] = round(diff_pct, 4)
    if diff_pct <= TOLERANCE_PCT:
        return "verified", "sources_agree", detail
    return "rejected", "mismatch", detail


def verify_signals(signals: list) -> tuple:
    """(deliverable_signals, rejected_signals, scan_info) — виж модулния
    докстринг. НЕ хвърля: всеки проблем се превръща в unverified/fail-open
    вердикт.

    rejected_signals[] (б1, Вариант А): отхвърлените напускат signals[], но
    остават видими — всеки носи двете цени, diff_pct и причина.
    """
    signals = [s for s in (signals or []) if isinstance(s, dict)]
    checked_at = datetime.now(timezone.utc).isoformat()
    deliverable: list = []
    rejected_signals: list = []
    details: list = []
    counts = {"verified": 0, "rejected": 0, "unverified": 0}

    # 1) кои сигнали имат числа за кръстосване
    wanted: dict = {}
    pending: list = []
    for sig in signals:
        token = str(sig.get("token") or "").upper()
        price = sig.get("price_usd")
        value = None
        if price is not None:
            try:
                value = float(price)
            except (TypeError, ValueError):
                value = None
        pending.append((sig, token, value))
        if value is not None:
            wanted.setdefault(token, value)

    # 2) източници (една CoinGecko заявка за всички символи)
    symbols = sorted(wanted)
    cg = _coingecko_source(symbols) if symbols else {}
    ds = {sym: _dexscreener_source(sym, wanted[sym]) for sym in symbols}

    # 3) вердикти
    for sig, token, value in pending:
        if value is None:
            # няма число → няма какво да се кръстосва; доставя се, но е
            # честно бележено като непроверено
            counts["unverified"] += 1
            details.append({"token": token, "verdict": "unverified",
                            "reason": "no_number_to_check"})
            deliverable.append(sig)
            continue
        verdict, reason, detail = _verdict(value,
                                           cg.get(token, (None, "missing")),
                                           ds.get(token, (None, "missing")))
        entry = {"token": token, "verdict": verdict, "reason": reason, **detail}
        details.append(entry)
        counts[verdict] += 1
        if verdict == "rejected":
            log.warning("value_check REJECTED token=%s signal=%.8g "
                        "coingecko=%s dexscreener=%s (%s) — сигналът не минава",
                        token, value, detail.get("coingecko_usd"),
                        detail.get("dexscreener_usd"), reason)
            # „не минава" → излиза от signals[], но влиза в rejected_signals[]
            # с двете цени, diff_pct и причината (клиентът вижда защо).
            rejected_entry = dict(sig)
            rejected_entry["verification"] = "rejected"
            rejected_entry["reason"] = reason
            rejected_entry["coingecko_usd"] = detail.get("coingecko_usd")
            rejected_entry["dexscreener_usd"] = detail.get("dexscreener_usd")
            rejected_entry["diff_pct"] = detail.get("diff_pct")
            rejected_signals.append(rejected_entry)
            continue
        if verdict == "unverified":
            log.warning("value_check UNVERIFIED token=%s (%s) — fail-open, "
                        "доставя се като непроверен", token, reason)
        deliverable.append(sig)

    if counts["rejected"] and counts["verified"] + counts["unverified"]:
        overall = "partial"
    elif counts["rejected"]:
        overall = "rejected"
    elif counts["unverified"]:
        overall = "unverified"
    else:
        overall = "verified"

    scan_info = {
        "verification": overall,
        "checked_at": checked_at,
        "tolerance_pct": TOLERANCE_PCT,
        "sources": ["coingecko", "dexscreener"],
        "checked": len(pending),
        "delivered": len(deliverable),
        "verified": counts["verified"],
        "rejected": counts["rejected"],
        "rejected_count": counts["rejected"],
        "unverified": counts["unverified"],
        "details": details,
    }
    return deliverable, rejected_signals, scan_info
