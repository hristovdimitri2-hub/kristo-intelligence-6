"""Audit #4 recovery tests — the OTHER half of the guards.

The 393 tests before this file proved the REFUSALS (C1 replay → 401, H2
mismatch → 401, depth shortfall → 401). Not one of them proved a PAYING
client could ever get the product back after a failure. This file does:

  F1/F6  settle → C2 refusal → retry → the client gets the DATA
         (idempotent settle keyed on the EIP-3009 NONCE, never payer+amount),
  nonce  two signals at the SAME price never adopt each other's transaction,
  F2     a facilitator-broadcast tx is found by the same channel-agnostic
         search — settle is never called a second time,
  F3     handler exception after consumption → JSON 500 (never HTML), the C1
         row survives, retry with the SAME proof recovers, and a third attempt
         AFTER delivery is still refused (no new double-spend hole),
  F5     the proof-rail hint quotes the real 12-block wait (~24s, not ~2s).

Crypto and network boundaries are stubbed (verify / settle / RPC); everything
the audits are actually about — the recovery logic — runs for real.
"""

import base64
import json
import re
import sys
import types

import pytest

PAYER = "0x" + "11" * 20
TX_SELF = "0x" + "aa" * 32          # a settlement broadcast by OUR wallet
TX_CDP = "0x" + "cc" * 32           # a settlement broadcast by a facilitator
NONCE_A = "0x" + "11" * 32
NONCE_B = "0x" + "22" * 32          # second signal, same fixed price
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TRANSFER_TOPIC = ("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef")
AUTH_USED_TOPIC = ("0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5")


def _standard_header(main, payer=PAYER, nonce=NONCE_A, standard=False) -> str:
    """A decodable PAYMENT-SIGNATURE payload (verify/settle are stubbed).

    standard=False → our legacy base64url (unpadded); standard=True → the
    x402 v2 SDK's safeBase64Encode form (STANDARD base64, padding kept).
    """
    payload = {
        "payload": {
            "authorization": {
                "from": payer,
                "to": main.X402_RECEIVER_ADDRESS,
                "value": 5000,              # /api/stats costs 0.005 USDC
                "validAfter": 0,
                "validBefore": 0,
                "nonce": nonce,
            },
        },
        "signature": "0x" + "ab" * 65,
    }
    data = json.dumps(payload).encode()
    if standard:
        return base64.b64encode(data).decode()
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _proof_header(tx, payer=PAYER, amount=0.05) -> str:
    payload = {"payer": payer, "transaction_hash": tx, "amount_usdc": amount}
    return base64.urlsafe_b64encode(
        json.dumps(payload).encode()).decode().rstrip("=")


def _topic_addr(addr: str) -> str:
    return "0x" + "00" * 12 + addr[2:]


def _auth_log(tx: str, block: int, payer: str, nonce: str) -> dict:
    """AuthorizationUsed(payer, nonce) — emitted by WHICHEVER settler ran."""
    return {
        "transactionHash": tx,
        "blockNumber": block,
        "topics": [AUTH_USED_TOPIC, _topic_addr(payer),
                   "0x" + nonce[2:].rjust(64, "0")],
    }


def _receipt(tx: str, block: int, payer: str, value_atomic: int,
             receiver: str) -> dict:
    """A successful receipt carrying the exact Transfer the nonce bought."""
    return {
        "status": 1,
        "blockNumber": block,
        "blockHash": "0x" + "cd" * 32,
        "logs": [{
            "address": USDC,
            "topics": [TRANSFER_TOPIC, _topic_addr(payer), _topic_addr(receiver)],
            "data": hex(value_atomic),
        }],
    }


