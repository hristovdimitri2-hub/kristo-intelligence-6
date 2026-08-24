from integrations.crm_store import CRMStore, PostgresCRMStore, create_crm_store


def test_create_crm_store_prefers_postgres_when_database_url_is_available(tmp_path):
    store = create_crm_store(
        tmp_path / "crm.db",
        database_url="postgresql://user:password@localhost:5432/crm",
    )

    assert isinstance(store, PostgresCRMStore)
    assert store.backend == "postgresql"


def test_create_crm_store_uses_sqlite_without_database_url(tmp_path):
    store = create_crm_store(tmp_path / "crm.db", database_url="")

    assert isinstance(store, CRMStore)
    assert store.backend == "sqlite"