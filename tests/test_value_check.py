# -*- coding: utf-8 -*-
"""
Фаза 1 — rule-based проверяващ слой „никой не лъже" (services/verifier.py).

Правила:
  * разминаване > толеранс ИЛИ един източник без цена → сигналът НЕ минава
    (не се доставя; логва се и влиза в scan_info.details);
  * източник с транспортна грешка / целият checker падне → fail-open:
    платеният сигнал СЕ ДОСТАВЯ, бележен като непроверен в scan_info;
  * отхвърлените/непроверените се записват в guard_events (дълготраен лог).

Под pytest проверката е изключена по подразбиране (tests/conftest.py) —
тук я включваме изрично и подменяме източниците с фалкове (без мрежа).
"""
import pytest


@pytest.fixture()
def verifier():
    from services import verifier
    verifier._dex_cache.clear()
    return verifier


def _fake_sources(monkeypatch, verifier, cg: dict, ds: dict):
    """cg/ds: {SYM: (price|None, 'ok'|'missing'|'error')}"""
    monkeypatch.setattr(verifier, "_coingecko_source",
                        lambda symbols: {s: cg.get(s, (None, "missing"))
                                         for s in symbols})
    monkeypatch.setattr(verifier, "_dexscreener_source",
                        lambda sym, ref: ds.get(sym, (None, "missing")))


def test_verified_when_sources_agree_within_tolerance(monkeypatch, verifier):
    _fake_sources(monkeypatch, verifier,
                  {"ETH": (2500.0, "ok")}, {"ETH": (2510.0, "ok")})  # 0.4%
    signals = [{"token": "ETH", "price_usd": 2501.2, "action": "recommend_buy"}]
    deliverable, scan_info = verifier.verify_signals(signals)
    assert len(deliverable) == 1
    assert scan_info["verification"] == "verified"
    assert scan_info["verified"] == 1 and scan_info["rejected"] == 0
    assert scan_info["details"][0]["verdict"] == "verified"
    assert scan_info["details"][0]["diff_pct"] == pytest.approx(0.398, abs=0.01)


def test_mismatch_beyond_tolerance_does_not_pass(monkeypatch, verifier, caplog):
    _fake_sources(monkeypatch, verifier,
                  {"ETH": (2500.0, "ok")}, {"ETH": (2600.0, "ok")})  # 3.8%
    signals = [{"token": "ETH", "price_usd": 2501.2},
               {"token": "ONDO", "price_usd": 0.38}]
    # ONDO няма фалкове → source missing → също не минава
    deliverable, scan_info = verifier.verify_signals(signals)
    assert deliverable == []                     # „сигналът не минава"
    assert scan_info["verification"] == "rejected"
    assert scan_info["rejected"] == 2
    eth = scan_info["details"][0]
    assert eth["verdict"] == "rejected" and eth["reason"] == "mismatch"
    assert eth["coingecko_usd"] == 2500.0 and eth["dexscreener_usd"] == 2600.0
    assert "REJECTED" in caplog.text             # лог за „кой агент лъже"


def test_one_source_missing_does_not_pass(monkeypatch, verifier):
    _fake_sources(monkeypatch, verifier,
                  {"ETH": (2500.0, "ok")}, {"ETH": (None, "missing")})
    deliverable, scan_info = verifier.verify_signals(
        [{"token": "ETH", "price_usd": 2501.2}])
    assert deliverable == []
    assert scan_info["details"][0]["reason"] == "source_missing:dexscreener"


def test_source_error_fails_open_delivering_unverified(monkeypatch, verifier):
    _fake_sources(monkeypatch, verifier,
                  {"ETH": (2500.0, "ok")}, {"ETH": (None, "error")})
    deliverable, scan_info = verifier.verify_signals(
        [{"token": "ETH", "price_usd": 2501.2}])
    # fail-open: парите са факт → доставя се, но е непроверен
    assert len(deliverable) == 1
    assert scan_info["verification"] == "unverified"
    assert scan_info["details"][0]["reason"] == "source_error:dexscreener"


def test_no_number_signal_delivered_but_marked_unverified(verifier):
    deliverable, scan_info = verifier.verify_signals(
        [{"token": "DEGEN", "price_usd": None, "action": "monitor"}])
    assert len(deliverable) == 1
    assert scan_info["unverified"] == 1
    assert scan_info["details"][0]["reason"] == "no_number_to_check"


