"""An isolated store must share the LOCAL file, and own only its Postgres link.

THE BUG THIS PINS, measured live on a PAID route:

    whaleflow store unavailable: database is locked

"database is locked" is a SQLITE message, and production's durable tables are
PostgreSQL — so the message was about the one thing isolation was never supposed
to touch. Every isolated store opened its own SQLite connection to the SAME file,
and SQLite permits one writer at a time.

The whole point of an isolated store is a separate POSTGRES LINK, because that is
the resource with a single lock and a queue of waiters behind it. The local file
was never contended; giving each background job its own handle to it created
contention where there had been none.
"""

from integrations.dashboard_store import DashboardStore


def _store(tmp_path, name, **kw):
    return DashboardStore(tmp_path / name, **kw)


def test_an_isolated_store_shares_the_local_lock_and_connection(tmp_path):
    """Sharing the lock is what removes the contention; sharing the connector is
    what makes it the SAME file rather than a second handle to it."""
    owner = _store(tmp_path, "owner.db")
    isolated = _store(tmp_path, "owner.db", ensure_schema=False,
                      share_sqlite_from=owner)

    assert isolated._write_lock is owner._write_lock, (
        "the isolated store has its own SQLite lock, so two jobs can write the "
        "same file at once and one gets `database is locked`")
    # A bound method is created fresh on every attribute access, so `is` on the
    # METHODS is always False. What must match is the underlying function and the
    # object it is bound to — which is what "the same connector" means.
    assert isolated._connect.__func__ is owner._connect.__func__, (
        "the isolated store uses a different connector function")
    assert isolated._connect.__self__ is owner, (
        "the isolated store opened a SECOND handle to the same file")


def test_an_isolated_store_still_owns_its_postgres_lock(tmp_path):
    """THE OTHER HALF, and it must not be lost while fixing the first.

    If isolation stopped isolating the durable link it would be pointless — the
    request path would queue behind the board build again, which is the outage
    this whole mechanism exists to prevent.
    """
    owner = _store(tmp_path, "owner.db")
    isolated = _store(tmp_path, "owner.db", ensure_schema=False,
                      share_sqlite_from=owner)

    assert isolated.history is not owner.history
    assert isolated.history._pg_lock is not owner.history._pg_lock


def test_a_normal_store_still_creates_its_own_database(tmp_path):
    """The default path must be unchanged: a store that owns its schema."""
    store = _store(tmp_path, "fresh.db")
    assert store._write_lock is not None
    # `_ensure_db` ran, so the local tables exist.
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r[0] if not hasattr(r, "keys") else r["name"] for r in rows}
    assert "meta" in names and "payapi_state" in names


def test_two_isolated_stores_do_not_fight_over_the_file(tmp_path):
    """THE SYMPTOM, in miniature: two stores on one file, both writing.

    Before the share, the second write raised `database is locked`. This asserts
    the behaviour a paid route depends on.
    """
    owner = _store(tmp_path, "owner.db")
    owner.set_meta("probe_a", "1")

    a = _store(tmp_path, "owner.db", ensure_schema=False, share_sqlite_from=owner)
    b = _store(tmp_path, "owner.db", ensure_schema=False, share_sqlite_from=owner)

    a.set_meta("probe_b", "2")
    b.set_meta("probe_c", "3")
    assert a.get_meta("probe_c") == "3", (
        "the two stores do not see the same file")
