"""Agent-bound, on-chain verified x402 settlement for Base USDC."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Optional
from uuid import uuid4

from config import BASE_RPC_URL


USDC_DECIMALS = 6
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TX_HASH_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class SettlementError(ValueError):
    def __init__(self, code: str, status_code: int = 400):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_request_hash(agent_id: str, endpoint: str, payload: Dict[str, Any]) -> str:
    value = json.dumps(
        {"agent_id": agent_id, "endpoint": endpoint, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(value.encode()).hexdigest()


def usdc_to_atomic(amount: float) -> int:
    value = Decimal(str(amount)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    if value <= 0:
        raise ValueError("payment amount must be positive")
    return int(value * (10**USDC_DECIMALS))


def _safe_address(value: Any) -> str:
    value = str(value or "")
    if not ADDRESS_RE.fullmatch(value):
        raise SettlementError("invalid_payment_address")
    return value.lower()


def _proof_int(value: Any, error_code: str) -> int:
    """Parse hostile proof fields without allowing decoder errors to escape."""
    if isinstance(value, bool):
        raise SettlementError(error_code)
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        raise SettlementError(error_code) from None


def decode_proof(header_value: str) -> Dict[str, Any]:
    if not header_value or len(header_value) > 16384:
        raise SettlementError("invalid_payment_proof")
    try:
        padded = header_value + "=" * (-len(header_value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        proof = json.loads(decoded.decode("utf-8"))
    except (
        ValueError,
        UnicodeEncodeError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ):
        raise SettlementError("invalid_payment_proof") from None
    if not isinstance(proof, dict):
        raise SettlementError("invalid_payment_proof")
    return proof


@dataclass(frozen=True)
class PaymentChallenge:
    challenge_id: str
    agent_id: str
    endpoint: str
    request_hash: str
    amount_atomic: int
    amount_usdc: float
    issued_at: datetime
    issued_block_number: int
    expires_at: datetime
    status: str = "issued"
    transaction_hash: Optional[str] = None

    @property
    def signing_message(self) -> str:
        return (
            "kristo-x402:v1:"
            f"{self.challenge_id}:{self.agent_id}:{self.endpoint}:"
            f"{self.request_hash}:{self.amount_atomic}:{self.issued_at.isoformat()}:"
            f"{self.issued_block_number}:{self.expires_at.isoformat()}"
        )

    def public_payload(self) -> Dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "request_hash": self.request_hash,
            "amount_atomic": str(self.amount_atomic),
            "issued_at": self.issued_at.isoformat(),
            "issued_block_number": self.issued_block_number,
            "expires_at": self.expires_at.isoformat(),
            "signing_message": self.signing_message,
        }


class PostgresX402SettlementStore:
    backend = "postgresql"

    def __init__(self, database_url: str):
        self.database_url = database_url

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _challenge(row: Dict[str, Any]) -> PaymentChallenge:
        return PaymentChallenge(
            challenge_id=row["challenge_id"],
            agent_id=row["agent_id"],
            endpoint=row["endpoint"],
            request_hash=row["request_hash"],
            amount_atomic=int(row["amount_atomic"]),
            amount_usdc=float(row["amount_usdc"]),
            issued_at=row["issued_at"],
            issued_block_number=int(row["issued_block_number"]),
            expires_at=row["expires_at"],
            status=row["status"],
            transaction_hash=row.get("transaction_hash"),
        )

    def is_healthy(self) -> bool:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT to_regclass('public.x402_payment_challenges') AS challenges,
                           to_regclass('public.x402_settlements') AS settlements
                    """
                )
                row = cur.fetchone()
                return bool(row and row["challenges"] and row["settlements"])
        except Exception:
            return False

    def create_challenge(
        self, *, agent_id: str, endpoint: str, request_hash: str, amount_usdc: float,
        issued_block_number: int, ttl_seconds: int,
    ) -> PaymentChallenge:
        challenge = PaymentChallenge(
            challenge_id=str(uuid4()),
            agent_id=agent_id,
            endpoint=endpoint,
            request_hash=request_hash,
            amount_atomic=usdc_to_atomic(amount_usdc),
            amount_usdc=round(float(amount_usdc), 6),
            issued_at=_now(),
            issued_block_number=int(issued_block_number),
            expires_at=_now() + timedelta(seconds=ttl_seconds),
        )
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.x402_payment_challenges
                  (challenge_id, agent_id, endpoint, request_hash, amount_atomic, amount_usdc,
                   issued_at, issued_block_number, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    challenge.challenge_id, challenge.agent_id, challenge.endpoint,
                    challenge.request_hash, challenge.amount_atomic, challenge.amount_usdc,
                    challenge.issued_at, challenge.issued_block_number, challenge.expires_at,
                ),
            )
        return challenge

    def get_challenge(self, challenge_id: str) -> Optional[PaymentChallenge]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM public.x402_payment_challenges WHERE challenge_id = %s",
                (challenge_id,),
            )
            row = cur.fetchone()
        return self._challenge(row) if row else None

    def settle_and_credit(
        self, *, challenge: PaymentChallenge, transaction_hash: str, payer_address: str,
        receiver_address: str, token_contract: str, block_number: int, confirmations: int,
    ) -> Dict[str, Any]:
        """Atomically make an accepted proof durable and credit only its bound agent."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM public.x402_payment_challenges WHERE challenge_id = %s FOR UPDATE",
                (challenge.challenge_id,),
            )
            current = cur.fetchone()
            if not current:
                raise SettlementError("unknown_payment_challenge", 404)
            if current["status"] == "settled":
                if current.get("transaction_hash") == transaction_hash:
                    return {"settled": True, "duplicate": True, "agent_id": current["agent_id"]}
                raise SettlementError("payment_challenge_already_used", 409)
            if current["expires_at"] <= _now():
                cur.execute(
                    "UPDATE public.x402_payment_challenges SET status = 'expired' WHERE challenge_id = %s",
                    (challenge.challenge_id,),
                )
                raise SettlementError("payment_challenge_expired", 410)
            cur.execute(
                """
                INSERT INTO public.x402_settlements (
                  transaction_hash, challenge_id, agent_id, payer_address, receiver_address,
                  token_contract, amount_atomic, block_number, confirmations
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(transaction_hash) DO NOTHING RETURNING transaction_hash
                """,
                (
                    transaction_hash, challenge.challenge_id, challenge.agent_id, payer_address,
                    receiver_address, token_contract, challenge.amount_atomic, block_number, confirmations,
                ),
            )
            if not cur.fetchone():
                raise SettlementError("transaction_already_settled", 409)
            cur.execute(
                """
                INSERT INTO public.agent_events (event_id, agent_id, event_type, occurred_at, amount_usd)
                VALUES (%s, %s, 'payment', %s, %s)
                """,
                (f"x402-payment:{challenge.challenge_id}", challenge.agent_id, _now(), challenge.amount_usdc),
            )
            cur.execute(
                """
                UPDATE public.agent_skus
                SET total_revenue = total_revenue + %s, last_updated = %s
                WHERE id = %s
                """,
                (challenge.amount_usdc, _now(), challenge.agent_id),
            )
            cur.execute(
                """
                UPDATE public.x402_payment_challenges
                SET status = 'settled', transaction_hash = %s, settled_at = %s
                WHERE challenge_id = %s
                """,
                (transaction_hash, _now(), challenge.challenge_id),
            )
        return {"settled": True, "duplicate": False, "agent_id": challenge.agent_id}

    def mark_delivered(self, challenge_id: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE public.x402_settlements SET delivery_status = 'delivered' WHERE challenge_id = %s",
                (challenge_id,),
            )


class DisabledX402SettlementStore:
    backend = "disabled"

    def is_healthy(self) -> bool:
        return False


class X402SettlementService:
    def __init__(
        self, *, database_url: str, receiver_address: str, token_contract: str, chain_id: int,
        rpc_url: str = BASE_RPC_URL, enabled: bool = False, confirmations: int = 2,
    ):
        self.enabled = enabled
        self.receiver_address = _safe_address(receiver_address)
        self.token_contract = _safe_address(token_contract)
        self.chain_id = int(chain_id)
        self.rpc_url = rpc_url
        self.confirmations = max(1, int(confirmations))
        self.ttl_seconds = min(max(int(os.getenv("X402_CHALLENGE_TTL_SECONDS", "300")), 60), 900)
        self.store = PostgresX402SettlementStore(database_url) if database_url else DisabledX402SettlementStore()

    @property
    def status(self) -> str:
        return "full" if self.enabled and self.store.is_healthy() else "discovery_only"

    def issue_challenge(self, *, agent_id: str, endpoint: str, request_hash: str, amount_usdc: float) -> PaymentChallenge:
        if self.status != "full":
            raise SettlementError("x402_settlement_unavailable", 503)
        try:
            web3 = self._web3()
            if web3.eth.chain_id != self.chain_id:
                raise SettlementError("wrong_rpc_chain", 503)
            issued_block_number = int(web3.eth.block_number)
            return self.store.create_challenge(
                agent_id=agent_id, endpoint=endpoint, request_hash=request_hash,
                amount_usdc=amount_usdc, issued_block_number=issued_block_number,
                ttl_seconds=self.ttl_seconds,
            )
        except SettlementError:
            raise
        except Exception as exc:
            raise SettlementError("payment_challenge_unavailable", 503) from exc

    def _web3(self):
        from web3 import Web3
        return Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 12}))

    def _validate_receipt(self, proof: Dict[str, Any], challenge: PaymentChallenge) -> Dict[str, Any]:
        tx_hash = str(proof.get("transaction_hash", ""))
        if not TX_HASH_RE.fullmatch(tx_hash):
            raise SettlementError("invalid_transaction_hash")
        payer = _safe_address(proof.get("payer"))
        if str(proof.get("challenge_id", "")) != challenge.challenge_id:
            raise SettlementError("payment_challenge_mismatch", 409)
        if _proof_int(proof.get("chain_id"), "invalid_payment_chain") != self.chain_id:
            raise SettlementError("wrong_payment_chain")
        if _safe_address(proof.get("receiver_address")) != self.receiver_address:
            raise SettlementError("wrong_payment_receiver")
        if _safe_address(proof.get("token_contract")) != self.token_contract:
            raise SettlementError("wrong_payment_token")
        if _proof_int(proof.get("amount_atomic"), "invalid_payment_amount") != challenge.amount_atomic:
            raise SettlementError("wrong_payment_amount")
        self._validate_signature(payer, str(proof.get("payer_signature", "")), challenge)

        try:
            web3 = self._web3()
            if web3.eth.chain_id != self.chain_id:
                raise SettlementError("wrong_rpc_chain", 503)
            receipt = web3.eth.get_transaction_receipt(tx_hash)
            if int(receipt["status"]) != 1:
                raise SettlementError("reverted_payment_transaction")
            block_number = int(receipt["blockNumber"])
            if (
                proof.get("block_number") is not None
                and _proof_int(proof["block_number"], "invalid_payment_block") != block_number
            ):
                raise SettlementError("payment_block_mismatch")
            if block_number <= challenge.issued_block_number:
                raise SettlementError("payment_outside_challenge_window", 409)
            latest = int(web3.eth.block_number)
            confirmations = latest - block_number + 1
            if confirmations < self.confirmations:
                raise SettlementError("payment_not_final", 409)
            block = web3.eth.get_block(block_number)
            block_time = datetime.fromtimestamp(int(block["timestamp"]), tz=timezone.utc)
            if block_time > challenge.expires_at:
                raise SettlementError("payment_outside_challenge_window", 409)
        except SettlementError:
            raise
        except Exception as exc:
            raise SettlementError("payment_receipt_unavailable", 503) from exc

        matched = False
        for log in receipt["logs"]:
            topics = [item.hex().lower() for item in log["topics"]]
            if (
                str(log["address"]).lower() == self.token_contract
                and len(topics) == 3
                and topics[0] == TRANSFER_TOPIC
                and ("0x" + topics[1][-40:]) == payer
                and ("0x" + topics[2][-40:]) == self.receiver_address
                and int(log["data"].hex(), 16) == challenge.amount_atomic
            ):
                matched = True
                break
        if not matched:
            raise SettlementError("payment_transfer_not_found")
        return {
            "transaction_hash": tx_hash.lower(), "payer": payer, "block_number": block_number,
            "confirmations": confirmations,
        }

    @staticmethod
    def _validate_signature(payer: str, signature: str, challenge: PaymentChallenge) -> None:
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct
            recovered = Account.recover_message(
                encode_defunct(text=challenge.signing_message), signature=signature
            ).lower()
        except Exception as exc:
            raise SettlementError("invalid_payment_signature") from exc
        if recovered != payer:
            raise SettlementError("payment_signature_payer_mismatch")

    def verify_and_settle(
        self, *, proof_header: str, agent_id: str, endpoint: str, request_hash: str
    ) -> Dict[str, Any]:
        if self.status != "full":
            raise SettlementError("x402_settlement_unavailable", 503)
        proof = decode_proof(proof_header)
        challenge_id = str(proof.get("challenge_id", ""))
        challenge = self.store.get_challenge(challenge_id)
        if not challenge:
            raise SettlementError("unknown_payment_challenge", 404)
        if (
            challenge.agent_id != agent_id
            or challenge.endpoint != endpoint
            or challenge.request_hash != request_hash
        ):
            raise SettlementError("payment_challenge_request_mismatch", 409)
        receipt = self._validate_receipt(proof, challenge)
        settled = self.store.settle_and_credit(
            challenge=challenge,
            transaction_hash=receipt["transaction_hash"],
            payer_address=receipt["payer"],
            receiver_address=self.receiver_address,
            token_contract=self.token_contract,
            block_number=receipt["block_number"],
            confirmations=receipt["confirmations"],
        )
        return {**settled, "challenge_id": challenge.challenge_id, **receipt}

    def mark_delivered(self, challenge_id: str) -> None:
        if self.status == "full":
            self.store.mark_delivered(challenge_id)