class _FakeEth:
    """Enough web3 for the nonce search + the standard rail's receipt/C2."""

    def __init__(self, block_number, receipts=None, auth_logs=None):
        self.block_number = block_number
        self.receipts = receipts or {}
        self.auth_logs = auth_logs or []
        self.get_logs_calls = []

    def get_logs(self, spec):
        self.get_logs_calls.append(spec)
        topics = spec.get("topics") or []
        out = []
        for lg in self.auth_logs:
            lt = lg.get("topics") or []
            if topics and lt:
                if topics[0].lower() != lt[0].lower():
                    continue
                if len(topics) > 1 and len(lt) > 1 and \
                        topics[1].lower() != lt[1].lower():
                    continue
                if len(topics) > 2 and len(lt) > 2 and \
                        topics[2].lower() != lt[2].lower():
                    continue
            if not (spec.get("fromBlock", 0) <= lg.get("blockNumber", 0)
                    <= spec.get("toBlock", 10 ** 9)):
                continue
            out.append(lg)
        return out

    def get_transaction_receipt(self, tx):
        if tx not in self.receipts:
            raise ValueError(f"receipt not found: {tx}")
        return self.receipts[tx]


def _install_fake_web3(monkeypatch, eth):
    """Route BOTH web3 constructions through one fake chain view.

    The nonce search uses `_get_verify_web3()` and the standard rail builds its
    own `Web3(HTTPProvider(...))` for the settlement receipt — installing a
    fake `web3` module covers both seams with the same `eth`, exactly like the
    C1/C2 guard tests do.
    """
    fake = types.ModuleType("web3")

    class _W3:
        HTTPProvider = staticmethod(
            lambda url, request_kwargs=None: ("fake", url))

        def __init__(self, provider=None, *args, **kwargs):
            self.eth = eth

        @staticmethod
        def to_checksum_address(addr):
            return addr

    fake.Web3 = _W3
    monkeypatch.setitem(sys.modules, "web3", fake)
    return fake


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """Isolated app + durable store + offline payment/network seams."""
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("KRISTO_C2_LAG_WAIT_SECONDS", "0")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    from integrations.catalog_store import create_catalog_store
    from integrations.dashboard_store import DashboardStore
    from services import connectors

    monkeypatch.setattr(main, "catalog_store",
                        create_catalog_store(tmp_path / "catalog.db"))
    dash = DashboardStore(tmp_path / "dashboard_state.db")
    monkeypatch.setattr(main, "dashboard_db", dash)

    # Payment seam: no free tier, per-test counters, no background work.
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    monkeypatch.setattr(main, "_paid_calls_usage", {})
    monkeypatch.setattr(main, "_verified_payments", set())
    monkeypatch.setattr(main, "_sales_history", [])
    monkeypatch.setattr(main, "_request_log", [])
    monkeypatch.setattr(main, "_daily_stats", {})
    monkeypatch.setattr(main, "_detect_reorgs", lambda *a, **k: 0)
    # The lazily-built Web3 is module-global: reset it so each test installs
    # ITS OWN fake chain view instead of inheriting the previous one's.
    monkeypatch.setattr(main, "_payment_verify_w3", None)
    # The route under test must never depend on CoinGecko answering.
    monkeypatch.setattr(main, "get_market_snapshot",
                        lambda *a, **k: {"source": "test_offline"})
    # Exceptions must reach the JSON handler, not the test runner.
    monkeypatch.setitem(main.app.config, "PROPAGATE_EXCEPTIONS", False)

    class _Env:
        pass
    e = _Env()
    e.main, e.dash, e.connectors = main, dash, connectors
    e.client = main.app.test_client()
    return e


# ── F1 / F6: settle → C2 refusal → retry → the client gets the DATA ───────

