# -*- coding: utf-8 -*-
"""
Пазарни казуси от 08.10.2026 (реални заявки към DexScreener) — трите
конкретни токена, заради които филтрите бяха сгрешени:

  ETH   — на Base се търгува като WETH. Символ-мапът търси/сверява под името,
          което двойката реално носи → сигналът се ПОТВЪРЖДАВА (преди филтър
          „точен символ" го правеше „никога наличен").
  KAITO — тънките му пулове ($862–$10.9k) са единственият пазар на Base, а
          цените съвпадат с CoinGecko. Праг $5k + по-широк толеранс за тънки
          пулове го пускат (преди: под $50k → винаги отпада).
  ONDO  — няма истинска Base двойка (само ethereum/solana + фалшив Base токен
          на $0.00000035). Остава честно „missing", но по Фикс 1 липсващ
          източник НЕ е отхвърляне: доставя се с unverified бележка.

HTTP към DexScreener е фалкиран (без мрежа в серията); филтрите, изборът на
пул, толерансът и вердиктите са ИСТИНСКИ (services/verifier.py).
"""
import pytest


@pytest.fixture()
def verifier():
    from services import verifier
    verifier._dex_cache.clear()
    yield verifier
    verifier._dex_cache.clear()


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _dex_pairs(monkeypatch, verifier, pairs, capture=None):
    """Фалкира DexScreener search endpoint-а с готов `pairs` отговор."""

    def fake_get(url, params=None, timeout=None):
        if capture is not None:
            capture.append(dict(params or {}))
        return _FakeResp({"pairs": pairs})

    monkeypatch.setattr(verifier.requests, "get", fake_get)


def _pair(symbol, price, liquidity, chain="base"):
    return {"baseToken": {"symbol": symbol}, "chainId": chain,
            "liquidity": {"usd": liquidity}, "priceUsd": str(price)}


def _fake_coco(monkeypatch, verifier, prices):
    monkeypatch.setattr(verifier, "_coingecko_source",
                        lambda symbols: {s: prices.get(s, (None, "missing"))
                                         for s in symbols})


# ── ETH → WETH мап (Фикс 2) ─────────────────────────────────────────────────

def test_eth_found_via_weth_map_on_base(monkeypatch, verifier):
    """ETH се търси/сверява като WETH на Base — иначе е „никога наличен"."""
    queries = []
    _dex_pairs(monkeypatch, verifier, [
        # фалшив „ETH" на Base — точният символ-гвард (и ratio-гвардът) го реже
        _pair("ETH", 0.00000035, 34_303.0),
        # истинската двойка на Base носи символ WETH
        _pair("WETH", 2558.38, 1_681_403.0),
    ], capture=queries)

    price, outcome, liq = verifier._dexscreener_source("ETH", 2562.04)

    assert queries[0]["q"] == "WETH"        # мапнатият символ отива в заявката
    assert outcome == "ok"
    assert price == 2558.38
    assert liq == 1_681_403.0


def test_eth_signal_confirmed_end_to_end(monkeypatch, verifier):
    """Целият поток: cg ok + WETH/Base пул → verified (diff 0.14%)."""
    _dex_pairs(monkeypatch, verifier, [
        _pair("WETH", 2558.38, 1_681_403.0),
    ])
    _fake_coco(monkeypatch, verifier, {"ETH": (2562.04, "ok")})

    deliverable, rejected, scan_info = verifier.verify_signals(
        [{"token": "ETH", "price_usd": 2560.0}])

    assert len(deliverable) == 1 and rejected == []
    assert scan_info["verification"] == "verified"
    assert scan_info["details"][0]["diff_pct"] < 0.2


# ── KAITO: тънки пулове минават (Фикс 2) ────────────────────────────────────

