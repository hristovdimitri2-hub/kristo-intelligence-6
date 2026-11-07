"""RED→GREEN: the 06.11 incident — "the chain is down" vs "our monitor did not start".

Two independent loops read this chain out of the same store:

  * `_blockchain_monitor_loop` — the dedicated payment monitor, whose wallet init
    is the ONLY thing `/health` used to measure; and
  * `_dashboard_scan_loop` — the sales scan, which holds its own Web3 connection,
    records sales from the same receiver, and was demonstrably working.

On 06.11 the monitor failed to initialise (plausibly the rate-limited public RPC
that `/ready`'s own docstring already names as this service's known failure mode).
`/health` then reported `blockchain.ready: false` for over half an hour and the
sentinel raised a Telegram alarm — while the sales scan read the same chain
successfully every 60 seconds. That is the audit's defect class in the other
direction: not "couldn't look" reported as "found nothing", but "it works" reported
as "it is down".

The fix splits the two questions and reports BOTH, so the false alarm stops
WITHOUT the monitor's real failure being hidden:

    blockchain.ready  = is the chain reachable (the dependency; what callers act on)
    blockchain.monitor_ready = did the dedicated redundant monitor start (one part)
"""

import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

# Mirrors main.py — the untouched defaults of `_wallet_state`.
_DEFAULTS = {
    "wallet_address": None,
    "fee_receiver": None,
    "usdc_balance": 0.0,
    "receiver_usdc_balance": 0.0,
    "rpc_connected": False,
    "chain_id": None,
    "network": "Base Mainnet",
    "receiver_valid": False,
    "rpc_error": None,
    "last_block_checked": 0,
    "last_check_time": None,
    "sales_scan_ok_at": None,
    "sales_scan_block": 0,
}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    from integrations.catalog_store import create_catalog_store
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setattr(
        main, "catalog_store", create_catalog_store(tmp_path / "catalog.db"))
    dash = DashboardStore(tmp_path / "dashboard_state.db")
    monkeypatch.setattr(main, "dashboard_db", dash)

    # A store that reports itself healthy, so the database is never the blocker and
    # each test is genuinely about the chain.
    class _LiveStore:
        backend = "sqlite"

        def is_healthy(self):
            return True

    monkeypatch.setattr(main, "crm_store", _LiveStore())
    return main.app.test_client(), main


def _startup_module(main_mod, wallet_state):
    """Stub of `sys.modules["__main__"]` the way `python main.py` builds it."""
    stub = types.ModuleType("__main__")
    stub.__file__ = "C:/app/main.py"  # basename == "main.py"
    stub._wallet_state = wallet_state
    stub._lock = main_mod._lock
    stub.crm_store = main_mod.crm_store
    # The shared store the worker process publishes to, plus the key names. Without
    # these the endpoint would fall back to this process's memory only — which is
    # exactly the bug, so the tests must exercise the real path.
    stub.dashboard_db = main_mod.dashboard_db
    stub.MONITOR_HEARTBEAT_KEY = main_mod.MONITOR_HEARTBEAT_KEY
    stub.MONITOR_HEARTBEAT_BLOCK_KEY = main_mod.MONITOR_HEARTBEAT_BLOCK_KEY
    stub.SALES_SCAN_HEARTBEAT_KEY = main_mod.SALES_SCAN_HEARTBEAT_KEY
    return stub


def _publish(monkeypatch, main_mod, wallet_state):
    monkeypatch.setitem(
        sys.modules, "__main__", _startup_module(main_mod, wallet_state))


def _worker_publishes(main_mod, monitor_at=None, monitor_block=None, scan_at=None):
    """Write the stamps the way the WORKER process does: to the shared store.

    This is the whole point of the 07.11 fix — the web process cannot see the
    worker's memory, so these tests put the evidence where it actually lands.
    """
    if monitor_at is not None:
        main_mod.dashboard_db.set_meta(main_mod.MONITOR_HEARTBEAT_KEY, monitor_at)
    if monitor_block is not None:
        main_mod.dashboard_db.set_meta(main_mod.MONITOR_HEARTBEAT_BLOCK_KEY,
                                       str(monitor_block))
    if scan_at is not None:
        main_mod.dashboard_db.set_meta(main_mod.SALES_SCAN_HEARTBEAT_KEY, scan_at)


def _ago(seconds):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


# ── the split itself ─────────────────────────────────────────────────────────


def test_a_dead_monitor_no_longer_reports_the_chain_as_down(client, monkeypatch):
    """06.11, exactly: monitor never started, sales scan reading fine."""
    flask_client, main_mod = client

    _publish(monkeypatch, main_mod,
             dict(_DEFAULTS, sales_scan_ok_at=_ago(30), sales_scan_block=53_969_441))

    body = flask_client.get("/health").get_json()

    assert body["blockchain"]["ready"] is True, (
        "the sales scan read the chain 30s ago, so the chain is not down: %r" % body)
    assert body["status"] == "ok", body


