"""
Base Network Listener
======================

Lightweight listener for incoming USDC transfers on the Base network.

The fee-receiver address is bound via `config.get_base_fee_receiver()`
which guarantees the correct wallet is always used, even if the
BASE_FEE_RECEIVER environment variable is missing.
"""

from __future__ import annotations

import logging
from typing import Optional

from config import get_base_fee_receiver, BASE_RPC_URL, BASE_USDC_CONTRACT

log = logging.getLogger("kristo.v5.base_listener")

# ERC-20 Transfer event topic: keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# ERC-20 ABI fragment (balanceOf + decimals)
_ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "owner", "type": "address"}],
     "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals",
     "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
]


class BaseListener:
    """
    Monitor-only Base listener that scans for incoming USDC Transfer
    events to the bound fee-receiver address.
    """

    def __init__(self, rpc_url: str = BASE_RPC_URL,
                 usdc_address: str = BASE_USDC_CONTRACT):
        try:
            from web3 import Web3
        except ImportError as exc:
            raise RuntimeError("web3 is not installed") from exc

        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        connected = (
            self.w3.is_connected()
            if hasattr(self.w3, "is_connected")
            else self.w3.isConnected()
        )
        if not connected:
            raise ConnectionError(f"Cannot connect to Base RPC at {rpc_url}")

        # ── Bind the fee receiver (HARD FALLBACK) ──
        self.fee_receiver = Web3.to_checksum_address(get_base_fee_receiver())
        self.usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(usdc_address), abi=_ERC20_ABI
        )
        log.info("BaseListener ready — tracking USDC transfers to %s", self.fee_receiver)

    def get_usdc_balance(self) -> float:
        """Return the real USDC balance of the fee-receiver address."""
        decimals = self.usdc.functions.decimals().call()
        raw = self.usdc.functions.balanceOf(self.fee_receiver).call()
        return raw / (10 ** decimals)

    def get_receiver_topic(self) -> str:
        """Return the padded 32-byte topic for the fee-receiver address."""
        addr = self.fee_receiver[2:] if self.fee_receiver.startswith("0x") else self.fee_receiver
        return "0x000000000000000000000000" + addr

    def scan_incoming_transfers(self, from_block: int, to_block: int) -> list:
        """
        Scan a block range for incoming USDC Transfer events to the
        fee-receiver address.  Returns a list of raw log entries.
        """
        receiver_topic = self.get_receiver_topic()
        logs = self.w3.eth.get_logs({
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": self.usdc.address,
            "topics": [TRANSFER_TOPIC, None, receiver_topic],
        })
        return logs


def get_fee_receiver_address() -> str:
    """Convenience function — returns the bound fee-receiver address."""
    return get_base_fee_receiver()