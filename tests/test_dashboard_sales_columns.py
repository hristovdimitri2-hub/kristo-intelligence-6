# -*- coding: utf-8 -*-
"""ON-CHAIN SALES · нови колони (14.10).

УСЛУГА: payload-ът носи `route` за всеки TX — доказателството е granted
claim-ът в `payment_guards` (същото join-че като CLIENTS секцията); без claim
→ route: None и таблото показва "—". КЛИЕНТ думите са JavaScript (CLS_WORDS в
dashboard.html) — тук закотваме payload страната + fail-open поведението.
"""
import pytest


@pytest.fixture()
def dash(monkeypatch):
    import main

    fake_sales = {
        "total_usdc": 0.006, "total_count": 2,
        "today_usdc": 0.003, "today_count": 1, "today_date": "2026-10-14",
        "external_payers": 1, "by_class": {},
        "history": [
            {"tx_hash": "0xAAA", "amount_usdc": 0.003,
             "payer_class": "external", "payer_label": "external",
             "sender": "0xabc", "block_number": 100,
             "ts": "2026-10-13T23:18:00+00:00", "source": "live"},
            {"tx_hash": "0xBBB", "amount_usdc": 0.003,
             "payer_class": "sampler", "payer_label": "market_crawler_54e1",
             "sender": "0xdef", "block_number": 200,
             "ts": "2026-10-14T14:19:24+00:00", "source": "live"},
        ],
    }
    monkeypatch.setattr(main.dashboard_db, "sales_summary",
                        lambda *a, **k: fake_sales)
    monkeypatch.setattr(main.dashboard_db, "guard_endpoint_map",
                        lambda: {"0xaaa": "/api/v1/whaleflow"})
    return main


def test_onchain_history_carries_route_from_granted_claim(dash):
    payload = dash._canonical_dashboard_payload()
    hist = payload["sections"]["onchain"]["history"]
    assert [r["route"] for r in hist] == ["/api/v1/whaleflow", None]


def test_route_join_fails_open_when_store_unavailable(dash, monkeypatch):
    def boom():
        raise RuntimeError("lock backend down")

    monkeypatch.setattr(dash.dashboard_db, "guard_endpoint_map", boom)
    payload = dash._canonical_dashboard_payload()
    onchain = payload["sections"]["onchain"]
    assert [r.get("route") for r in onchain["history"]] == [None, None]
    # останалата част от секцията не се чупи
    assert onchain["total_count"] == 2
    assert onchain["class_labels"]   # КЛИЕНТ думите си имат подложка (labels)


def test_dashboard_template_has_service_and_client_columns():
    from pathlib import Path
    html = Path("templates/dashboard.html").read_text(encoding="utf-8")
    assert "<th>УСЛУГА</th>" in html
    assert "<th>КЛИЕНТ</th>" in html
    assert "CLS_WORDS" in html
    assert "човек / външен клиент" in html
    assert "бот — сондьор" in html
    assert "наш тест" in html
    assert "sales-table" in html          # sort scope — само тази таблица
    assert "data-v=" in html              # стойностите за сортиране
    # старата разцветка е запазена (tag класовете)
    assert ".tag.external" in html and ".tag.sampler" in html \
        and ".tag.canary" in html