def test_settle_c2_refusal_then_retry_delivers(env, monkeypatch):
    """The audit's headline scenario: money moved, node behind, retry works."""
    main, dash, client = env.main, env.dash, env.client

    settle_calls = []

    def fake_settle(header, requirements):
        settle_calls.append(header)
        return TX_SELF, "settled_self_broadcast"

    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (True, PAYER, "verified_locally"))
    monkeypatch.setattr(env.connectors, "settle_standard_payment", fake_settle)

    receipt = _receipt(TX_SELF, 100, PAYER, 5000, main.X402_RECEIVER_ADDRESS)
    eth = _FakeEth(block_number=99, receipts={TX_SELF: receipt}, auth_logs=[])
    _install_fake_web3(monkeypatch, eth)
    header = _standard_header(main)

    # attempt 1: settle landed, our node is still behind → 425, nothing claimed
    r1 = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": header})
    body1 = r1.get_json()
    assert r1.status_code == 425, body1
    assert body1["error"] == "settlement_in_flight"
    assert body1["transaction"] == TX_SELF
    assert "PAYMENT-SIGNATURE" not in body1["message"], \
        "never tell a payer whose money already moved to retry the signature"
    assert "PAYMENT-RESPONSE" not in r1.headers
    assert dash.payment_guard_stats()["consumed_total"] == 0
    assert len(settle_calls) == 1

    # the settlement is mined (AuthorizationUsed emitted) and our node caught up
    eth.block_number = 105
    eth.auth_logs = [_auth_log(TX_SELF, 100, PAYER, NONCE_A)]

    # attempt 2: ADOPT the same tx by nonce — settle must NOT run again
    r2 = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": header})
    assert r2.status_code == 200, r2.get_json()
    assert len(settle_calls) == 1, "idempotent settle: adopted, never re-settled"
    assert dash.payment_guard_stats()["consumed_total"] == 1
    receipt = json.loads(base64.b64decode(r2.headers["PAYMENT-RESPONSE"]))
    assert receipt["transaction"] == TX_SELF
    assert r2.headers.get("X-Request-Id")
    row = dash.payment_guard_row(TX_SELF)
    assert row and row["delivered_at"], "a produced response stamps the claim"

    # attempt 3: delivered → the SAME signature is a true replay now
    r3 = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": header})
    assert r3.status_code == 401
    assert "replay" in (r3.get_json().get("reason") or "")
    assert dash.payment_guard_stats()["consumed_total"] == 1


def test_same_price_signals_never_adopt_the_wrong_tx(env, monkeypatch):
    """Nonce, NOT payer+amount: fixed prices would collide two signals."""
    main = env.main
    receipt = _receipt(TX_SELF, 100, PAYER, 5000, main.X402_RECEIVER_ADDRESS)
    eth = _FakeEth(block_number=200, receipts={TX_SELF: receipt},
                   auth_logs=[_auth_log(TX_SELF, 100, PAYER, NONCE_A)])
    _install_fake_web3(monkeypatch, eth)

    # same payer, same price, DIFFERENT nonce → never adopt TX_SELF
    assert main._find_settlement_by_nonce(PAYER, NONCE_B, 0.005) is None
    # the right nonce at the right price → adopts the right tx
    found = main._find_settlement_by_nonce(PAYER, NONCE_A, 0.005)
    assert found and found["tx_hash"] == TX_SELF
    # the right nonce but a DIFFERENT price → still refuses (amount check)
    assert main._find_settlement_by_nonce(PAYER, NONCE_A, 0.003) is None
    # …and the query itself is keyed on (payer, nonce), verbatim
    spec = eth.get_logs_calls[-1]
    assert spec["topics"][0] == AUTH_USED_TOPIC
    assert spec["topics"][1] == _topic_addr(PAYER)
    assert spec["topics"][2] == "0x" + NONCE_A[2:].rjust(64, "0")


def test_facilitator_settled_tx_is_found_and_settle_never_runs(env, monkeypatch):
    """Channel-agnostic: whoever broadcast it, the nonce search finds it."""
    main, dash, client = env.main, env.dash, env.client

    receipt = _receipt(TX_CDP, 300, PAYER, 5000, main.X402_RECEIVER_ADDRESS)
    eth = _FakeEth(block_number=305, receipts={TX_CDP: receipt},
                   auth_logs=[_auth_log(TX_CDP, 300, PAYER, NONCE_A)])
    _install_fake_web3(monkeypatch, eth)
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (True, PAYER, "verified_locally"))

    def no_settle(*a, **k):
        raise AssertionError("settle must not run — the tx already exists")
    monkeypatch.setattr(env.connectors, "settle_standard_payment", no_settle)

    header = _standard_header(main, nonce=NONCE_A)
    r = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": header})
    assert r.status_code == 200, r.get_json()
    assert dash.payment_guard_stats()["consumed_total"] == 1
    row = dash.payment_guard_row(TX_CDP)
    assert row and row["delivered_at"]
    receipt = json.loads(base64.b64decode(r.headers["PAYMENT-RESPONSE"]))
    assert receipt["transaction"] == TX_CDP


