"""Never sign twice for one purchase intent.

WHY THIS EXISTS. On x402-foundation/x402#4367 the duplicate-settlement question was
answered with a mechanism rather than an opinion: every double-settled intent in a
published stress test was **two distinct nonces on the same payer** — two separate
signed authorizations about two seconds apart — not one authorization replayed. The
money moved twice because it was authorised twice.

Under `exact`, the signed nonce IS the idempotency key, and USDC records its
consumption irreversibly through `authorizationState(authorizer, nonce)`. Nothing in
the protocol needs to change; what is missing is that a client which retries after a
timeout has no memory of what it already signed.

THE RULE, in three lines:

  1. Persist `(payer, nonce)` BEFORE the signed request is sent.
  2. On any retry — after a timeout, a dropped connection, or a paid error — ask the
     token contract `authorizationState(payer, nonce)` first.
  3. `true` means it is already consumed: do not sign again, replay the stored result.
     `false` means it was never used: signing again is safe.

`false` is also what a settle-failure looks like, which is the point — a failed
settlement and a lost response are indistinguishable from the balance, and only the
nonce tells you which retry is free.

This module is deliberately small and has no framework in it. It is the client half of
the answer; the seller half is a durable claim on whatever the retried request carries.

    store = NonceStore("intents.db")
    decision = decide(store, payer, nonce, intent="buy-brief-2026-11-27", rpc_url=RPC)
    if decision == "replay":
        return store.result(payer, nonce)
    store.claim(payer, nonce, intent)
    ... sign and send ...
    store.record(payer, nonce, response_body)
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

#: USDC on Base. `authorizationState` is EIP-3009 and this contract implements it.
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DEFAULT_RPC = "https://mainnet.base.org"

#: Minimal ABI — one view function, so nothing else has to be trusted.
AUTHORIZATION_STATE_ABI = [{
    "name": "authorizationState",
    "type": "function",
    "stateMutability": "view",
    "inputs": [{"name": "authorizer", "type": "address"},
               {"name": "nonce", "type": "bytes32"}],
    "outputs": [{"name": "", "type": "bool"}],
}]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signed_nonces (
    payer      TEXT NOT NULL,
    nonce      TEXT NOT NULL,
    intent     TEXT NOT NULL,
    signed_at  REAL NOT NULL,
    consumed   INTEGER NOT NULL DEFAULT 0,
    result     TEXT,
    PRIMARY KEY (payer, nonce)
);
"""


class NonceStore:
    """A durable record of what this client has already signed.

    Durable on purpose. An in-process set is exactly what the rule cannot use: the
    case it protects against is a process that died between signing and hearing back,
    and that process takes its memory with it.
    """

    def __init__(self, path: str | Path = "x402_intents.db"):
        self.path = str(path)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def claim(self, payer: str, nonce: str, intent: str) -> bool:
        """Record the intent BEFORE sending. False means this pair is already known."""
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO signed_nonces (payer, nonce, intent, signed_at) "
                "VALUES (?, ?, ?, ?)",
                (payer.lower(), nonce.lower(), intent, time.time()))
            return cursor.rowcount > 0

    def mark_consumed(self, payer: str, nonce: str, result: Optional[str] = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE signed_nonces SET consumed = 1, result = COALESCE(?, result) "
                "WHERE payer = ? AND nonce = ?",
                (result, payer.lower(), nonce.lower()))

    def result(self, payer: str, nonce: str) -> Optional[dict]:
        """The stored answer for an already-consumed nonce, if one was kept."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result FROM signed_nonces WHERE payer = ? AND nonce = ?",
                (payer.lower(), nonce.lower())).fetchone()
        if not row or not row["result"]:
            return None
        try:
            return json.loads(row["result"])
        except ValueError:
            return None

    def known(self, payer: str, nonce: str) -> bool:
        with self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM signed_nonces WHERE payer = ? AND nonce = ?",
                (payer.lower(), nonce.lower())).fetchone() is not None


def is_consumed(payer: str, nonce: str, rpc_url: str = DEFAULT_RPC,
                usdc: str = USDC_BASE, timeout: int = 30) -> bool:
    """Ask the token contract whether this authorization has been used.

    Raises rather than guessing. A chain we could not read is not a licence to sign
    again — that is the whole failure this module exists to prevent.
    """
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
    contract = w3.eth.contract(address=Web3.to_checksum_address(usdc),
                               abi=AUTHORIZATION_STATE_ABI)
    raw = nonce if str(nonce).startswith("0x") else "0x" + str(nonce)
    if len(raw) != 66:
        raise ValueError("nonce must be 32 bytes of hex, got %d chars" % len(raw))
    return bool(contract.functions.authorizationState(
        Web3.to_checksum_address(payer), bytes.fromhex(raw[2:])).call())


def decide(store: NonceStore, payer: str, nonce: str, intent: str,
           rpc_url: str = DEFAULT_RPC) -> str:
    """One of three answers, and they lead to three different actions.

    ``"replay"``
        The contract says consumed. Do not sign again; return the stored result.
    ``"sign"``
        The contract says unconsumed. Safe to sign — this is also what a settlement
        failure looks like, and a settlement failure moved no money.
    ``"unknown"``
        The nonce was never recorded here AND the chain could not be read. Refuse and
        let the caller decide: signing on an unreadable chain is how one intent pays
        twice.
    """
    if store.known(payer, nonce):
        try:
            if is_consumed(payer, nonce, rpc_url):
                store.mark_consumed(payer, nonce)
                return "replay"
        except Exception:                                      # noqa: BLE001
            return "unknown"
        return "sign"
    try:
        if is_consumed(payer, nonce, rpc_url):
            store.claim(payer, nonce, intent)
            store.mark_consumed(payer, nonce)
            return "replay"
    except Exception:                                          # noqa: BLE001
        return "unknown"
    return "sign"
