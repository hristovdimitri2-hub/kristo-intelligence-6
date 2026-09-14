# ── AUDIT FINDING (Табло 2.0): the FAST path ignores WHO paid ───────────────

"""Payment guards C1 / C2 / H2 + the Day-of-Truth verified-sales seed.

C1 — durable replay lock (SQLite `payment_guards`, survives restarts).
C2 — confirmation depth (12 blocks by default) before a proof is trusted.
H2 — endpoint binding: a proof scoped to one endpoint cannot buy another.

Plus two regressions that matter more than any of them:
  * PRIORITY-0: `SALES_CHUNK_BLOCKS=10` must NOT be clamped up to 50 by a
    hidden floor, and a chunk the RPC refuses must be retried with a halved
    span rather than stalling the watermark.
  * the seeded manifest must reproduce the chain truth exactly
    ($0.028 over 8 transfers) and stay idempotent.
"""

import base64
import json
import sys
import types

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
    return main.app.test_client(), main, dash


def _proof_header(tx_hash: str, payer: str = "0x" + "11" * 20,
                  amount_usdc: float = 0.003, endpoint: str | None = None) -> str:
    payload = {
        "payer": payer,
        "transaction_hash": tx_hash,
        "amount_usdc": amount_usdc,
    }
    if endpoint is not None:
        payload["endpoint"] = endpoint
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return raw.rstrip("=")


def _paid_ready(main, monkeypatch, tx_hash, amount=0.05, dash=None):
    """Exhaust the free tier and make the FAST path resolve the proof offline.

    `amount` defaults to 0.05 — comfortably above every per-route price
    (/api/stats is $0.005, the rest $0.003), so the test exercises the guard
    under test rather than the price comparison.
    """
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    monkeypatch.setattr(main, "_paid_calls_usage", {})
    monkeypatch.setattr(main, "_verified_payments", set())
    monkeypatch.setattr(main, "_sales_history", [{
        "tx_hash": tx_hash, "token": "USDC", "amount_usd": amount,
        "sender": "0x" + "11" * 20,
    }])


# ── fake web3 (scan) ─────────────────────────────────────────────────────────

def _install_fake_web3(monkeypatch, logs, blocks_ts, latest=10_000,
                       max_span=None):
    """Install a fake `web3` module. With `max_span` set, get_logs raises for
    any range WIDER than that — exactly how drpc/pokt free tiers refuse a wide
    recipient-filtered query."""
    fake = types.ModuleType("web3")

    class FakeEth:
        def __init__(self):
            self.block_number = latest
            self.spans = []

        def is_connected(self):
            return True

        def get_logs(self, spec):
            lo, hi = spec["fromBlock"], spec["toBlock"]
            self.spans.append(hi - lo + 1)
            if max_span is not None and (hi - lo + 1) > max_span:
                raise ValueError("query exceeds the RPC's range limit")
            return [lg for lg in logs if lo <= lg["blockNumber"] <= hi]

        def get_block(self, n):
            return {"timestamp": blocks_ts.get(n, 0)}

    class FakeWeb3:
        HTTPProvider = staticmethod(lambda url, request_kwargs=None: ("p", url))
        last_eth = None

        def __init__(self, provider):
            self.eth = FakeEth()
            FakeWeb3.last_eth = self.eth

        def is_connected(self):
            return True

        @staticmethod
        def to_checksum_address(a):
            return a

        @staticmethod
        def to_hex(h):
            return (("0x" + bytes(h).hex())
                    if isinstance(h, (bytes, bytearray)) else str(h))

    fake.Web3 = FakeWeb3
    monkeypatch.setitem(sys.modules, "web3", fake)
    return FakeWeb3


def _sale_log(tx_hex_last: str, amount_usdc: float, frm_hex20: str,
              block: int) -> dict:
    return {
        "topics": [b"\x01", bytes.fromhex(frm_hex20), bytes.fromhex("00" * 20)],
        "data": int(amount_usdc * 1_000_000).to_bytes(32, "big"),
        "blockNumber": block,
        "transactionHash": bytes.fromhex(tx_hex_last),
    }


# ── C1: durable replay lock ──────────────────────────────────────────────────

def test_c1_same_proof_cannot_buy_two_calls(client, monkeypatch):
    test_client, main, _ = client
    tx = "0x" + "ab" * 32
    _paid_ready(main, monkeypatch, tx)
    header = _proof_header(tx)

    first = test_client.get("/api/stats", headers={"X-Payment-Proof": header})
    assert first.status_code == 200, first.get_data(as_text=True)[:200]

    second = test_client.get("/api/stats", headers={"X-Payment-Proof": header})
    assert second.status_code == 401
    assert second.get_json()["error"] == "invalid_payment_proof"


