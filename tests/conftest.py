"""Suite-wide guard: pytest must never start production background threads.

pytest imports every test module at COLLECTION — before any monkeypatch
fixture runs. `tests/test_stripe_vip_flow.py` and `tests/test_sales_system.py`
import `main` at module level, and `main.py` starts its background threads on
import unless KRISTO_DISABLE_BACKGROUND_THREADS=true is already in the
environment (gate at `_start_background_threads`, main.py ~5242).

Those daemons (dashboard-scan with the SALES_CHUNK_BLOCKS default of 5000,
whaleflow-scan, blockchain-monitor, …) live for the whole session and can fire
mid-test: while `tests/test_whaleflow.py` has its refusing fake web3 installed
in sys.modules, the dashboard-scan loop's 5000-block getLogs lands in the
test's shared `attempts` closure and

    assert max(attempts) == 250   # observed 5000 — suite only, 1 in 4 runs

fails (observed 25.09; passes alone because no test file imports `main`).
Setting the flag HERE — before collection imports — guarantees no production
thread ever starts under pytest. No test asserts that the threads start.
"""
import os

os.environ["KRISTO_DISABLE_BACKGROUND_THREADS"] = "true"
# Фаза 1 value-check (services/verifier.py) прави реални HTTP заявки към
# CoinGecko/DexScreener — под pytest това би забавило и разклатило серията.
# По подразбиране проверката е ИЗКЛЮЧЕНА тук; тестовете, които я проверяват,
# я включват изрично с monkeypatch.setenv("VALUE_CHECK_ENABLED", "1") и
# подменят източниците с фалкове (никаква мрежа в серията).
os.environ.setdefault("VALUE_CHECK_ENABLED", "0")

import pytest


@pytest.fixture(autouse=True)
def _reset_dashboard_stats_cache():
    """The /api/dashboard-stats TTL cache lives on the shared `main` module.

    Without a per-test reset, a payload built by one test (e.g. with a seeded
    sale of 0.031) leaks into later tests that expect a fresh empty-store
    build — observed 11.10 in test_dashboard_v2 and test_integration.

    The same applies to `_DASHBOARD_LAST_GOOD`, and MORE so: since 05.11 the
    request path serves /api/dashboard/data from that cache and rebuilds only
    in the background, so a payload built under one test's seeded database
    would otherwise be replayed to every later test in the session. That is
    correct in production and poison under pytest. Cleared here rather than in
    each test, so a test added later cannot forget to do it.
    """
    import main
    if hasattr(main, "_reset_stats_cache"):
        main._reset_stats_cache()
    _clear = getattr(main, "_DASHBOARD_LAST_GOOD", None)
    _lock = getattr(main, "_DASHBOARD_LAST_GOOD_LOCK", None)
    _inflight = getattr(main, "_DASHBOARD_REFRESHING", None)
    _errors = getattr(main, "_DASHBOARD_LAST_ERROR", None)
    _timings = getattr(main, "_DASHBOARD_LAST_BUILD_TIMINGS", None)

    def _reset():
        if _clear is None or _lock is None:
            return
        with _lock:
            _clear.clear()
            if _inflight is not None:
                _inflight.clear()
            if _errors is not None:
                _errors.clear()
        if _timings is not None:
            _timings.clear()

    _reset()
    yield
    if hasattr(main, "_reset_stats_cache"):
        main._reset_stats_cache()
    _reset()


@pytest.fixture(autouse=True)
def _reset_request_summary_caches():
    """The traffic-summary caches on the shared store are process-global too.

    `requests_summary` replays a TTL-cached payload and overlays a parked
    all-time snapshot. Both live on the one `dashboard_db` instance that the
    whole session shares, so without this a snapshot parked by one test — or a
    summary computed over another test's seeded rows — is served to every later
    test. That is exactly the leak the dashboard-payload fixture above was
    written for; this is the same hazard one layer down.
    """
    import main
    store = getattr(main, "dashboard_db", None)
    history = getattr(store, "history", None)
    if history is None:
        yield
        return

    def _clear():
        for name, value in (("_summary_value", None), ("_summary_json", "{}"),
                            ("_summary_at", 0.0), ("_summary_limit", None),
                            ("_snapshot_value", None)):
            if hasattr(history, name):
                setattr(history, name, value)
        if hasattr(history, "_snapshot_refreshing"):
            history._snapshot_refreshing = False

    _clear()
    yield
    _clear()


@pytest.fixture(autouse=True)
def _no_market_data_retry_sleep(monkeypatch):
    """A CoinGecko retry must not sleep inside a request a test is timing.

    `services/market_data.py` retries a failed upstream call with a bounded
    jittered backoff — base 0.25 s plus up to 25 %, so ~0.25–0.31 s. That sleep
    happens in the SAME thread as the request that triggered it. Any test that
    counts sleeps in a request path therefore breaks whenever CoinGecko is
    unreachable or rate-limited, which is exactly the CI environment and not the
    developer's warm cache.

    Observed 20.11.2026 in CI on 8fe1ef3: `test_a5_reverted_receipt_polls_then_
    overrides_to_delivery` asserted `sleeps == [2, 2, 2, 2]` and got a fifth
    entry of 0.2615 — one market-data backoff, not a payment bug. The same
    commit's runs on 567eb6c and 241d977 went green, so the pipeline was
    reporting the upstream's availability, not our code.

    Zeroing the base makes the computed delay 0, so the retry still happens and
    still falls back to stale data — only the pause disappears. Production reads
    the same constants from the environment and is untouched. Tests that are
    ABOUT the backoff (`test_market_data_resilience.py`) set their own values.
    """
    from services import market_data
    monkeypatch.setattr(market_data, "_COINGECKO_BACKOFF_BASE_SECONDS", 0)


@pytest.fixture(autouse=True)
def _no_board_persistence_in_the_shared_store(monkeypatch):
    """Keep the dashboard board out of the developer's real database.

    Since 09.11 a successful build persists the PUBLIC board into the durable
    store so that a restart serves it instead of answering 503 "warming". Under
    pytest that store is the developer's own working database, which would mean:

      * a board written by one test seeding the cold path of every later test,
        exactly the leak the caches above are cleared to prevent; and
      * a real database write per test session for no benefit.

    So the accessor is pointed at nothing here, and the tests that are ABOUT
    persistence point it at a fake of their own. Nothing about production
    changes — this fixture exists only so that "no test can forget".
    """
    import main
    if hasattr(main, "_dashboard_meta_store"):
        monkeypatch.setattr(main, "_dashboard_meta_store", lambda: None)
    # The one-shot seed is per PROCESS by design, so a test that ran it would
    # otherwise leave every later test unseeded.
    if hasattr(main, "_DASHBOARD_SEED_THREAD"):
        monkeypatch.setattr(main, "_DASHBOARD_SEED_THREAD", None)
        monkeypatch.setattr(main, "_DASHBOARD_SEED_DONE", False)


os.environ.setdefault("VALUE_CHECK_ENABLED", "0")
