# -*- coding: utf-8 -*-
"""Sentinel weekly report: exactly six market numbers (owner ask, 18.10)."""


def test_market_numbers_returns_exactly_six(monkeypatch):
    """Even when every external feed fails, the block stays six lines."""
    import requests as rq
    from services import sentinel

    def boom(*a, **k):
        raise rq.RequestException("offline")

    monkeypatch.setattr(sentinel, "_dashboard_store", lambda: None)
    monkeypatch.setattr(rq, "get", boom)
    monkeypatch.setattr(rq, "post", boom)

    rows = sentinel._market_numbers()
    assert len(rows) == 6
    labels = ("BTC/USD", "ETH/USD", "Base gas", "DeFi TVL",
              "x402 Trust resources", "402 payments (7d)")
    for row, lab in zip(rows, labels):
        assert lab in row, row
        assert row.endswith("n/a"), row


def test_build_report_contains_the_six_numbers(monkeypatch):
    from services import sentinel

    fake = [
        "• BTC/USD: $67,000",
        "• ETH/USD: $2,400",
        "• Base gas: 0.05 gwei",
        "• DeFi TVL (DefiLlama): $180.0B",
        "• x402 Trust resources (x402-doctor API): 55,812",
        "• Our 402 payments (7d): 12 · $0.0360 USDC",
    ]
    monkeypatch.setattr(sentinel, "_market_numbers", lambda: fake)
    report = sentinel._build_report({"health": "ok"})
    assert "🧭 Market (6 numbers)" in report
    for line in fake:
        assert line in report
    # exactly six bullet lines survive into the report
    assert sum(1 for l in report.splitlines() if l.startswith("• ")) == 6