def test_c1_replay_survives_a_restart(client, monkeypatch):
    """The old guard was a RAM set — a deploy resurrected consumed proofs.
    The SQLite claim must hold even after the process forgets everything."""
    test_client, main, dash = client
    tx = "0x" + "cd" * 32
    _paid_ready(main, monkeypatch, tx)
    header = _proof_header(tx)

    assert test_client.get(
        "/api/stats", headers={"X-Payment-Proof": header}).status_code == 200

    # "restart": RAM state is gone, the database is not.
    monkeypatch.setattr(main, "_verified_payments", set())
    monkeypatch.setattr(main, "_free_tier_usage", {})

    replay = test_client.get("/api/stats", headers={"X-Payment-Proof": header})
    assert replay.status_code == 401
    assert dash.payment_guard_stats()["consumed_total"] == 1


def test_c1_store_claim_is_atomic(tmp_path):
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "g.db")
    tx = "0x" + "ef" * 32
    assert store.claim_payment_tx(tx, endpoint="/api/stats", amount_usdc=0.003)
    assert not store.claim_payment_tx(tx, endpoint="/api/stats", amount_usdc=0.003)
    assert not store.claim_payment_tx(tx, endpoint="/api/sales")
    stats = store.payment_guard_stats()
    assert stats["consumed_total"] == 1
    assert stats["by_endpoint"] == {"/api/stats": 1}
    # Enriched telemetry (Табло 2.0): the dashboard shows WHEN the guard last
    # granted a call, so the shape is additive rather than exact-match.
    assert stats["last_claim_endpoint"] == "/api/stats"
    assert stats["last_claim_at"]


# ── H2: endpoint binding ─────────────────────────────────────────────────────

def test_h2_bound_proof_is_rejected_on_another_endpoint(client, monkeypatch):
    """$0.003 of /api/stats must not unlock /api/sales."""
    test_client, main, dash = client
    tx = "0x" + "1a" * 32
    _paid_ready(main, monkeypatch, tx)
    header = _proof_header(tx, endpoint="/api/stats")

    wrong = test_client.get("/api/sales", headers={"X-Payment-Proof": header})
    assert wrong.status_code == 401
    # Rejected BEFORE any RPC work and before consumption.
    assert dash.payment_guard_stats()["consumed_total"] == 0

    right = test_client.get("/api/stats", headers={"X-Payment-Proof": header})
    assert right.status_code == 200


def test_h2_legacy_unbound_proof_still_works(client, monkeypatch):
    """Clients that omit `endpoint` are not broken by the hardening."""
    test_client, main, _ = client
    tx = "0x" + "2b" * 32
    _paid_ready(main, monkeypatch, tx)

    resp = test_client.get("/api/sales",
                           headers={"X-Payment-Proof": _proof_header(tx)})
    assert resp.status_code == 200


def test_h2_matcher_is_trailing_slash_tolerant():
    import main
    assert main._proof_endpoint_matches("", "/api/stats") is True
    assert main._proof_endpoint_matches("/api/stats", "/api/stats") is True
    assert main._proof_endpoint_matches("/api/stats/", "/api/stats") is True
    assert main._proof_endpoint_matches("/api/stats", "/api/sales") is False


# ── C2: confirmation depth ───────────────────────────────────────────────────

class _Topic:
    """Mimics web3's HexBytes: .hex() returns WITH the 0x prefix."""

    def __init__(self, hexstr: str):
        self._h = hexstr

    def hex(self) -> str:
        return self._h


def _fake_verify_w3(receipt_block, latest, amount_usdc=0.003, status=1):
    import main

    usdc = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    recv = main.X402_RECEIVER_ADDRESS.lower().replace("0x", "")
    frm = ("11" * 20)
    log = {
        "address": usdc,
        "topics": [
            _Topic(main._TRANSFER_EVENT_TOPIC),
            _Topic("0x" + frm.rjust(64, "0")),
            _Topic("0x" + recv.rjust(64, "0")),
        ],
        "data": int(amount_usdc * 1_000_000).to_bytes(32, "big"),
    }

    class Eth:
        def __init__(self):
            self.block_number = latest

        def get_transaction_receipt(self, tx):
            return {"status": status, "blockNumber": receipt_block,
                    "logs": [log]}

    class W3:
        def __init__(self):
            self.eth = Eth()

    return W3()