def test_but_the_monitor_failure_is_still_visible(client, monkeypatch):
    """The split must not become a way to hide the monitor being dead."""
    flask_client, main_mod = client

    _publish(monkeypatch, main_mod,
             dict(_DEFAULTS, sales_scan_ok_at=_ago(30), sales_scan_block=53_969_441))

    chain = flask_client.get("/health").get_json()["blockchain"]

    assert chain["monitor_ready"] is False, (
        "the dedicated monitor never initialised and the board must still say so")
    assert chain["chain_id"] is None
    assert chain["monitor"]["last_block_checked"] == 0


def test_the_proof_of_life_is_published_for_a_human_to_read(client, monkeypatch):
    """An operator must be able to see WHY the chain counts as readable."""
    flask_client, main_mod = client
    stamp = _ago(45)

    _publish(monkeypatch, main_mod,
             dict(_DEFAULTS, sales_scan_ok_at=stamp, sales_scan_block=53_969_441))

    chain = flask_client.get("/health").get_json()["blockchain"]

    assert chain["sales_scan_ok_at"] == stamp
    assert chain["sales_scan_block"] == 53_969_441


def test_a_healthy_monitor_alone_is_still_enough(client, monkeypatch):
    """The pre-06.11 path must not regress: no scan stamp, monitor fine → ready."""
    flask_client, main_mod = client
    import config

    _publish(monkeypatch, main_mod,
             dict(_DEFAULTS, rpc_connected=True, chain_id=config.BASE_CHAIN_ID,
                  receiver_valid=True,
                  fee_receiver=main_mod.X402_RECEIVER_ADDRESS))

    body = flask_client.get("/health").get_json()

    assert body["blockchain"]["ready"] is True
    assert body["blockchain"]["monitor_ready"] is True
    assert body["status"] == "ok"


def test_neither_scanner_working_is_still_degraded(client, monkeypatch):
    """The honest case: nothing is reading the chain, so say so."""
    flask_client, main_mod = client

    _publish(monkeypatch, main_mod, dict(_DEFAULTS))

    body = flask_client.get("/health").get_json()

    assert body["blockchain"]["ready"] is False
    assert body["blockchain"]["monitor_ready"] is False
    assert body["status"] == "degraded"


# ── an absence is not evidence ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "stamp, why",
    [
        (None, "no stamp at all"),
        ("", "empty stamp"),
        ("not-a-timestamp", "unparseable stamp"),
        (_ago(601), "stale beyond the freshness window"),
        (_ago(-300), "a stamp in the future"),
    ],
    ids=["missing", "empty", "unparseable", "stale", "future"],
)
def test_only_a_fresh_readable_stamp_counts_as_proof(client, monkeypatch, stamp,
                                                     why):
    """Every unreadable or aged stamp must fall back to the monitor's own state.

    A clock we cannot read is an absence, and an absence must never be promoted
    into a healthy chain — the rule this whole audit applies everywhere else.
    """
    flask_client, main_mod = client

    _publish(monkeypatch, main_mod, dict(_DEFAULTS, sales_scan_ok_at=stamp))

    body = flask_client.get("/health").get_json()

    assert body["blockchain"]["ready"] is False, (
        "%s was accepted as proof that the chain is reachable" % why)
    assert body["status"] == "degraded"


def test_ready_follows_the_same_verdict_as_health(client, monkeypatch):
    """/health and /ready must not disagree — they read one helper on purpose."""
    flask_client, main_mod = client

    _publish(monkeypatch, main_mod,
             dict(_DEFAULTS, sales_scan_ok_at=_ago(30)))
    assert flask_client.get("/ready").status_code == 200
    assert flask_client.get("/ready").get_json()["blockchain"]["monitor_ready"] is False

    _publish(monkeypatch, main_mod, dict(_DEFAULTS))
    assert flask_client.get("/ready").status_code == 503


def test_the_freshness_window_tolerates_missed_cycles(client, monkeypatch):
    """The scan runs every 60s; one slow cycle must not flicker the board."""
    flask_client, main_mod = client
    from app.blueprints import discovery

    assert discovery.SALES_SCAN_FRESH_SECONDS >= 300, (
        "a window under five missed 60s cycles would flicker on a slow RPC call")

    _publish(monkeypatch, main_mod,
             dict(_DEFAULTS, sales_scan_ok_at=_ago(discovery.SALES_SCAN_FRESH_SECONDS - 1)))
    assert flask_client.get("/health").get_json()["blockchain"]["ready"] is True


# ── the monitor must not be single-homed on one public RPC ───────────────────