def test_kaito_thin_pool_passes_with_matching_prices(monkeypatch, verifier):
    """Тънък пул ($862–$10.9k), но цените съвпадат с CoinGecko → verified.

    Под $5k кандидатите се режат ($862/$3.2k), избира се най-дълбокият
    ($10 892 @ 0.3160); толерансът за тънък пул е по-широк."""
    _dex_pairs(monkeypatch, verifier, [
        _pair("KAITO", 0.3265, 3_257.0),     # под $5k — отпада
        _pair("KAITO", 0.3139, 862.0),       # под $5k — отпада
        _pair("KAITO", 0.3170, 8_622.0),
        _pair("KAITO", 0.3160, 10_892.0),    # най-дълбокият ≥ $5k
    ])
    _fake_coco(monkeypatch, verifier, {"KAITO": (0.315093, "ok")})

    deliverable, rejected, scan_info = verifier.verify_signals(
        [{"token": "KAITO", "price_usd": 0.315093}])

    assert len(deliverable) == 1 and rejected == []
    assert scan_info["verification"] == "verified"
    detail = scan_info["details"][0]
    assert detail["dexscreener_usd"] == 0.3160
    assert detail["dex_liquidity_usd"] == 10_892.0
    assert detail["tolerance_pct"] == verifier.THIN_POOL_TOLERANCE_PCT
    assert detail["diff_pct"] < 0.5


def test_thin_pool_wider_tolerance_but_not_endless(monkeypatch, verifier):
    """2.6% разминаване: тънък пул → verified (3% толеранс);
    дълбок пул ($250k) → rejected (обичайните 2%). Толерансът не е безкраен."""
    signal = [{"token": "KAITO", "price_usd": 0.315093}]
    _fake_coco(monkeypatch, verifier, {"KAITO": (0.315093, "ok")})

    monkeypatch.setattr(verifier, "_dexscreener_source",
                        lambda sym, ref: (0.3235, "ok", 10_892.0))
    d1, r1, s1 = verifier.verify_signals(signal)
    assert len(d1) == 1 and r1 == []
    assert s1["details"][0]["diff_pct"] == pytest.approx(2.596, abs=0.01)

    monkeypatch.setattr(verifier, "_dexscreener_source",
                        lambda sym, ref: (0.3235, "ok", 250_000.0))
    d2, r2, s2 = verifier.verify_signals(signal)
    assert d2 == [] and len(r2) == 1
    assert r2[0]["reason"] == "mismatch"
    assert r2[0]["diff_pct"] == pytest.approx(2.596, abs=0.01)


# ── ONDO: честно „missing" ≠ отхвърляне (Фикс 1) ────────────────────────────

def test_ondo_honest_missing_is_delivered_unverified(monkeypatch, verifier):
    """Няма истинска Base двойка (само фалшив токен на $0.00000035) →
    DexScreener е честно „missing" → по Фикс 1 сигналът СЕ ДОСТАВЯ с
    unverified бележка и НЕ влиза в rejected_signals[]."""
    _dex_pairs(monkeypatch, verifier, [
        _pair("ONDO", 0.4637, 1_731_588.0, chain="ethereum"),   # друга верига
        _pair("ONDO", 0.4653, 205_103.0, chain="solana"),       # друга верига
        _pair("ONDO", 0.00000035, 34_303.0),                    # фалшив Base
    ])
    _fake_coco(monkeypatch, verifier, {"ONDO": (0.465, "ok")})

    price, outcome, liq = verifier._dexscreener_source("ONDO", 0.465)
    assert (price, outcome, liq) == (None, "missing", None)   # ratio-гвардът
                                                              # реже фалшивия
    deliverable, rejected, scan_info = verifier.verify_signals(
        [{"token": "ONDO", "price_usd": 0.465}])

    assert len(deliverable) == 1        # платеният сигнал се доставя
    assert rejected == []               # липсващ източник ≠ несъответствие
    assert scan_info["verification"] == "unverified"
    assert scan_info["unverified"] == 1 and scan_info["rejected"] == 0
    detail = scan_info["details"][0]
    assert detail["reason"] == "source_missing:dexscreener"
    assert detail["coingecko_usd"] == 0.465
    assert detail["dexscreener_usd"] is None