def test_c2_depth_thresholds(monkeypatch):
    import main
    monkeypatch.setenv("MIN_PAYMENT_CONFIRMATIONS", "12")
    assert main._confirmations_ok(100, 111) is True    # exactly 12
    assert main._confirmations_ok(100, 110) is False   # 11
    assert main._confirmations_ok(100, 100) is False   # at the tip
    assert main._confirmations_ok(0, 100) is False     # unknown block
    assert main._confirmations_ok(101, 100) is False   # impossible
    monkeypatch.setenv("MIN_PAYMENT_CONFIRMATIONS", "1")
    assert main._confirmations_ok(100, 100) is True


def test_c2_rejects_a_receipt_at_the_chain_tip(client, monkeypatch):
    _, main, _ = client
    monkeypatch.setenv("MIN_PAYMENT_CONFIRMATIONS", "12")
    monkeypatch.setattr(main, "_get_verify_web3",
                        lambda: _fake_verify_w3(receipt_block=1000, latest=1000))
    assert main._verify_payment_onchain("0x" + "cd" * 32,
                                        "0x" + "11" * 20, 0.003) is None


def test_c2_accepts_a_deeply_buried_receipt(client, monkeypatch):
    _, main, _ = client
    monkeypatch.setenv("MIN_PAYMENT_CONFIRMATIONS", "12")
    monkeypatch.setattr(main, "_get_verify_web3",
                        lambda: _fake_verify_w3(receipt_block=1000, latest=1011))
    assert main._verify_payment_onchain("0x" + "cd" * 32,
                                        "0x" + "11" * 20, 0.003) == 0.003


# ── PRIORITY-0 regression: the chunk floor that caused the zero-sales bug ────

def test_sales_chunk_env_is_not_clamped_upwards(tmp_path, monkeypatch):
    """SALES_CHUNK_BLOCKS=10 used to be silently raised to 50 — the one width
    the free RPCs reject — which stalled the scan and zeroed the dashboard."""
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setenv("SALES_CHUNK_BLOCKS", "10")
    monkeypatch.setenv("BASE_FEE_RECEIVER",
                       "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f")
    logs = [_sale_log("77", 0.003, "aa" * 20, 55)]
    _install_fake_web3(monkeypatch, logs, {55: 1_700_000_000}, latest=100,
                       max_span=10)
    store = DashboardStore(tmp_path / "d.db")
    added = store.scan_window(1, 100, rpc_url="http://fake")
    assert added == 1, "a 10-block query is accepted — the sale must be found"
    assert store.get_meta("sales_effective_chunk") == "10"


def test_scan_halves_a_rejected_chunk_instead_of_stalling(tmp_path, monkeypatch):
    """Even with the default width, a refused chunk must be RETRIED narrower —
    never skipped, and never a stalled watermark."""
    from integrations.dashboard_store import DashboardStore

    monkeypatch.delenv("SALES_CHUNK_BLOCKS", raising=False)
    monkeypatch.setenv("BASE_FEE_RECEIVER",
                       "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f")
    logs = [_sale_log("88", 0.003, "bb" * 20, 55)]
    _install_fake_web3(monkeypatch, logs, {55: 1_700_000_000}, latest=100,
                       max_span=10)
    store = DashboardStore(tmp_path / "d.db")
    added = store.scan_window(1, 100, rpc_url="http://fake")
    assert added == 1
    # 5000 → 2500 → ... → 19 → 9 (accepted)
    assert int(store.get_meta("sales_effective_chunk")) == 9
    assert store.get_meta("sales_safe_scanned_block") == "100"


# ── Day-of-Truth: the seeded manifest IS the chain ───────────────────────────

def test_seed_manifest_reproduces_chain_truth(tmp_path):
    from integrations.dashboard_store import DashboardStore
    from integrations.verified_sales import VERIFIED_SALES, expected_totals

    exp = expected_totals()
    assert exp == {"total_usdc": 0.031, "total_count": 9,
                   "distinct_senders": 5}
    for row in VERIFIED_SALES:
        tx = row["tx_hash"]
        assert tx.startswith("0x") and len(tx) == 66, f"truncated hash: {tx}"
        assert tx == tx.lower()
        assert row["block_number"] > 0
        assert row["amount_usdc"] in (0.003, 0.005)

    store = DashboardStore(tmp_path / "seed.db")
    result = store.seed_verified_sales()
    assert result["inserted"] == 9
    summary = store.sales_summary()
    assert summary["total_usdc"] == 0.031
    assert summary["total_count"] == 9
    assert summary["external_payers"] == 3
    assert summary["by_class"]["canary"]["count"] == 5
    assert summary["by_class"]["sampler"]["count"] == 1
    # Idempotent: a second boot inserts nothing and changes nothing.
    assert store.seed_verified_sales()["inserted"] == 0
    assert store.sales_summary()["total_count"] == 9