# ── F3: a consumed payment survives a handler failure and RECOVERS ────────

def test_handler_error_is_json_and_the_same_proof_recovers(env, monkeypatch):
    """JSON 500 (never HTML), C1 row kept, retry delivers, 4th attempt refused."""
    main, dash, client = env.main, env.dash, env.client
    real_safe_jsonify = main._safe_jsonify

    def boom(*a, **k):
        raise RuntimeError("simulated handler failure after a paid grant")
    monkeypatch.setattr(main, "_safe_jsonify", boom)

    # proof rail, fast path: this tx is already on our books under OUR payer
    monkeypatch.setattr(main, "_sales_history", [{
        "tx_hash": TX_SELF, "token": "USDC", "amount_usd": 0.05,
        "sender": PAYER,
    }])
    header = _proof_header(TX_SELF, amount=0.05)

    r1 = client.get("/api/stats", headers={"X-Payment-Proof": header})
    assert r1.status_code == 500
    assert r1.is_json, f"HTML error page after a payment: {r1.data[:200]!r}"
    body = r1.get_json()
    assert body["error"] == "internal_error" and body["request_id"]
    assert r1.headers.get("X-Request-Id")
    # the money is not lost with the response: claim stays, nothing delivered
    assert dash.payment_guard_stats()["consumed_total"] == 1
    row = dash.payment_guard_row(TX_SELF)
    assert row and row["delivered_at"] is None

    # heal the fault and retry THE SAME proof → the product arrives
    monkeypatch.setattr(main, "_safe_jsonify", real_safe_jsonify)
    r2 = client.get("/api/stats", headers={"X-Payment-Proof": header})
    assert r2.status_code == 200, r2.get_json()
    assert dash.payment_guard_stats()["consumed_total"] == 1, \
        "a recovery re-uses the claim, it never creates a second one"
    row = dash.payment_guard_row(TX_SELF)
    assert row and row["delivered_at"], "delivery stamps the claim"

    # …and a THIRD attempt is refused: this time the product DID go out
    r3 = client.get("/api/stats", headers={"X-Payment-Proof": header})
    assert r3.status_code == 401
    assert r3.get_json()["error"] == "invalid_payment_proof"
    assert dash.payment_guard_stats()["consumed_total"] == 1


def test_whaleflow_store_failure_is_json_503_and_recovers(env, monkeypatch):
    """The one paid route with a raw DB read: JSON, not HTML — and recoverable."""
    main, dash, client = env.main, env.dash, env.client
    real_summary = dash.whaleflow_summary

    def db_blip(**k):
        raise RuntimeError("simulated store outage")
    monkeypatch.setattr(dash, "whaleflow_summary", db_blip)

    monkeypatch.setattr(main, "_sales_history", [{
        "tx_hash": TX_SELF, "token": "USDC", "amount_usd": 0.05,
        "sender": PAYER,
    }])
    header = _proof_header(TX_SELF, amount=0.05)

    r1 = client.get("/api/v1/whaleflow", headers={"X-Payment-Proof": header})
    assert r1.status_code == 503
    assert r1.is_json, f"HTML error page after a payment: {r1.data[:200]!r}"
    body = r1.get_json()
    assert body["error"] == "whaleflow_store_unavailable"
    assert "NOT lost" in body["message"]
    assert dash.payment_guard_stats()["consumed_total"] == 1
    assert dash.payment_guard_row(TX_SELF)["delivered_at"] is None

    monkeypatch.setattr(dash, "whaleflow_summary", real_summary)
    r2 = client.get("/api/v1/whaleflow", headers={"X-Payment-Proof": header})
    assert r2.status_code == 200, r2.get_json()
    assert r2.get_json()["ok"] is True
    assert dash.payment_guard_row(TX_SELF)["delivered_at"]


