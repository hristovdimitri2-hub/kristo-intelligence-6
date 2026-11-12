# -*- coding: utf-8 -*-
"""The board must heal its own local file at RUNTIME, not only at boot.

Measured 2026-11-12: `/api/dashboard/data` answered 500 with an EMPTY cache and

    dashboard: background refresh failed ... database disk image is malformed

The local SQLite file had gone bad *after* the process started. The boot-time
heal had already run and had nothing to complain about, so every later build
failed, no payload was ever published, and the board stayed 500 for the life of
that process. A restart would have cleared it; nothing else would.

These two tests pin the remedy: the store can be healed on demand, and the build
retries exactly once after healing.
"""
import sqlite3

import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    from integrations.catalog_store import create_catalog_store
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setattr(main, "catalog_store",
                        create_catalog_store(tmp_path / "catalog.db"))
    dash = DashboardStore(tmp_path / "dashboard_state.db")
    monkeypatch.setattr(main, "dashboard_db", dash)
    return main, dash, tmp_path


def test_the_store_can_be_healed_after_it_went_bad(client):
    """The file is readable at construction and corrupt later — the exact case
    a boot-time-only heal cannot see."""
    _main, dash, tmp_path = client
    path = tmp_path / "dashboard_state.db"
    assert path.exists()

    dash.set_meta("healing_probe", "kept")           # healthy: it works

    path.write_bytes(b"this is not a sqlite file any more\n")   # goes bad

    assert dash.heal_local_store("test: database disk image is malformed") is True
    quarantined = list(tmp_path.glob("dashboard_state.db.corrupt-*"))
    assert quarantined, "the bad file must be kept as evidence, never deleted"
    assert quarantined[0].read_bytes().startswith(b"this is not a sqlite")

    with sqlite3.connect(str(path)) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "payapi_state"} <= names


def test_the_build_heals_and_retries_exactly_once(client, monkeypatch):
    """The failure path must recover, and must not loop."""
    main, dash, _tmp = client
    calls = []

    def flaky(*, include_crm=False, include_sales_detail=False):
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.DatabaseError("database disk image is malformed")
        return {"ok": True, "sections": {}, "attempt": len(calls)}

    monkeypatch.setattr(main, "_canonical_dashboard_payload", flaky)
    healed = []
    real_heal = dash.heal_local_store
    monkeypatch.setattr(dash, "heal_local_store",
                        lambda reason: healed.append(reason) or real_heal(reason))

    payload = main._dashboard_build((False, False), False, False)
    assert payload["ok"] is True
    assert payload["attempt"] == 2, "the build must have been retried"
    assert len(calls) == 2, "exactly one retry, never a loop"
    assert healed and "malformed" in healed[0]


def test_a_second_failure_is_not_swallowed(client, monkeypatch):
    """If it is still broken after the heal, the error must surface — a board
    that cannot build has to say so rather than serve an empty success."""
    main, dash, _tmp = client

    def always_broken(*, include_crm=False, include_sales_detail=False):
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", always_broken)
    with pytest.raises(sqlite3.DatabaseError):
        main._dashboard_build((False, False), False, False)


def test_a_non_local_error_is_not_treated_as_corruption(client, monkeypatch):
    """A Postgres failure must not quarantine a perfectly good local file."""
    main, dash, tmp_path = client
    healed = []
    monkeypatch.setattr(dash, "heal_local_store",
                        lambda reason: healed.append(reason) or True)

    def pg_down(*, include_crm=False, include_sales_detail=False):
        raise RuntimeError("could not connect to server")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", pg_down)
    with pytest.raises(RuntimeError):
        main._dashboard_build((False, False), False, False)
    assert healed == [], (
        "only a local-storage error may quarantine the local file")