def test_tolerance_boundary_exactly_at_limit(monkeypatch, verifier):
    # 2% точно → минава; 2.1% → не минава
    _fake_sources(monkeypatch, verifier,
                  {"ETH": (100.0, "ok")}, {"ETH": (102.0, "ok")})
    d1, s1 = verifier.verify_signals([{"token": "ETH", "price_usd": 101.0}])
    assert len(d1) == 1 and s1["verified"] == 1
    verifier._dex_cache.clear()
    _fake_sources(monkeypatch, verifier,
                  {"ETH": (100.0, "ok")}, {"ETH": (102.1, "ok")})
    d2, s2 = verifier.verify_signals([{"token": "ETH", "price_usd": 101.0}])
    assert d2 == [] and s2["rejected"] == 1


# ── route ниво: scan_info + двойния fail-open + guard_events ────────────────

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "t")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("VALUE_CHECK_ENABLED", "1")
    import main
    sample = {"generated_at": "2026-10-07T00:00:00+00:00", "signals": [
        {"token": "ETH", "action": "recommend_buy", "confidence": 0.82,
         "price_usd": 2501.2, "reasoning": "Core L1", "note": "price=$2501.2"},
        {"token": "ONDO", "action": "monitor", "confidence": 0.41,
         "price_usd": 0.38, "reasoning": "RWA", "note": ""},
    ]}
    monkeypatch.setattr(main, "_latest_signals", sample)
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 1000)
    main._free_tier_usage.clear()
    return main.app.test_client()


def test_route_delivers_scan_info_and_all_when_verified(client, monkeypatch, verifier):
    _fake_sources(monkeypatch, verifier,
                  {"ETH": (2500.0, "ok"), "ONDO": (0.381, "ok")},
                  {"ETH": (2510.0, "ok"), "ONDO": (0.38, "ok")})
    r = client.get("/api/v1/signal")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["signal_count"] == 2
    assert payload["scan_info"]["verification"] == "verified"
    assert payload["scan_info"]["sources"] == ["coingecko", "dexscreener"]


def test_route_excludes_rejected_signal_and_records_guard_event(
        client, monkeypatch, verifier):
    import main
    _fake_sources(monkeypatch, verifier,
                  {"ETH": (2500.0, "ok"), "ONDO": (0.38, "ok")},
                  {"ETH": (2600.0, "ok"), "ONDO": (None, "missing")})
    events = []
    monkeypatch.setattr(main.dashboard_db, "record_guard_event",
                        lambda kind, **kw: events.append((kind, kw)))
    r = client.get("/api/v1/signal")
    payload = r.get_json()
    # и двата отхвърлени → „не минават"; парите са факт, но лъжа не се доставя
    assert payload["signals"] == []
    assert payload["signal_count"] == 0
    assert payload["scan_info"]["verification"] == "rejected"
    assert payload["scan_info"]["rejected"] == 2
    # дълготраен лог за „кой агент редовно лъже"
    kinds = [k for k, _ in events]
    assert kinds.count("value_check_rejected") == 2
    assert all(kw["endpoint"] == "/api/v1/signal" for _, kw in events)


def test_route_fail_open_when_checker_crashes(client, monkeypatch):
    """Ако целият checker падне, платеният сигнал се доставя непокътнат."""
    from services import verifier as v

    def boom(signals):
        raise RuntimeError("checker exploded")

    monkeypatch.setattr(v, "verify_signals", boom)
    r = client.get("/api/v1/signal")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["signal_count"] == 2          # всичко се доставя
    assert payload["scan_info"]["verification"] == "unverified"
    assert "checker_error" in payload["scan_info"]["reason"]


def test_route_disabled_check_returns_signals_untouched(client, monkeypatch):
    monkeypatch.setenv("VALUE_CHECK_ENABLED", "0")
    r = client.get("/api/v1/signal")
    payload = r.get_json()
    assert payload["signal_count"] == 2
    assert payload["scan_info"]["verification"] == "disabled"


def test_route_source_error_is_fail_open_delivered(client, monkeypatch, verifier):
    """Транспортна грешка на източник ≠ отхвърляне — доставя се като непроверен."""
    import main
    _fake_sources(monkeypatch, verifier,
                  {"ETH": (2500.0, "ok"), "ONDO": (0.38, "ok")},
                  {"ETH": (None, "error"), "ONDO": (0.38, "ok")})
    events = []
    monkeypatch.setattr(main.dashboard_db, "record_guard_event",
                        lambda kind, **kw: events.append(kind))
    r = client.get("/api/v1/signal")
    payload = r.get_json()
    assert payload["signal_count"] == 2          # fail-open: доставено
    assert payload["scan_info"]["verification"] == "unverified"
    assert "value_check_unverified" in events    # и е логнато трайно