def test_rpc_candidates_put_the_operator_s_choice_first(monkeypatch):
    """The primary stays first, so an installation that set only it is unchanged."""
    import config

    monkeypatch.delenv("BASE_RPC_FALLBACKS", raising=False)
    monkeypatch.setattr(config, "BASE_RPC_URL", "https://primary.example")

    candidates = config.base_rpc_candidates()

    assert candidates[0] == "https://primary.example"
    assert len(candidates) > 1, (
        "one endpoint is the single point of failure this whole fix is about")


def test_rpc_candidates_are_deduplicated(monkeypatch):
    """Listing the primary again must not make the monitor dial it twice."""
    import config

    monkeypatch.setattr(config, "BASE_RPC_URL", "https://primary.example")
    monkeypatch.setenv(
        "BASE_RPC_FALLBACKS",
        "https://primary.example, https://b.example, https://b.example")

    assert config.base_rpc_candidates() == (
        "https://primary.example", "https://b.example")


def test_rpc_candidates_are_configurable(monkeypatch):
    import config

    monkeypatch.setattr(config, "BASE_RPC_URL", "https://primary.example")
    monkeypatch.setenv("BASE_RPC_FALLBACKS", "https://only.example")

    assert config.base_rpc_candidates() == (
        "https://primary.example", "https://only.example")


def test_init_wallet_tries_the_next_endpoint_when_one_refuses(client, monkeypatch):
    """The 06.11 failure: one refused endpoint took the whole monitor with it."""
    _flask, main_mod = client
    import config

    monkeypatch.delenv("WALLET_PRIVATE_KEY", raising=False)
    monkeypatch.setattr(config, "BASE_RPC_URL", "https://first.example")
    monkeypatch.setenv("BASE_RPC_FALLBACKS", "https://second.example")

    tried = []

    def _fake_connect(rpc_url, fee_receiver, usdc_address):
        tried.append(rpc_url)
        if rpc_url == "https://first.example":
            raise ConnectionError("rpc_unreachable")
        return object(), config.BASE_CHAIN_ID

    monkeypatch.setattr(main_mod, "_connect_monitor_only", _fake_connect)

    with main_mod._lock:
        main_mod._wallet_state.update(dict(_DEFAULTS))

    wallet = main_mod._init_wallet()

    assert tried == ["https://first.example", "https://second.example"], (
        "the monitor stopped at the first refusal, which is exactly the 06.11 bug")
    assert wallet is not None, "a working fallback endpoint was not used"
    assert main_mod._wallet_state["rpc_connected"] is True


def test_init_wallet_records_a_redacted_reason_when_nothing_answers(client,
                                                                    monkeypatch):
    """`ready: false` with no cause attached is an alarm nobody can act on.

    The reason must go through `redact_rpc`: a paid endpoint carries its api key
    in the path, and the old code logged the raw url on this very path.
    """
    _flask, main_mod = client
    import config

    monkeypatch.delenv("WALLET_PRIVATE_KEY", raising=False)
    # The secret-bearing endpoint is deliberately LAST: `rpc_error` keeps the
    # reason from the FINAL attempt, so this checks redaction on the value that is
    # actually stored and published, not on one that gets overwritten.
    monkeypatch.setattr(config, "BASE_RPC_URL", "https://first.example")
    monkeypatch.setenv("BASE_RPC_FALLBACKS",
                       "https://base.example.com/v2/SUPERSECRETKEY123")

    def _always_refuse(rpc_url, fee_receiver, usdc_address):
        raise ConnectionError("cannot connect to %s" % rpc_url)

    monkeypatch.setattr(main_mod, "_connect_monitor_only", _always_refuse)

    with main_mod._lock:
        main_mod._wallet_state.update(dict(_DEFAULTS))

    assert main_mod._init_wallet() is None

    reason = main_mod._wallet_state["rpc_error"]
    assert reason, "the monitor failed and recorded no reason"
    assert "SUPERSECRETKEY123" not in reason, (
        "the RPC api key was written into the state that /health publishes: %r" % reason)
    assert "***" in reason, (
        "the key was dropped but the redaction marker is missing: %r" % reason)


def test_the_reason_reaches_the_health_body(client, monkeypatch):
    """/health is where an operator looks, so the cause must be published there.

    Before 06.11 the "cannot connect" path returned None having written nothing, so
    the board could say `ready: false` and no surface anywhere said why.
    """
    flask_client, main_mod = client

    _publish(monkeypatch, main_mod,
             dict(_DEFAULTS,
                  rpc_error="rpc_unreachable: https://base.example.com/v2/***"))

    chain = flask_client.get("/health").get_json()["blockchain"]

    assert chain["monitor_ready"] is False
    assert chain["rpc_error"] == "rpc_unreachable: https://base.example.com/v2/***", (
        "the board reports the monitor as down without reporting the cause")