def test_a_scan_row_is_never_overwritten_by_the_seed(tmp_path):
    """Precedence: a row already recorded from the chain scan wins."""
    from integrations.dashboard_store import DashboardStore

    tx = "0xb8a52dcd61962af4b2d15d6f166b6c5038bbe9c40c171b37508a199bd40a45e6"
    store = DashboardStore(tmp_path / "prec.db")
    assert store.record_sale(tx_hash=tx, amount_usdc=0.005,
                             sender="0x7e6b6556322c4e26c567a867964ac793f5ee2b1c",
                             block_number=50783187, source="scan")
    store.seed_verified_sales()
    rows = [h for h in store.sales_summary()["history"] if h["tx_hash"] == tx]
    assert len(rows) == 1
    assert rows[0]["source"] == "scan"


def test_admin_seed_route_repairs_a_wiped_store(client, monkeypatch):
    """A fresh (deploy-wiped) filesystem can be repaired without a redeploy."""
    test_client, main, dash = client
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")

    assert test_client.post("/api/admin/seed-sales").status_code == 401

    resp = test_client.post("/api/admin/seed-sales",
                            headers={"X-Admin-Token": "test-admin-token"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["onchain"]["total_usdc"] == 0.031
    assert body["onchain"]["total_count"] == 9
    assert body["onchain"]["external_payers"] == 3


def test_a_published_tx_hash_cannot_be_claimed_by_another_payer(
        client, monkeypatch):
    """The dashboard publishes all 8 full tx hashes (Табло 2.0 requires it).

    The slow path verifies `from_addr == payer` on-chain. The FAST path (the
    tx is already in _sales_history) looked the hash up WITHOUT checking who
    sent it — so anyone reading our own public dashboard could present a real,
    published hash with their own address in `payer` and get a paid call for
    free. The proof must be bound to the recorded sender.
    """
    test_client, main, dash = client
    # A real, publicly visible payment: canary $0.005 to the bound receiver.
    real_tx = ("0xb8a52dcd61962af4b2d15d6f166b6c5038bbe9d40c171b37508a199bd40a45e6"
               .replace("9d40c", "9c40c"))
    real_sender = "0x7e6b6556322c4e26c567a867964ac793f5ee2b1c"
    attacker = "0x" + "ba" * 20

    _paid_ready(main, monkeypatch, real_tx, amount=0.005)
    monkeypatch.setattr(main, "_sales_history", [{
        "tx_hash": real_tx, "token": "USDC", "amount_usd": 0.005,
        "sender": real_sender,
    }])

    # Attacker copies the published hash but claims it as their own payment.
    forged = test_client.get("/api/v1/signal", headers={
        "X-Payment-Proof": _proof_header(real_tx, payer=attacker)})
    assert forged.status_code != 200, \
        "a published tx hash was accepted from a DIFFERENT payer"

    # The genuine payer still gets through (the fix must not break the rail).
    genuine = test_client.get("/api/v1/signal", headers={
        "X-Payment-Proof": _proof_header(real_tx, payer=real_sender)})
    assert genuine.status_code == 200
    assert dash.payment_guard_stats()["consumed_total"] == 1


# ── C2 conversion fix: re-read the clock before refusing (14.09) ────────────

def test_c2_refreshes_the_head_and_accepts_a_one_block_lag(client, monkeypatch):
    """The FOURTH payer's case, exactly.

    Settlement block 51313253 vs head 51313252: a facilitator had already mined
    the tx while our own view lagged ONE block. That is a stale clock, not an
    unconfirmed payment — refusing it lost us a paying agent (it never retried).
    A single re-read must now settle it.
    """
    _test_client, main, dash = client
    monkeypatch.setenv("KRISTO_C2_LAG_WAIT_SECONDS", "0")
    heads = iter([51313252, 51313253])            # stale, then refreshed

    accepted = main._confirmations_ok_with_lag_refresh(
        receipt_block=51313253, read_head=lambda: next(heads), required=1,
        endpoint="/api/v1/signal",
        tx_hash=("0x06b4c8f2bb1a9f0356c277f7c4845863430951fdea2724e47a0354"
                 "225d658ce7"),
        rail="standard")

    assert accepted is True, "a one-block lag must not refuse a valid payment"
    kinds = dash.guard_stats(recent_limit=5)["by_kind"]
    assert kinds.get("head_refreshed_and_accepted") == 1
    assert "c2_insufficient_confirmations" not in kinds
    event = dash.guard_stats(recent_limit=1)["recent_blocks"][0]
    assert event["endpoint"] == "/api/v1/signal"
    assert "51313253" in event["detail"] and "51313252" in event["detail"]


def test_c2_waits_once_then_accepts_when_the_head_catches_up(client,
                                                             monkeypatch):
    """If one re-read is not enough (the block landed mid-request), the read
    after a short wait decides — and the event says it needed the wait."""
    _test_client, main, dash = client
    monkeypatch.setenv("KRISTO_C2_LAG_WAIT_SECONDS", "0")
    heads = iter([1000, 1000, 1001])              # stale, stale, then caught up
    reads = []

    def read_head():
        value = next(heads)
        reads.append(value)
        return value

    assert main._confirmations_ok_with_lag_refresh(
        receipt_block=1001, read_head=read_head, required=1,
        endpoint="/api/v1/signal", tx_hash="0x" + "cc" * 32,
        rail="standard") is True
    assert len(reads) == 3, "one re-read plus one retry after the wait"
    assert dash.guard_stats(recent_limit=5)["by_kind"].get(
        "waited_and_accepted") == 1


def test_c2_still_fails_closed_when_the_node_is_really_lagging(client,
                                                               monkeypatch):
    """50 blocks behind is NOT a clock skew — the node is genuinely behind and
    fail-closed wins after the re-read and the retry (philosophy preserved)."""
    _test_client, main, dash = client
    monkeypatch.setenv("KRISTO_C2_LAG_WAIT_SECONDS", "0")
    reads = []

    def read_head():
        reads.append(1)
        return 950                                # never catches up to 1000

    assert main._confirmations_ok_with_lag_refresh(
        receipt_block=1000, read_head=read_head, required=1,
        endpoint="/api/v1/signal", tx_hash="0x" + "dd" * 32,
        rail="standard") is False, "a genuinely lagging node must still refuse"
    assert len(reads) == 3, "it must try (re-read + retry) before refusing"
    kinds = dash.guard_stats(recent_limit=5)["by_kind"]
    assert kinds.get("node_lagging_rejected") == 1
    assert kinds.get("head_refreshed_and_accepted") is None


def test_c2_depth_shortfall_behaviour_is_unchanged(client, monkeypatch):
    """The original case must be untouched: a block that IS known but not buried
    deep enough keeps the old event and the old refusal — and never triggers a
    refresh, because that is not a clock problem."""
    _test_client, main, dash = client
    monkeypatch.setenv("KRISTO_C2_LAG_WAIT_SECONDS", "0")
    reads = []

    def read_head():
        reads.append(1)
        return 1000                               # and block 999 sits at the tip

    assert main._confirmations_ok_with_lag_refresh(
        receipt_block=999, read_head=read_head, required=12,
        endpoint="/api/v1/signal", tx_hash="0x" + "ee" * 32,
        rail="proof") is False
    assert len(reads) == 1, "no refresh/wait for a depth shortfall"
    kinds = dash.guard_stats(recent_limit=5)["by_kind"]
    assert kinds.get("c2_insufficient_confirmations") == 1
    assert "node_lagging_rejected" not in kinds

    # And a deep, healthy block is still accepted with a single read, silently
    # (980 → 21 confirmations ≥ 12). Nothing new must be recorded: compare the
    # event counts before/after, since the depth event above is still there.
    before = dict(kinds)
    assert main._confirmations_ok_with_lag_refresh(
        receipt_block=980, read_head=lambda: 1000, required=12,
        endpoint="/api/v1/signal", tx_hash="0x" + "ff" * 32,
        rail="proof") is True
    assert dash.guard_stats(recent_limit=5)["by_kind"] == before, \
        "a healthy payment must not add a guard event"


def test_c2_lag_wait_is_configurable_and_defaults_to_one_base_block(
        client, monkeypatch):
    """2.5s by default (one Base block is 2s) and tunable — tests run with 0."""
    _test_client, main, _dash = client
    monkeypatch.delenv("KRISTO_C2_LAG_WAIT_SECONDS", raising=False)
    assert main._c2_lag_wait_seconds() == main.C2_LAG_WAIT_SECONDS_DEFAULT
    assert main.C2_LAG_WAIT_SECONDS_DEFAULT >= 2.0
    monkeypatch.setenv("KRISTO_C2_LAG_WAIT_SECONDS", "0.25")
    assert main._c2_lag_wait_seconds() == 0.25
    monkeypatch.setenv("KRISTO_C2_LAG_WAIT_SECONDS", "not-a-number")
    assert main._c2_lag_wait_seconds() == main.C2_LAG_WAIT_SECONDS_DEFAULT