# ── F5: the hint must quote the REAL wait on this rail ────────────────────

def test_proof_hint_quotes_the_real_12_block_wait(env, monkeypatch):
    """~2s lied: this rail requires 12 confirmations (~24s) before retrying."""
    main = env.main
    monkeypatch.setattr(main, "_verify_payment_onchain",
                        lambda *a, **k: None)   # receipt not deep enough yet
    header = _proof_header(TX_SELF, amount=0.05)
    r = env.client.get("/api/stats", headers={"X-Payment-Proof": header})
    assert r.status_code == 401
    hint = r.get_json()["hint"]
    assert "~24s" in hint and "12" in hint
    assert "~2s" not in hint
    assert "SAME proof" in hint


def test_reverted_settlement_reason_states_both_outcomes(env, monkeypatch):
    """Audit #4 check в: the OUT-of-window nonce-revert must not lie.

    In-window retries are adopted by nonce (covered above). When the search
    does NOT confirm the spend (outside the 5000-block window, or a balance
    revert), the old reason blamed the payer wholesale. It must now say both
    outcomes, because only one is true and a revert cannot say which.
    """
    main, client = env.main, env.client
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (True, PAYER, "verified_locally"))
    monkeypatch.setattr(
        env.connectors, "settle_standard_payment",
        lambda h, r: (None, "self_broadcast_reverted: tx 0x" + "ee" * 32 +
                      " — the on-chain transferWithAuthorization failed "
                      "(insufficient buyer USDC balance or authorization "
                      "already used)"))
    _install_fake_web3(monkeypatch, _FakeEth(block_number=99))

    r = client.get("/api/stats",
                   headers={"PAYMENT-SIGNATURE": _standard_header(main)})
    assert r.status_code == 401
    reason = r.get_json()["reason"]
    assert reason.startswith("settlement_failed:")
    assert "NO new payment is needed" in reason
    assert "search window" in reason and "fund it and retry" in reason
    # …and this unproven case must NOT pretend to be the in-window 425.
    assert r.get_json()["error"] == "invalid_standard_payment"


# ── Audit #5: THEIR decoder, VERBATIM, run against OUR emitted headers ──────
#
# Verbatim from coinbase/x402 @ main:
#   typescript/packages/core/src/utils/index.ts:
#     export const Base64EncodedRegex = /^[A-Za-z0-9+/]*={0,2}$/;
#   typescript/packages/core/src/http/index.ts:
#     export function decodePaymentRequiredHeader(paymentRequiredHeader) {
#       if (!Base64EncodedRegex.test(paymentRequiredHeader)) {
#         throw new Error("Invalid payment required header");
#       }
#       return JSON.parse(safeBase64Decode(paymentRequiredHeader));
#     }
#     export function decodePaymentResponseHeader(paymentResponseHeader) {
#       if (!Base64EncodedRegex.test(paymentResponseHeader)) {
#         throw new Error("Invalid payment response header");
#       }
#       return JSON.parse(safeBase64Decode(paymentResponseHeader));
#     }
# safeBase64Decode's browser branch is atob(): STANDARD alphabet only —
# base64url's -/_ make it throw, exactly like validate=True does below.

_THEIR_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


def _their_safe_b64_decode(data: str) -> str:
    """atob-equivalent: standard alphabet, forgiving padding."""
    return base64.b64decode(
        data + "=" * (-len(data) % 4), validate=True).decode()


def _their_decode_payment_required(header: str) -> dict:
    if not _THEIR_BASE64_RE.match(header):
        raise ValueError("Invalid payment required header")
    return json.loads(_their_safe_b64_decode(header))


