"""
Blockchain / Base network wallet utilities.

Handles the 0.10 USDC per-request fee on Base. The payment is made fully
non-blocking: a transaction timeout, balance pre-check, and graceful
fallback ensure the program never hangs while waiting for a receipt.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

# ── Central configuration (bound wallet address) ───────────────────────────
from config import get_base_fee_receiver

try:
    from web3 import Web3
    from web3.exceptions import TransactionNotFound
    _HAS_WEB3 = True
except Exception:  # pragma: no cover — web3 is optional at import time
    _HAS_WEB3 = False

log = logging.getLogger("kristo.v5.wallet")

# ERC-20 `transfer(address,uint256)` ABI fragment
_ERC20_TRANSFER_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]

# How long (seconds) to wait for a receipt before giving up gracefully.
_RECEIPT_TIMEOUT = 60
# Polling interval while waiting for a receipt.
_POLL_INTERVAL = 2


class Wallet:
    """Lightweight Base wallet wrapper for USDC fee payments."""

    def __init__(self, private_key: str, rpc_url: str, usdc_address: str,
                 fee_receiver: str, fee_amount_usdc: float = 0.10):
        if not _HAS_WEB3:
            raise RuntimeError(
                "web3 is not installed. Install with: pip install web3"
            )
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        # web3.py v6+ uses is_connected(); older versions use isConnected()
        connected = (
            self.w3.is_connected()
            if hasattr(self.w3, "is_connected")
            else self.w3.isConnected()
        )
        if not connected:
            raise ConnectionError(f"Cannot connect to Base RPC at {rpc_url}")
        self.account = self.w3.eth.account.from_key(private_key)
        self.usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(usdc_address), abi=_ERC20_TRANSFER_ABI
        )
        self.fee_receiver = Web3.to_checksum_address(fee_receiver)
        self.fee_amount_usdc = fee_amount_usdc

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls) -> Optional["Wallet"]:
        """Build a Wallet from environment variables. Returns None if no key set."""
        pk = os.getenv("WALLET_PRIVATE_KEY", "").strip()
        if not pk:
            return None
        try:
            return cls(
                private_key=pk,
                rpc_url=os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
                usdc_address=os.getenv(
                    "BASE_USDC_CONTRACT",
                    "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                ),
                fee_receiver=get_base_fee_receiver(),  # hard fallback to bound address
                fee_amount_usdc=float(os.getenv("BASE_FEE_AMOUNT_USDC", "0.10")),
            )
        except Exception as exc:
            log.error("Failed to initialize wallet: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------
    def get_usdc_balance(self) -> float:
        decimals = self.usdc.functions.decimals().call()
        raw = self.usdc.functions.balanceOf(self.account.address).call()
        return raw / (10 ** decimals)

    # ------------------------------------------------------------------
    # Fee payment — NON-BLOCKING
    # ------------------------------------------------------------------
    def pay_request_fee(self) -> bool:
        """
        Pay the 0.10 USDC fee on Base. Never hangs:
          * pre-checks balance,
          * uses a bounded wait for the receipt,
          * falls back gracefully on any error.
        Returns True if paid, False otherwise.
        """
        try:
            # Guard: a zero/burn address as receiver would revert the transfer.
            if int(self.fee_receiver, 16) == 0:
                log.warning(
                    "Fee receiver is the zero address — skipping on-chain payment "
                    "(configure BASE_FEE_RECEIVER to enable)."
                )
                return False

            balance = self.get_usdc_balance()
            if balance < self.fee_amount_usdc:
                log.warning(
                    "Insufficient USDC balance: %.4f < %.4f — skipping fee.",
                    balance, self.fee_amount_usdc,
                )
                return False

            decimals = self.usdc.functions.decimals().call()
            amount_raw = int(self.fee_amount_usdc * (10 ** decimals))

            nonce = self.w3.eth.get_transaction_count(self.account.address)
            tx = self.usdc.functions.transfer(
                self.fee_receiver, amount_raw
            ).build_transaction({
                "from": self.account.address,
                "nonce": nonce,
                "gas": 120_000,
                "maxFeePerGas": self.w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": self.w3.eth.gas_price,
                "chainId": int(os.getenv("BASE_CHAIN_ID", "8453")),
            })
            signed = self.account.sign_transaction(tx)
            # web3.py v7 renamed rawTransaction -> raw_transaction; support both.
            raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            log.info("Fee tx sent: %s", tx_hash.hex())

            # Bounded wait — never hangs forever.
            receipt = self._wait_for_receipt(tx_hash, timeout=_RECEIPT_TIMEOUT)
            if receipt is None:
                log.warning("Fee tx not mined within %ds — treating as pending.", _RECEIPT_TIMEOUT)
                return False
            if receipt.get("status") == 1:
                log.info("Fee tx confirmed in block %s", receipt.get("blockNumber"))
                return True
            log.error("Fee tx reverted. Receipt: %s", receipt)
            return False
        except Exception as exc:
            log.error("Fee payment failed (non-fatal): %s", exc)
            return False

    def _wait_for_receipt(self, tx_hash, timeout: int):
        """Poll for a receipt up to `timeout` seconds. Returns None on timeout."""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                return self.w3.eth.get_transaction_receipt(tx_hash)
            except TransactionNotFound:
                time.sleep(_POLL_INTERVAL)
            except Exception as exc:
                log.warning("Receipt poll error: %s", exc)
                time.sleep(_POLL_INTERVAL)
        return None