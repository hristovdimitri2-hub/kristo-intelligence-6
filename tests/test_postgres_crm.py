from integrations.crm_store import (CRMStore, LeadRecord, PostgresCRMStore,
                                    create_crm_store)


def test_create_crm_store_prefers_postgres_when_database_url_is_available(
        tmp_path, monkeypatch):
    """The Postgres store is chosen when DATABASE_URL is set.

    The connection is FAKED on purpose. `create_crm_store` builds the Postgres
    store eagerly, so a real `connect()` runs here — and against a host that is
    not listening it does not fail fast: the suite HANGS (found 14.09 while
    installing psycopg, which is in requirements.txt, so anyone running the
    tests on a normal machine is exposed). This test is about WHICH store is
    chosen; reachability has its own tests below.
    """
    class _FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            return None

        def fetchall(self):
            return []

        def fetchone(self):
            return None

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self):
            return _FakeCursor()

        def commit(self):
            return None

    monkeypatch.setattr(PostgresCRMStore, "_connect", lambda self: _FakeConn())
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


def test_postgres_crm_creates_its_schema_on_first_use(monkeypatch):
    """AUDIT A2b (13.09): the Postgres store ASSUMED the `leads` table already
    existed. The moment DATABASE_URL pointed at a BRAND-NEW Render Postgres,
    every CRM read raised `psycopg.errors.UndefinedTable: relation "leads" does
    not exist`, which turned /api/dashboard/data into an HTTP 500 for everyone.
    It must create its own schema, exactly like the SQLite store does."""
    executed = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            executed.append(" ".join(str(sql).split()))

        def fetchall(self):
            return []

        def fetchone(self):
            return None

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            executed.append("COMMIT")

    monkeypatch.setattr(PostgresCRMStore, "_connect", lambda self: FakeConn())
    store = PostgresCRMStore("postgresql://user:pw@example.invalid:5432/db")

    assert store.backend == "postgresql"
    sql = " ".join(executed)
    assert "CREATE TABLE IF NOT EXISTS leads" in sql      # idempotent
    assert "COMMIT" in executed
    # Every column add_lead() writes must exist in the created table.
    for column in ("email", "source", "campaign", "utm_source", "utm_medium",
                   "utm_campaign", "status", "created_at", "plan",
                   "telegram_chat_id", "amount_usd", "payment_status"):
        assert column in sql, f"schema is missing column {column}"


def test_postgres_crm_booting_survives_an_unreachable_database(monkeypatch,
                                                               caplog):
    """A new/unreachable database must never stop the app from booting: /health
    has to keep answering and the failure stays visible in the logs instead of
    killing the process at import time.

    The failure is SIMULATED on purpose. A real `connect()` to a dead host does
    not fail fast on Windows — it blocked this suite for **130 seconds** (a
    firewall that drops a SYN instead of refusing it) and still proved nothing
    more than the raised error proves. What matters is that `_ensure_schema`
    swallows the provider's exception and logs it, which is exactly the branch
    this drives.
    """
    import logging

    def _unreachable(self):
        raise RuntimeError("psycopg OperationalError: connection refused")

    monkeypatch.setattr(PostgresCRMStore, "_connect", _unreachable)
    with caplog.at_level(logging.WARNING, logger="integrations.crm_store"):
        store = PostgresCRMStore("postgresql://user:pw@127.0.0.1:1/db")

    assert store.backend == "postgresql"
    assert store.database_url.endswith("/db")
    # The boot survived AND said so — a silent failure would look like a healthy
    # store that mysteriously returns nothing.
    assert any("schema init failed" in r.getMessage()
               for r in caplog.records), "the failure must be logged"


def test_postgres_schema_and_mark_paid_carry_the_payment_facts(monkeypatch):
    """The Postgres store needs the same two columns as SQLite, ALTERed in for the
    live table (which predates them), and `mark_paid` must write both — while the
    upsert must refuse to downgrade a paid lead (the re-submitted form sends
    "pending"/$0)."""
    executed = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            executed.append(str(sql))

        def fetchall(self):
            return []

        def fetchone(self):
            # A real upsert / UPDATE ... RETURNING always yields the stored row.
            return {"email": "buyer@example.com", "payment_status": "pending",
                    "amount_usd": 0.0, "paid_at": None, "checkout_id": None}

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            executed.append("COMMIT")

    monkeypatch.setattr(PostgresCRMStore, "_connect", lambda self: FakeConn())
    store = PostgresCRMStore("postgresql://user:pw@example.invalid:5432/db")

    def code_only(parts):
        """The SQL with its `--` comments stripped: the comments TALK about the
        columns (that is their job), so they must not satisfy an assertion."""
        text = ""
        for part in parts:
            for line in str(part).splitlines():
                text += " " + line.split("--")[0]
        return " ".join(text.split())

    schema = code_only(executed)
    assert "paid_at TEXT" in schema and "checkout_id TEXT" in schema
    assert "ALTER TABLE leads ADD COLUMN IF NOT EXISTS" in schema, \
        "the live table must be migrated, not recreated"

    executed.clear()
    store.add_lead(LeadRecord(email="buyer@example.com", source="website",
                              campaign="launch"))
    upsert = code_only(executed)
    assert "INSERT INTO leads" in upsert and "DO UPDATE SET" in upsert
    # The upsert keeps the payment facts of a paid row.
    assert "leads.payment_status = 'paid'" in upsert
    assert "THEN leads.amount_usd ELSE EXCLUDED.amount_usd END" in upsert
    update_part = upsert.split("DO UPDATE SET")[1]
    assert "paid_at" not in update_part and "checkout_id" not in update_part, \
        "add_lead must never write payment facts — only mark_paid does"

    executed.clear()
    store.mark_paid("buyer@example.com", 34.8, "starter",
                    checkout_id="cs_live_first", paid_at="2026-09-16T08:56:08+00:00")
    mark = code_only(executed)
    assert "paid_at = CASE WHEN" in mark, mark
    assert "checkout_id = CASE WHEN" in mark, mark
    assert "RETURNING *" in mark