def _their_decode_payment_response(header: str) -> dict:
    if not _THEIR_BASE64_RE.match(header):
        raise ValueError("Invalid payment response header")
    return json.loads(_their_safe_b64_decode(header))


def test_payment_response_passes_their_verbatim_decoder(env, monkeypatch):
    """Audit #5 FIX 1: the receipt must survive THEIR decodePaymentResponseHeader."""
    main, client = env.main, env.client
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (True, PAYER, "verified_locally"))
    receipt = _receipt(TX_CDP, 300, PAYER, 5000, main.X402_RECEIVER_ADDRESS)
    eth = _FakeEth(block_number=305, receipts={TX_CDP: receipt},
                   auth_logs=[_auth_log(TX_CDP, 300, PAYER, NONCE_A)])
    _install_fake_web3(monkeypatch, eth)

    r = client.get("/api/stats",
                   headers={"PAYMENT-SIGNATURE": _standard_header(main)})
    assert r.status_code == 200, r.get_json()
    header = r.headers["PAYMENT-RESPONSE"]
    assert _THEIR_BASE64_RE.match(header), "their regex gate must pass"
    settlement = _their_decode_payment_response(header)
    assert settlement["success"] is True
    assert settlement["transaction"] == TX_CDP
    assert settlement["network"] == "eip155:8453"
    # control: RAW JSON — the audit-#5 bug — is what their decoder rejected
    with pytest.raises(ValueError, match="Invalid payment response header"):
        _their_decode_payment_response(json.dumps(settlement))


def test_payment_required_with_query_url_passes_their_decoder(env):
    """Audit #5 FIX 2: a '?' in resource.url must not flip the alphabet.

    base64 sextet 63 sits at raw-JSON offset ≡ 2 (mod 3): urlsafe encodes it
    as '_' (their regex REJECTS), standard as '/' (their regex ACCEPTS). We
    sweep the path length until the old form would have contained '_'.
    """
    main = env.main
    old_breaker = None
    for pad in range(3):
        endpoint = "/api/stats" + "z" * pad + "?x=1"
        with main.app.test_request_context(endpoint):
            resp = main._x402_payment_required_response(endpoint, 0.005)
        header = resp.headers["PAYMENT-REQUIRED"]
        # the NEW form must pass their gate on every sweep position …
        decoded = _their_decode_payment_required(header)
        assert decoded["x402Version"] == 2
        assert decoded["resource"]["url"].endswith(endpoint)
        # … while the OLD base64url form fails on exactly one position
        raw = json.dumps(decoded)          # byte-identical to the payload
        old = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
        if "_" in old or "-" in old:
            old_breaker = old
            break
    assert old_breaker, "could not force a urlsafe char with '?' in the URL"
    with pytest.raises(ValueError, match="Invalid payment required header"):
        _their_decode_payment_required(old_breaker)


