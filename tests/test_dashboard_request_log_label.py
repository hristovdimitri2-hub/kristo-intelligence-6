# -*- coding: utf-8 -*-
"""Етикетът на трафик историята трябва да сочи РЕАЛНИЯ ѝ двигател.

ДЕФЕКТЪТ (намерен на живо 06.11): payload-ът носеше hard-coded низа
``"постоянен лог (SQLite)"``. Той е бил верен някога, но durable таблиците
(request_log, onchain_sales, payment_guards) са преместени в PostgreSQL на 14.09
— boot логът казва ``Durable store ready (postgresql)``. Оттогава таблото
съобщаваше на оператора, че историята на трафика живее във файл, който deploy
може да изтрие: точно обратното на причината таблицата да бъде преместена.

Защо това е дефект от същия клас, който цялата сесия изкоренява: таблото е
инструмент, на който се вярва. Етикет, който описва резервния вариант като
живия, подвежда точно там, където човекът решава дали данните му са в
безопасност.

ЗАКОВКА: етикетът се ИЗВЕЖДА от хранилището, не се повтаря като литерал — и
тези тестове пазят и двете посоки, за да не може да изостане отново нито в
единия, нито в другия бекенд.
"""
import pytest


@pytest.fixture()
def dash():
    import main
    return main


def _label_with_backend(dash, monkeypatch, backend):
    monkeypatch.setattr(type(dash.dashboard_db), "backend",
                        property(lambda self: backend))
    payload = dash._canonical_dashboard_payload()
    return payload["sections"]["requests"]["label"]


def test_label_names_postgresql_when_postgresql_holds_the_history(dash, monkeypatch):
    label = _label_with_backend(dash, monkeypatch, "postgresql")
    assert label == "постоянен лог (PostgreSQL)"
    # Инверт: старият литерал не бива да оцелее по никоя пътека.
    assert "SQLite" not in label


def test_label_names_sqlite_when_sqlite_is_really_the_backend(dash, monkeypatch):
    # Ако DATABASE_URL изчезне, SQLite Е истината — и етикетът трябва да го каже,
    # вместо да твърди PostgreSQL по навик. Дефектът беше литерал, не изборът на
    # дума: затова се пази и тази посока.
    label = _label_with_backend(dash, monkeypatch, "sqlite")
    assert label == "постоянен лог (SQLite)"


def test_the_store_exposes_the_backend_it_actually_uses():
    # Свойството, от което етикетът черпи, трябва да съществува и да отговаря на
    # HistoryStore (единственият собственик на durable таблиците).
    import os
    import tempfile

    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(os.path.join(tempfile.mkdtemp(), "t.db"))
    assert store.backend == store.history.backend
    assert store.backend in ("postgresql", "sqlite")
