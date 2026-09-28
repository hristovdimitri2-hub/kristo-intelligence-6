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