def test_verify_accepts_standard_and_urlsafe_signatures(env):
    """Audit #5 double compatibility: the SDK's STANDARD base64 and our
    legacy base64url both decode, precheck clean and recover the signer —
    no existing client breaks when the standard form becomes common."""
    import time as _time

    from eth_account import Account
    from eth_account.messages import encode_typed_data

    main, connectors = env.main, env.connectors
    acct = Account.create()
    now = int(_time.time())
    accepted = {
        "scheme": "exact",
        "network": "eip155:8453",
        "amount": "5000",
        "asset": USDC,
        "payTo": main.X402_RECEIVER_ADDRESS,
        "maxTimeoutSeconds": 60,
        "extra": {"name": "USD Coin", "version": "2"},
    }
    authorization = {
        "from": acct.address,
        "to": main.X402_RECEIVER_ADDRESS,
        "value": "5000",
        "validAfter": str(now - 600),
        "validBefore": str(now + 60),
        "nonce": NONCE_A,
    }
    eip712_types = {"TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]}
    sm = encode_typed_data(
        domain_data={"name": "USD Coin", "version": "2", "chainId": 8453,
                     "verifyingContract": USDC},
        message_types=eip712_types, message_data=authorization)
    payload = {
        "x402Version": 2,
        "accepted": accepted,
        "payload": {"authorization": authorization,
                    "signature": "0x" + acct.sign_message(sm).signature.hex()},
        "extensions": {},
    }
    requirements = {"amount": "5000", "asset": USDC,
                    "payTo": main.X402_RECEIVER_ADDRESS}
    raw = json.dumps(payload).encode()
    forms = {
        "standard (SDK safeBase64Encode)": base64.b64encode(raw).decode(),
        "urlsafe (our legacy)": base64.urlsafe_b64encode(raw).decode().rstrip("="),
    }
    for name, header in forms.items():
        decoded = connectors.decode_payment_payload(header)
        assert decoded == payload, name
        assert connectors.precheck_payment_payload(decoded, requirements) == [], name
        recovered, err = connectors._local_recover_signer(decoded)
        assert recovered and recovered.lower() == acct.address.lower(), (name, err)


def test_standard_b64_signature_drives_the_425_path(env, monkeypatch):
    """Audit #5 × #4: the C2-refusal 425 fires identically for the SDK's
    standard-base64 PAYMENT-SIGNATURE."""
    main, client = env.main, env.client
    settle_calls = []

    def fake_settle(header, requirements):
        settle_calls.append(header)
        return TX_SELF, "settled_self_broadcast"

    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (True, PAYER, "verified_locally"))
    monkeypatch.setattr(env.connectors, "settle_standard_payment", fake_settle)
    receipt = _receipt(TX_SELF, 100, PAYER, 5000, main.X402_RECEIVER_ADDRESS)
    eth = _FakeEth(block_number=99, receipts={TX_SELF: receipt}, auth_logs=[])
    _install_fake_web3(monkeypatch, eth)

    header = _standard_header(main, standard=True)
    assert "-" not in header and "_" not in header, \
        "SDK form must be STANDARD base64 (btoa alphabet)"
    r = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": header})
    assert r.status_code == 425, r.get_json()
    assert r.get_json()["error"] == "settlement_in_flight"
    assert r.get_json()["transaction"] == TX_SELF
    assert len(settle_calls) == 1


def test_standard_b64_signature_drives_json500_recovery(env, monkeypatch):
    """Audit #5 × #4/F3: JSON 500 after a standard-base64 signed grant, C1
    row survives, the SAME header recovers, receipt passes THEIR decoder."""
    main, dash, client = env.main, env.dash, env.client
    real_safe_jsonify = main._safe_jsonify

    def boom(*a, **k):
        raise RuntimeError("simulated handler failure (audit #5)")
    monkeypatch.setattr(main, "_safe_jsonify", boom)
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (True, PAYER, "verified_locally"))
    monkeypatch.setattr(env.connectors, "settle_standard_payment",
                        lambda h, r: (TX_SELF, "settled"))
    receipt = _receipt(TX_SELF, 300, PAYER, 5000, main.X402_RECEIVER_ADDRESS)
    eth = _FakeEth(block_number=305, receipts={TX_SELF: receipt}, auth_logs=[])
    _install_fake_web3(monkeypatch, eth)
    header = _standard_header(main, standard=True)

    r1 = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": header})
    assert r1.status_code == 500, r1.data[:300]
    assert r1.is_json, f"HTML error page after a paid grant: {r1.data[:160]!r}"
    assert r1.get_json()["error"] == "internal_error"
    assert r1.headers.get("X-Request-Id")
    row = dash.payment_guard_row(TX_SELF)
    assert row and not row["delivered_at"], "a 500 must not stamp delivery"

    monkeypatch.setattr(main, "_safe_jsonify", real_safe_jsonify)
    r2 = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": header})
    assert r2.status_code == 200, r2.get_json()
    settlement = _their_decode_payment_response(r2.headers["PAYMENT-RESPONSE"])
    assert settlement["success"] is True
    assert settlement["transaction"] == TX_SELF
    row = dash.payment_guard_row(TX_SELF)
    assert row and row["delivered_at"], "recovery delivery stamps the claim"