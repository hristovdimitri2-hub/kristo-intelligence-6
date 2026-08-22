import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from integrations.x402_settlement import (
    PaymentChallenge,
    SettlementError,
    X402SettlementService,
    canonical_request_hash,
    decode_proof,
)


PAYER = "0x1111111111111111111111111111111111111111"
RECEIVER = "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TX_HASH = "0x" + "a" * 64


def _proof(payload):
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


class FakeSettlementStore:
    def __init__(self, challenge):
        self.challenge = challenge
        self.calls = []

    def is_healthy(self):
        return True

    def get_challenge(self, challenge_id):
        return self.challenge if challenge_id == self.challenge.challenge_id else None

    def settle_and_credit(self, **kwargs):
        self.calls.append(kwargs)
        return {"settled": True, "duplicate": False, "agent_id": kwargs["challenge"].agent_id}


def _service(challenge):
    service = X402SettlementService(
        database_url="",
        receiver_address=RECEIVER,
        token_contract=USDC,
        chain_id=8453,
        enabled=True,
        confirmations=2,
    )
    service.store = FakeSettlementStore(challenge)
    return service


def test_payment_proof_is_bound_to_exact_challenge_and_request(monkeypatch):
    request_hash = canonical_request_hash("whaleflow-radar", "/agent", {"input": "ETH"})
    challenge = PaymentChallenge(
        challenge_id="challenge-1",
        agent_id="whaleflow-radar",
        endpoint="/agent",
        request_hash=request_hash,
        amount_atomic=30_000,
        amount_usdc=0.03,
        issued_at=datetime.now(timezone.utc),
        issued_block_number=99,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service = _service(challenge)
    monkeypatch.setattr(
        service,
        "_validate_receipt",
        lambda proof, _: {
            "transaction_hash": TX_HASH,
            "payer": PAYER.lower(),
            "block_number": 100,
            "confirmations": 3,
        },
    )
    proof = _proof(
        {
            "challenge_id": challenge.challenge_id,
            "payer": PAYER,
            "payer_signature": "mocked",
            "transaction_hash": TX_HASH,
        }
    )

    result = service.verify_and_settle(
        proof_header=proof,
        agent_id="whaleflow-radar",
        endpoint="/agent",
        request_hash=request_hash,
    )

    assert result["settled"] is True
    assert result["challenge_id"] == challenge.challenge_id
    assert service.store.calls[0]["transaction_hash"] == TX_HASH

    with pytest.raises(SettlementError, match="payment_challenge_request_mismatch"):
        service.verify_and_settle(
            proof_header=proof,
            agent_id="whaleflow-radar",
            endpoint="/agent",
            request_hash="different-request",
        )


def test_malformed_payment_proofs_return_stable_client_errors(monkeypatch):
    challenge = PaymentChallenge(
        challenge_id="challenge-invalid",
        agent_id="whaleflow-radar",
        endpoint="/agent",
        request_hash="request",
        amount_atomic=30_000,
        amount_usdc=0.03,
        issued_at=datetime.now(timezone.utc),
        issued_block_number=99,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service = _service(challenge)

    with pytest.raises(SettlementError, match="invalid_payment_proof"):
        decode_proof("💥")

    invalid_chain = {
        "transaction_hash": TX_HASH,
        "payer": PAYER,
        "challenge_id": challenge.challenge_id,
        "chain_id": "not-a-number",
    }
    with pytest.raises(SettlementError, match="invalid_payment_chain"):
        service._validate_receipt(invalid_chain, challenge)

    invalid_amount = {
        **invalid_chain,
        "chain_id": 8453,
        "receiver_address": RECEIVER,
        "token_contract": USDC,
        "amount_atomic": "not-a-number",
    }
    with pytest.raises(SettlementError, match="invalid_payment_amount"):
        service._validate_receipt(invalid_amount, challenge)


def test_receipt_requires_exact_base_usdc_transfer(monkeypatch):
    challenge = PaymentChallenge(
        challenge_id="challenge-2",
        agent_id="whaleflow-radar",
        endpoint="/agent",
        request_hash="request",
        amount_atomic=30_000,
        amount_usdc=0.03,
        issued_at=datetime.now(timezone.utc),
        issued_block_number=99,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service = _service(challenge)
    monkeypatch.setattr(service, "_validate_signature", lambda *_: None)

    class HexValue(str):
        def hex(self):
            return str(self)

    sender_topic = "0x" + "0" * 24 + PAYER[2:].lower()
    receiver_topic = "0x" + "0" * 24 + RECEIVER[2:].lower()

    class FakeEth:
        chain_id = 8453
        block_number = 102

        def get_transaction_receipt(self, _):
            return {
                "status": 1,
                "blockNumber": 100,
                "logs": [
                    {
                        "address": USDC,
                        "topics": [
                            HexValue("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"),
                            HexValue(sender_topic),
                            HexValue(receiver_topic),
                        ],
                        "data": HexValue("0x" + challenge.amount_atomic.to_bytes(32, "big").hex()),
                    }
                ],
            }

        def get_block(self, _):
            return {"timestamp": int(datetime.now(timezone.utc).timestamp())}

    class FakeWeb3:
        eth = FakeEth()

    monkeypatch.setattr(service, "_web3", lambda: FakeWeb3())
    proof = {
        "challenge_id": challenge.challenge_id,
        "transaction_hash": TX_HASH,
        "payer": PAYER,
        "payer_signature": "mocked",
        "chain_id": 8453,
        "receiver_address": RECEIVER,
        "token_contract": USDC,
        "amount_atomic": "30000",
        "block_number": 100,
    }

    verified = service._validate_receipt(proof, challenge)
    assert verified["confirmations"] == 3

    proof["amount_atomic"] = "1"
    with pytest.raises(SettlementError, match="wrong_payment_amount"):
        service._validate_receipt(proof, challenge)


def test_receipt_before_challenge_is_rejected(monkeypatch):
    issued_at = datetime.now(timezone.utc)
    challenge = PaymentChallenge(
        challenge_id="challenge-3",
        agent_id="whaleflow-radar",
        endpoint="/agent",
        request_hash="request",
        amount_atomic=30_000,
        amount_usdc=0.03,
        issued_at=issued_at,
        issued_block_number=100,
        expires_at=issued_at + timedelta(minutes=5),
    )
    service = _service(challenge)
    monkeypatch.setattr(service, "_validate_signature", lambda *_: None)

    class FakeEth:
        chain_id = 8453
        block_number = 102

        def get_transaction_receipt(self, _):
            return {"status": 1, "blockNumber": 100, "logs": []}

        def get_block(self, _):
            return {"timestamp": int((issued_at - timedelta(seconds=1)).timestamp())}

    class FakeWeb3:
        eth = FakeEth()

    monkeypatch.setattr(service, "_web3", lambda: FakeWeb3())
    proof = {
        "challenge_id": challenge.challenge_id, "transaction_hash": TX_HASH,
        "payer": PAYER, "payer_signature": "mocked", "chain_id": 8453,
        "receiver_address": RECEIVER, "token_contract": USDC, "amount_atomic": "30000",
    }
    with pytest.raises(SettlementError, match="payment_outside_challenge_window"):
        service._validate_receipt(proof, challenge)