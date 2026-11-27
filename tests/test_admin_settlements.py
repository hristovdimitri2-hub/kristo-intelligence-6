"""The settlement export, which exists to be handed to somebody else.

A reconciliation is only worth anything if the other party can re-check every
row, so the things pinned here are the ones that make it checkable: the
transaction hash is present, the count is honest about whether it is complete,
and nobody without the admin token can read it.
"""
import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main

    return main.app.test_client()


def test_the_export_refuses_a_caller_without_the_admin_token(client):
    assert client.get("/api/admin/settlements").status_code != 200


def test_the_export_returns_rows_carrying_the_join_key(client, monkeypatch):
    import main

    seen = {}

    def fake_rows(limit=500):
        seen["limit"] = limit
        return {"rows": [{"tx_hash": "0x" + "ab" * 32, "block_number": 42,
                          "ts": "2026-11-27T00:00:00+00:00",
                          "sender": "0x" + "cd" * 20, "amount_usdc": 0.005,
                          "payer_class": "external", "payer_label": None,
                          "source": "live"}],
                "returned": 1, "total": 189, "limit": limit, "complete": False,
                "oldest_row_ts": None, "newest_row_ts": None}

    monkeypatch.setattr(main.dashboard_db, "settlement_rows", fake_rows)
    body = client.get("/api/admin/settlements?limit=250",
                      headers={"X-Admin-Token": "test-admin-token"}).get_json()

    assert body["ok"] is True
    assert seen["limit"] == 250
    assert body["rows"][0]["tx_hash"].startswith("0x")
    assert body["complete"] is False, (
        "a truncated export must say so — a sample read as the whole ledger is "
        "the defect this export exists to make impossible")
    assert body["total"] == 189


def test_an_unreadable_store_is_a_clean_error_not_a_500(client, monkeypatch):
    import main

    def boom(limit=500):
        raise RuntimeError("store is down")

    monkeypatch.setattr(main.dashboard_db, "settlement_rows", boom)
    response = client.get("/api/admin/settlements",
                          headers={"X-Admin-Token": "test-admin-token"})

    assert response.status_code == 503
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"] == "store_unreadable"


def test_the_limit_is_clamped_before_any_sql_runs(client, monkeypatch):
    import main

    seen = {}

    def fake_rows(limit=500):
        seen["limit"] = limit
        return {"rows": [], "returned": 0, "total": 0, "limit": limit,
                "complete": True, "oldest_row_ts": None, "newest_row_ts": None}

    monkeypatch.setattr(main.dashboard_db, "settlement_rows", fake_rows)
    for asked, expected in (("99999", 99999), ("nonsense", 500)):
        client.get(f"/api/admin/settlements?limit={asked}",
                   headers={"X-Admin-Token": "test-admin-token"})
        assert seen["limit"] == expected
