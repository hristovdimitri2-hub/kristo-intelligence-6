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

os.environ.setdefault("VALUE_CHECK_ENABLED", "0")
