# -*- coding: utf-8 -*-
"""The isolation memo is READ by pool, so it must be WRITTEN by pool.

THE DEFECT THIS PINS, and why the existing guard walked past it.

`_isolated_store(purpose)` computes `pool = _ISOLATION_POOLS.get(purpose,
purpose)` and then looks the cache up as `_isolated_stores.get(pool)`. For 7 of
the 8 purposes the pool name differs from the purpose name
(`sentinel` -> `background-light`, `requests-snapshot` -> `snapshot`,
`whaleflow-scan` -> `background-heavy`, ...). The cache was written as
`_isolated_stores[purpose]`, so for those 7 the lookup could never hit.

The consequence was not a slow path, it was the exact failure the pool was
introduced to prevent, described in the comment sitting directly above the bug: a
Postgres connection per call exhausts the database's connection limit. The
existing test `test_the_pool_count_is_bounded_below_the_connection_limit` checked
the MAP and the map was always correct — so it passed while the memo was dead.

The log line inside `_isolated_store` is the memo's own witness: a working cache
prints it once per process. On 2026-11-09 18:00 it printed 8 times in 7 seconds
for `sentinel`, and on 2026-11-10 12:00-12:20 `sentinel` 10 times,
`reorg-watch` 5 times, `requests-snapshot` 3 times — a fresh DashboardStore, a
fresh HistoryStore and a fresh Postgres link each time, the previous object
dropped without being closed.
"""
from types import SimpleNamespace

import pytest


class _FakeStore:
    """Counts constructions: that number IS the number of Postgres links."""

    built = 0

    def __init__(self, *args, **kwargs):
        _FakeStore.built += 1
        self.backend = "postgresql"


@pytest.fixture()
def isolated(monkeypatch):
    """`_isolated_store` only takes the pool path on a Postgres backend."""
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    _FakeStore.built = 0
    monkeypatch.setattr(main, "DashboardStore", _FakeStore)
    monkeypatch.setattr(main, "dashboard_db",
                        SimpleNamespace(backend="postgresql"))
    main._isolated_stores.clear()
    yield main
    main._isolated_stores.clear()


def test_a_second_call_reuses_the_same_store(isolated):
    """The memo has to hit, or every call opens another Postgres link."""
    main = isolated
    first = main._isolated_store("sentinel")
    second = main._isolated_store("sentinel")
    assert first is second, (
        "a second call built a NEW store: the memo is keyed by purpose while it "
        "is read by pool, so it can never hit")
    assert _FakeStore.built == 1, (
        "%d stores built for two calls — each one is a Postgres connection"
        % _FakeStore.built)


def test_the_memo_is_keyed_by_pool_and_not_by_purpose(isolated):
    """Naming the key is the whole fix; assert the name, not just the reuse."""
    main = isolated
    main._isolated_store("sentinel")
    assert "background-light" in main._isolated_stores, (
        "the store is not filed under its pool")
    assert "sentinel" not in main._isolated_stores, (
        "the store is filed under its purpose, which is what broke the lookup")


def test_purposes_that_share_a_pool_share_one_connection(isolated):
    """Pool sharing is deliberate in `_ISOLATION_POOLS`; it must actually happen.

    If each purpose got its own store the pool count would be meaningless and the
    connection ceiling that motivated the design would be back.
    """
    main = isolated
    sentinel = main._isolated_store("sentinel")
    reorg = main._isolated_store("reorg-watch")
    assert sentinel is reorg, (
        "sentinel and reorg-watch are both mapped to background-light but got "
        "different stores")
    assert _FakeStore.built == 1


def test_distinct_pools_still_get_distinct_stores(isolated):
    """The fix must not collapse the pools into one shared connection."""
    main = isolated
    sentinel = main._isolated_store("sentinel")           # background-light
    build = main._isolated_store("dashboard-build")        # its own pool
    scan = main._isolated_store("whaleflow-scan")          # background-heavy
    assert len({id(sentinel), id(build), id(scan)}) == 3, (
        "pools that must not contend ended up sharing one store")
    assert _FakeStore.built == 3


def test_every_declared_pool_builds_exactly_one_store(isolated):
    """One store per pool, whatever the call order — the property the design wants."""
    main = isolated
    purposes = sorted(set(main._ISOLATION_POOLS) | {"a-brand-new-job"})
    for purpose in purposes:
        main._isolated_store(purpose)
    for purpose in purposes:
        main._isolated_store(purpose)
    pools = {main._ISOLATION_POOLS.get(p, p) for p in purposes}
    assert _FakeStore.built == len(pools), (
        "%d stores built for %d pools across two full passes"
        % (_FakeStore.built, len(pools)))
    assert set(main._isolated_stores) == pools