# ── the split deployment: the evidence lives in the SHARED store ─────────────
#
# scripts/worker.py's own diagram is the reason these exist: web is HTTP-only
# (KRISTO_DISABLE_BACKGROUND_THREADS=true), the worker is background-only, and
# POSTGRES is the shared state. Memory cannot cross that line, so an endpoint that
# reads only memory cannot see the loops at all — which is what /health was doing
# when it called a demonstrably-working chain dead for over fifteen hours.


def test_a_worker_monitor_heartbeat_proves_the_monitor_is_running(client,
                                                                monkeypatch):
    """07.11, exactly: the web process has no threads, the worker has the monitor."""
    flask_client, main_mod = client

    _publish(monkeypatch, main_mod, dict(_DEFAULTS))          # web: no threads at all
    _worker_publishes(main_mod, monitor_at=_ago(20), monitor_block=54_244_552)

    body = flask_client.get("/health").get_json()

    assert body["blockchain"]["ready"] is True
    assert body["blockchain"]["monitor_ready"] is True, (
        "the worker's monitor is running and the board must be able to say so")
    assert body["status"] == "ok"
    assert body["blockchain"]["monitor"]["last_block_checked"] == 54_244_552, (
        "the worker's position is invisible from here, which was the whole defect")


def test_a_worker_sales_scan_heartbeat_keeps_the_chain_honest(client, monkeypatch):
    """The scan is a separate loop, so its heartbeat is separate evidence."""
    flask_client, main_mod = client

    _publish(monkeypatch, main_mod, dict(_DEFAULTS))
    _worker_publishes(main_mod, scan_at=_ago(30))

    chain = flask_client.get("/health").get_json()["blockchain"]

    assert chain["ready"] is True
    assert chain["monitor_ready"] is False, (
        "the monitor is NOT running, and the split must not hide that")
    assert chain["sales_scan_ok_at"]


def test_a_stale_shared_heartbeat_is_not_proof(client, monkeypatch):
    """The worker dying must eventually show, not be cached forever as healthy."""
    flask_client, main_mod = client
    from app.blueprints import discovery

    old = _ago(discovery.SALES_SCAN_FRESH_SECONDS + 60)
    _publish(monkeypatch, main_mod, dict(_DEFAULTS))
    _worker_publishes(main_mod, monitor_at=old, scan_at=old)

    body = flask_client.get("/health").get_json()

    assert body["blockchain"]["ready"] is False, (
        "a heartbeat older than the window was still counted as a live chain")
    assert body["status"] == "degraded"


def test_health_survives_a_shared_store_that_cannot_answer(client, monkeypatch):
    """/health is what the platform health-checks, so it must not raise."""
    flask_client, main_mod = client

    class _DeadStore:
        def get_meta(self, *args, **kwargs):
            raise RuntimeError("database is unreachable")

    _publish(monkeypatch, main_mod, dict(_DEFAULTS))
    sys.modules["__main__"].dashboard_db = _DeadStore()

    response = flask_client.get("/health")

    assert response.status_code == 200
    assert response.get_json()["blockchain"]["ready"] is False


def test_publish_heartbeat_writes_both_places(client):
    """Memory for the single-process case, the shared store for the split one."""
    _flask, main_mod = client
    with main_mod._lock:
        main_mod._wallet_state.update(dict(_DEFAULTS))

    stamp = main_mod._publish_heartbeat(
        "last_check_time", main_mod.MONITOR_HEARTBEAT_KEY,
        block=1234, state_block_key="last_block_checked",
        meta_block_key=main_mod.MONITOR_HEARTBEAT_BLOCK_KEY)

    with main_mod._lock:
        assert main_mod._wallet_state["last_check_time"] == stamp
        assert main_mod._wallet_state["last_block_checked"] == 1234
    assert main_mod.dashboard_db.get_meta(main_mod.MONITOR_HEARTBEAT_KEY) == stamp
    assert main_mod.dashboard_db.get_meta(
        main_mod.MONITOR_HEARTBEAT_BLOCK_KEY) == "1234"


def test_publish_heartbeat_survives_an_unwritable_store(client, monkeypatch):
    """A store that cannot be written must not kill the loop that proved the chain."""
    _flask, main_mod = client

    class _DeadStore:
        def set_meta(self, *args, **kwargs):
            raise RuntimeError("database is unreachable")

    monkeypatch.setattr(main_mod, "dashboard_db", _DeadStore())
    with main_mod._lock:
        main_mod._wallet_state.update(dict(_DEFAULTS))

    stamp = main_mod._publish_heartbeat("last_check_time",
                                        main_mod.MONITOR_HEARTBEAT_KEY)

    assert stamp, "the in-process stamp must still be published"
    with main_mod._lock:
        assert main_mod._wallet_state["last_check_time"] == stamp

