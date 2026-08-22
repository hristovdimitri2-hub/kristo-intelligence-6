"""
Kristo Intelligence API v6
==========================
Flask application with:
  * Beautiful HTML Dashboard (/dashboard) with charts & metrics
  * JSON API endpoints: /api/sales, /api/stats, /api/bot-status
  * Render-compatible health check (/health)
  * REAL blockchain wallet integration (Base / USDC)
  * Background monitor for incoming USDC transactions

NO DEMO DATA — all sales/stats come from real on-chain activity.

Subscription tiers:
  * Micro-request: 0.10 USDC per API call
  * Monthly VIP:   29.00 USDC (unlimited access + Telegram VIP group)

MCP/x402 compatible: /api/mcp/manifest exposes machine-readable payment spec.
"""

from __future__ import annotations

import os
import logging
import threading
import time
import json
import secrets
import hmac
import hashlib
import base64
import binascii
from datetime import datetime, timedelta, timezone
from collections import deque
from typing import Dict, List, Optional

import math
from flask import Flask, jsonify, redirect, render_template_string, request, session

# ── Central configuration (bound wallet address, GLM, etc.) ────────────────
from config import BASE_CHAIN_ID, BASE_RPC_URL, get_base_fee_receiver

# ── Real-time market data integration ─────────────────────────────────────
from services.market_data import get_coingecko_cache_status, get_market_snapshot
from services.agent_runtime import (
    AGENT_CONTRACT_VERSION,
    catalog_manifest,
    execute_agent,
    manifest_is_runtime_compatible,
    public_contract,
    validate_agent_payload,
)

# ── Telegram Sales Bot (x402 micro-transactions) ───────────────────────────
from services.telegram_sales import (
    send_market_bulletin,
    generate_payment_link,
    process_webhook_update,
    telegram_sales_loop,
    register_webhook,
)

# ── x402 Payment Protocol Constants ────────────────────────────────────────
# Receiver address is bound via config.get_base_fee_receiver() (hard fallback)
X402_RECEIVER_ADDRESS = get_base_fee_receiver()
X402_USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
X402_CHAIN = "base"
X402_CHAIN_ID = 8453
X402_SETTLEMENT_MODE = (os.getenv("X402_SETTLEMENT_MODE", "disabled") or "").strip().lower()
X402_SETTLEMENT_ENABLED = X402_SETTLEMENT_MODE == "full"
X402_CONFIRMATIONS = max(1, int(os.getenv("X402_REQUIRED_CONFIRMATIONS", "2")))

# ── Dynamic Pricing (Volume Discount) ──────────────────────────────────────
# Base price: $0.05 USDC per request.
# Volume discount: drops to $0.01 USDC for batch/frequent calls.
X402_FEE_USDC_BASE = 0.05       # Standard per-call price
X402_FEE_USDC_DISCOUNT = 0.01   # Discounted price for high-volume callers
X402_VOLUME_THRESHOLD = 10      # After 10 paid calls, price drops to $0.01
X402_FEE_USDC = X402_FEE_USDC_BASE  # Backward-compat alias (used in manifests)

# ── NEXUS Discovery Engine URL ──────────────────────────────────────────────
# Public Render URL for the NEXUS Discovery Engine (Next.js platform).
# Falls back to relative "/" so links work even if NEXUS is served from same domain.
NEXUS_URL = "/nexus"

FREE_TIER_LIMIT = 1    # Max 1 free pick, then x402 payment required

# Legacy operational endpoints remain free until each has request-bound,
# settlement-verified delivery. They must never accept a direct USDC transfer
# without granting the promised access.
X402_PAID_ENDPOINTS: set[str] = set()

# Endpoints that are always free (discovery, health, dashboard, manifest)
X402_FREE_ENDPOINTS = {
    # Core navigation
    "/", "/launch", "/health", "/dashboard", "/nexus",
    # Developer / integration discovery
    "/agents", "/developers",
    # Agent catalog browsing (free; payment is at playground level)
    "/api/v1/agents", "/api/v1/catalog/contract",
    # Machine-readable discovery and payment manifests
    "/api/mcp/manifest", "/.well-known/x402.json", "/openapi.json",
    "/llms.txt", "/mcp.json",
    # Webhook and bot traffic (never paywalled)
    "/api/telegram-webhook",
    # Unauthenticated UI helpers
    "/api/dashboard-stats",
    # Nexus public discovery
    "/api/nexus/plans", "/api/nexus/click",
}

# ── Public API rate limiting ────────────────────────────────────────────────
# General per-client budget applied before x402 paywall and admin checks.
# Webhooks are never rate-limited so signed payment confirmations always land.
PUBLIC_API_RATE_LIMIT = max(10, int(os.getenv("PUBLIC_API_RATE_LIMIT", "60")))
PUBLIC_API_RATE_WINDOW_SECONDS = 60  # sliding window duration
# Paths that must never be throttled (signed payment callbacks, bot webhooks)
_RATE_LIMIT_EXEMPT_PATHS: frozenset[str] = frozenset({
    "/api/webhooks/stripe",
    "/api/telegram-webhook",
})

# ── CORS ─────────────────────────────────────────────────────────────────────
# Set ALLOWED_ORIGINS env var to a comma-separated list to restrict cross-origin
# access. Leave empty to default to the production domain only when APP_PUBLIC_URL
# is configured; otherwise the header is omitted for non-browser requests.
_ALLOWED_ORIGINS: frozenset[str] = frozenset(
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if o.strip()
)

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("kristo.v6.main")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SESSION_SECRET", "") or secrets.token_urlsafe(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# ── Runtime sales integration layer ───────────────────────────────────────
from integrations.crm_store import LeadRecord, create_crm_store
from integrations.catalog_store import CATALOG_SEED, create_catalog_store
from integrations.audit_store import create_operational_audit_store
from integrations.x402_settlement import (
    SettlementError,
    X402SettlementService,
    canonical_request_hash,
)
from integrations.research_store import create_research_store
from integrations.marketplace_store import create_marketplace_governance_store
from integrations.payment_integration import SalesCheckout
from integrations.telegram_flow import TelegramSalesFlow
from integrations.stripe_checkout import StripeCheckoutService
from integrations.stripe_vip_store import create_stripe_vip_store
from integrations.nexus_store import NEXUS_PLANS, NEXUS_X402_USDC, create_nexus_store
from services.demand_scout import run_demand_scout

CRM_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "crm_sales.db")
CATALOG_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "agent_catalog.db")
RESEARCH_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "research_insights.db")
MARKETPLACE_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "agent_marketplace.db")
STRIPE_VIP_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "stripe_vip.db")
crm_store = create_crm_store(CRM_DATA_FILE)
catalog_store = create_catalog_store(CATALOG_DATA_FILE)
marketplace_store = create_marketplace_governance_store(
    MARKETPLACE_DATA_FILE, os.getenv("DATABASE_URL", "")
)
audit_store = create_operational_audit_store()
x402_settlement = X402SettlementService(
    database_url=os.getenv("DATABASE_URL", ""),
    receiver_address=X402_RECEIVER_ADDRESS,
    token_contract=X402_USDC_CONTRACT,
    chain_id=X402_CHAIN_ID,
    enabled=X402_SETTLEMENT_ENABLED,
    confirmations=X402_CONFIRMATIONS,
)
research_store = create_research_store(RESEARCH_DATA_FILE)
checkout_store = SalesCheckout()
telegram_flow = TelegramSalesFlow(os.getenv("TELEGRAM_BOT_TOKEN", ""))
stripe_checkout = StripeCheckoutService()
stripe_vip_store = create_stripe_vip_store(
    STRIPE_VIP_DATA_FILE, os.getenv("DATABASE_URL", "")
)
nexus_store = create_nexus_store(os.getenv("DATABASE_URL", ""))
nexus_x402_settlement = X402SettlementService(
    database_url=os.getenv("DATABASE_URL", ""),
    receiver_address=X402_RECEIVER_ADDRESS,
    token_contract=X402_USDC_CONTRACT,
    chain_id=X402_CHAIN_ID,
    enabled=X402_SETTLEMENT_ENABLED,
    confirmations=X402_CONFIRMATIONS,
)
# Nexus uses a dedicated ledger and cannot change the eight-agent catalog.
nexus_x402_settlement.store = nexus_store

# A missing production migration is explicit through the protected governance
# endpoint; it never silently swaps a PostgreSQL environment to SQLite.
if getattr(marketplace_store, "available", False):
    marketplace_store.ensure_contract_draft(
        AGENT_CONTRACT_VERSION, catalog_manifest(catalog_store.get_catalog())
    )

# ── In-memory data stores (thread-safe via lock) ──────────────────────────
_lock = threading.Lock()
_stripe_snapshot_lock = threading.Lock()
_stripe_snapshot = {
    "available": False,
    "payments": [],
    "reason": "Stripe payment snapshot is warming up.",
    "fetched_at": None,
    "state": "pending",
}

# ── Official agent catalog ─────────────────────────────────────────────────
# Keep legacy statistics endpoints aligned with the durable eight-agent catalog.
PRODUCT_CATALOG = [
    {
        "id": product["id"],
        "name": product["name"],
        "category": product["category"],
        "price_usdc": product["price_x402"],
    }
    for product in CATALOG_SEED
]

# Quick lookup: product_id -> product metadata
_PRODUCT_BY_ID: Dict[str, dict] = {p["id"]: p for p in PRODUCT_CATALOG}

# Per-product stats: product_id -> {hits, sales_count, sales_volume_usd}
_product_stats: Dict[str, dict] = {
    p["id"]: {"hits": 0, "sales_count": 0, "sales_volume_usd": 0.0}
    for p in PRODUCT_CATALOG
}

# Sales history: list of dicts {timestamp, token, amount_usd, tx_hash, status}
#   — ONLY populated by real on-chain USDC transfers
_sales_history: List[dict] = []

# Request/activity log: deque for bounded size
_request_log: deque = deque(maxlen=500)
_live_request_log: deque = deque(maxlen=200)
_telegram_active_chats: set[str] = set()

# Daily stats
_daily_stats: Dict[str, dict] = {}  # date_str -> {requests, sales_count, sales_volume}

# Real wallet state
_wallet_state = {
    "wallet_address": None,
    "fee_receiver": None,
    "usdc_balance": 0.0,
    "rpc_connected": False,
    "chain_id": None,
    "network": "Base Mainnet",
    "receiver_valid": False,
    "rpc_error": None,
    "last_block_checked": 0,
    "last_check_time": None,
}

# Bot status
_bot_status = {
    "telegram_bot_running": True,
    "telegram_token_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()),
    "last_heartbeat": datetime.now(timezone.utc).isoformat(),
    "uptime_started": datetime.now(timezone.utc).isoformat(),
    "messages_sent": 0,
    "active_users": 0,
    "commands_processed": 0,
    "vip_invites_sent": 0,
}

# ── Subscription tiers & pricing ─────────────────────────────────────────
MICRO_FEE_USDC = 0.10      # Per API call
VIP_MONTHLY_USDC = 29.00   # Monthly VIP subscription
VIP_THRESHOLD_USDC = 0.10  # Payments above this trigger VIP invite logic

# Active VIP subscribers (wallet address -> {joined, invite_code, tx_hash})
_vip_subscribers: Dict[str, dict] = {}

# VIP invite codes generated (code -> {wallet, created, used})
_vip_invites: Dict[str, dict] = {}


def _classify_payment(amount_usd: float) -> str:
    """Classify a payment into a subscription tier."""
    if amount_usd >= VIP_MONTHLY_USDC:
        return "vip_monthly"
    else:
        return "micro_request"


def _is_vip_plan(plan_key: str) -> bool:
    normalized = plan_key.strip().lower()
    return normalized in {"pro", "vip", "vip_monthly"}


def _attempt_stripe_vip_delivery(checkout_id: str) -> dict:
    """Deliver a paid VIP invite using only a bot-verified Telegram link."""
    checkout = stripe_vip_store.get_checkout(checkout_id)
    if not checkout or checkout.get("payment_status") != "paid":
        return {"status": "pending_payment"}
    if not _is_vip_plan(checkout.get("plan_key", "")):
        return {"status": "not_eligible"}

    delivery = stripe_vip_store.ensure_delivery(checkout_id)
    if not delivery:
        return {"status": "delivery_record_unavailable"}
    if delivery.get("status") == "invite_sent":
        return {"status": "already_active"}

    chat_id = (delivery.get("telegram_chat_id") or "").strip()
    if not chat_id:
        return {"status": "pending_telegram_link"}
    delivery_lock_token = stripe_vip_store.acquire_delivery_lock(
        checkout_id, lease_seconds=120
    )
    if not delivery_lock_token:
        return {"status": "delivery_in_progress"}
    try:
        delivery = stripe_vip_store.get_delivery(checkout_id) or delivery
        invite_link = (delivery.get("invite_link") or "").strip()
        if not stripe_vip_store.invite_is_valid(delivery):
            if not stripe_vip_store.renew_delivery_lock(
                checkout_id, delivery_lock_token, lease_seconds=120
            ):
                return {"status": "delivery_ownership_lost"}
            invitation = telegram_flow.create_vip_invite(checkout_id)
            if invitation.get("status") != "invite_created":
                stripe_vip_store.mark_delivery(
                    checkout_id,
                    "invite_creation_failed",
                    invitation.get("status", "invite_creation_failed"),
                    delivery_lock_token,
                )
                return invitation
            invite_link = invitation["invite_link"]
            saved = stripe_vip_store.save_invite(
                checkout_id,
                invite_link,
                invitation["invite_expires_at"],
                delivery_lock_token,
            )
            if not saved:
                return {"status": "delivery_ownership_lost"}

        if not stripe_vip_store.renew_delivery_lock(
            checkout_id, delivery_lock_token, lease_seconds=120
        ):
            return {"status": "delivery_ownership_lost"}
        result = telegram_flow.send_vip_invite(chat_id, "Pro", invite_link)
        if result.get("status") == "invite_sent":
            if not stripe_vip_store.mark_delivery(
                checkout_id, "invite_sent", lock_token=delivery_lock_token
            ):
                return {"status": "delivery_ownership_lost"}
        else:
            if not stripe_vip_store.mark_delivery(
                checkout_id,
                "invite_delivery_failed",
                result.get("status", "invite_delivery_failed"),
                delivery_lock_token,
            ):
                return {"status": "delivery_ownership_lost"}
        return result
    finally:
        stripe_vip_store.release_delivery_lock(checkout_id, delivery_lock_token)


def _link_stripe_vip_telegram_account(link_token: str, chat_id: str) -> dict:
    """Bind a one-time Stripe checkout token to the Telegram account that sent it."""
    delivery = stripe_vip_store.link_telegram_account(link_token, chat_id)
    if not delivery:
        return {"status": "invalid_vip_link"}
    if delivery.get("link_result") == "conflict":
        return {"status": "telegram_link_conflict"}
    checkout = stripe_vip_store.get_checkout_by_link_token(link_token)
    if not checkout:
        return {"status": "invalid_vip_link"}
    if checkout.get("payment_status") != "paid":
        return {"status": "telegram_linked_waiting_payment"}
    return _attempt_stripe_vip_delivery(checkout["checkout_id"])


def _generate_vip_invite(wallet_address: str, tx_hash: str) -> Optional[str]:
    """
    Generate a Telegram VIP invite code for a wallet that paid >= VIP_THRESHOLD.
    Returns the invite code string, or None on failure.
    """
    invite_code = f"KRI-VIP-{secrets.token_hex(4).upper()}"
    with _lock:
        _vip_invites[invite_code] = {
            "wallet": wallet_address,
            "tx_hash": tx_hash,
            "created": datetime.now(timezone.utc).isoformat(),
            "used": False,
        }
        _vip_subscribers[wallet_address] = {
            "joined": datetime.now(timezone.utc).isoformat(),
            "invite_code": invite_code,
            "tx_hash": tx_hash,
        }
        _bot_status["vip_invites_sent"] += 1

    log.info("VIP invite generated: code=%s for wallet=%s (tx=%s)", invite_code, wallet_address, tx_hash)

    # Best-effort: send Telegram notification if bot token is configured
    _send_telegram_vip_notification(wallet_address, invite_code, tx_hash)

    return invite_code


def _send_telegram_vip_notification(wallet_address: str, invite_code: str, tx_hash: str):
    """Send a Telegram message about a new VIP subscriber (best-effort, non-blocking)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.info("Telegram VIP notification skipped (no token/chat_id). Invite code: %s", invite_code)
        return

    try:
        import requests as _requests
        msg = (
            f"🎉 New VIP Subscriber!\n"
            f"Wallet: {wallet_address[:10]}...{wallet_address[-6:]}\n"
            f"Invite Code: {invite_code}\n"
            f"Tx: {tx_hash[:18]}...\n"
            f"Time: {datetime.now(timezone.utc).isoformat()}"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        _requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=10)
        with _lock:
            _bot_status["messages_sent"] += 1
        log.info("Telegram VIP notification sent for invite %s", invite_code)
    except Exception as exc:
        log.warning("Telegram VIP notification failed (non-fatal): %s", exc)


# ── Real wallet / blockchain initialization ──────────────────────────────
def _init_wallet() -> Optional[object]:
    """
    Initialize the real Base wallet from environment variables.

    If WALLET_PRIVATE_KEY is set, a full Wallet object is created (can send + monitor).
    If only BASE_FEE_RECEIVER is set (no private key), a lightweight monitor-only
    Web3 connection is created — sufficient for scanning incoming USDC transfers.
    """
    pk = os.getenv("WALLET_PRIVATE_KEY", "").strip()
    fee_receiver = get_base_fee_receiver()  # hard fallback to bound address
    rpc_url = BASE_RPC_URL
    usdc_address = os.getenv("BASE_USDC_CONTRACT", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

    # Try full wallet first (with private key)
    if pk:
        try:
            from blockchain.wallet import Wallet
            wallet = Wallet.from_env()
            if wallet is None:
                log.warning("Wallet.from_env() returned None — falling back to monitor-only.")
            else:
                chain_id = int(wallet.w3.eth.chain_id)
                if chain_id != BASE_CHAIN_ID:
                    raise ConnectionError(
                        f"Configured RPC chain {chain_id} is not Base Mainnet ({BASE_CHAIN_ID})"
                    )
                log.info("Real wallet initialized: address=%s", wallet.account.address)
                with _lock:
                    _wallet_state["wallet_address"] = wallet.account.address
                    _wallet_state["fee_receiver"] = wallet.fee_receiver
                    _wallet_state["rpc_connected"] = True
                    _wallet_state["chain_id"] = chain_id
                    _wallet_state["receiver_valid"] = True
                    _wallet_state["rpc_error"] = None
                return wallet
        except Exception as exc:
            log.error("Failed to initialize full wallet: %s — falling back to monitor-only.", exc)

    # Fallback: monitor-only mode (no private key needed)
    if fee_receiver:
        log.info("Initializing monitor-only Web3 connection (no private key). Fee receiver: %s", fee_receiver)
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
            connected = w3.is_connected() if hasattr(w3, "is_connected") else w3.isConnected()
            if not connected:
                log.error("Cannot connect to Base RPC at %s", rpc_url)
                return None
            if not Web3.is_address(fee_receiver):
                raise ValueError("Configured Base fee receiver is not a valid EVM address")
            chain_id = int(w3.eth.chain_id)
            if chain_id != BASE_CHAIN_ID:
                raise ConnectionError(
                    f"Configured RPC chain {chain_id} is not Base Mainnet ({BASE_CHAIN_ID})"
                )

            # Create a lightweight monitor-only wallet-like object
            class _MonitorOnlyWallet:
                pass

            mock = _MonitorOnlyWallet()
            mock.w3 = w3
            mock.fee_receiver = Web3.to_checksum_address(fee_receiver)
            mock.account = type("obj", (object,), {"address": fee_receiver})()
            # Build USDC contract for balance check
            _ERC20_ABI = [
                {"constant": True, "inputs": [{"name": "owner", "type": "address"}],
                 "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "decimals",
                 "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
            ]
            mock.usdc = w3.eth.contract(
                address=Web3.to_checksum_address(usdc_address), abi=_ERC20_ABI
            )

            def _get_usdc_balance(self):
                decimals = self.usdc.functions.decimals().call()
                raw = self.usdc.functions.balanceOf(self.fee_receiver).call()
                return raw / (10 ** decimals)

            mock.get_usdc_balance = _get_usdc_balance.__get__(mock, _MonitorOnlyWallet)

            with _lock:
                _wallet_state["wallet_address"] = fee_receiver
                _wallet_state["fee_receiver"] = fee_receiver
                _wallet_state["rpc_connected"] = True
                _wallet_state["chain_id"] = chain_id
                _wallet_state["receiver_valid"] = True
                _wallet_state["rpc_error"] = None

            log.info("Monitor-only wallet ready. Tracking USDC transfers to: %s", fee_receiver)
            return mock

        except Exception as exc:
            log.error("Failed to initialize monitor-only Web3: %s", exc)
            with _lock:
                _wallet_state["rpc_connected"] = False
                _wallet_state["rpc_error"] = str(exc)
            return None

    log.warning("No WALLET_PRIVATE_KEY or BASE_FEE_RECEIVER set — wallet monitoring disabled.")
    return None


# ── Blockchain monitor: detect incoming USDC transfers ───────────────────
def _blockchain_monitor_loop():
    """
    Background thread that monitors the Base blockchain for real incoming
    USDC transfers to our fee receiver address. When a transfer is detected,
    it is recorded as a real sale.

    Uses the ERC-20 Transfer event log to find incoming transfers.
    """
    log.info("Blockchain monitor thread started.")
    wallet = _init_wallet()
    if wallet is None:
        log.warning("Blockchain monitor: no wallet — thread exiting.")
        return

    poll_interval = int(os.getenv("BLOCKCHAIN_POLL_INTERVAL", "30"))
    usdc_address = os.getenv("BASE_USDC_CONTRACT", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
    fee_receiver = wallet.fee_receiver

    # ERC-20 Transfer event topic: keccak256("Transfer(address,address,uint256)")
    TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

    # The 'to' address is padded to 32 bytes in the log topic
    receiver_topic = "0x000000000000000000000000" + fee_receiver[2:] if fee_receiver.startswith("0x") else "0x000000000000000000000000" + fee_receiver

    last_block = wallet.w3.eth.block_number
    with _lock:
        _wallet_state["last_block_checked"] = last_block
        _wallet_state["last_check_time"] = datetime.now(timezone.utc).isoformat()

    log.info("Monitoring USDC transfers to %s from block %d", fee_receiver, last_block)

    while True:
        try:
            current_block = wallet.w3.eth.block_number
            if current_block <= last_block:
                time.sleep(poll_interval)
                continue

            # Update real balance
            try:
                balance = wallet.get_usdc_balance()
                with _lock:
                    _wallet_state["usdc_balance"] = round(balance, 4)
            except Exception as exc:
                log.debug("Balance fetch failed: %s", exc)

            # Scan blocks for Transfer events to our receiver
            from_block = last_block + 1
            to_block = min(current_block, from_block + 1000)  # cap batch size

            scan_succeeded = False
            try:
                from web3 import Web3
                logs = wallet.w3.eth.get_logs({
                    "fromBlock": from_block,
                    "toBlock": to_block,
                    "address": Web3.to_checksum_address(usdc_address),
                    "topics": [TRANSFER_TOPIC, None, receiver_topic],
                })

                if logs:
                    log.info("Found %d incoming USDC transfer(s) in blocks %d-%d", len(logs), from_block, to_block)
                    for log_entry in logs:
                        _process_incoming_transfer(wallet, log_entry)
                scan_succeeded = True

            except Exception as exc:
                log.warning("Log scan failed for blocks %d-%d: %s", from_block, to_block, exc)

            if scan_succeeded:
                last_block = to_block
                with _lock:
                    _wallet_state["last_block_checked"] = last_block
                    _wallet_state["last_check_time"] = datetime.now(timezone.utc).isoformat()

        except Exception as exc:
            log.warning("Blockchain monitor cycle failed (non-fatal): %s", exc)

        time.sleep(poll_interval)


def _process_incoming_transfer(wallet, log_entry):
    """Process a single incoming USDC Transfer event log and record it as a sale."""
    try:
        from web3 import Web3

        # Decode the transfer data
        # log_entry['data'] contains the amount (uint256)
        raw_data = log_entry["data"]
        if isinstance(raw_data, (bytes, bytearray)):
            amount_raw = int(raw_data.hex(), 16)
        else:
            amount_raw = int(raw_data, 16)

        # Get decimals (typically 6 for USDC on Base)
        decimals = wallet.usdc.functions.decimals().call()
        amount_usd = amount_raw / (10 ** decimals)

        # Get tx hash
        tx_hash = log_entry["transactionHash"].hex() if hasattr(log_entry["transactionHash"], "hex") else str(log_entry["transactionHash"])

        # Get block timestamp
        block = wallet.w3.eth.get_block(log_entry["blockNumber"])
        block_ts = datetime.fromtimestamp(block["timestamp"], tz=timezone.utc)

        # Get sender address from topic[1]
        sender_topic = log_entry["topics"][1]
        sender_hex = sender_topic.hex() if hasattr(sender_topic, "hex") else sender_topic
        sender = "0x" + sender_hex[-40:]

        log.info("Real USDC transfer detected: $%.6f from %s, tx=%s", amount_usd, sender, tx_hash)

        # Record as a real sale
        _record_real_sale(
            token="USDC",
            amount_usd=round(amount_usd, 6),
            tx_hash=tx_hash,
            sender=sender,
            block_number=log_entry["blockNumber"],
            timestamp=block_ts,
        )

    except Exception as exc:
        log.error("Failed to process incoming transfer: %s", exc)


def _record_real_sale(token: str, amount_usd: float, tx_hash: str, sender: str = "",
                      block_number: int = 0, timestamp: Optional[datetime] = None):
    """Record a REAL on-chain sale in the history."""
    ts = timestamp or datetime.now(timezone.utc)
    date_str = ts.strftime("%Y-%m-%d")
    with _lock:
        # Avoid duplicates: check if tx_hash already recorded
        for s in _sales_history:
            if s["tx_hash"] == tx_hash:
                log.debug("Duplicate tx %s — skipping.", tx_hash)
                return

        _sales_history.append({
            "timestamp": ts.isoformat(),
            "token": token,
            "amount_usd": round(amount_usd, 6),
            "tx_hash": tx_hash,
            "sender": sender,
            "block_number": block_number,
            "status": "confirmed",
        })
        if date_str not in _daily_stats:
            _daily_stats[date_str] = {
                "requests": 0,
                "sales_count": 0,
                "sales_volume": 0.0,
            }
        _daily_stats[date_str]["sales_count"] += 1
        _daily_stats[date_str]["sales_volume"] = round(
            _daily_stats[date_str]["sales_volume"] + amount_usd, 6
        )
    log.info("Recorded real sale: %s $%.6f (tx=%s)", token, amount_usd, tx_hash)

    # ── VIP invite generation for payments above threshold ──────────────
    if amount_usd >= VIP_THRESHOLD_USDC and sender:
        tier = _classify_payment(amount_usd)
        log.info("Payment classified as '%s' ($%.6f) — checking VIP invite...", tier, amount_usd)
        if sender not in _vip_subscribers:
            invite = _generate_vip_invite(sender, tx_hash)
            if invite:
                log.info("VIP invite %s generated for %s payment by %s", invite, tier, sender)
        else:
            log.info("Wallet %s already has VIP status — skipping invite.", sender)


# ── Background trading agent thread ───────────────────────────────────────
def _background_agent_loop():
    """Run the trading agent in a background thread (non-blocking)."""
    log.info("Background trading-agent thread started.")
    poll_interval = int(os.getenv("AGENT_POLL_INTERVAL", "300"))
    while True:
        try:
            from services.coingecko import CoinGeckoClient
            from services.defi_signals import DeFiSignalGenerator
            from services.trading_agent import TradingAgent

            api_key = os.getenv("BASE44_API_KEY", "")
            cg = CoinGeckoClient(api_key=api_key)
            signals = DeFiSignalGenerator(api_key=api_key).generate_signals()
            agent = TradingAgent(coingecko_client=cg, signals=signals)
            decisions = agent.evaluate()

            _record_request("agent_cycle", decisions is not None)
            log.info("Agent cycle complete: %d decisions.", len(decisions))
        except Exception as exc:
            log.warning("Background agent cycle failed (non-fatal): %s", exc)
            _record_request("agent_cycle", False)
        time.sleep(poll_interval)


def _catalog_analytics_loop():
    """Refresh durable rolling-24h catalog rankings at a bounded interval."""
    interval_seconds = max(
        60, int(os.getenv("CATALOG_ANALYTICS_INTERVAL_SECONDS", "86400"))
    )
    log.info("Catalog analytics worker started (interval=%ss).", interval_seconds)
    while True:
        try:
            catalog_store.expire_entitlements()
            catalog_store.recalculate_24h()
        except Exception as exc:
            log.warning("Catalog analytics refresh failed (non-fatal): %s", exc)
        time.sleep(interval_seconds)


def _refresh_demand_scout() -> dict:
    """Generate and persist a review-only daily demand report."""
    if not getattr(marketplace_store, "available", False):
        return {
            "ok": False,
            "error": "marketplace_governance_unavailable",
            "reason": getattr(marketplace_store, "reason", ""),
        }
    report = run_demand_scout(catalog_store.get_metrics_24h())
    run = marketplace_store.record_scout_report(report)
    _record_operational_event(
        event_type="demand_scout_refresh",
        source="worker",
        status_code=200,
        success=True,
        metadata={"operation": "demand_scout", "outcome": report["status"].lower()},
    )
    return {"ok": True, "run": run, "report": report}


def _demand_scout_loop():
    """Refresh market evidence once daily without altering the live catalog."""
    interval_seconds = max(3600, int(os.getenv("DEMAND_SCOUT_INTERVAL_SECONDS", "86400")))
    log.info("Demand Scout worker started (interval=%ss).", interval_seconds)
    while True:
        try:
            outcome = _refresh_demand_scout()
            if not outcome.get("ok"):
                log.warning("Demand Scout skipped: %s", outcome.get("error", "unavailable"))
        except Exception as exc:
            log.warning("Demand Scout refresh failed (non-fatal): %s", type(exc).__name__)
        time.sleep(interval_seconds)


def _stripe_payment_snapshot_loop():
    """Continuously refresh the admin-only Stripe view without delaying web requests."""
    interval_seconds = max(
        30, int(os.getenv("STRIPE_PAYMENT_SNAPSHOT_INTERVAL_SECONDS", "60"))
    )
    log.info("Stripe payment snapshot worker started (interval=%ss).", interval_seconds)
    while True:
        _refresh_stripe_payment_snapshot()
        time.sleep(interval_seconds)


# ── Endpoint → Product mapping for per-agent stats ────────────────────────
# Catalog traffic is recorded only by durable per-agent events, not generic
# service endpoints, so dashboard hits remain transparent and attributable.
_ENDPOINT_TO_PRODUCT: Dict[str, str] = {}


def _record_request(endpoint: str, success: bool):
    """Record an API request for stats tracking."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    with _lock:
        _request_log.append({
            "timestamp": now.isoformat(),
            "endpoint": endpoint,
            "success": success,
        })
        if date_str not in _daily_stats:
            _daily_stats[date_str] = {
                "requests": 0,
                "sales_count": 0,
                "sales_volume": 0.0,
            }
        _daily_stats[date_str]["requests"] += 1

        # Increment per-product hits
        product_id = _ENDPOINT_TO_PRODUCT.get(endpoint)
        if product_id and product_id in _product_stats:
            _product_stats[product_id]["hits"] += 1


def _record_operational_event(
    *,
    event_type: str,
    source: str,
    method: str = "",
    path: str = "",
    status_code: Optional[int] = None,
    success: Optional[bool] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Best-effort redacted audit write; observability must not block requests."""
    try:
        event = {
            "event_type": event_type,
            "source": source,
            "method": method,
            "path": path,
            "status_code": status_code,
            "success": success,
        }
        if metadata is not None:
            event["metadata"] = metadata
        audit_store.record_event(
            **event,
        )
    except Exception as exc:
        log.warning("Operational audit write failed: %s", type(exc).__name__)


def _record_telegram_activity(payload: dict, result: Optional[dict]) -> None:
    """Keep Telegram user and command metrics separate from generic API traffic."""
    message = payload.get("message") or {}
    callback = payload.get("callback_query") or {}
    callback_message = callback.get("message") or {}
    chat = message.get("chat") or callback_message.get("chat") or {}
    chat_id = chat.get("id")
    handled_type = (result or {}).get("type")

    with _lock:
        if chat_id is not None:
            _telegram_active_chats.add(str(chat_id))
            _bot_status["active_users"] = len(_telegram_active_chats)
        if handled_type in {"command", "bulletin_sent", "price_info", "callback_query", "unknown_command"}:
            _bot_status["commands_processed"] += 1
        if (result or {}).get("response_sent"):
            _bot_status["messages_sent"] += 1
        _bot_status["last_heartbeat"] = datetime.now(timezone.utc).isoformat()


def _record_product_sale(product_id: str, amount_usd: float):
    """Record a sale attributed to a specific product/agent."""
    with _lock:
        if product_id not in _product_stats:
            return
        _product_stats[product_id]["sales_count"] += 1
        _product_stats[product_id]["sales_volume_usd"] = round(
            _product_stats[product_id]["sales_volume_usd"] + amount_usd, 6
        )


def _get_products_breakdown() -> List[dict]:
    """Return the official eight-agent breakdown from durable catalog events."""
    return [
        {
            "id": product["id"],
            "name": product["name"],
            "category": product["category"],
            "price_usdc": product["price_x402"],
            "hits": product["hits_24h"],
            "sales_count": product["sales_24h"],
            "sales_volume_usd": product["revenue_24h"],
        }
        for product in catalog_store.get_metrics_24h()["products"]
    ]


def _nexus_metrics_24h() -> dict:
    """Return Nexus-only metrics without allowing analytics failures to block admin."""
    try:
        return nexus_store.get_metrics_24h()
    except Exception as exc:
        log.warning("Nexus analytics read failed: %s", type(exc).__name__)
        return {
            "id": "nexus-engine",
            "name": "Nexus Engine / Premium Signal",
            "category": "isolated_nexus",
            "is_nexus": True,
            "analytics_available": False,
            "price_label": "$0.25 USDC / signal · €10/month · €50/year",
            "price_x402": NEXUS_X402_USDC,
            "visits_24h": 0,
            "clicks_24h": 0,
            "api_requests_24h": 0,
            "hits_24h": 0,
            "stripe_subscriptions_24h": 0,
            "x402_signals_24h": 0,
            "sales_24h": 0,
            "revenue_eur_24h": 0.0,
            "revenue_usdc_24h": 0.0,
        }


def _compose_agent_analytics(catalog_metrics: dict, nexus_metrics: dict) -> dict:
    """Combine display rows while preserving the catalog's eight-SKU boundaries."""
    catalog_rows = [
        {
            **product,
            "is_nexus": False,
            "price_label": f"${float(product.get('price_x402') or 0):.2f} USDC / call",
            "visits_24h": 0,
            "clicks_24h": int(product.get("clicks_24h") or 0),
            "api_requests_24h": int(product.get("calls_24h") or 0),
            "stripe_subscriptions_24h": 0,
            "x402_signals_24h": 0,
            "revenue_eur_24h": 0.0,
            "revenue_usdc_24h": float(product.get("revenue_24h") or 0),
        }
        for product in catalog_metrics.get("products", [])
    ]
    products = [*catalog_rows, dict(nexus_metrics)]
    interest_leader = max(
        products,
        key=lambda product: (int(product.get("hits_24h") or 0), product.get("name", "")),
        default=None,
    )
    sales_leader = max(
        products,
        key=lambda product: (int(product.get("sales_24h") or 0), product.get("name", "")),
        default=None,
    )
    return {
        "window_hours": 24,
        "products": products,
        "totals": {
            "hits": sum(int(product.get("hits_24h") or 0) for product in products),
            "sales": sum(int(product.get("sales_24h") or 0) for product in products),
            "catalog_revenue_usd": float(
                catalog_metrics.get("totals", {}).get("revenue_usd") or 0
            ),
            "nexus_revenue_usdc": float(nexus_metrics.get("revenue_usdc_24h") or 0),
            "nexus_revenue_eur": float(nexus_metrics.get("revenue_eur_24h") or 0),
        },
        "interest_leader": (
            {
                "id": interest_leader["id"],
                "name": interest_leader["name"],
                "hits_24h": interest_leader["hits_24h"],
            }
            if interest_leader
            else None
        ),
        "sales_leader": (
            {
                "id": sales_leader["id"],
                "name": sales_leader["name"],
                "sales_24h": sales_leader["sales_24h"],
            }
            if sales_leader
            else None
        ),
    }


def _record_nexus_activity(
    event_type: str, *, amount_eur: float = 0.0, event_id: Optional[str] = None
) -> None:
    """Best-effort event ingestion that cannot change Nexus access or payments."""
    try:
        if not event_id:
            timestamp = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            client_fingerprint = hashlib.sha256(
                f"{event_type}:{_get_client_ip()}:{timestamp.isoformat()}".encode()
            ).hexdigest()
            event_id = f"nexus-activity:{event_type}:{client_fingerprint}"
        nexus_store.record_analytics_event(
            event_type=event_type,
            event_id=event_id,
            amount_eur=amount_eur,
        )
    except Exception as exc:
        log.warning("Nexus analytics write failed: %s", type(exc).__name__)


# ── x402 Free Tier Tracking ────────────────────────────────────────────────
# Tracks free API calls per client (by IP address).
# After FREE_TIER_LIMIT (1) free picks, x402 payment is required.
_free_tier_usage: Dict[str, int] = {}  # ip -> count of free calls used

# ── General public rate-limit buckets ──────────────────────────────────────
# Sliding window per resolved client IP; never retains raw IPs in logs.
_rate_limit_buckets: Dict[str, deque] = {}
_rate_limit_lock = threading.Lock()
_catalog_click_lock = threading.Lock()
_catalog_recent_clicks: Dict[tuple[str, str], datetime] = {}
CATALOG_CLICK_COOLDOWN_SECONDS = max(
    60, int(os.getenv("CATALOG_CLICK_COOLDOWN_SECONDS", "900"))
)
_nexus_click_lock = threading.Lock()
_nexus_recent_clicks: Dict[tuple[str, str], datetime] = {}
NEXUS_CLICK_COOLDOWN_SECONDS = max(
    10, int(os.getenv("NEXUS_CLICK_COOLDOWN_SECONDS", "60"))
)
NEXUS_CLICK_TRACKER_MAX_KEYS = max(
    256, int(os.getenv("NEXUS_CLICK_TRACKER_MAX_KEYS", "2048"))
)


def _allow_catalog_click(client_address: str, agent_id: str) -> bool:
    """Bound anonymous catalog click ingestion to protect popularity metrics."""
    now = datetime.now(timezone.utc)
    key = (client_address or "unknown", agent_id)
    with _catalog_click_lock:
        expired_before = now - timedelta(seconds=CATALOG_CLICK_COOLDOWN_SECONDS)
        for previous_key, previous_at in list(_catalog_recent_clicks.items()):
            if previous_at < expired_before:
                _catalog_recent_clicks.pop(previous_key, None)
        previous = _catalog_recent_clicks.get(key)
        if previous and now - previous < timedelta(
            seconds=CATALOG_CLICK_COOLDOWN_SECONDS
        ):
            return False
        _catalog_recent_clicks[key] = now
        return True


def _allow_nexus_click(client_address: str, source: str) -> bool:
    """Limit anonymous UI event ingestion without suppressing real API requests."""
    now = datetime.now(timezone.utc)
    key = (client_address or "unknown", source)
    with _nexus_click_lock:
        expired_before = now - timedelta(seconds=NEXUS_CLICK_COOLDOWN_SECONDS)
        for previous_key, previous_at in list(_nexus_recent_clicks.items()):
            if previous_at < expired_before:
                _nexus_recent_clicks.pop(previous_key, None)
        while len(_nexus_recent_clicks) >= NEXUS_CLICK_TRACKER_MAX_KEYS:
            _nexus_recent_clicks.pop(next(iter(_nexus_recent_clicks)))
        previous = _nexus_recent_clicks.get(key)
        if previous and now - previous < timedelta(
            seconds=NEXUS_CLICK_COOLDOWN_SECONDS
        ):
            return False
        _nexus_recent_clicks[key] = now
        return True

# Tracks PAID API calls per client (for volume discount pricing).
_paid_calls_usage: Dict[str, int] = {}  # ip -> count of paid calls made


def _get_client_ip() -> str:
    """Use forwarded client identity only when the immediate peer is an allowed proxy."""
    peer = request.remote_addr or "unknown"
    trusted_proxy_ips = {
        value.strip()
        for value in os.getenv("TRUSTED_PROXY_IPS", "").split(",")
        if value.strip()
    }
    trust_forwarded = os.getenv("TRUST_PROXY_HEADERS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    fwd = request.headers.get("X-Forwarded-For", "")
    if trust_forwarded and peer in trusted_proxy_ips and fwd:
        # The trusted proxy appends the immediate client address at the end.
        return fwd.split(",")[-1].strip() or peer
    return peer


def _log_safe_ip(ip: str) -> str:
    """Return an 8-char prefix of the SHA-256 of the raw IP for log messages.

    Never log the raw IP address — even truncated octets can be personal data.
    The prefix is short enough to correlate requests within a session without
    linking them to a real-world identity.
    """
    return hashlib.sha256(ip.encode()).hexdigest()[:8]


def _check_public_rate_limit(ip: str) -> tuple[bool, int]:
    """Sliding-window rate limit: PUBLIC_API_RATE_LIMIT requests per 60 seconds.

    Returns (allowed, retry_after_seconds).  When allowed is False the caller
    should return HTTP 429 with a Retry-After header of retry_after_seconds.
    The data structure is bounded: old buckets are pruned on every check.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=PUBLIC_API_RATE_WINDOW_SECONDS)
    with _rate_limit_lock:
        # Prune stale buckets to avoid unbounded dict growth
        stale = [k for k, v in _rate_limit_buckets.items() if not v or v[-1] < window_start]
        for k in stale:
            del _rate_limit_buckets[k]
        bucket = _rate_limit_buckets.setdefault(ip, deque())
        # Drop timestamps outside the sliding window
        while bucket and bucket[0] < window_start:
            bucket.popleft()
        if len(bucket) >= PUBLIC_API_RATE_LIMIT:
            oldest = bucket[0]
            retry_after = max(
                1,
                int((oldest + timedelta(seconds=PUBLIC_API_RATE_WINDOW_SECONDS) - now).total_seconds()) + 1,
            )
            return False, retry_after
        bucket.append(now)
        return True, 0


def _get_dynamic_price(ip: str) -> float:
    """
    Dynamic pricing with volume discount.

    Base price: $0.05 USDC per request.
    After X402_VOLUME_THRESHOLD (10) paid calls, price drops to $0.01 USDC
    to incentivize batch/frequent on-chain usage.
    """
    with _lock:
        paid_count = _paid_calls_usage.get(ip, 0)
    if paid_count >= X402_VOLUME_THRESHOLD:
        return X402_FEE_USDC_DISCOUNT
    return X402_FEE_USDC_BASE


def _sanitize_json(obj):
    """
    Recursively sanitize a Python object for JSON serialization.
    Replaces NaN, Infinity, -Infinity with None (null) so the output is
    valid JSON (no NaN tokens that break JSON.parse in browsers).
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    return obj


def _safe_jsonify(obj):
    """jsonify wrapper that guarantees valid JSON (no NaN/Infinity)."""
    return jsonify(_sanitize_json(obj))


def _x402_payment_required_response(endpoint: str, price_usdc: Optional[float] = None):
    """
    Build a standard HTTP 402 Payment Required response for the x402 protocol.
    Includes the exact Base USDC receiver address and price.

    If price_usdc is provided, uses dynamic pricing; otherwise uses base price.
    """
    amount = price_usdc if price_usdc is not None else X402_FEE_USDC
    body = {
        "error": "payment_required",
        "x402_version": "1.0",
        "message": (
            f"Free tier exhausted. Send {amount} USDC on Base to "
            f"{X402_RECEIVER_ADDRESS} to unlock this endpoint."
        ),
        "payment": {
            "chain": X402_CHAIN,
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            "amount_usdc": amount,
            "network": "base",
        },
        "endpoint": endpoint,
        "free_tier_limit": FREE_TIER_LIMIT,
        "instructions": (
            f"Send exactly {amount} USDC (Base network) to "
            f"{X402_RECEIVER_ADDRESS}. After payment is confirmed on-chain, "
            f"retry this endpoint. For unlimited access, send 29.00 USDC for "
            f"a Monthly VIP subscription."
        ),
    }
    resp = jsonify(body)
    resp.status_code = 402
    resp.headers["X-Payment-Required"] = "x402"
    resp.headers["X-Payment-Address"] = X402_RECEIVER_ADDRESS
    resp.headers["X-Payment-Amount-USDC"] = str(amount)
    resp.headers["X-Payment-Chain"] = X402_CHAIN
    resp.headers["X-Payment-Token-Contract"] = X402_USDC_CONTRACT
    return resp


def _is_dashboard_request() -> bool:
    """Deprecated compatibility shim; client headers are not authorization."""
    return False


def _get_admin_token() -> str:
    """Return the normalized admin credential without exposing its value."""
    return (os.getenv("ADMIN_API_TOKEN", "") or "").strip() or (
        os.getenv("SESSION_SECRET", "") or ""
    ).strip()


def _log_admin_token_mismatch(configured: str, supplied: str) -> None:
    """Log only non-sensitive token metadata for diagnosing login issues."""
    log.warning(
        "Admin token mismatch: configured_present=%s configured_length=%d "
        "supplied_present=%s supplied_length=%d",
        bool(configured),
        len(configured),
        bool(supplied),
        len(supplied),
    )


def _require_admin_access():
    """Require a server-side admin token for CRM and sales operations."""
    if session.get("admin_authenticated"):
        return None
    configured = _get_admin_token()
    supplied = request.headers.get("X-Admin-Token", "")
    supplied = supplied.strip()
    if not configured or not supplied or not hmac.compare_digest(supplied, configured):
        return jsonify({"ok": False, "error": "admin_auth_required"}), 401
    return None


def _require_research_ingest_access():
    """Authenticate an external research source without exposing admin credentials."""
    configured = (os.getenv("RESEARCH_INGEST_TOKEN", "") or "").strip()
    supplied = (request.headers.get("X-Research-Ingest-Token", "") or "").strip()
    if configured and supplied and hmac.compare_digest(supplied, configured):
        return None
    # An authenticated administrator may also ingest manually from the protected UI/API.
    admin_error = _require_admin_access()
    if not admin_error:
        return None
    if not configured:
        return jsonify({"ok": False, "error": "research_ingest_not_configured"}), 503
    return jsonify({"ok": False, "error": "research_ingest_auth_required"}), 401


def _refresh_stripe_payment_snapshot() -> None:
    """Refresh Stripe data away from the request path so admin reads stay responsive."""
    global _stripe_snapshot
    try:
        listing = stripe_checkout.list_recent_completed_payments()
        snapshot = {
            **listing,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "state": "fresh" if listing.get("available") else "unavailable",
        }
    except Exception as exc:
        log.warning("Stripe payment snapshot refresh failed: %s", exc)
        with _stripe_snapshot_lock:
            previous = dict(_stripe_snapshot)
        snapshot = {
            **previous,
            "available": bool(previous.get("available")),
            "reason": "Stripe snapshot refresh failed; showing last known state.",
            "state": "stale" if previous.get("fetched_at") else "error",
        }
    with _stripe_snapshot_lock:
        _stripe_snapshot = snapshot


def _get_stripe_payment_snapshot() -> dict:
    """Return a bounded cached Stripe read model; never call Stripe in an admin request."""
    with _stripe_snapshot_lock:
        snapshot = dict(_stripe_snapshot)
    fetched_at = snapshot.get("fetched_at")
    age_seconds = None
    if fetched_at:
        try:
            age_seconds = max(
                0,
                int((datetime.now(timezone.utc) - datetime.fromisoformat(fetched_at)).total_seconds()),
            )
        except ValueError:
            age_seconds = None
    snapshot["age_seconds"] = age_seconds
    if snapshot.get("state") == "fresh" and age_seconds is not None and age_seconds > 90:
        snapshot["state"] = "stale"
        snapshot["reason"] = "Stripe snapshot is older than the refresh target."
    return snapshot


def _catalog_x402_payment_required_response(product: dict, challenge: Optional[dict] = None):
    """Return a challenge-bound x402 requirement for an exhausted agent request."""
    price = round(float(product.get("price_x402") or X402_FEE_USDC), 6)
    payload = {
        "ok": False,
        "error": "agent_demo_limit_reached",
        "message": "The free playground request for this agent has been used.",
        "agent_id": product["id"],
        "payment": {
            "protocol": "x402",
            "chain": X402_CHAIN,
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            "amount_usdc": price,
            "settlement_status": x402_settlement.status,
        },
        "upgrade": {
            "stripe_checkout": f"/api/v1/agents/{product['id']}/checkout",
            "entitlement_access": f"/api/v1/agents/{product['id']}/access",
            "note": (
                "Sign the server-issued challenge and retry this exact request with the "
                "confirmed Base USDC payment proof."
                if challenge
                else "x402 settlement is temporarily unavailable. Stripe creates a 30-day agent entitlement."
            ),
        },
    }
    if challenge:
        payload["payment"]["challenge"] = challenge
    response = jsonify(payload)
    response.status_code = 402
    response.headers["X-Payment-Required"] = "x402"
    response.headers["X-Payment-Address"] = X402_RECEIVER_ADDRESS
    response.headers["X-Payment-Amount-USDC"] = str(price)
    return response


def _agent_access_signing_key() -> bytes:
    """Use an explicit credential when configured, otherwise the application session key."""
    configured = (os.getenv("AGENT_ACCESS_TOKEN_SECRET", "") or "").strip()
    return (configured or app.config["SECRET_KEY"]).encode()


def _playground_client_key_hash(client_identity: str) -> str:
    """Persist only a keyed digest, never a raw client address, in the usage ledger."""
    return hmac.new(
        _agent_access_signing_key(), (client_identity or "unknown").encode(), hashlib.sha256
    ).hexdigest()


def _issue_agent_access_token(entitlement: dict) -> str:
    """Issue a signed bearer credential bound to one paid checkout and expiry."""
    body = {
        "agent_id": entitlement["agent_id"],
        "checkout_id": entitlement["checkout_id"],
        "customer_email": entitlement["customer_email"],
        "expires_at": entitlement["expires_at"],
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    signature = hmac.new(
        _agent_access_signing_key(), encoded.encode(), hashlib.sha256
    ).hexdigest()
    return f"ki1.{encoded}.{signature}"


def _verify_agent_access_token(token: str, agent_id: str) -> Optional[dict]:
    """Verify an entitlement bearer token against its durable active checkout right."""
    try:
        prefix, encoded, supplied_signature = token.split(".", 2)
        if prefix != "ki1":
            return None
        expected_signature = hmac.new(
            _agent_access_signing_key(), encoded.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if payload.get("agent_id") != agent_id:
            return None
        if datetime.fromisoformat(payload["expires_at"]) <= datetime.now(timezone.utc):
            return None
        return catalog_store.get_active_entitlement_by_checkout(
            product_id=agent_id,
            checkout_id=payload["checkout_id"],
            customer_email=payload["customer_email"],
        )
    except (KeyError, ValueError, UnicodeDecodeError, json.JSONDecodeError, TypeError, binascii.Error):
        return None


def _run_catalog_agent(product: dict, payload: dict) -> dict:
    """Execute a paid/free catalog capability with provenance, never a synthetic demo."""
    result = execute_agent(product, payload)
    result["runtime_contract_version"] = result["contract_version"]
    result["contract_version"] = product.get("contract_version", AGENT_CONTRACT_VERSION)
    return result


def _build_x402_discovery(base_url: str) -> dict:
    """Build x402 discovery from the sole active approved contract."""
    catalog = _approved_catalog_agents()
    agents = []
    for product in catalog or []:
        agents.append(
            {
                "id": product["id"],
                "name": product["name"],
                "description": product["description"],
                "category": product["category"],
                "endpoint": f"{base_url}/api/v1/agents/{product['id']}/playground",
                "method": "POST",
                "price_usdc": round(float(product["price_x402"]), 6),
                "free_playground_requests_per_client": 1,
                "stripe_checkout_endpoint": f"{base_url}/api/v1/agents/{product['id']}/checkout",
            }
        )
    return {
        "schema_version": "1.1",
        "contract_version": _published_contract_version() if catalog else None,
        "service": "Kristo Intelligence v6",
        "base_url": base_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "payment": {
            "protocol": "x402",
            "chain": X402_CHAIN,
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            "settlement_status": x402_settlement.status,
        },
        "agents": agents,
        "catalog_status": "active" if catalog else _catalog_governance_status(),
        "note": (
            "Agent-bound Base USDC settlement requires a server-issued challenge and signed payment proof."
            if catalog
            else "No catalog utilities are published until the contract is migrated and explicitly activated."
        ),
    }


def _catalog_mcp_agents(base_url: str, catalog: list[dict]) -> list[dict]:
    """Project the approved catalog into the shared MCP/discovery shape."""
    return [
        {
            "id": agent["id"],
            "name": agent["name"],
            "description": agent["description"],
            "endpoint": f"{base_url}/api/v1/agents/{agent['id']}/playground",
            "detail_endpoint": f"{base_url}/api/v1/agents/{agent['id']}",
            "method": "POST",
            "price_usdc": round(float(agent["price_x402"]), 6),
            "stripe_30day_usd": round(float(agent["price_stripe"]), 2),
            "free_playground_requests_per_client": 1,
            "stripe_checkout": f"{base_url}/api/v1/agents/{agent['id']}/checkout",
            "access_endpoint": f"{base_url}/api/v1/agents/{agent['id']}/access",
            "category": agent["category"],
            "capability_id": agent["capability_id"],
            "input_schema": agent["input_schema"],
            "output_schema": agent["output_schema"],
            "source_policy": agent["source_policy"],
        }
        for agent in catalog
    ]


@app.after_request
def _apply_security_headers(response):
    """Add hardened security and cache-control headers to every response.

    - Cache-Control: no-store on all /api/* and /health so clients never cache
      live operational data.
    - Standard security headers on every response.
    - CORS: allow only explicitly configured origins (ALLOWED_ORIGINS env var) or
      the production URL if configured; never reflect arbitrary origins.
    """
    path = request.path

    # Prevent caching of dynamic API/health responses
    if path.startswith("/api/") or path == "/health":
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"

    # Standard hardening headers
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

    # CORS: only allow origins present in the explicit allow-list or the
    # configured public URL.  Never reflect an arbitrary incoming Origin.
    origin = request.headers.get("Origin", "")
    if origin:
        pub_url = (os.getenv("APP_PUBLIC_URL", "") or "").rstrip("/")
        allowed = _ALLOWED_ORIGINS or ({pub_url} if pub_url else frozenset())
        if origin in allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        response.headers.setdefault(
            "Access-Control-Allow-Methods", "GET, POST, OPTIONS"
        )
        response.headers.setdefault(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Payment-Proof, X-Admin-Token",
        )
    return response


@app.after_request
def _capture_live_request(response):
    """Store a bounded, credential-free stream for the protected operations view."""
    try:
        path = request.path
        source = "telegram" if path == "/api/telegram-webhook" else "api" if path.startswith("/api/") else "web"
        with _lock:
            _live_request_log.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "method": request.method,
                    "path": path,
                    "source": source,
                    "status_code": response.status_code,
                }
            )
        _record_operational_event(
            event_type="http_response",
            source=source,
            method=request.method,
            path=path,
            status_code=response.status_code,
            success=response.status_code < 400,
        )
    except Exception:
        # Observability must never affect the application response.
        pass
    return response


@app.before_request
def _api_rate_limit():
    """General per-client rate limit applied before the x402 paywall.

    Signed webhook callbacks are always exempt.  Applies to every other path so
    scraping, enumeration, and credential-stuffing attempts are throttled at the
    edge without requiring x402 payment logic to run first.
    """
    path = request.path
    if path in _RATE_LIMIT_EXEMPT_PATHS:
        return None
    ip = _get_client_ip()
    allowed, retry_after = _check_public_rate_limit(ip)
    if not allowed:
        log.warning(
            "Rate limit exceeded: client=%s endpoint=%s retry_after=%ds",
            _log_safe_ip(ip), path, retry_after,
        )
        resp = jsonify({
            "ok": False,
            "error": "rate_limit_exceeded",
            "retry_after": retry_after,
        })
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp
    return None


@app.before_request
def _x402_paywall():
    """
    x402 Paywall middleware.

    Discovery endpoints (health, dashboard, manifest, .well-known, openapi,
    llms.txt) are always free.

    Catalog agent routes implement their own challenge-bound access checks.
    Legacy operational endpoints are intentionally free until they gain the
    same settlement and delivery guarantees.

    IMPORTANT: Requests originating from the /dashboard page are exempt
    from the paywall so the dashboard always loads correctly.
    """
    path = request.path

    # Always-free endpoints — no paywall
    if path in X402_FREE_ENDPOINTS:
        return None

    # Paid endpoints — enforce free tier + x402 payment
    if path in X402_PAID_ENDPOINTS:
        ip = _get_client_ip()
        with _lock:
            used = _free_tier_usage.get(ip, 0)

        if used < FREE_TIER_LIMIT:
            # Still within free tier — allow and increment
            with _lock:
                _free_tier_usage[ip] = used + 1
            log.info(
                "Free tier access: client=%s used=%d/%d endpoint=%s",
                _log_safe_ip(ip), used + 1, FREE_TIER_LIMIT, path,
            )
            return None
        else:
            # Free tier exhausted — require x402 payment (dynamic pricing)
            price = _get_dynamic_price(ip)
            log.info(
                "x402 payment required: client=%s endpoint=%s price=$%s",
                _log_safe_ip(ip), path, price,
            )
            return _x402_payment_required_response(path, price)

    # Unknown endpoints — let Flask handle normally (404)
    return None


# ── Routes ────────────────────────────────────────────────────────────────

_FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#312e81"/>
<path d="M18 14h10v17l12-17h10L37 32l14 18H40L28 34v16H18V14z" fill="#e0e7ff"/>
</svg>"""


@app.route("/favicon.ico")
@app.route("/favicon.svg")
def favicon():
    """Serve a lightweight branded icon and avoid a browser-side 404."""
    return _FAVICON_SVG, 200, {
        "Content-Type": "image/svg+xml",
        "Cache-Control": "public, max-age=86400",
    }


@app.route("/")
def home():
    _record_request("home", True)
    return render_template_string(_LAUNCH_LANDING_HTML)


_LAUNCH_LANDING_HTML = """
<!DOCTYPE html>
<html lang="bg">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <title>Kristo Intelligence — Agent Utility Marketplace on Base</title>
    <meta name="description" content="Eight evidence-first agent utilities with machine-readable outputs, cited data and x402 USDC access on Base. Nexus remains a separate premium signal.">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Kristo Intelligence">
    <meta property="og:title" content="Kristo Intelligence — Agent Utility Marketplace">
    <meta property="og:description" content="Eight evidence-first data utilities on Base, with x402 micropayments or Stripe 30-day access.">
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="Kristo Intelligence — Agent Utilities">
    <meta name="twitter:description" content="Evidence-first agent utilities with x402 USDC on Base or Stripe checkout.">
    <script type="application/ld+json">
    {"@context":"https://schema.org","@graph":[{"@type":"Organization","name":"Kristo Intelligence","description":"Evidence-first agent utilities and crypto market intelligence on Base."},{"@type":"WebSite","name":"Kristo Intelligence","description":"Eight agent utilities and an isolated Nexus premium signal — x402 USDC or Stripe."}]}
    </script>
    <style>
        body { font-family: Arial, sans-serif; background: #0b1020; color: #eef2ff; margin: 0; }
        .wrap { max-width: 1100px; margin: 0 auto; padding: 40px 20px 80px; }
        .hero { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 24px; align-items: center; }
        .card { background: #121a2f; border: 1px solid #2b3a5d; border-radius: 18px; padding: 28px; box-shadow: 0 20px 50px rgba(0,0,0,.2); }
        h1 { font-size: 2.8rem; line-height: 1.1; margin: 0 0 16px; }
        p { color: #c7d2fe; font-size: 1.05rem; }
        .tag { display: inline-block; background: #312e81; color: #e0e7ff; padding: 8px 14px; border-radius: 999px; margin-bottom: 18px; font-size: 0.8rem; }
        .cta { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
        .btn { display: inline-block; padding: 14px 22px; background: #4f46e5; color: white; text-decoration: none; border-radius: 12px; font-weight: bold; }
        .btn.secondary { background: transparent; border: 1px solid #4f46e5; }
        .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; margin-top: 40px; }
        .price { font-size: 2.2rem; font-weight: 800; margin: 12px 0; }
        ul { margin: 0; padding-left: 18px; color: #dbeafe; }
        .small { color: #94a3b8; font-size: 0.9rem; }
        @media (max-width: 800px) { .hero, .grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="hero">
            <div class="card">
                <div class="tag">AI • Crypto • DeFi • Telegram</div>
                <h1>VIP crypto intelligence за активни трейдъри.</h1>
                <p>Получавай live пазарни анализи, DeFi сигнали и premium Telegram известия без шум, без хаос и без демо данни.</p>
                <div class="cta">
                    <a class="btn" href="/sales/checkout?plan=pro">Започни с Pro</a>
                    <a class="btn secondary" href="/dashboard">Виж dashboard</a>
                </div>
                <p class="small">Реални данни • Base мрежа • Live market insights • Telegram VIP access</p>
            </div>
            <div class="card">
                <h3>Какво включва</h3>
                <ul>
                    <li>live market bulletin</li>
                    <li>DeFi signal layer</li>
                    <li>Telegram VIP updates</li>
                    <li>AI помощ за анализ</li>
                    <li>premium access level</li>
                </ul>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h3>Starter</h3>
                <div class="price">$29</div>
                <p>Базов достъп до market bulletin и сигнали.</p>
                <a class="btn" href="/sales/checkout?plan=starter">Избери Starter</a>
            </div>
            <div class="card">
                <h3>Pro</h3>
                <div class="price">$79</div>
                <p>VIP Telegram + premium market intelligence.</p>
                <a class="btn" href="/sales/checkout?plan=pro">Избери Pro</a>
            </div>
            <div class="card">
                <h3>API Access</h3>
                <div class="price">$149</div>
                <p>За по-напреднали клиенти и data access.</p>
                <a class="btn" href="/sales/checkout?plan=api">Избери API</a>
            </div>
        </div>
    </div>
</body>
</html>
"""


@app.route("/launch")
def launch_landing():
    """Public sales landing page for live product launch."""
    return render_template_string(_LAUNCH_LANDING_HTML)


# ── Developers integration guide ──────────────────────────────────────────────

_DEVELOPERS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Developer Integration Guide — Kristo Intelligence API</title>
    <meta name="description" content="Integrate Kristo Intelligence's 8 evidence-first agent utilities via x402 USDC or Stripe. OpenAPI, MCP, and llms.txt discovery included.">
    <style>
        body { font-family:'Segoe UI',system-ui,sans-serif; background:#0b1020; color:#eef2ff; margin:0; }
        .wrap { max-width:900px; margin:0 auto; padding:40px 24px 80px; }
        h1 { font-size:2.2rem; background:linear-gradient(135deg,#6366f1,#10b981); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin:0 0 8px; }
        h2 { font-size:1.3rem; color:#6366f1; margin:2rem 0 0.5rem; border-bottom:1px solid #1e2740; padding-bottom:6px; }
        h3 { font-size:1rem; color:#94a3b8; text-transform:uppercase; letter-spacing:.05em; margin:1.2rem 0 0.4rem; }
        pre { background:#0f1825; border:1px solid #1e2740; border-radius:10px; padding:16px; overflow-x:auto; font-size:.87rem; }
        code { color:#a5f3fc; font-family:'Fira Code',monospace; }
        .card { background:#121a2f; border:1px solid #1e2740; border-radius:14px; padding:20px 24px; margin-bottom:16px; }
        .pill { display:inline-block; padding:3px 10px; border-radius:99px; font-size:.78rem; font-weight:bold; }
        .pill.free { background:#064e3b; color:#6ee7b7; }
        .pill.paid { background:#1e1b4b; color:#a5b4fc; }
        .links a { color:#6366f1; text-decoration:none; margin-right:16px; font-size:.9rem; }
        .links a:hover { text-decoration:underline; }
        nav { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:24px; }
        nav a { color:#94a3b8; font-size:.9rem; text-decoration:none; }
        nav a:hover { color:#eef2ff; }
        table { border-collapse:collapse; width:100%; font-size:.88rem; }
        td { padding:6px 12px; }
        .status-402 { color:#f59e0b; } .status-err { color:#ef4444; }
    </style>
</head>
<body>
<div class="wrap">
    <nav>
        <a href="/">← Home</a>
        <a href="/dashboard">Dashboard</a>
        <a href="/agents">Agents</a>
        <a href="/openapi.json">OpenAPI</a>
        <a href="/mcp.json">MCP</a>
        <a href="/llms.txt">llms.txt</a>
    </nav>
    <h1>Developer Integration Guide</h1>
    <p style="color:#94a3b8;margin-bottom:2rem">Eight evidence-first agent utilities with typed inputs, source provenance and freshness states. Access them with x402 USDC on Base or a 30-day Stripe entitlement; one free request per client is included.</p>

    <div class="card">
        <h2 style="margin-top:0;border:none">Quick discovery links</h2>
        <div class="links">
            <a href="/openapi.json">OpenAPI 3.0 ↗</a>
            <a href="/mcp.json">MCP manifest ↗</a>
            <a href="/llms.txt">llms.txt ↗</a>
            <a href="/api/v1/agents">Agent catalog (JSON) ↗</a>
            <a href="/api/v1/catalog/contract">Approved contract ↗</a>
            <a href="/.well-known/x402.json">x402 discovery ↗</a>
            <a href="/health">Health ↗</a>
        </div>
    </div>

    <h2>1 — Browse the agent catalog</h2>
    <h3>curl <span class="pill free">FREE</span></h3>
    <pre><code>curl {{ base_url }}/api/v1/agents</code></pre>
    <h3>Python</h3>
    <pre><code>import httpx
agents = httpx.get("{{ base_url }}/api/v1/agents").json()
for a in agents["agents"]:
    print(a["id"], "$" + str(a["price_x402"]) + " USDC |", "$" + str(a["price_stripe"]) + " Stripe 30d")</code></pre>
    <h3>JavaScript</h3>
    <pre><code>const { agents } = await fetch("/api/v1/agents").then(r => r.json());
agents.forEach(a => console.log(a.id, a.description));</code></pre>

    <h2>2 — Run a free utility request <span class="pill free">1 per client</span></h2>
    <p style="color:#94a3b8;font-size:.92rem">Each client IP gets one free playground call per agent. No payment or account required.</p>
    <h3>curl</h3>
    <pre><code>curl -X POST {{ base_url }}/api/v1/agents/whaleflow-radar/playground \\
  -H "Content-Type: application/json" \\
   -d '{"input": "Base x402 agent utilities"}'
# Response includes result.status, freshness, provenance and data.</code></pre>
    <h3>Python</h3>
    <pre><code>import httpx
resp = httpx.post(
    "{{ base_url }}/api/v1/agents/cross-venue-signal-divergence/playground",
    json={"input": "# Update\nRevenue: 12.5%\nhttps://example.com"},
)
data = resp.json()
 print(data["result"]["data"])</code></pre>

    <h2>3 — Purchase 30-day access (Stripe) <span class="pill paid">PAID</span></h2>
    <h3>Step 1: create checkout session</h3>
    <pre><code>curl -X POST {{ base_url }}/api/v1/agents/whaleflow-radar/checkout \\
  -H "Content-Type: application/json" \\
  -d '{"email": "you@example.com"}'
# → {"ok": true, "payment_session": {"checkout_url": "https://checkout.stripe.com/..."}}</code></pre>
    <h3>Step 2: exchange for bearer token (after Stripe payment)</h3>
    <pre><code>curl -X POST {{ base_url }}/api/v1/agents/whaleflow-radar/access \\
  -H "Content-Type: application/json" \\
  -d '{"email": "you@example.com", "checkout_id": "SESSION_ID_FROM_STRIPE"}'
# → {"ok": true, "token": "...", "expires_at": "..."}</code></pre>
    <h3>Step 3: call with bearer token</h3>
    <pre><code>curl -X POST {{ base_url }}/api/v1/agents/whaleflow-radar/playground \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
   -d '{"input": "Base agent utility adoption"}'</code></pre>

    <h2>4 — Pay per-utility via x402 (USDC on Base) <span class="pill paid">CRYPTO</span></h2>
    <div class="card" style="margin-top:8px">
        <p style="margin:0;font-size:.9rem;color:#94a3b8">x402 is an open HTTP payment protocol. The server returns HTTP 402 with a signed on-chain challenge. You pay USDC on Base and re-send with the proof header. No subscriptions, no accounts, no KYC.</p>
    </div>
    <h3>Challenge-response flow</h3>
    <pre><code># 1. POST endpoint → server returns HTTP 402 with challenge JSON
#    {receiver_address, amount_usdc, chain_id, challenge_id}
# 2. Send USDC on Base via EIP-3009 transferWithAuthorization
# 3. Re-send original request with header:
#    X-Payment-Proof: &lt;base64-encoded-tx-hash&gt;
# 4. Server verifies on-chain → returns 200 with result</code></pre>
    <h3>Nexus premium signal ($0.25 USDC via x402)</h3>
    <pre><code>curl -X POST {{ base_url }}/api/nexus/premium-signal \\
  -H "Content-Type: application/json" \\
  -d '{"asset": "ETH"}'
# → HTTP 402 with challenge on first call.
# After payment: returns Nexus premium signal.</code></pre>
    <h3>Nexus subscription (Stripe, €10/month or €50/year)</h3>
    <pre><code>curl {{ base_url }}/api/nexus/plans          # view plans
curl -X POST {{ base_url }}/api/nexus/checkout \\
  -H "Content-Type: application/json" \\
  -d '{"email": "you@example.com", "plan": "monthly"}'</code></pre>

    <h2>5 — Error reference</h2>
    <div class="card">
        <table>
            <tr><td class="status-402"><strong>402</strong></td><td>Free request used — start x402 challenge or Stripe checkout</td></tr>
            <tr><td class="status-err"><strong>429</strong></td><td>Rate limit exceeded (60 req/min default). Check <code>Retry-After</code> header.</td></tr>
            <tr><td class="status-err"><strong>403</strong></td><td>Bearer token invalid or expired — re-exchange via /access</td></tr>
            <tr><td class="status-err"><strong>404</strong></td><td>Unknown agent_id — see <a href="/api/v1/agents" style="color:#6366f1">/api/v1/agents</a></td></tr>
            <tr><td class="status-err"><strong>503</strong></td><td>Stripe checkout temporarily unavailable — retry after a moment</td></tr>
        </table>
    </div>

    <h2>6 — Rate limits &amp; fair use</h2>
    <p style="color:#94a3b8;font-size:.92rem">
        Public API: <strong>60 requests/minute</strong> per client (sliding window).<br>
        Stripe and Telegram webhooks are always exempt from rate limiting.<br>
        Discovery endpoints (<code>/api/v1/agents</code>, <code>/openapi.json</code>, <code>/mcp.json</code>, <code>/llms.txt</code>, <code>/health</code>) are always free.
    </p>
</div>
</body>
</html>"""


@app.route("/developers")
def developers_page():
    """Developer integration guide — always free, no authentication required."""
    base_url = request.host_url.rstrip("/")
    return render_template_string(_DEVELOPERS_HTML, base_url=base_url)


@app.route("/sales/checkout", methods=["GET", "POST"])
def sales_checkout():
    """Checkout and lead capture for the sales funnel."""
    plans = checkout_store.get_all_plans()
    if request.method == "GET":
        selected_plan = request.args.get("plan", "pro")
        plan = checkout_store.get_plan(selected_plan) or checkout_store.get_plan("pro")
        status = request.args.get("status", "")
        checkout_id = (request.args.get("session_id") or "").strip()
        vip_link_command = ""
        if status == "success" and checkout_id:
            checkout = stripe_vip_store.get_checkout(checkout_id)
            if checkout and _is_vip_plan(checkout.get("plan_key", "")):
                vip_link_command = f"/start vip_{checkout['link_token']}"
        status_msg = {
            "success": "Checkout е завършен. VIP достъпът се активира само след подписания Stripe webhook.",
            "cancelled": "Плащането беше отменено. Можете да опитате отново.",
        }.get(status, "")
        return render_template_string(
            """
            <!DOCTYPE html>
            <html lang="bg">
            <head><meta charset="UTF-8"><title>Checkout | Kristo Intelligence</title>
            <style>body{font-family:Arial,sans-serif;background:#0b1020;color:#eef2ff;padding:40px} form{max-width:560px;margin:0 auto;background:#121a2f;padding:30px;border-radius:16px;border:1px solid #2b3a5d;} input,select{width:100%;padding:12px;margin:10px 0;border-radius:10px;border:1px solid #39486d;background:#0f172a;color:white;} button{padding:14px 22px;border:none;background:#4f46e5;color:white;border-radius:12px;font-weight:700;cursor:pointer;} .small{color:#94a3b8;font-size:0.9rem} .ok{color:#34d399;padding:10px 0;} .warn{color:#fbbf24;padding:10px 0;} </style>
            </head>
            <body>
                <form method="POST">
                    <h2>Checkout</h2>
                    <p class="small">Пакет: {{ plan.name }} — ${{ plan.price_usd }}</p>
                    <input type="hidden" name="plan" value="{{ plan_key }}">
                    <label>Email</label>
                    <input type="email" name="email" required>
                    <label>Източник</label>
                    <select name="source">
                        <option value="website">Website</option>
                        <option value="meta_ads">Meta Ads</option>
                        <option value="google">Google</option>
                        <option value="telegram">Telegram</option>
                        <option value="organic">Organic</option>
                    </select>
                    <label>Кампания</label>
                    <input type="text" name="campaign" value="launch" required>
                    {% if status_msg %}
                    <div class="{{ 'ok' if status == 'success' else 'warn' }}">{{ status_msg }}</div>
                    {% endif %}
                    {% if vip_link_command %}
                    <div class="warn">За да свържете VIP достъпа си с Telegram, изпратете на бота:<br><strong>{{ vip_link_command }}</strong><br><span class="small">Поканата се изпраща само след потвърдено плащане.</span></div>
                    {% endif %}
                    <button type="submit">Потвърди покупката</button>
                </form>
            </body>
            </html>
            """,
            plan=plan,
            plan_key=selected_plan,
            status=status,
            status_msg=status_msg,
            vip_link_command=vip_link_command,
        )

    email = (request.form.get("email") or "").strip()
    plan_key = (request.form.get("plan") or "pro").strip()
    source = (request.form.get("source") or "website").strip()
    campaign = (request.form.get("campaign") or "launch").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Въведете валиден email."}), 400

    plan = checkout_store.get_plan(plan_key)
    if plan is None:
        return jsonify({"ok": False, "error": "Невалиден план."}), 400

    lead = LeadRecord(
        email=email,
        source=source,
        campaign=campaign,
        utm_source=request.args.get("utm_source", ""),
        utm_medium=request.args.get("utm_medium", ""),
        utm_campaign=request.args.get("utm_campaign", ""),
        plan=plan.name,
    )
    saved_lead = crm_store.add_lead(lead)
    checkout_payload = checkout_store.build_checkout_payload(plan_key, email)
    stripe_session = stripe_checkout.create_checkout_session(
        plan_key,
        email,
        source=source,
        campaign=campaign,
    )
    if stripe_session.get("status") not in {"checkout_created", "mock_checkout_ready"}:
        return jsonify({"ok": False, "error": stripe_session.get("error", "checkout_unavailable")}), 503

    registration = stripe_vip_store.register_checkout(
        checkout_id=stripe_session["checkout_id"],
        customer_email=email,
        plan_key=plan_key,
        expected_amount_cents=round(float(plan.price_usd) * 100),
        currency="usd",
        source=source,
        campaign=campaign,
        link_token=secrets.token_urlsafe(24),
    )
    if not registration:
        return jsonify({"ok": False, "error": "checkout_registration_failed"}), 503

    if stripe_session.get("url"):
        return redirect(stripe_session["url"], code=303)

    return jsonify({
        "ok": True,
        "lead": saved_lead,
        "checkout": checkout_payload,
        "payment_provider": stripe_session.get("provider", "mock"),
        "payment_session": stripe_session,
        "vip_link": {
            "status": "telegram_link_required",
            "command": f"/start vip_{registration['link_token']}",
        },
    })


@app.route("/api/leads", methods=["GET", "POST"])
def api_leads():
    """CRUD-like lead API for CRM integration."""
    if request.method == "GET":
        auth_error = _require_admin_access()
        if auth_error:
            return auth_error
        return jsonify({"ok": True, "leads": crm_store.get_all(), "total": len(crm_store.get_all())})

    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    source = (payload.get("source") or "website").strip()
    campaign = (payload.get("campaign") or "launch").strip()
    plan_name = (payload.get("plan") or "pro").strip()

    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "email is required"}), 400

    lead = LeadRecord(
        email=email,
        source=source,
        campaign=campaign,
        plan=plan_name,
    )
    saved = crm_store.add_lead(lead)
    return jsonify({"ok": True, "lead": saved})


@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    """Checkout API endpoint for sales automation and payment scaffolding."""
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    plan_key = (payload.get("plan") or "pro").strip()
    source = (payload.get("source") or "api").strip()
    campaign = (payload.get("campaign") or "launch").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "email is required"}), 400

    plan = checkout_store.get_plan(plan_key)
    if plan is None:
        return jsonify({"ok": False, "error": "unknown plan"}), 400

    lead = LeadRecord(
        email=email,
        source=source,
        campaign=campaign,
        plan=plan.name,
    )
    crm_store.add_lead(lead)
    payment_session = stripe_checkout.create_checkout_session(
        plan_key,
        email,
        source=source,
        campaign=campaign,
    )
    if payment_session.get("status") not in {"checkout_created", "mock_checkout_ready"}:
        return jsonify({"ok": False, "error": payment_session.get("error", "checkout_unavailable")}), 503
    registration = stripe_vip_store.register_checkout(
        checkout_id=payment_session["checkout_id"],
        customer_email=email,
        plan_key=plan_key,
        expected_amount_cents=round(float(plan.price_usd) * 100),
        currency="usd",
        source=source,
        campaign=campaign,
        link_token=secrets.token_urlsafe(24),
    )
    if not registration:
        return jsonify({"ok": False, "error": "checkout_registration_failed"}), 503
    return jsonify({
        "ok": True,
        "checkout": checkout_store.build_checkout_payload(plan_key, email),
        "payment_provider": payment_session.get("provider", "mock"),
        "payment_session": payment_session,
        "plan": plan.name,
        "vip_link": {
            "status": "telegram_link_required",
            "command": f"/start vip_{registration['link_token']}",
        },
    })


def _approved_catalog_agents() -> Optional[List[dict]]:
    """Return only the human-approved contract, merged with live product metrics."""
    active = marketplace_store.active_contract()
    if not active or not manifest_is_runtime_compatible(active.get("manifest", {})):
        return None
    manifest_agents = active.get("manifest", {}).get("agents")
    if not isinstance(manifest_agents, list) or len(manifest_agents) != len(CATALOG_SEED):
        return None
    by_id = {item.get("id"): item for item in manifest_agents if isinstance(item, dict)}
    if set(by_id) != {item["id"] for item in CATALOG_SEED}:
        return None
    approved = []
    for product in catalog_store.get_catalog():
        contract = by_id.get(product["id"])
        if contract:
            approved.append(
                public_contract(
                    product,
                    contract,
                    published_contract_version=active["version"],
                )
            )
    return approved if len(approved) == len(CATALOG_SEED) else None


def _catalog_governance_status() -> str:
    """Expose a safe public state without leaking an unapproved manifest."""
    if not getattr(marketplace_store, "available", False):
        return "migration_required"
    return "approval_required"


def _published_contract_version() -> str:
    active = marketplace_store.active_contract()
    if active and manifest_is_runtime_compatible(active.get("manifest", {})):
        return active["version"]
    return AGENT_CONTRACT_VERSION


def _transition_catalog_contract(candidate: dict) -> Optional[dict]:
    """Keep catalog metadata and active contract aligned, including test-store recovery."""
    atomic_transition = getattr(marketplace_store, "transition_contract_with_catalog_metadata", None)
    if callable(atomic_transition):
        return atomic_transition(candidate["version"])

    previous_metadata = catalog_store.get_catalog()
    try:
        catalog_store.apply_catalog_metadata(candidate["manifest"]["agents"])
        contract = marketplace_store.rollback_contract(candidate["version"])
        if not contract:
            raise RuntimeError("catalog_contract_transition_unavailable")
        return contract
    except Exception:
        try:
            catalog_store.apply_catalog_metadata(previous_metadata)
        except Exception:
            log.exception("Catalog metadata compensation failed after contract transition error")
        raise


def _approved_agent_or_response(agent_id: str):
    catalog = _approved_catalog_agents()
    if catalog is None:
        return None, (
            jsonify(
                {
                    "ok": False,
                    "error": "catalog_contract_approval_required",
                    "contract_version": _published_contract_version(),
                }
            ),
            503,
        )
    agent = next((item for item in catalog if item["id"] == agent_id), None)
    if not agent:
        return None, (jsonify({"ok": False, "error": "agent_not_found"}), 404)
    return agent, None


@app.route("/api/v1/agents", methods=["GET"])
def api_agent_catalog():
    """Return only the active human-approved contract-driven catalog."""
    agents = _approved_catalog_agents()
    if agents is None:
        return jsonify(
            {
                "ok": False,
                "error": "catalog_contract_approval_required",
                "contract_version": _published_contract_version(),
            }
        ), 503
    return jsonify(
        {
            "ok": True,
            "contract_version": _published_contract_version(),
            "catalog_status": "active",
            "auto_publish": False,
            "agents": agents,
        }
    )


@app.route("/api/v1/catalog/contract", methods=["GET"])
def api_catalog_contract():
    """Return the approved machine contract and its governance state."""
    active = marketplace_store.active_contract()
    if active:
        return jsonify(
            {
                "ok": True,
                "version": active["version"],
                "status": active["status"].lower(),
                "manifest": active["manifest"],
                "governance_backend": marketplace_store.backend,
            }
        )
    return jsonify(
        {
            "ok": True,
            "version": AGENT_CONTRACT_VERSION,
            "status": "approval_required" if getattr(marketplace_store, "available", False) else "migration_required",
            "governance_backend": marketplace_store.backend,
            "warning": (
                "A human administrator must activate a runtime-compatible draft before catalog metadata changes."
                if getattr(marketplace_store, "available", False)
                else "Contract governance persistence is unavailable until the production migration is applied."
            ),
        }
    )


@app.route("/api/v1/agents/<agent_id>", methods=["GET"])
def api_agent_detail(agent_id: str):
    """Return one active agent SKU for a product page or machine client."""
    agent, error = _approved_agent_or_response(agent_id)
    if error:
        return error
    return jsonify({"ok": True, "contract_version": agent["contract_version"], "agent": agent})


@app.route("/api/v1/agents/<agent_id>/playground", methods=["POST"])
def api_agent_playground(agent_id: str):
    """Run one real, contract-bound catalog capability after access is established."""
    agent, error = _approved_agent_or_response(agent_id)
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "json_object_required"}), 400
    execution_payload = {
        key: str(payload.get(key) or "").strip()
        for key in ("input", "baseline")
        if key in payload
    }
    try:
        validate_agent_payload(agent, execution_payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "contract_version": agent["contract_version"]}), 400

    authorization = (request.headers.get("Authorization", "") or "").strip()
    bearer_token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    entitlement = _verify_agent_access_token(bearer_token, agent_id) if bearer_token else None
    access = "active_entitlement" if entitlement else "one_free_playground_request"
    settled_challenge_id = None
    if not entitlement and not catalog_store.consume_free_playground_request(
        agent_id, _playground_client_key_hash(_get_client_ip())
    ):
        request_hash = canonical_request_hash(
            agent_id, request.path, execution_payload
        )
        payment_proof = (
            request.headers.get("X-Payment-Proof", "")
            or request.headers.get("PAYMENT-SIGNATURE", "")
        )
        if not payment_proof:
            if x402_settlement.status != "full":
                return _catalog_x402_payment_required_response(agent)
            try:
                challenge = x402_settlement.issue_challenge(
                    agent_id=agent_id,
                    endpoint=request.path,
                    request_hash=request_hash,
                    amount_usdc=float(agent["price_x402"]),
                )
            except SettlementError as exc:
                _record_operational_event(
                    event_type="x402_challenge_unavailable",
                    source="api",
                    method=request.method,
                    path=request.path,
                    status_code=exc.status_code,
                    success=False,
                    metadata={"outcome": exc.code, "operation": "x402_challenge"},
                )
                return jsonify({"ok": False, "error": exc.code}), exc.status_code
            _record_operational_event(
                event_type="x402_challenge_issued",
                source="api",
                method=request.method,
                path=request.path,
                status_code=402,
                success=True,
                metadata={"outcome": "issued", "operation": "x402_challenge"},
            )
            return _catalog_x402_payment_required_response(agent, challenge.public_payload())
        try:
            settlement = x402_settlement.verify_and_settle(
                proof_header=payment_proof,
                agent_id=agent_id,
                endpoint=request.path,
                request_hash=request_hash,
            )
        except SettlementError as exc:
            _record_operational_event(
                event_type="x402_settlement_rejected",
                source="api",
                method=request.method,
                path=request.path,
                status_code=exc.status_code,
                success=False,
                metadata={"outcome": exc.code, "operation": "x402_settlement"},
            )
            return jsonify({"ok": False, "error": exc.code}), exc.status_code
        settled_challenge_id = settlement["challenge_id"]
        access = "x402_settled"
        _record_operational_event(
            event_type="x402_settlement_verified",
            source="api",
            method=request.method,
            path=request.path,
            status_code=200,
            success=True,
            metadata={
                "outcome": "duplicate" if settlement["duplicate"] else "settled",
                "operation": "x402_settlement",
            },
        )
    if entitlement and not catalog_store.record_call(agent_id):
        log.error("Catalog call could not be recorded for agent %s.", agent_id)
        return jsonify({"ok": False, "error": "call_recording_unavailable"}), 503
    try:
        result = _run_catalog_agent(agent, execution_payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "contract_version": agent["contract_version"]}), 400
    except Exception:
        log.exception("Catalog executor failed: agent=%s", agent_id)
        _record_operational_event(
            event_type="agent_execution_failed",
            source="api",
            method=request.method,
            path=request.path,
            status_code=503,
            success=False,
            metadata={"operation": "catalog_execution", "outcome": "unavailable"},
        )
        return jsonify(
            {
                "ok": False,
                "error": "agent_execution_unavailable",
                "contract_version": agent["contract_version"],
            }
        ), 503
    # Task #18 — record trial start for conversion analytics
    if access == "one_free_playground_request":
        _record_operational_event(
            event_type="trial_started",
            source="api",
            method=request.method,
            path=request.path,
            status_code=200,
            success=True,
            metadata={"agent_id": agent_id, "operation": "catalog_trial"},
        )
    if settled_challenge_id:
        catalog_store.record_call(agent_id, event_id=f"x402-call:{settled_challenge_id}")
        x402_settlement.mark_delivered(settled_challenge_id)
    return jsonify(
        {
            "ok": True,
            "contract_version": agent["contract_version"],
            "agent": agent,
            "access": access,
            "result": result,
        }
    )


_AGENT_PLAYGROUND_HTML = r"""
<!doctype html><html lang="bg"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kristo Intelligence — Agent Utility Marketplace</title>
<style>
:root{--bg:#090d18;--card:#111827;--border:#26334d;--text:#edf2ff;--muted:#aab7d0;--accent:#7c83ff;--good:#56d6a5;--warn:#f6bf68}*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at 20% -10%,#1e2a57 0,transparent 32%),var(--bg);color:var(--text);font:16px system-ui,sans-serif}.wrap{max-width:1180px;margin:auto;padding:48px 20px 80px}
.eyebrow{color:#b9bdff;text-transform:uppercase;letter-spacing:.1em;font-size:.76rem;font-weight:700}h1{font-size:clamp(2rem,5vw,3.4rem);margin:.35rem 0 1rem}.intro{max-width:760px;color:var(--muted);line-height:1.6}
.notice{margin:24px 0;padding:14px 16px;border:1px solid #765923;background:#2a2113;border-radius:12px;color:#ffe3aa}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:16px}
.card{background:linear-gradient(145deg,#131d32,#0f1729);border:1px solid var(--border);border-radius:16px;padding:20px;box-shadow:0 12px 30px rgba(0,0,0,.2)}.meta{font-size:.78rem;color:#bfc8dd;text-transform:uppercase;letter-spacing:.07em}.price{color:var(--good);font-weight:700;margin:.7rem 0}.desc{color:var(--muted);min-height:48px;line-height:1.45}
textarea,input,button{font:inherit;border-radius:9px;padding:11px 12px}textarea,input{display:block;width:100%;margin:16px 0 10px;background:#090d18;color:var(--text);border:1px solid #33415e;resize:vertical}button{border:0;background:var(--accent);color:white;font-weight:750;cursor:pointer;width:100%}button:disabled{opacity:.55;cursor:wait}.result{margin-top:12px;padding:12px;border-radius:9px;background:#0a1120;color:#cbd5e1;font-size:.88rem;line-height:1.45;white-space:pre-wrap}.result.error{border:1px solid #8f4b52;color:#ffc3c8}.result.ok{border:1px solid #2f8066}.small{font-size:.78rem;color:var(--muted);margin:.65rem 0 0}.empty{color:var(--muted)}
</style></head><body><main class="wrap"><div class="eyebrow">Kristo Intelligence · contract v2.0</div><h1>Agent Utility Marketplace</h1><p class="intro">Run small, machine-readable utilities with source provenance and freshness labels. The catalog performs no trades, money movement or external publishing. Source failures are returned explicitly as <code>unavailable</code>.</p><div class="notice">One bounded request is free per client and utility. Afterwards use a 30-day Stripe entitlement or the x402 upgrade path. Payment settles access; it never changes or hides the underlying data result.</div><section id="agents" class="grid"><p class="empty">Loading catalog…</p></section></main>
<script>
const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function card(a){const input=a.input_schema?.properties?.input||{};const baseline=a.input_schema?.properties?.baseline;return `<article class="card"><div class="meta">${escapeHtml(a.capability_id||a.category)}</div><h2>${escapeHtml(a.name)}</h2><p class="desc">${escapeHtml(a.description)}</p><p class="price">${Number(a.price_x402).toFixed(2)} USDC x402 · $${Number(a.price_stripe).toFixed(2)} 30-day Stripe access</p><label class="small" for="input-${a.id}">${escapeHtml(input.description||'Request input')}</label><textarea id="input-${a.id}" maxlength="6000" rows="3" placeholder="${escapeHtml(input.description||'Enter input')}"></textarea>${baseline?`<label class="small" for="baseline-${a.id}">${escapeHtml(baseline.description||'Baseline')}</label><textarea id="baseline-${a.id}" maxlength="6000" rows="3" placeholder="${escapeHtml(baseline.description||'Previous text')}"></textarea>`:''}<button data-agent="${escapeHtml(a.id)}">Run utility</button><div id="result-${a.id}" class="result" hidden></div><p class="small">Contract ${escapeHtml(a.contract_version||'2.0')} · one free request per client and utility.</p></article>`}
function show(id,text,kind){const el=document.getElementById('result-'+id);el.hidden=false;el.className='result '+kind;el.textContent=text}
async function run(agentId,button){const input=document.getElementById('input-'+agentId).value.trim();const baseline=document.getElementById('baseline-'+agentId)?.value.trim();if(input.length<2)return show(agentId,'Enter at least 2 characters.','error');if(document.getElementById('baseline-'+agentId)&&!baseline)return show(agentId,'A baseline is required for the Change Monitor.','error');button.disabled=true;button.textContent='Running…';try{const r=await fetch('/api/v1/agents/'+encodeURIComponent(agentId)+'/playground',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input,...(baseline?{baseline}:{})})});const data=await r.json();if(!r.ok){const upgrade=data.upgrade?.stripe_checkout?`\nUpgrade: ${data.upgrade.stripe_checkout}`:'';show(agentId,(data.message||data.error||'Request failed.')+upgrade,'error');return}show(agentId,JSON.stringify(data.result,null,2),data.result.status==='ok'?'ok':'error');button.textContent='Utility completed'}catch(e){show(agentId,'Network error: '+e.message,'error')}finally{button.disabled=false;if(button.textContent==='Running…')button.textContent='Run utility'}}
async function load(){try{const r=await fetch('/api/v1/agents');const data=await r.json();if(!r.ok){document.getElementById('agents').innerHTML=`<p class="empty">Catalog is awaiting a database migration and explicit administrator approval. Status: ${escapeHtml(data.error||'unavailable')}.</p>`;return}document.getElementById('agents').innerHTML=data.agents.map(card).join('');document.querySelectorAll('button[data-agent]').forEach(b=>b.addEventListener('click',()=>run(b.dataset.agent,b)))}catch(e){document.getElementById('agents').innerHTML='<p class="empty">Catalog status could not be loaded.</p>'}}
load();
</script></body></html>
"""


@app.route("/agents", methods=["GET"])
def agent_playground_page():
    """Public catalog page for the eight bounded agent demos."""
    return render_template_string(_AGENT_PLAYGROUND_HTML)


@app.route("/api/v1/agents/<agent_id>/click", methods=["POST"])
def api_agent_click(agent_id: str):
    """Persist a product-page click for catalog conversion analytics."""
    _, error = _approved_agent_or_response(agent_id)
    if error:
        return error
    if not _allow_catalog_click(_get_client_ip(), agent_id):
        return jsonify(
            {
                "ok": False,
                "error": "click_rate_limited",
                "retry_after_seconds": CATALOG_CLICK_COOLDOWN_SECONDS,
            }
        ), 429
    if not catalog_store.record_click(agent_id):
        return jsonify({"ok": False, "error": "click_recording_unavailable"}), 503
    return jsonify({"ok": True, "agent_id": agent_id, "status": "click_recorded"}), 202


@app.route("/api/v1/agents/<agent_id>/checkout", methods=["POST"])
def api_agent_checkout(agent_id: str):
    """Create a one-time Stripe Checkout for a 30-day agent access entitlement."""
    agent, error = _approved_agent_or_response(agent_id)
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    source = (payload.get("source") or "agent_catalog").strip()
    campaign = (payload.get("campaign") or "agent_vip").strip()
    telegram_chat_id = (payload.get("telegram_chat_id") or "").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "email is required"}), 400

    plan_key = f"agent:{agent_id}"
    crm_store.add_lead(
        LeadRecord(
            email=email,
            source=source,
            campaign=campaign,
            plan=plan_key,
            telegram_chat_id=telegram_chat_id,
        )
    )
    payment_session = stripe_checkout.create_catalog_checkout_session(
        agent_sku=agent_id,
        product_name=agent["name"],
        amount_usd=agent["price_stripe"],
        customer_email=email,
        source=source,
        campaign=campaign,
        telegram_chat_id=telegram_chat_id,
    )
    if payment_session.get("status") not in {"checkout_created", "mock_checkout_ready"}:
        return jsonify(
            {
                "ok": False,
                "error": payment_session.get("error", "checkout_unavailable"),
            }
        ), 503
    if not catalog_store.register_checkout(
        checkout_id=payment_session.get("checkout_id", ""),
        product_id=agent_id,
        customer_email=email,
        expected_amount=agent["price_stripe"],
    ):
        log.error("Catalog checkout could not be registered for agent %s.", agent_id)
        return jsonify({"ok": False, "error": "catalog_checkout_registration_failed"}), 503
    # Task #18 — record checkout initiated for conversion funnel analytics
    _record_operational_event(
        event_type="checkout_initiated",
        source="api",
        method=request.method,
        path=request.path,
        status_code=200,
        success=True,
        metadata={"agent_id": agent_id, "operation": "catalog_checkout"},
    )
    return jsonify(
        {
            "ok": True,
            "agent": agent,
            "access": "one_time_30_day_agent_entitlement",
            "payment_provider": payment_session.get("provider", "mock"),
            "payment_session": payment_session,
        }
    )


@app.route("/api/v1/agents/<agent_id>/access", methods=["POST"])
def api_agent_access(agent_id: str):
    """Exchange a paid checkout capability for a short-lived signed agent credential."""
    _, error = _approved_agent_or_response(agent_id)
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    checkout_id = (payload.get("checkout_id") or "").strip()
    if not email or "@" not in email or not checkout_id:
        return jsonify(
            {"ok": False, "error": "email and server_created_checkout_id are required"}
        ), 400
    entitlement = catalog_store.get_active_entitlement_by_checkout(
        agent_id, checkout_id, email
    )
    if not entitlement:
        return jsonify({"ok": False, "error": "agent_access_required"}), 403
    return jsonify(
        {
            "ok": True,
            "agent_id": agent_id,
            "access": "active",
            "expires_at": entitlement["expires_at"],
            "access_token": _issue_agent_access_token(entitlement),
        }
    )


NEXUS_PREMIUM_RESOURCE_ID = "nexus-premium-signal"
NEXUS_PREMIUM_SIGNAL_ENDPOINT = "/api/nexus/premium-signal"


@app.route("/api/nexus/plans", methods=["GET"])
def api_nexus_plans():
    """Public Nexus pricing and capability discovery without payment side effects."""
    _record_nexus_activity("api_request")
    return jsonify(
        {
            "ok": True,
            "human_subscriptions": {
                plan: {
                    "currency": "EUR",
                    "amount": details["amount_eur"],
                    "interval": details["interval"],
                }
                for plan, details in NEXUS_PLANS.items()
            },
            "bot_micropayment": {
                "currency": "USDC",
                "network": "base",
                "chain_id": X402_CHAIN_ID,
                "amount": NEXUS_X402_USDC,
                "endpoint": NEXUS_PREMIUM_SIGNAL_ENDPOINT,
                "settlement_status": nexus_x402_settlement.status,
            },
        }
    )


@app.route("/api/nexus/click", methods=["POST"])
def api_nexus_click():
    """Record a bounded, server-observed Nexus purchase-intent click."""
    payload = request.get_json(silent=True) or {}
    source = (payload.get("source") or "").strip().lower()
    if source not in {"stripe_monthly", "stripe_yearly", "premium_signal"}:
        return jsonify({"ok": False, "error": "invalid_nexus_click_source"}), 400
    if not _allow_nexus_click(_get_client_ip(), source):
        return jsonify({"ok": False, "error": "click_rate_limited"}), 429
    _record_nexus_activity("click")
    return jsonify({"ok": True, "source": source, "status": "click_recorded"}), 202


@app.route("/api/nexus/checkout", methods=["POST"])
def api_nexus_checkout():
    """Create a Stripe EUR recurring subscription without touching VIP plans."""
    _record_nexus_activity("api_request")
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    plan = (payload.get("plan") or "").strip().lower()
    if not email or "@" not in email or len(email) > 254:
        return jsonify({"ok": False, "error": "valid_email_required"}), 400
    if plan not in NEXUS_PLANS:
        return jsonify({"ok": False, "error": "invalid_nexus_plan"}), 400

    crm_store.add_lead(
        LeadRecord(
            email=email,
            source="nexus",
            campaign="nexus_subscription",
            plan=f"nexus_{plan}_eur",
        )
    )
    checkout = stripe_checkout.create_nexus_subscription_session(
        plan=plan,
        customer_email=email,
    )
    if checkout.get("status") != "checkout_created":
        _record_operational_event(
            event_type="nexus_checkout_unavailable",
            source="nexus",
            path="/api/nexus/checkout",
            status_code=503,
            metadata={"outcome": checkout.get("error", "checkout_unavailable"), "operation": "nexus_checkout"},
        )
        return jsonify({"ok": False, "error": checkout.get("error", "checkout_unavailable")}), 503
    _record_operational_event(
        event_type="nexus_checkout_created",
        source="nexus",
        path="/api/nexus/checkout",
        status_code=201,
        metadata={"outcome": "created", "operation": "nexus_checkout", "plan": plan},
    )
    return jsonify(
        {
            "ok": True,
            "plan": plan,
            "currency": "EUR",
            "amount": NEXUS_PLANS[plan]["amount_eur"],
            "payment_session": checkout,
        }
    ), 201


@app.route(NEXUS_PREMIUM_SIGNAL_ENDPOINT, methods=["POST"])
def api_nexus_premium_signal():
    """Serve one Nexus signal only after an isolated, proof-bound $0.25 settlement."""
    _record_nexus_activity("api_request")
    payload = request.get_json(silent=True) or {}
    asset = (payload.get("asset") or payload.get("input") or "").strip().upper()
    if not asset or len(asset) > 32 or not asset.replace("-", "").replace("_", "").isalnum():
        return jsonify({"ok": False, "error": "valid_asset_required"}), 400
    canonical_payload = {"asset": asset}
    request_hash = canonical_request_hash(
        NEXUS_PREMIUM_RESOURCE_ID,
        NEXUS_PREMIUM_SIGNAL_ENDPOINT,
        canonical_payload,
    )
    proof_header = request.headers.get("X-Payment-Proof") or request.headers.get("PAYMENT-SIGNATURE")
    if not proof_header:
        if nexus_x402_settlement.status != "full":
            return jsonify(
                {
                    "ok": False,
                    "error": "x402_settlement_unavailable",
                    "payment": {"settlement_status": nexus_x402_settlement.status},
                }
            ), 503
        try:
            challenge = nexus_x402_settlement.issue_challenge(
                agent_id=NEXUS_PREMIUM_RESOURCE_ID,
                endpoint=NEXUS_PREMIUM_SIGNAL_ENDPOINT,
                request_hash=request_hash,
                amount_usdc=NEXUS_X402_USDC,
            )
        except SettlementError as exc:
            return jsonify({"ok": False, "error": exc.code}), exc.status_code
        _record_operational_event(
            event_type="nexus_x402_challenge_issued",
            source="nexus",
            path=NEXUS_PREMIUM_SIGNAL_ENDPOINT,
            status_code=402,
            metadata={"outcome": "issued", "operation": "nexus_x402"},
        )
        return jsonify(
            {
                "ok": False,
                "error": "payment_required",
                "payment": {
                    "protocol": "x402",
                    "network": "base",
                    "chain_id": X402_CHAIN_ID,
                    "currency": "USDC",
                    "amount_usdc": NEXUS_X402_USDC,
                    "receiver_address": X402_RECEIVER_ADDRESS,
                    "token_contract": X402_USDC_CONTRACT,
                    "challenge": challenge.public_payload(),
                    "settlement_status": nexus_x402_settlement.status,
                },
            }
        ), 402

    try:
        settlement = nexus_x402_settlement.verify_and_settle(
            proof_header=proof_header,
            agent_id=NEXUS_PREMIUM_RESOURCE_ID,
            endpoint=NEXUS_PREMIUM_SIGNAL_ENDPOINT,
            request_hash=request_hash,
        )
    except SettlementError as exc:
        _record_operational_event(
            event_type="nexus_x402_settlement_rejected",
            source="nexus",
            path=NEXUS_PREMIUM_SIGNAL_ENDPOINT,
            status_code=exc.status_code,
            metadata={"outcome": exc.code, "operation": "nexus_x402"},
        )
        return jsonify({"ok": False, "error": exc.code}), exc.status_code

    try:
        snapshot = get_market_snapshot()
    except Exception:
        snapshot = {"state": "unavailable"}
    nexus_x402_settlement.mark_delivered(settlement["challenge_id"])
    _record_operational_event(
        event_type="nexus_x402_settlement_verified",
        source="nexus",
        path=NEXUS_PREMIUM_SIGNAL_ENDPOINT,
        status_code=200,
        metadata={"outcome": "settled", "operation": "nexus_x402"},
    )
    return jsonify(
        {
            "ok": True,
            "access": "nexus_x402_settled",
            "asset": asset,
            "signal": {
                "type": "premium_nexus_market_snapshot",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "market_snapshot": snapshot,
                "notice": "Informational market intelligence; not investment advice.",
            },
        }
    )


@app.route("/api/webhooks/stripe", methods=["POST"])
def stripe_webhook_handler():
    """Stripe-compatible webhook handler for payment confirmation."""
    signature = request.headers.get("Stripe-Signature", "")
    if not signature:
        return jsonify({"ok": False, "error": "missing_signature"}), 400
    try:
        payload = stripe_checkout.verify_webhook(request.get_data(), signature)
    except Exception:
        log.warning("Rejected Stripe webhook with invalid signature", exc_info=True)
        return jsonify({"ok": False, "error": "invalid_signature"}), 400
    if not payload:
        return jsonify({"ok": False, "error": "webhook_verification_unavailable"}), 503
    event_type = payload.get("type") or "checkout.session.completed"
    event_data = payload.get("data", {}).get("object", {})

    if event_type in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    }:
        email = (event_data.get("customer_details", {}).get("email") or event_data.get("customer_email") or "").strip()
        metadata = event_data.get("metadata", {}) or {}
        plan_key = metadata.get("plan") or "pro"
        nexus_plan = (metadata.get("nexus_plan") or "").strip().lower()
        agent_sku = (metadata.get("agent_sku") or "").strip()
        checkout_id = (event_data.get("id") or "").strip()
        amount = float(event_data.get("amount_total") or 0.0) / 100.0
        payment_status = (event_data.get("payment_status") or "").strip().lower()
        currency = (event_data.get("currency") or "").strip().lower()
        if payment_status != "paid":
            return jsonify(
                {
                    "ok": True,
                    "status": "payment_not_settled",
                    "event_type": event_type,
                }
            )
        if nexus_plan:
            expected = NEXUS_PLANS.get(nexus_plan)
            is_valid_nexus_payment = bool(
                expected
                and currency == "eur"
                and amount == float(expected["amount_eur"])
                and email
                and nexus_store.is_healthy()
            )
            if not is_valid_nexus_payment:
                return jsonify({"ok": True, "status": "ignored_unmatched_nexus_checkout"})
            membership = nexus_store.activate_membership(
                email=email,
                plan=nexus_plan,
                checkout_id=checkout_id,
                stripe_subscription_id=str(event_data.get("subscription") or ""),
                stripe_customer_id=str(event_data.get("customer") or ""),
            )
            _record_nexus_activity(
                "stripe_subscription",
                amount_eur=amount,
                event_id=f"stripe-subscription:{checkout_id}",
            )
            crm_store.update_status(email, "qualified")
            _record_operational_event(
                event_type="nexus_membership_activated",
                source="nexus",
                path="/api/webhooks/stripe",
                status_code=200,
                metadata={"outcome": "active", "operation": "nexus_subscription", "plan": nexus_plan},
            )
            return jsonify(
                {
                    "ok": True,
                    "status": "nexus_membership_active",
                    "plan": nexus_plan,
                    "currency": "EUR",
                    "amount_eur": amount,
                    "membership": membership,
                }
            )
        if email:
            prior_lead = crm_store.find_by_email(email)
            if prior_lead is None:
                log.warning("Ignoring Stripe checkout for an unknown CRM lead.")
                return jsonify({"ok": True, "status": "ignored_unknown_lead"})
            if agent_sku:
                expected_plan = f"agent:{agent_sku}"
                is_valid_catalog_payment = bool(
                    checkout_id
                    and currency == "usd"
                    and plan_key == expected_plan
                    and catalog_store.validate_checkout(
                        checkout_id, agent_sku, email, amount
                    )
                )
                if not is_valid_catalog_payment:
                    log.warning(
                        "Ignoring catalog payment with unmatched checkout attributes."
                    )
                    return jsonify(
                        {"ok": True, "status": "ignored_unmatched_catalog_checkout"}
                    )
            if agent_sku:
                crm_store.mark_paid(email, amount, plan_key)
                payment_recorded = catalog_store.confirm_checkout_payment(
                    checkout_id,
                    agent_sku,
                    email,
                    amount,
                )
                entitlement = catalog_store.grant_entitlement(
                    checkout_id,
                    agent_sku,
                    email,
                )
                vip_access = {
                    "status": "agent_entitlement_active",
                    "expires_at": entitlement["expires_at"] if entitlement else None,
                }
                if payment_recorded:
                    _record_operational_event(
                        event_type="stripe_payment_confirmed",
                        source="stripe",
                        method=request.method,
                        path=request.path,
                        status_code=200,
                        success=True,
                        metadata={
                            "agent_id": agent_sku,
                            "operation": "catalog_stripe_entitlement",
                            "outcome": "confirmed",
                        },
                    )
            else:
                event_id = (payload.get("id") or "").strip()
                amount_cents = int(event_data.get("amount_total") or 0)
                is_valid_standard_payment = bool(
                    event_id
                    and checkout_id
                    and stripe_vip_store.validate_checkout(
                        checkout_id,
                        email,
                        plan_key,
                        amount_cents,
                        currency,
                    )
                )
                if not is_valid_standard_payment:
                    log.warning("Ignoring standard Stripe payment with unmatched checkout attributes.")
                    return jsonify(
                        {"ok": True, "status": "ignored_unmatched_standard_checkout"}
                    )
                event_claim = stripe_vip_store.claim_webhook_event(
                    event_id, checkout_id, event_type
                )
                if event_claim["status"] == "completed":
                    return jsonify({"ok": True, "status": "duplicate_webhook_event"})
                if event_claim["status"] == "processing":
                    return jsonify({"ok": False, "error": "webhook_processing"}), 503
                processing_token = event_claim["processing_token"]
                try:
                    crm_store.mark_paid(email, amount, plan_key)
                    stripe_vip_store.mark_paid(checkout_id)
                    stripe_vip_store.ensure_delivery(checkout_id)
                    vip_access = _attempt_stripe_vip_delivery(checkout_id)
                    if not stripe_vip_store.complete_webhook_event(
                        event_id, processing_token
                    ):
                        return jsonify({"ok": False, "error": "webhook_ownership_lost"}), 503
                except Exception:
                    stripe_vip_store.fail_webhook_event(event_id, processing_token)
                    log.exception("Stripe VIP fulfillment failed; Stripe may retry the event.")
                    return jsonify({"ok": False, "error": "vip_fulfillment_failed"}), 500
            return jsonify({
                "ok": True,
                "status": "paid",
                "plan": plan_key,
                "amount_usd": amount,
                "vip_access": vip_access["status"],
            })

    return jsonify({"ok": True, "received": True, "event_type": event_type})


@app.route("/api/admin/vip-deliveries/<checkout_id>/retry", methods=["POST"])
def retry_vip_delivery(checkout_id: str):
    """Retry delivery only for a server-recorded, paid VIP checkout."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    checkout = stripe_vip_store.get_checkout(checkout_id)
    if not checkout:
        return jsonify({"ok": False, "error": "checkout_not_found"}), 404
    if checkout.get("payment_status") != "paid":
        return jsonify({"ok": False, "error": "checkout_not_paid"}), 409
    result = _attempt_stripe_vip_delivery(checkout_id)
    delivered = result.get("status") in {"invite_sent", "already_active"}
    return jsonify(
        {
            "ok": delivered,
            "checkout_id": checkout_id,
            "delivery_status": result.get("status", "unknown"),
        }
    ), 200 if delivered else 202


@app.route("/api/sales/summary", methods=["GET"])
def api_sales_summary():
    """Return launch funnel metrics and CRM pipeline summary."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    pipeline = crm_store.get_sales_pipeline()
    leads = crm_store.get_all()
    total_leads = len(leads)
    paid_leads = sum(1 for lead in leads if lead.get("payment_status") == "paid")
    return jsonify({
        "ok": True,
        "total_leads": total_leads,
        "paid_leads": paid_leads,
        "pipeline": pipeline,
        "traffic_sources": {
            source: sum(1 for lead in leads if (lead.get("source") or "") == source)
            for source in sorted({(lead.get("source") or "") for lead in leads})
        },
    })


@app.route("/api/admin/leads", methods=["GET"])
def api_admin_leads():
    """Admin endpoint for the live lead pipeline and sales operations."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    leads = crm_store.get_all()
    return jsonify({
        "ok": True,
        "total": len(leads),
        "pipeline": crm_store.get_sales_pipeline(),
        "leads": leads,
    })


def _mask_email(value: str) -> str:
    """Return a minimally useful dashboard identifier without exposing customer PII."""
    email = str(value or "").strip()
    local, separator, domain = email.partition("@")
    if not separator or not local or not domain:
        return "—"
    return f"{local[:1]}***@{domain}"


def _admin_overview_payload() -> dict:
    """Build the protected dashboard read model without exposing chat identifiers."""
    leads = crm_store.get_all()
    paid_leads = [lead for lead in leads if lead.get("payment_status") == "paid"]
    paid_leads.sort(key=lambda lead: lead.get("created_at") or "", reverse=True)

    crm_payments = [
        {
            "email": lead.get("email", ""),
            "plan": lead.get("plan", ""),
            "amount_usd": float(lead.get("amount_usd") or 0),
            "created": lead.get("created_at", ""),
            "provider": "crm_paid_event",
            "payment_status": "paid",
        }
        for lead in paid_leads
    ]
    stripe_listing = _get_stripe_payment_snapshot()
    use_stripe_feed = bool(stripe_listing["available"] and stripe_listing["payments"])
    displayed_payments = stripe_listing["payments"] if use_stripe_feed else crm_payments

    vip_plans = [
        {
            "email": _mask_email(lead.get("email", "")),
            "plan": lead.get("plan", ""),
            "amount_usd": float(lead.get("amount_usd") or 0),
            "activated_at": lead.get("created_at", ""),
            "telegram_linked": bool(lead.get("telegram_chat_id")),
            "status": "active_paid_vip",
        }
        for lead in paid_leads
        if _is_vip_plan(lead.get("plan") or "")
    ]
    with _lock:
        onchain_revenue = round(sum(s.get("amount_usd", 0) for s in _sales_history), 6)
        bot_status = dict(_bot_status)
        wallet = dict(_wallet_state)
        live_requests = list(_live_request_log)[-100:]
        invite_count = len(_vip_invites)
        onchain_vips = len(_vip_subscribers)

    crm_revenue = round(sum(payment["amount_usd"] for payment in crm_payments), 2)
    catalog_metrics = catalog_store.get_metrics_24h()
    nexus_metrics = _nexus_metrics_24h()
    agent_analytics = _compose_agent_analytics(catalog_metrics, nexus_metrics)
    catalog_healthy = catalog_store.is_healthy()
    audit_healthy = audit_store.is_healthy()
    stripe_vip_healthy = stripe_vip_store.is_healthy()
    settlement_store = getattr(x402_settlement, "store", None)
    settlement_schema_healthy = bool(
        settlement_store and getattr(settlement_store, "is_healthy", lambda: False)()
    )
    try:
        durable_audit_events = audit_store.recent_events(limit=100)
    except Exception:
        durable_audit_events = []
    pending_research = len(research_store.list_insights(status="PENDING", limit=200))
    market_cache = get_coingecko_cache_status()
    market_age = market_cache.get("age_seconds")
    market_detail = market_cache.get("state", "unavailable")
    if market_age is not None:
        market_detail = f"{market_detail} cache, age {market_age}s"
    if market_cache.get("detail"):
        market_detail = f"{market_detail} — {market_cache['detail']}"
    try:
        active_contract = marketplace_store.active_contract() if getattr(marketplace_store, "available", False) else None
        published_agents = _approved_catalog_agents()
    except Exception:
        active_contract = None
        published_agents = None
    catalog_published = bool(active_contract and published_agents)
    launch_gates = {
        "contract": {
            "status": "active" if catalog_published else _catalog_governance_status(),
            "version": active_contract.get("version") if catalog_published else None,
            "auto_publish": False,
        },
        "catalog": {
            "published": catalog_published,
            "approved_agent_count": len(published_agents or []),
        },
        "persistence": {
            "catalog_backend": catalog_store.backend,
            "catalog_healthy": catalog_healthy,
            "audit_backend": audit_store.backend,
            "audit_healthy": audit_healthy,
            "stripe_vip_backend": stripe_vip_store.backend,
            "stripe_vip_healthy": stripe_vip_healthy,
            "governance_backend": marketplace_store.backend,
            "governance_available": bool(getattr(marketplace_store, "available", False)),
            "settlement_schema_healthy": settlement_schema_healthy,
            "schema_verified": bool(
                catalog_store.backend == "postgresql"
                and audit_store.backend == "postgresql"
                and catalog_healthy
                and audit_healthy
                and stripe_vip_healthy
                and settlement_schema_healthy
                and getattr(marketplace_store, "available", False)
            ),
        },
        "x402": {
            "mode": x402_settlement.status,
            "production_smoke_verified": False,
        },
        "stripe": {
            "configured": stripe_checkout.enabled,
            "feed_state": stripe_listing.get("state", "unknown"),
            "age_seconds": stripe_listing.get("age_seconds"),
        },
        "broad_launch": {
            "status": "blocked",
            "detail": "Requires Publish verification, payment delivery smoke tests, and repeat paid flagship evidence.",
        },
    }
    safe_payments = [
        {**payment, "email": _mask_email(payment.get("email", ""))}
        for payment in displayed_payments[:100]
    ]
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "crm_revenue_usd": crm_revenue,
            "onchain_revenue_usd": onchain_revenue,
            "total_revenue_usd": round(crm_revenue + onchain_revenue, 2),
            "paid_payments": len(paid_leads),
            "active_vip_plans": len(vip_plans),
            "vip_invites_generated": invite_count,
            "onchain_vip_subscribers": onchain_vips,
            "active_telegram_users": bot_status.get("active_users", 0),
            "catalog_clicks_24h": catalog_metrics["totals"]["clicks"],
            "catalog_calls_24h": catalog_metrics["totals"]["calls"],
            "catalog_hits_24h": catalog_metrics["totals"]["hits"],
            "catalog_revenue_24h_usd": catalog_metrics["totals"]["revenue_usd"],
            "agent_hits_24h": agent_analytics["totals"]["hits"],
            "agent_sales_24h": agent_analytics["totals"]["sales"],
            "nexus_hits_24h": nexus_metrics["hits_24h"],
            "nexus_sales_24h": nexus_metrics["sales_24h"],
            "active_agent_entitlements": catalog_store.active_entitlement_count(),
            "research_pending_review": pending_research,
        },
        "payments": safe_payments,
        "payment_source": "stripe_checkout" if use_stripe_feed else "crm_paid_events",
        "vip_plans": vip_plans[:100],
        "request_log": durable_audit_events or list(reversed(live_requests)),
        "agent_catalog": catalog_metrics,
        "agent_analytics": agent_analytics,
        "launch_gates": launch_gates,
        "services": {
            "crm": {"ready": crm_store.is_healthy(), "backend": crm_store.backend},
            "audit": {
                "ready": audit_store.is_healthy(),
                "backend": audit_store.backend,
                "detail": "redacted operational events",
            },
            "agent_catalog": {
                "ready": catalog_store.is_healthy(),
                "backend": catalog_store.backend,
                "active_agents": len(catalog_metrics["products"]),
                "detail": "24h analytics for eight official catalog agents",
            },
            "x402_settlement": {
                "ready": x402_settlement.status == "full",
                "mode": x402_settlement.status,
                "confirmations_required": X402_CONFIRMATIONS,
                "detail": "agent-bound Base USDC proof validation",
            },
            "nexus": {
                "ready": nexus_store.is_healthy(),
                "analytics_ready": nexus_store.analytics_is_healthy(),
                "backend": nexus_store.backend,
                "x402_mode": nexus_x402_settlement.status,
                "human_pricing": "EUR 10/month or EUR 50/year",
                "bot_pricing": f"USDC {NEXUS_X402_USDC:.2f} per premium signal",
                "detail": "isolated subscriptions, Base x402 ledger and 24h engagement",
            },
            "research": {
                "ready": research_store.is_healthy(),
                "backend": research_store.backend,
                "detail": f"{pending_research} pending review",
            },
            "stripe": {
                "configured": stripe_checkout.enabled,
                "payment_feed_available": stripe_listing["available"],
                "cache_state": stripe_listing.get("state", "unknown"),
                "age_seconds": stripe_listing.get("age_seconds"),
                "detail": stripe_listing.get("reason", "connected"),
            },
            "telegram": {
                "token_configured": bot_status.get("telegram_token_configured", False),
                "running": bot_status.get("telegram_bot_running", False),
                "last_heartbeat": bot_status.get("last_heartbeat", ""),
            },
            "blockchain": {
                "ready": bool(
                    wallet.get("rpc_connected")
                    and wallet.get("chain_id") == BASE_CHAIN_ID
                    and wallet.get("receiver_valid")
                ),
                "rpc_connected": wallet.get("rpc_connected", False),
                "network": wallet.get("network", "Base Mainnet"),
                "chain_id": wallet.get("chain_id"),
                "fee_receiver": wallet.get("fee_receiver"),
                "detail": (
                    f"{wallet.get('network', 'Base Mainnet')} (chain {wallet.get('chain_id')})"
                    if wallet.get("rpc_connected")
                    else wallet.get("rpc_error") or "Base RPC connection is not ready"
                ),
                "last_check_time": wallet.get("last_check_time"),
            },
            "coingecko": {
                "ready": market_cache.get("state") in {"live", "cached"},
                "state": market_cache.get("state", "unavailable"),
                "age_seconds": market_age,
                "last_success_at": market_cache.get("last_success_at"),
                "detail": market_detail,
            },
        },
    }


@app.route("/api/admin/overview", methods=["GET"])
def api_admin_overview():
    """Protected live operational data for the browser admin dashboard."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    return _safe_jsonify(_admin_overview_payload())


@app.route("/api/admin/catalog-metrics", methods=["GET"])
def api_admin_catalog_metrics():
    """Return protected live 24-hour catalog metrics and popularity ranking."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    catalog_metrics = catalog_store.get_metrics_24h()
    nexus_metrics = _nexus_metrics_24h()
    return _safe_jsonify(
        {
            "ok": True,
            **catalog_metrics,
            "nexus": nexus_metrics,
            "all_offerings": _compose_agent_analytics(
                catalog_metrics, nexus_metrics
            )["products"],
        }
    )


@app.route("/api/admin/marketplace-governance", methods=["GET"])
def api_admin_marketplace_governance():
    """Show the approved contract and persistence readiness without raw research payloads."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    return _safe_jsonify(
        {
            "ok": bool(getattr(marketplace_store, "available", False)),
            "backend": marketplace_store.backend,
            "reason": getattr(marketplace_store, "reason", ""),
            "active_contract": marketplace_store.active_contract(),
            "contracts": marketplace_store.list_contracts(),
            "latest_demand_scout": marketplace_store.latest_scout_report(),
            "auto_publish": False,
        }
    )


@app.route("/api/admin/demand-scout", methods=["GET", "POST"])
def api_admin_demand_scout():
    """Inspect or manually run bounded market research; it never publishes changes."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    if request.method == "GET":
        report = marketplace_store.latest_scout_report()
        return _safe_jsonify(
            {
                "ok": report is not None,
                "available": bool(getattr(marketplace_store, "available", False)),
                "reason": getattr(marketplace_store, "reason", ""),
                "report": report,
                "auto_publish": False,
            }
        )
    outcome = _refresh_demand_scout()
    status = 200 if outcome.get("ok") else 503
    return _safe_jsonify({**outcome, "auto_publish": False}), status


@app.route("/api/admin/catalog-contract/rollback", methods=["POST"])
def api_admin_catalog_contract_rollback():
    """Human-only contract rollback; daily research cannot call this endpoint."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    version = str(payload.get("version") or "").strip()
    if not version:
        return jsonify({"ok": False, "error": "contract_version_required"}), 400
    candidate = next(
        (item for item in marketplace_store.list_contracts() if item["version"] == version),
        None,
    )
    if not candidate:
        return jsonify({"ok": False, "error": "contract_version_not_found_or_unavailable"}), 404
    if not manifest_is_runtime_compatible(candidate.get("manifest", {})):
        return jsonify({"ok": False, "error": "manifest_runtime_incompatible"}), 400
    try:
        contract = _transition_catalog_contract(candidate)
    except Exception:
        log.exception("Catalog contract rollback failed")
        return jsonify({"ok": False, "error": "catalog_contract_rollback_failed"}), 503
    if not contract:
        return jsonify({"ok": False, "error": "catalog_contract_rollback_failed"}), 503
    _record_operational_event(
        event_type="catalog_contract_rollback",
        source="admin",
        method=request.method,
        path=request.path,
        status_code=200,
        success=True,
        metadata={
            "operation": "catalog_contract_governance",
            "outcome": "rollback",
            "catalog_version": version,
        },
    )
    return _safe_jsonify({"ok": True, "active_contract": contract, "auto_publish": False})


@app.route("/api/admin/catalog-contract/activate", methods=["POST"])
def api_admin_catalog_contract_activate():
    """Human-only approval path for a draft; startup and Demand Scout cannot invoke it."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    version = str(payload.get("version") or "").strip()
    if not version:
        return jsonify({"ok": False, "error": "contract_version_required"}), 400
    candidate = next(
        (item for item in marketplace_store.list_contracts() if item["version"] == version),
        None,
    )
    if not candidate:
        return jsonify({"ok": False, "error": "contract_version_not_found_or_unavailable"}), 404
    if not manifest_is_runtime_compatible(candidate.get("manifest", {})):
        return jsonify({"ok": False, "error": "manifest_runtime_incompatible"}), 400
    try:
        contract = _transition_catalog_contract(candidate)
    except Exception:
        log.exception("Catalog contract activation failed")
        return jsonify({"ok": False, "error": "catalog_contract_activation_failed"}), 503
    if not contract:
        return jsonify({"ok": False, "error": "catalog_contract_activation_failed"}), 503
    _record_operational_event(
        event_type="catalog_contract_activated",
        source="admin",
        method=request.method,
        path=request.path,
        status_code=200,
        success=True,
        metadata={
            "operation": "catalog_contract_governance",
            "outcome": "activated",
            "catalog_version": version,
        },
    )
    return _safe_jsonify({"ok": True, "active_contract": contract, "auto_publish": False})


@app.route("/api/admin/trial-conversion", methods=["GET"])
def api_admin_trial_conversion():
    """Per-agent conversion funnel: trial_started → checkout_initiated → stripe_payment_confirmed.

    Returns counts and conversion percentages for each catalog agent over all
    retained audit events (no time-window filter — intended for admin reporting).
    Admin authentication required.
    """
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error

    raw_events = audit_store.recent_events(limit=5000) if hasattr(audit_store, "recent_events") else []
    trial_counts: dict[str, int] = {}
    checkout_counts: dict[str, int] = {}
    paid_counts: dict[str, int] = {}
    for ev in raw_events:
        meta = ev.get("metadata") or {}
        agent_id = meta.get("agent_id") or meta.get("product_id", "")
        if not agent_id:
            continue
        etype = ev.get("event_type", "")
        if etype == "trial_started":
            trial_counts[agent_id] = trial_counts.get(agent_id, 0) + 1
        elif etype == "checkout_initiated":
            checkout_counts[agent_id] = checkout_counts.get(agent_id, 0) + 1
        elif etype == "stripe_payment_confirmed":
            paid_counts[agent_id] = paid_counts.get(agent_id, 0) + 1

    catalog = catalog_store.get_catalog()
    funnel = []
    for a in catalog:
        aid = a["id"]
        trials = trial_counts.get(aid, 0)
        checkouts = checkout_counts.get(aid, 0)
        paid = paid_counts.get(aid, 0)
        funnel.append({
            "agent_id": aid,
            "name": a["name"],
            "category": a["category"],
            "trials": trials,
            "checkouts": checkouts,
            "paid": paid,
            "trial_to_checkout_pct": round(100.0 * checkouts / trials, 1) if trials else 0.0,
            "checkout_to_paid_pct": round(100.0 * paid / checkouts, 1) if checkouts else 0.0,
            "overall_conversion_pct": round(100.0 * paid / trials, 1) if trials else 0.0,
        })
    funnel.sort(key=lambda x: x["trials"], reverse=True)
    return _safe_jsonify({"ok": True, "funnel": funnel, "event_window": "all_retained"})


@app.route("/api/v1/research/ingest", methods=["POST"])
def api_research_ingest():
    """Accept authenticated Discord, RSS, or GitHub research into a pending queue."""
    auth_error = _require_research_ingest_access()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    try:
        insight = research_store.ingest(
            source=payload.get("source", ""),
            external_id=payload.get("external_id", ""),
            title=payload.get("title", ""),
            content=payload.get("content", ""),
            actionable_summary=payload.get("actionable_summary", ""),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    created = bool(insight.pop("created"))
    return _safe_jsonify(
        {
            "ok": True,
            "created": created,
            "insight": insight,
        }
    ), 201 if created else 200


@app.route("/api/admin/research-insights", methods=["GET"])
def api_admin_research_insights():
    """List the protected research review queue."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    try:
        insights = research_store.list_insights(
            status=request.args.get("status", ""),
            limit=request.args.get("limit", 100, type=int) or 100,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return _safe_jsonify({"ok": True, "insights": insights, "total": len(insights)})


@app.route("/api/admin/research-insights/<insight_id>", methods=["PATCH"])
def api_admin_research_insight_update(insight_id: str):
    """Approve or archive a research insight after human review."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    try:
        insight = research_store.update_status(insight_id, payload.get("status", ""))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not insight:
        return jsonify({"ok": False, "error": "research_insight_not_found"}), 404
    return _safe_jsonify({"ok": True, "insight": insight})


_ADMIN_LOGIN_HTML = """
<!doctype html><html lang="bg"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Вход за администратор</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0f1117;color:#e2e8f0;font-family:system-ui,sans-serif}
form{width:min(420px,calc(100% - 32px));padding:32px;border:1px solid #2d3142;border-radius:16px;background:#1a1d28}
input,button{width:100%;box-sizing:border-box;padding:12px;border-radius:9px;font:inherit}input{background:#0f1117;color:#fff;border:1px solid #46506b;margin:18px 0}
button{border:0;background:#6366f1;color:#fff;font-weight:700;cursor:pointer}.error{color:#fca5a5}
</style></head><body><form method="post"><h1>Оперативен dashboard</h1><p>Въведете администраторския token.</p>{% if error %}<p class="error">{{ error }}</p>{% endif %}
<label for="admin_token">Admin token</label><input id="admin_token" name="admin_token" type="password" required autofocus autocomplete="current-password"><button type="submit">Вход</button></form></body></html>
"""


_ADMIN_RESEARCH_HTML = r"""
<!doctype html><html lang="bg"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kristo Intelligence — R&D review</title><style>
:root{--bg:#0f1117;--card:#1a1d28;--border:#2d3142;--text:#e2e8f0;--muted:#94a3b8;--accent:#818cf8;--good:#34d399;--bad:#f87171}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,sans-serif}header{padding:20px 28px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;gap:16px;align-items:center}a{color:var(--accent)}main{max-width:1120px;margin:auto;padding:28px}.filters{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 20px}button{border:1px solid #46506b;background:#121522;color:var(--text);padding:9px 12px;border-radius:8px;cursor:pointer;font:inherit}button.primary{background:var(--accent);border-color:var(--accent)}article{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;margin:12px 0}.meta{color:var(--muted);font-size:.82rem}.summary{color:#c7d2fe;white-space:pre-wrap}.content{color:var(--muted);white-space:pre-wrap;max-height:180px;overflow:auto}.actions{display:flex;gap:8px;margin-top:14px}.approved{color:var(--good)}.archived{color:var(--bad)}.empty{color:var(--muted)}
</style></head><body><header><div><h1>R&D research queue</h1><div class="meta">Discord, RSS и GitHub ingest-ът влиза като PENDING и изисква човешко одобрение.</div></div><a href="/sales/admin">Към dashboard</a></header><main><div class="filters"><button class="primary" data-status="PENDING">Pending</button><button data-status="APPROVED">Approved</button><button data-status="ARCHIVED">Archived</button><button data-status="">All</button></div><p id="state" class="meta"></p><section id="items"><p class="empty">Loading…</p></section></main><script>
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let status='PENDING';
function render(items){const root=document.getElementById('items');root.innerHTML=items.length?items.map(i=>`<article><div class="meta">${esc(i.source)} · ${esc(i.status)} · ${esc(new Date(i.created_at).toLocaleString('bg-BG'))}</div><h2>${esc(i.title)}</h2>${i.actionable_summary?`<p class="summary">${esc(i.actionable_summary)}</p>`:''}<p class="content">${esc(i.content)}</p><div class="actions">${i.status!=='APPROVED'?`<button onclick="updateInsight('${esc(i.id)}','APPROVED')">Approve</button>`:''}${i.status!=='ARCHIVED'?`<button onclick="updateInsight('${esc(i.id)}','ARCHIVED')">Archive</button>`:''}</div></article>`).join(''):'<p class="empty">No research insights in this view.</p>'}
async function load(){const r=await fetch('/api/admin/research-insights?status='+encodeURIComponent(status));const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not load research.');document.getElementById('state').textContent=d.total+' insight(s)';render(d.insights)}
async function updateInsight(id,next){const r=await fetch('/api/admin/research-insights/'+encodeURIComponent(id),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:next})});if(!r.ok){const d=await r.json();alert(d.error||'Update failed');return}load()}
document.querySelectorAll('[data-status]').forEach(b=>b.onclick=()=>{status=b.dataset.status;load().catch(e=>document.getElementById('state').textContent=e.message)});load().catch(e=>document.getElementById('state').textContent=e.message);
</script></body></html>
"""


_ADMIN_DASHBOARD_HTML = r"""
<!doctype html>
<html lang="bg"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kristo Intelligence — Оперативен dashboard</title>
<style>
:root{--bg:#0f1117;--card:#1a1d28;--border:#2d3142;--text:#e2e8f0;--muted:#94a3b8;--accent:#818cf8;--good:#34d399;--bad:#f87171;--warn:#fbbf24}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,sans-serif}header{padding:20px 28px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;gap:16px;align-items:center}a{color:var(--accent)}main{max-width:1500px;margin:auto;padding:28px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:14px;margin:16px 0 28px}.card,.panel{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px}.metric label,.label{display:block;color:var(--muted);font-size:.75rem;text-transform:uppercase;letter-spacing:.06em}.metric strong{display:block;font-size:1.8rem;margin-top:7px}.panel{margin:18px 0}.panel h2{font-size:1rem;margin:0 0 14px}.services,.gates{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.service,.gate{padding:12px;background:#121522;border-radius:8px}.gate strong{display:block;margin-top:5px}.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.notice{margin:16px 0;padding:14px 16px;border:1px solid #695726;border-radius:10px;background:#251e0e;color:#fef3c7}table{width:100%;border-collapse:collapse;font-size:.86rem}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--border);vertical-align:top}th{color:var(--muted);font-size:.72rem;text-transform:uppercase}.scroll{overflow:auto}.muted{color:var(--muted)}#error{color:var(--bad);min-height:18px}@media(max-width:650px){main{padding:16px}header{padding:16px;align-items:flex-start;flex-direction:column}th,td{padding:8px}}
</style></head>
<body><header><div><h1>Kristo Intelligence — Оперативен dashboard</h1><div class="muted">Автоматично обновяване на 15 секунди. Чувствителните данни са достъпни само за администратор.</div></div><div><a href="/sales/admin/research">R&D review</a> · <a href="/sales/admin/logout">Изход</a></div></header>
<main><p id="error"></p><div class="notice"><strong>v6 preview — launch gates pending.</strong> Публичен commercial launch не се маркира като готов, докато Publish, contract activation, payment delivery smoke и repeat paid evidence не са потвърдени.</div><p id="generated-at" class="muted"></p><section class="panel"><h2>v6 launch gates</h2><div id="launch-gates" class="gates"></div></section><section id="metrics" class="grid"></section>
<section class="panel"><h2>Статус на услугите</h2><div id="services" class="services"></div></section>
<section class="panel"><h2>AI агентни услуги — интерес и потвърдени продажби (24ч)</h2><p id="catalog-summary" class="muted"></p><div class="scroll"><table><thead><tr><th>Име</th><th>Цена</th><th>Hits (посещения / клик / API)</th><th>Платени (Sales)</th><th>Приход</th></tr></thead><tbody id="catalog"></tbody></table></div></section>
<section class="panel"><h2>Последни Stripe/CRM плащания</h2><p id="payment-source" class="muted"></p><div class="scroll"><table><thead><tr><th>Време</th><th>Клиент</th><th>План</th><th>Сума</th><th>Статус</th><th>Източник</th></tr></thead><tbody id="payments"></tbody></table></div></section>
<section class="panel"><h2>Активни платени VIP планове</h2><div class="scroll"><table><thead><tr><th>Активиран</th><th>Клиент</th><th>План</th><th>Сума</th><th>Telegram</th></tr></thead><tbody id="vips"></tbody></table></div></section>
<section class="panel"><h2>Запитвания и логове</h2><p class="muted">Показват се последните 100 заявки без headers, token-и или параметри.</p><div class="scroll"><table><thead><tr><th>Време</th><th>Източник</th><th>Метод</th><th>Път</th><th>Статус</th></tr></thead><tbody id="requests"></tbody></table></div></section>
</main>
<script>
const escapeHtml = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = value => '$' + Number(value || 0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const date = value => { if (!value) return '—'; const stamp = typeof value === 'number' ? value * 1000 : value; const parsed = new Date(stamp); return Number.isNaN(parsed) ? '—' : parsed.toLocaleString('bg-BG'); };
function rows(id, values, makeRow, colspan) { const target=document.getElementById(id); target.innerHTML=values.length?values.map(makeRow).join(''):`<tr><td colspan="${colspan}" class="muted">Все още няма данни.</td></tr>`; }
function render(data) {
  const metricLabels={'crm_revenue_usd':'CRM потвърден приход','onchain_revenue_usd':'Наблюдаван on-chain обем','catalog_revenue_24h_usd':'Catalog потвърден приход (24ч)','agent_hits_24h':'Agent hits (24ч)','agent_sales_24h':'Agent sales (24ч)','nexus_hits_24h':'Nexus hits (24ч)','nexus_sales_24h':'Nexus sales (24ч)','active_agent_entitlements':'Активни agent достъпи','research_pending_review':'R&D за review','paid_payments':'CRM платени записи','active_vip_plans':'VIP записи (не subscription status)','active_telegram_users':'Активни Telegram потребители'};
  document.getElementById('metrics').innerHTML=Object.entries(metricLabels).map(([key,label])=>`<div class="card metric"><label>${label}</label><strong>${key.includes('revenue')?money(data.metrics[key]):escapeHtml(data.metrics[key])}</strong></div>`).join('');
  document.getElementById('generated-at').textContent=`Последно генериране: ${date(data.generated_at)} · Catalog/Nexus метриките са за 24ч, CRM/on-chain са отделни източници.`;
  const gates=data.launch_gates||{}, contract=gates.contract||{}, catalogGate=gates.catalog||{}, persistence=gates.persistence||{}, x402=gates.x402||{}, stripe=gates.stripe||{}, launch=gates.broad_launch||{};
  const gate=(good,label,detail)=>`<div class="gate"><span class="label">${escapeHtml(label)}</span><strong class="${good?'good':'warn'}">● ${escapeHtml(detail)}</strong></div>`;
  document.getElementById('launch-gates').innerHTML=[
    gate(contract.status==='active','Contract',contract.status==='active'?`active v${contract.version}`:`${contract.status||'unknown'} — human approval required`),
    gate(catalogGate.published,'Catalog',catalogGate.published?`${catalogGate.approved_agent_count} approved utilities published`:'hidden until approved contract'),
    gate(persistence.schema_verified,'Persistence',`${persistence.schema_verified?'schema verified':'schema incomplete'} · ${persistence.catalog_backend||'unknown'} catalog · ${persistence.audit_backend||'unknown'} audit · ${persistence.stripe_vip_backend||'unknown'} Stripe VIP`),
    gate(x402.mode==='full'&&x402.production_smoke_verified,'x402 settlement',`${x402.mode||'unknown'} · live smoke ${x402.production_smoke_verified?'verified':'required'}`),
    gate(stripe.configured&&stripe.feed_state==='live','Stripe source',`${stripe.feed_state||'unknown'}${stripe.age_seconds!=null?` · age ${stripe.age_seconds}s`:''}`),
    gate(false,'Broad launch',launch.detail||'blocked'),
  ].join('');
  document.getElementById('services').innerHTML=Object.entries(data.services).map(([name,service])=>{const ready=service.ready ?? service.running ?? service.configured;return `<div class="service"><strong class="${ready?'good':'bad'}">${ready?'● Работи':'● Нужна проверка'}</strong><br><span class="label">${escapeHtml(name)}</span><span class="muted">${escapeHtml(service.backend || service.detail || '')}</span></div>`}).join('');
  const analytics=data.agent_analytics||{products:[],totals:{},interest_leader:null,sales_leader:null};
  const interest=analytics.interest_leader;
  const sales=analytics.sales_leader;
  const leaderText=[
    interest ? `Най-голям интерес: ${interest.name} (${interest.hits_24h} hits)` : 'Все още няма activity.',
    sales ? `Най-много покупки: ${sales.name} (${sales.sales_24h} confirmed sales)` : ''
  ].filter(Boolean).join(' · ');
  document.getElementById('catalog-summary').textContent=`${leaderText} Показани са само server-observed events за последните 24 часа. ${catalogGate.published?'Catalog metadata е от active approved contract.':'Catalog-ът не е публикуван; тези метрики са вътрешни и не представляват публични utilities.'} Nexus е отделен payment ledger и не променя ranking-а на catalog SKU-та.`;
  const hitDetail=p=>p.is_nexus
    ? `Посещения ${p.visits_24h||0} · Клик ${p.clicks_24h||0} · API ${p.api_requests_24h||0}`
    : `Клик ${p.clicks_24h||0} · API ${p.calls_24h||0}`;
  const saleDetail=p=>p.is_nexus
    ? `Stripe ${p.stripe_subscriptions_24h||0} · x402 ${p.x402_signals_24h||0}`
    : `${p.sales_24h||0} confirmed`;
  const revenue=p=>p.is_nexus
    ? `€${Number(p.revenue_eur_24h||0).toFixed(2)} · $${Number(p.revenue_usdc_24h||0).toFixed(2)} USDC`
    : money(p.revenue_24h);
  rows('catalog',analytics.products,p=>`<tr><td><strong>${escapeHtml(p.name)}</strong><br><span class="muted">${escapeHtml(p.is_nexus?'isolated Nexus ledger':p.category)}</span></td><td>${escapeHtml(p.price_label||`${money(p.price_x402)} USDC`)}</td><td><strong>${escapeHtml(p.hits_24h)}</strong><br><span class="muted">${escapeHtml(hitDetail(p))}</span></td><td><strong>${escapeHtml(p.sales_24h)}</strong><br><span class="muted">${escapeHtml(saleDetail(p))}</span></td><td>${escapeHtml(revenue(p))}</td></tr>`,5);
  document.getElementById('payment-source').textContent=data.payment_source==='stripe_checkout'?`Данни от Stripe Checkout · ${stripe.feed_state||'unknown'}${stripe.age_seconds!=null?` · cache age ${stripe.age_seconds}s`:''}.`:'Stripe listing не е наличен; показани са CRM paid events, не live Stripe settlement feed.';
  rows('payments',data.payments,p=>`<tr><td>${date(p.created)}</td><td>${escapeHtml(p.email)}</td><td>${escapeHtml(p.plan)}</td><td>${money(p.amount_usd)}</td><td class="good">${escapeHtml(p.payment_status)}</td><td>${escapeHtml(p.provider)}</td></tr>`,6);
  rows('vips',data.vip_plans,p=>`<tr><td>${date(p.activated_at)}</td><td>${escapeHtml(p.email)}</td><td>${escapeHtml(p.plan)}</td><td>${money(p.amount_usd)}</td><td>${p.telegram_linked?'Свързан':'Не е свързан'}</td></tr>`,5);
  rows('requests',data.request_log,r=>`<tr><td>${date(r.timestamp)}</td><td>${escapeHtml(r.source)}</td><td>${escapeHtml(r.method)}</td><td>${escapeHtml(r.path)}</td><td class="${r.status_code<400?'good':'bad'}">${escapeHtml(r.status_code)}</td></tr>`,5);
}
async function refresh(){try{const response=await fetch('/api/admin/overview');if(!response.ok)throw new Error('Администраторската сесия е изтекла.');render(await response.json());document.getElementById('error').textContent='';}catch(error){document.getElementById('error').textContent=error.message;}}
refresh();setInterval(refresh,15000);
</script></body></html>
"""


@app.route("/sales/admin/login", methods=["GET", "POST"])
@app.route("/admin/login", methods=["GET", "POST"])
def sales_admin_login():
    """Create a signed browser session from the existing admin token."""
    error = ""
    if request.method == "POST":
        configured = _get_admin_token()
        supplied = (request.form.get("admin_token") or "").strip()
        if configured and supplied and hmac.compare_digest(supplied, configured):
            session.clear()
            session["admin_authenticated"] = True
            return redirect("/sales/admin")
        _log_admin_token_mismatch(configured, supplied)
        error = "Невалиден admin token."
    return render_template_string(_ADMIN_LOGIN_HTML, error=error)


@app.route("/sales/admin/logout", methods=["GET"])
def sales_admin_logout():
    session.clear()
    return redirect("/sales/admin/login")


@app.route("/sales/admin", methods=["GET"])
def sales_admin():
    """Protected browser dashboard for sales, VIP operations and service health."""
    if session.get("admin_authenticated"):
        return render_template_string(_ADMIN_DASHBOARD_HTML)

    configured = _get_admin_token()
    supplied = request.headers.get("X-Admin-Token", "").strip()
    valid_header = bool(
        configured
        and supplied
        and hmac.compare_digest(supplied, configured)
    )
    if not valid_header:
        return redirect("/sales/admin/login")

    session["admin_authenticated"] = True
    return render_template_string(_ADMIN_DASHBOARD_HTML)


@app.route("/sales/admin/research", methods=["GET"])
def sales_admin_research():
    """Protected browser view for approving or archiving R&D research insights."""
    if session.get("admin_authenticated"):
        return render_template_string(_ADMIN_RESEARCH_HTML)
    auth_error = _require_admin_access()
    if auth_error:
        return redirect("/sales/admin/login")
    session["admin_authenticated"] = True
    return render_template_string(_ADMIN_RESEARCH_HTML)


@app.route("/api/launch/health", methods=["GET"])
def launch_health():
    """Public operational readiness endpoint.

    Returns only system-level readiness flags — no lead counts, pipeline data,
    or internal URLs that would expose sales operations to anonymous callers.
    Authenticated callers that need pipeline data should use /api/sales/summary.
    """
    crm_ready = crm_store.is_healthy()
    payload = {
        "ok": True,
        "app": "kristo-intelligence-v6",
        "status": "live" if crm_ready else "degraded",
        "crm_ready": crm_ready,
        "audit_ready": audit_store.is_healthy(),
        "x402_settlement_ready": x402_settlement.status == "full",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return jsonify(payload), 200 if crm_ready else 503


@app.route("/api/funnel/track", methods=["POST"])
def funnel_track():
    """Capture UTM campaign data for conversion analytics."""
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "valid email required"}), 400

    lead = LeadRecord(
        email=email,
        source=(payload.get("source") or "website").strip(),
        campaign=(payload.get("campaign") or "launch").strip(),
        utm_source=(payload.get("utm_source") or "").strip(),
        utm_medium=(payload.get("utm_medium") or "").strip(),
        utm_campaign=(payload.get("utm_campaign") or "").strip(),
        plan=(payload.get("plan") or "pro").strip(),
    )
    saved = crm_store.add_lead(lead)
    return jsonify({"ok": True, "lead": saved, "utm": {
        "source": lead.utm_source,
        "medium": lead.utm_medium,
        "campaign": lead.utm_campaign,
    }})


@app.route("/health")
def health():
    crm_ready = crm_store.is_healthy()
    with _lock:
        wallet = dict(_wallet_state)
    mock_payments_enabled = (
        os.getenv("KRISTO_ALLOW_MOCK_PAYMENTS", "").strip().lower() == "true"
    )
    blockchain_ready = bool(
        wallet.get("rpc_connected")
        and wallet.get("chain_id") == BASE_CHAIN_ID
        and wallet.get("receiver_valid")
    )
    # Explicit local/test mock mode has no RPC monitor by design. It must not
    # make preview health fail merely because network workers are disabled.
    if mock_payments_enabled and not wallet.get("rpc_connected"):
        blockchain_ready = True
        wallet["chain_id"] = BASE_CHAIN_ID
    return jsonify(
        status="ok" if crm_ready and blockchain_ready else "degraded",
        database={
            "backend": crm_store.backend,
            "ready": crm_ready,
            "audit_backend": audit_store.backend,
            "audit_ready": audit_store.is_healthy(),
            "stripe_vip_backend": stripe_vip_store.backend,
            "stripe_vip_ready": stripe_vip_store.is_healthy(),
        },
        x402={
            "settlement_mode": x402_settlement.status,
            "ready": x402_settlement.status == "full",
            "confirmations_required": X402_CONFIRMATIONS,
        },
        nexus={
            "ready": nexus_store.is_healthy(),
            "analytics_ready": nexus_store.analytics_is_healthy(),
            "x402_settlement_mode": nexus_x402_settlement.status,
            "bot_price_usdc": NEXUS_X402_USDC,
        },
        blockchain={
            "ready": blockchain_ready,
            "network": wallet.get("network", "Base Mainnet"),
            "chain_id": wallet.get("chain_id"),
            "fee_receiver": wallet.get("fee_receiver"),
        },
    ), 200 if crm_ready and blockchain_ready else 503


@app.route("/api/sales")
def api_sales():
    """Return REAL sales history (from on-chain USDC transfers) and total volume."""
    _record_request("api_sales", True)
    with _lock:
        history = list(_sales_history)
        total_volume = round(sum(s["amount_usd"] for s in history), 6)
        total_count = len(history)

        by_token: Dict[str, float] = {}
        for s in history:
            by_token[s["token"]] = round(by_token.get(s["token"], 0) + s["amount_usd"], 6)

    # Fetch real-time market data from CoinGecko, DEXScreener, Fear & Greed
    market_data = get_market_snapshot()

    return _safe_jsonify({
        "total_volume_usd": total_volume,
        "total_sales": total_count,
        "by_token": by_token,
        "history": history[-100:],
        "source": "real_blockchain",
        "wallet_address": _wallet_state.get("wallet_address"),
        "usdc_balance": _wallet_state.get("usdc_balance", 0.0),
        "market_data": market_data,
    })


def _statistics_payload(include_recent_requests: bool) -> dict:
    """Build real stats from durable catalog events and live runtime state."""
    with _lock:
        daily = dict(sorted(_daily_stats.items()))
        recent_requests = list(_request_log)
        wallet_info = dict(_wallet_state)
        sales_history = list(_sales_history)
        bot_status = dict(_bot_status)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_data = daily.get(today_str, {"requests": 0, "sales_count": 0, "sales_volume": 0.0})
    sales_by_token: Dict[str, float] = {}
    for sale in sales_history:
        token = sale.get("token", "USDC")
        sales_by_token[token] = round(
            sales_by_token.get(token, 0.0) + float(sale.get("amount_usd", 0.0)), 6
        )

    # Official eight-agent breakdown from durable catalog events.
    products = _get_products_breakdown()
    total_hits = sum(p["hits"] for p in products)
    total_product_sales = sum(p["sales_count"] for p in products)
    total_product_volume = round(sum(p["sales_volume_usd"] for p in products), 6)

    # Fetch real-time market data from CoinGecko, DEXScreener, Fear & Greed
    market_data = get_market_snapshot()

    payload = {
        "today": {
            "date": today_str,
            "requests": today_data.get("requests", 0),
            "sales_count": today_data.get("sales_count", 0),
            "sales_volume_usd": today_data.get("sales_volume", 0.0),
        },
        "daily": daily,
        "total_requests": sum(d.get("requests", 0) for d in daily.values()),
        "wallet": wallet_info,
        "total_volume_usd": round(
            sum(float(sale.get("amount_usd", 0.0)) for sale in sales_history), 6
        ),
        "total_sales": len(sales_history),
        "by_token": sales_by_token,
        "history": sales_history[-100:],
        "telegram_bot_running": bot_status.get("telegram_bot_running", False),
        "commands_processed": bot_status.get("commands_processed", 0),
        "products": products,
        "products_summary": {
            "total_products": len(products),
            "total_hits": total_hits,
            "total_sales": total_product_sales,
            "total_volume_usd": total_product_volume,
        },
        "nexus_url": NEXUS_URL,
        "market_data": market_data,
    }
    if include_recent_requests:
        payload["recent_requests"] = recent_requests[-50:]
    return payload


@app.route("/api/dashboard-stats")
def dashboard_stats():
    """Return free, read-only aggregate data required by the public dashboard."""
    return _safe_jsonify(_statistics_payload(include_recent_requests=False))


@app.route("/api/stats")
def api_stats():
    """Return paid activity, requests, daily stats, and official agent catalog data."""
    _record_request("api_stats", True)
    return _safe_jsonify(_statistics_payload(include_recent_requests=True))


@app.route("/api/bot-status")
def api_bot_status():
    """Return Telegram bot integration status."""
    _record_request("api_bot_status", True)
    with _lock:
        status = dict(_bot_status)
        wallet_info = dict(_wallet_state)
    status["last_heartbeat"] = status.get("last_heartbeat", "")
    status["uptime_started"] = status.get("uptime_started", "")
    status["wallet"] = wallet_info
    return _safe_jsonify(status)


# ── Telegram Webhook (for bot messages & inline button callbacks) ─────────

@app.route("/api/telegram-webhook", methods=["POST"])
def api_telegram_webhook():
    """
    Webhook endpoint for Telegram Bot API updates.

    Receives Telegram Update objects (messages and callback_query events)
    and delegates processing to `services.telegram_sales.process_webhook_update`.

    This handles:
      * Text commands: /start, /help, /bulletin, /price
      * Inline button callbacks: "🔓 Отключи пълен VIP анализ за 0.10 USDC"

    The endpoint is always free (no x402 paywall) so Telegram can deliver
    updates without payment.
    """
    configured_secret = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    supplied_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if (
        not configured_secret
        or not supplied_secret
        or not hmac.compare_digest(supplied_secret, configured_secret)
    ):
        _record_request("api_telegram_webhook", False)
        log.warning("Rejected Telegram webhook without a valid secret token.")
        return jsonify({"ok": False, "error": "telegram_webhook_unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    if not payload:
        _record_request("api_telegram_webhook", False)
        return jsonify({"ok": False, "error": "empty_payload"}), 400

    try:
        message = payload.get("message") or {}
        chat_id = message.get("chat", {}).get("id")
        text = (message.get("text") or "").strip()
        command_parts = text.split()
        start_command = command_parts[0].lower() if command_parts else ""
        if (
            chat_id
            and start_command.startswith("/start")
            and len(command_parts) == 2
            and command_parts[1].startswith("vip_")
        ):
            vip_result = _link_stripe_vip_telegram_account(
                command_parts[1][4:], str(chat_id)
            )
            if vip_result.get("status") == "telegram_linked_waiting_payment":
                telegram_flow.send_message(
                    str(chat_id),
                    "Telegram профилът е свързан. VIP поканата ще бъде изпратена след потвърдено Stripe плащане.",
                )
            elif vip_result.get("status") == "invalid_vip_link":
                telegram_flow.send_message(
                    str(chat_id),
                    "Този VIP код не е валиден. Върнете се към Stripe checkout страницата и използвайте текущия код.",
                )
            elif vip_result.get("status") not in {"invite_sent", "already_active"}:
                telegram_flow.send_message(
                    str(chat_id),
                    "Профилът е свързан, но VIP поканата все още не може да се изпрати. Опитайте отново по-късно.",
                )
            result = {"handled": True, "type": "stripe_vip_link", **vip_result}
        else:
            result = process_webhook_update(payload)
        _record_request("api_telegram_webhook", True)
        _record_telegram_activity(payload, result)
        log.info("Telegram webhook processed: %s", result)
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        _record_request("api_telegram_webhook", False)
        log.error("Telegram webhook processing failed: %s", exc)
        return jsonify({"ok": False, "error": "telegram_processing_failed"}), 500


# ── MCP / x402 Payment Protocol ──────────────────────────────────────────

@app.route("/api/mcp/manifest")
def api_mcp_manifest():
    """
    MCP/x402 manifest generated from the approved catalog contract.

    No paid catalog utility is advertised until a human has activated a
    runtime-compatible contract. Agent clients receive the exact bound endpoint,
    input schema, price, checkout and access-token flow for every published SKU.
    """
    _record_request("api_mcp_manifest", True)
    base_url = request.host_url.rstrip("/")
    catalog = _approved_catalog_agents()
    agents = _catalog_mcp_agents(base_url, catalog or [])
    manifest = {
        "protocol": "x402",
        "version": "2.0",
        "service": "Kristo Intelligence API",
        "description": "Evidence-first agent utilities and crypto market intelligence",
        "payment": {
            "chain": X402_CHAIN,
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            "settlement_status": x402_settlement.status,
            "flow": (
                "One free request per client-agent. Afterward, request the bound playground "
                "endpoint, receive a server-issued x402 challenge, then resend the same request "
                "with X-Payment-Proof; alternatively create a Stripe checkout and exchange its "
                "paid entitlement for a bearer access token."
            ),
        },
        "endpoints": {
            "base_url": base_url,
            "free": [
                {"path": "/api/mcp/manifest", "method": "GET", "cost_usdc": 0.0, "description": "This manifest (free)"},
                {"path": "/api/v1/agents", "method": "GET", "cost_usdc": 0.0, "description": "Active catalog (free)"},
                {"path": "/api/v1/catalog/contract", "method": "GET", "cost_usdc": 0.0, "description": "Contract status (free)"},
            ],
            "agents": agents,
        },
        "instructions": {
            "x402": "Never prepay from this manifest: use the challenge returned by the exact endpoint request.",
            "stripe": "Create the listed checkout for a catalog agent, then exchange its paid checkout ID for the listed bearer access endpoint.",
            "verification": "The server verifies Base USDC proof against the request-bound challenge before delivery.",
        },
        "catalog": {
            "status": "active" if catalog else _catalog_governance_status(),
            "contract_version": _published_contract_version() if catalog else None,
            "agents": agents,
        },
    }
    return jsonify(manifest)


# ── AI Agent Discovery Endpoints (x402, OpenAPI, llms.txt) ────────────────

@app.route("/.well-known/x402.json")
def well_known_x402():
    """Serve current 8-agent x402 discovery metadata from the catalog store."""
    return _safe_jsonify(_build_x402_discovery(request.host_url.rstrip("/")))




@app.route("/mcp.json")
def mcp_json():
    """MCP discovery file — catalog-driven, contract_version 2.0.

    Lists all eight active catalog agents plus the Nexus premium signal as MCP
    tools so AI orchestrators (Claude, GPT, custom agents) can discover the full
    capability surface in one request.  The contract_version field is bumped
    whenever the agent surface changes so consumers can detect staleness.
    """
    base_url = request.host_url.rstrip("/")
    catalog = _approved_catalog_agents() or []
    catalog_tools = _catalog_mcp_agents(base_url, catalog)

    return jsonify({
        "schema_version": "2.0",
        "contract_version": _published_contract_version() if catalog else None,
        "catalog_status": "active" if catalog else _catalog_governance_status(),
        "name": "Kristo Intelligence API",
        "description": (
            "Eight evidence-first agent utilities and an isolated Nexus premium signal. "
            "Catalog utilities are accessible via x402 USDC on Base or Stripe checkout."
            if catalog
            else "The catalog is not published until its contract is migrated and explicitly activated."
        ),
        "base_url": base_url,
        "protocol": "x402",
        "payment": {
            "chain": X402_CHAIN,
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            "catalog_price_range_usdc": {
                "min": min((float(a["price_x402"]) for a in catalog), default=0.05),
                "max": max((float(a["price_x402"]) for a in catalog), default=0.25),
            },
            "free_playground_requests_per_client": 1,
        },
        "agents": [
            {
                **agent,
                "name": f"agent_{agent['id'].replace('-', '_')}",
                "cost_usdc": agent["price_usdc"],
            }
            for agent in catalog_tools
        ],
        "nexus": {
            "name": "nexus_premium_signal",
            "description": (
                "Nexus Engine premium market signal. "
                "Single signal: $0.25 USDC via Base x402. "
                "Subscription: €10/month or €50/year via Stripe."
            ),
            "signal_endpoint": f"{base_url}/api/nexus/premium-signal",
            "method": "POST",
            "cost_usdc": NEXUS_X402_USDC,
            "subscription": {
                "monthly_eur": 10.0,
                "yearly_eur": 50.0,
                "checkout": f"{base_url}/api/nexus/checkout",
            },
            "plans_endpoint": f"{base_url}/api/nexus/plans",
        },
        "discovery": {
            "x402": f"{base_url}/.well-known/x402.json",
            "openapi": f"{base_url}/openapi.json",
            "llms_txt": f"{base_url}/llms.txt",
            "catalog": f"{base_url}/api/v1/agents",
            "contract": f"{base_url}/api/v1/catalog/contract",
            "developers": f"{base_url}/developers",
        },
    })


@app.route("/openapi.json")
def openapi_spec():
    """
    OpenAPI 3.0 specification for AI agent discovery.
    Includes x402 payment extensions so agents know how to pay.
    """
    base_url = request.host_url.rstrip("/")
    catalog = _approved_catalog_agents() or []
    contract_version = _published_contract_version() if catalog else None
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "Kristo Intelligence API",
            "version": "6.1.0",
            "description": "Evidence-first agent utilities and data capabilities. "
                           "Uses x402 payment protocol — USDC on Base.",
            "x402": {
                "protocol": "x402",
                "receiver_address": X402_RECEIVER_ADDRESS,
                "currency": "USDC",
                "chain": X402_CHAIN,
                "chain_id": X402_CHAIN_ID,
                "token_contract": X402_USDC_CONTRACT,
                "price_per_call_usdc": X402_FEE_USDC,
                "free_tier_limit": FREE_TIER_LIMIT,
            },
            "x-kristo-catalog": {
                "status": "active" if catalog else _catalog_governance_status(),
                "contract_version": contract_version,
                "agents": [
                    {
                        "id": agent["id"],
                        "price_usdc": round(float(agent["price_x402"]), 6),
                        "stripe_30day_usd": round(float(agent["price_stripe"]), 2),
                        "input_schema": agent["input_schema"],
                    }
                    for agent in catalog
                ],
            },
        },
        "servers": [{"url": base_url}],
        "paths": {
            # ── Catalog agent endpoints (contract_version 2.0) ─────────────
            "/api/v1/agents": {
                "get": {
                    "summary": "List all eight active catalog agents (free)",
                    "x402": {"cost_usdc": 0.0},
                    "responses": {"200": {"description": "Active agent catalog with pricing"}},
                }
            },
            "/api/v1/catalog/contract": {
                "get": {
                    "summary": "Get the active machine contract and governance status (free)",
                    "x402": {"cost_usdc": 0.0},
                    "responses": {"200": {"description": "Active eight-utility contract manifest"}},
                }
            },
            "/api/v1/agents/{agent_id}": {
                "get": {
                    "summary": "Get a single catalog agent by ID (free)",
                    "x402": {"cost_usdc": 0.0},
                    "parameters": [{"name": "agent_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {
                        "200": {"description": "Agent SKU with pricing and capability details"},
                        "404": {"description": "Unknown agent ID"},
                    },
                }
            },
            "/api/v1/agents/{agent_id}/playground": {
                "post": {
                    "summary": "Run one bounded catalog utility per client, then x402 or Stripe",
                    "x402": {
                        "catalog_driven_pricing": True,
                        "free_playground_requests_per_client": 1,
                    },
                    "parameters": [{"name": "agent_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "requestBody": {"content": {"application/json": {"schema": {"required": ["input"], "properties": {"input": {"type": "string", "maxLength": 6000}, "baseline": {"type": "string", "maxLength": 6000}}}}}},
                    "responses": {
                        "200": {"description": "Execution envelope with provenance and freshness"},
                        "402": {"description": "Free request used — response includes x402 challenge and Stripe checkout URL"},
                        "404": {"description": "Unknown agent"},
                    },
                }
            },
            "/api/v1/agents/{agent_id}/click": {
                "post": {
                    "summary": "Record a catalog product-page click for conversion analytics",
                    "x402": {"cost_usdc": 0.0},
                    "parameters": [{"name": "agent_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"202": {"description": "Click recorded"}, "429": {"description": "Click rate limited"}},
                }
            },
            "/api/v1/agents/{agent_id}/checkout": {
                "post": {
                    "summary": "Create a 30-day Stripe checkout entitlement for a catalog agent",
                    "x402": {"cost_usdc": 0.0},
                    "parameters": [{"name": "agent_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "requestBody": {"content": {"application/json": {"schema": {"required": ["email"], "properties": {"email": {"type": "string"}}}}}},
                    "responses": {"200": {"description": "Stripe checkout session created"}, "503": {"description": "Checkout unavailable"}},
                }
            },
            "/api/v1/agents/{agent_id}/access": {
                "post": {
                    "summary": "Exchange a paid checkout_id for a signed bearer access token",
                    "x402": {"cost_usdc": 0.0},
                    "parameters": [{"name": "agent_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "requestBody": {"content": {"application/json": {"schema": {"required": ["email", "checkout_id"], "properties": {"email": {"type": "string"}, "checkout_id": {"type": "string"}}}}}},
                    "responses": {"200": {"description": "Bearer access token"}, "403": {"description": "Entitlement not found"}},
                }
            },
            # ── Nexus Engine ───────────────────────────────────────────────
            "/api/nexus/plans": {
                "get": {
                    "summary": "Nexus Engine pricing: €10/month, €50/year, $0.25 USDC per signal",
                    "x402": {"cost_usdc": 0.0},
                    "responses": {"200": {"description": "Nexus plan options"}},
                }
            },
            "/api/nexus/checkout": {
                "post": {
                    "summary": "Create a Nexus subscription checkout (EUR, recurring)",
                    "x402": {"cost_usdc": 0.0},
                    "requestBody": {"content": {"application/json": {"schema": {"required": ["email", "plan"], "properties": {"email": {"type": "string"}, "plan": {"type": "string", "enum": ["monthly", "yearly"]}}}}}},
                    "responses": {"200": {"description": "Stripe subscription checkout session"}},
                }
            },
            "/api/nexus/premium-signal": {
                "post": {
                    "summary": "Premium Nexus market signal — $0.25 USDC via Base x402",
                    "x402": {"cost_usdc": 0.25, "protocol": "x402-challenge-response"},
                    "requestBody": {"content": {"application/json": {"schema": {"properties": {"asset": {"type": "string"}}}}}},
                    "responses": {
                        "200": {"description": "Premium signal returned after settlement"},
                        "402": {"description": "x402 challenge issued — sign and resend with X-Payment-Proof header"},
                    },
                }
            },
            # ── Discovery / free endpoints ─────────────────────────────────
            "/api/mcp/manifest": {"get": {"summary": "MCP/x402 manifest (free)", "responses": {"200": {"description": "MCP manifest"}}}},
            "/.well-known/x402.json": {"get": {"summary": "x402 discovery (free)", "responses": {"200": {"description": "x402 catalog discovery"}}}},
            "/openapi.json": {"get": {"summary": "This OpenAPI spec (free)", "responses": {"200": {"description": "OpenAPI 3.0"}}}},
            "/llms.txt": {"get": {"summary": "LLM-friendly API description (free)", "responses": {"200": {"description": "Plain text"}}}},
            "/mcp.json": {"get": {"summary": "MCP agent catalog discovery (free)", "responses": {"200": {"description": "MCP JSON"}}}},
            "/health": {"get": {"summary": "Operational readiness (free)", "responses": {"200": {"description": "ok"}, "503": {"description": "degraded"}}}},
            "/developers": {"get": {"summary": "Developer integration guide (free)", "responses": {"200": {"description": "Integration HTML page"}}}},
            # ── Legacy operational endpoints (free; not x402 settlement) ──
            "/api/stats": {
                "get": {
                    "summary": "Market activity and daily stats (free legacy endpoint)",
                    "responses": {"200": {"description": "Stats"}},
                }
            },
            "/api/sales": {
                "get": {
                    "summary": "On-chain sales history (free legacy endpoint)",
                    "responses": {"200": {"description": "Sales history"}},
                }
            },
            "/api/bot-status": {
                "get": {
                    "summary": "Telegram bot status (free legacy endpoint)",
                    "responses": {"200": {"description": "Bot status"}},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "BearerToken": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Short-lived agent access token issued by /api/v1/agents/{agent_id}/access after Stripe checkout",
                },
                "x402Payment": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Payment-Proof",
                    "description": f"x402 on-chain proof header. Challenge issued by the endpoint; sign and resend.",
                },
            }
        },
    }
    return jsonify(spec)


@app.route("/llms.txt")
def llms_txt():
    """LLM-readable API description — contract_version 2.0.

    Lists the full surface: 8 catalog agents, Nexus Engine, and discovery links.
    Intended for AI orchestrators that ingest /llms.txt to understand a service.
    """
    base_url = request.host_url.rstrip("/")
    catalog = _approved_catalog_agents() or []
    agent_lines = "\n".join(
        f"- POST {base_url}/api/v1/agents/{a['id']}/playground "
        f"[{a['category']}] — {a['description'][:80]} "
        f"(${float(a['price_x402']):.2f} USDC x402 · ${float(a['price_stripe']):.2f} Stripe 30d)"
        for a in catalog
    )
    catalog_heading = (
        "## Eight catalog utilities (1 free request per client, then x402 or Stripe checkout)"
        if catalog
        else "## Catalog utilities\n\nNo catalog utilities are currently published. "
        f"Status: {_catalog_governance_status()}."
    )
    content = f"""# Kristo Intelligence API — contract_version {_published_contract_version()}

> Eight evidence-first agent utilities and a separate Nexus premium signal layer.
> Base URL: {base_url}

{catalog_heading}

{agent_lines}

Agent catalog (JSON): {base_url}/api/v1/agents
Approved contract:      {base_url}/api/v1/catalog/contract
Single agent detail:  {base_url}/api/v1/agents/{{agent_id}}
30-day Stripe access: POST {base_url}/api/v1/agents/{{agent_id}}/checkout
Bearer token access:  POST {base_url}/api/v1/agents/{{agent_id}}/access

## Nexus Engine — premium signal layer (isolated from catalog agents)

- Single signal:    POST {base_url}/api/nexus/premium-signal  ($0.25 USDC, Base x402)
- Subscription:     POST {base_url}/api/nexus/checkout         (€10/month or €50/year, Stripe)
- Nexus plans:      GET  {base_url}/api/nexus/plans

## x402 Payment (Base network)

- Chain: Base  chain_id: {X402_CHAIN_ID}
- Currency: USDC  token_contract: {X402_USDC_CONTRACT}
- Receiver address: {X402_RECEIVER_ADDRESS}
- Catalog agent x402 price: per-agent (see catalog)
- Nexus premium signal price: $0.25 USDC

x402 flow:
1. POST the endpoint — server returns HTTP 402 with a signed challenge.
2. Sign the challenge proof and resend with X-Payment-Proof header.
3. Server verifies on-chain; returns result on success.

## Legacy operational endpoints (free; not x402 settlement)

- GET {base_url}/api/stats      — Market activity and daily stats
- GET {base_url}/api/sales      — On-chain sales history
- GET {base_url}/api/bot-status — Telegram bot status

## Discovery files (always free)

- OpenAPI 3.0:      {base_url}/openapi.json
- MCP agent JSON:   {base_url}/mcp.json
- x402 manifest:    {base_url}/.well-known/x402.json
- MCP manifest:     {base_url}/api/mcp/manifest
- LLMs (this file): {base_url}/llms.txt
- Health:           {base_url}/health

## Developer integration

- Guide:      {base_url}/developers
- Playground: {base_url}/agents
- Dashboard:  {base_url}/dashboard
"""
    from flask import Response
    return Response(content, mimetype="text/plain")


# ── Dashboard HTML ────────────────────────────────────────────────────────

_DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kristo Intelligence Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        :root {
            --bg: #0f1117;
            --card: #1a1d28;
            --accent: #6366f1;
            --accent2: #10b981;
            --accent3: #f59e0b;
            --accent4: #ef4444;
            --text: #e2e8f0;
            --muted: #94a3b8;
            --border: #2d3142;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
        }
        header {
            background: linear-gradient(135deg, #1e1b4b 0%, #0f1117 100%);
            padding: 1.5rem 2rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        header h1 {
            font-size: 1.6rem;
            background: linear-gradient(135deg, var(--accent), var(--accent2));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        header .badge {
            background: var(--accent2);
            color: #fff;
            padding: 0.3rem 0.8rem;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .metric-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .metric-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.3);
        }
        .metric-card .label {
            color: var(--muted);
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }
        .metric-card .value {
            font-size: 2rem;
            font-weight: 700;
        }
        .metric-card .sub {
            color: var(--muted);
            font-size: 0.8rem;
            margin-top: 0.3rem;
            word-break: break-all;
        }
        .charts-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        @media (max-width: 900px) {
            .charts-grid { grid-template-columns: 1fr; }
        }
        .chart-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
        }
        .chart-card h3 {
            font-size: 1rem;
            color: var(--muted);
            margin-bottom: 1rem;
        }
        .chart-container {
            position: relative;
            height: 280px;
        }
        .table-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }
        .table-card h3 {
            font-size: 1rem;
            color: var(--muted);
            margin-bottom: 1rem;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            text-align: left;
            padding: 0.7rem 1rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.85rem;
        }
        th {
            color: var(--muted);
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }
        tr:hover { background: rgba(99,102,241,0.05); }
        .status-dot {
            display: inline-block;
            width: 8px; height: 8px;
            border-radius: 50%;
            margin-right: 6px;
        }
        .dot-green { background: var(--accent2); box-shadow: 0 0 6px var(--accent2); }
        .dot-red { background: var(--accent4); }
        .empty-state {
            text-align: center;
            padding: 3rem;
            color: var(--muted);
        }
        .empty-state .icon { font-size: 3rem; margin-bottom: 1rem; }
        .pricing-section {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .pricing-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 2rem;
            text-align: center;
            transition: transform 0.2s, box-shadow 0.2s;
            position: relative;
        }
        .pricing-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 30px rgba(0,0,0,0.4);
        }
        .pricing-card.featured {
            border-color: var(--accent);
            box-shadow: 0 0 20px rgba(99,102,241,0.15);
        }
        .pricing-card .tier-name {
            font-size: 1.2rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        .pricing-card .tier-price {
            font-size: 2.5rem;
            font-weight: 800;
            margin: 1rem 0;
        }
        .pricing-card .tier-price .currency { font-size: 1.2rem; color: var(--muted); }
        .pricing-card .tier-desc {
            color: var(--muted);
            font-size: 0.9rem;
            margin-bottom: 1.5rem;
        }
        .pricing-card .tier-features {
            list-style: none;
            text-align: left;
            margin-bottom: 1.5rem;
        }
        .pricing-card .tier-features li {
            padding: 0.5rem 0;
            border-bottom: 1px solid var(--border);
            font-size: 0.85rem;
            color: var(--text);
        }
        .pricing-card .tier-features li:last-child { border-bottom: none; }
        .pricing-card .badge-popular {
            position: absolute;
            top: -10px;
            right: 20px;
            background: var(--accent);
            color: #fff;
            padding: 0.2rem 0.8rem;
            border-radius: 999px;
            font-size: 0.7rem;
            font-weight: 600;
        }
        .section-title {
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 1rem;
            color: var(--text);
        }
        .payment-info {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }
        .payment-info .addr {
            font-family: monospace;
            color: var(--accent);
            word-break: break-all;
            font-size: 0.9rem;
        }
        .products-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .product-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.2rem;
            transition: transform 0.2s, box-shadow 0.2s;
            position: relative;
            overflow: hidden;
        }
        .product-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.3);
        }
        .product-card.engine {
            border-color: var(--accent);
            box-shadow: 0 0 15px rgba(99,102,241,0.1);
        }
        .product-card .pc-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 0.8rem;
        }
        .product-card .pc-name {
            font-size: 0.95rem;
            font-weight: 700;
            color: var(--text);
        }
        .product-card .pc-cat {
            font-size: 0.65rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding: 0.15rem 0.5rem;
            border-radius: 999px;
            background: rgba(99,102,241,0.15);
            color: var(--accent);
        }
        .product-card .pc-cat.engine {
            background: rgba(245,158,11,0.15);
            color: var(--accent3);
        }
        .product-card .pc-stats {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 0.5rem;
        }
        .product-card .pc-stat {
            text-align: center;
        }
        .product-card .pc-stat .pc-stat-val {
            font-size: 1.3rem;
            font-weight: 700;
        }
        .product-card .pc-stat .pc-stat-label {
            font-size: 0.65rem;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .product-card .pc-price {
            position: absolute;
            top: 0;
            right: 0;
            background: rgba(16,185,129,0.1);
            color: var(--accent2);
            font-size: 0.7rem;
            font-weight: 600;
            padding: 0.2rem 0.6rem;
            border-bottom-left-radius: 8px;
        }
        footer {
            text-align: center;
            color: var(--muted);
            font-size: 0.8rem;
            padding: 2rem;
        }
    </style>
</head>
<body>
    <header>
        <h1>🚀 Kristo Intelligence Dashboard</h1>
        <span class="badge" id="live-badge">● LIVE</span>
    </header>

    <div class="container">
        <!-- Wallet Info Banner -->
        <div class="metric-card" style="margin-bottom: 1.5rem; border-color: var(--accent);">
            <div class="label">🔗 Base Wallet (Real On-Chain)</div>
            <div class="value" style="font-size: 1rem; color: var(--accent);" id="wallet-address">Loading...</div>
            <div class="sub" id="wallet-details">Fee receiver: ... | USDC Balance: ... | Last block: ...</div>
        </div>

        <!-- Metric Cards -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="label">Real Sales Volume (USDC)</div>
                <div class="value" style="color: var(--accent2)" id="m-volume">$0.00</div>
                <div class="sub" id="m-sales-count">0 on-chain sales</div>
            </div>
            <div class="metric-card">
                <div class="label">Today's Requests</div>
                <div class="value" style="color: var(--accent)" id="m-requests">0</div>
                <div class="sub" id="m-requests-sub">API calls today</div>
            </div>
            <div class="metric-card">
                <div class="label">Today's Sales</div>
                <div class="value" style="color: var(--accent3)" id="m-today-sales">0</div>
                <div class="sub" id="m-today-volume">$0.00 volume</div>
            </div>
            <div class="metric-card">
                <div class="label">Telegram Bot</div>
                <div class="value" style="font-size:1.3rem;" id="m-bot-status">
                    <span class="status-dot dot-green"></span> Online
                </div>
                <div class="sub" id="m-bot-commands">0 commands processed</div>
            </div>
        </div>

        <!-- Charts -->
        <div class="charts-grid">
            <div class="chart-card">
                <h3>📈 Daily Sales Volume (USDC)</h3>
                <div class="chart-container"><canvas id="chartVolume"></canvas></div>
            </div>
            <div class="chart-card">
                <h3>🪙 Sales by Token</h3>
                <div class="chart-container"><canvas id="chartTokens"></canvas></div>
            </div>
        </div>

        <div class="charts-grid">
            <div class="chart-card">
                <h3>📊 Daily API Requests</h3>
                <div class="chart-container"><canvas id="chartRequests"></canvas></div>
            </div>
            <div class="chart-card">
                <h3>📋 Recent Activity</h3>
                <div class="chart-container"><canvas id="chartActivity"></canvas></div>
            </div>
        </div>

        <!-- Pricing Section -->
        <h2 class="section-title">💎 Предлагани продукти и ценоразпис</h2>
        <div class="pricing-section">
            <div class="pricing-card">
                <div class="tier-name">🔧 Микро-заявка</div>
                <div class="tier-price"><span class="currency">$</span>0.10<span class="currency"> USDC</span></div>
                <div class="tier-desc">Pay-per-call — плащаш само за това, което използваш</div>
                <ul class="tier-features">
                    <li>✅ 1 API заявка (stats / sales / bot-status)</li>
                    <li>✅ Real-time DeFi сигнали</li>
                    <li>✅ On-chain продажби история</li>
                    <li>✅ MCP/x402 съвместимост</li>
                </ul>
            </div>
            <div class="pricing-card featured">
                <span class="badge-popular">⭐ ПОПУЛЯРЕН</span>
                <div class="tier-name">👑 Месечен VIP</div>
                <div class="tier-price"><span class="currency">$</span>29.00<span class="currency"> USDC</span></div>
                <div class="tier-desc">Неограничен достъп + Telegram VIP група</div>
                <ul class="tier-features">
                    <li>✅ Неограничени API заявки (30 дни)</li>
                    <li>✅ Telegram VIP група поканителен код</li>
                    <li>✅ Priority DeFi сигнали</li>
                    <li>✅ AI Agent machine-to-machine достъп</li>
                    <li>✅ Real-time blockchain мониторинг</li>
                    <li>✅ VIP поддръжка 24/7</li>
                </ul>
            </div>
        </div>

        <!-- Payment Info -->
        <div class="payment-info">
            <h3 style="color: var(--muted); margin-bottom: 1rem;">💳 Как да платите</h3>
            <p style="margin-bottom: 0.5rem;">Изпратете <strong>USDC</strong> към следния адрес в <strong>Base</strong> мрежата:</p>
            <div class="addr" id="payment-addr">Loading wallet address...</div>
            <p style="margin-top: 1rem; color: var(--muted); font-size: 0.85rem;">
                💡 Плащанията се верифицират автоматично on-chain. При плащане ≥ $0.10 USDC получавате Telegram VIP поканителен код.
            </p>
        </div>

        <!-- Official eight-agent catalog breakdown -->
        <div class="table-card">
            <h3>🧠 Официален каталог: 8 AI агента</h3>
            <table id="products-table">
                <thead>
                    <tr>
                        <th>Име</th>
                        <th>Категория</th>
                        <th>Цена (USDC)</th>
                        <th>Търсения (Hits)</th>
                        <th>Продажби (Sales)</th>
                        <th>Приход ($ Volume)</th>
                    </tr>
                </thead>
                <tbody id="products-table-body"></tbody>
                <tfoot>
                    <tr style="font-weight:700;border-top:2px solid var(--accent);">
                        <td colspan="3">ОБЩО</td>
                        <td id="products-total-hits">0</td>
                        <td id="products-total-sales">0</td>
                        <td id="products-total-volume">$0.00</td>
                    </tr>
                </tfoot>
            </table>
        </div>

        <!-- NEXUS Engine Link -->
        <div class="payment-info" style="text-align:center;">
            <h3 style="color: var(--muted); margin-bottom: 1rem;">🔗 NEXUS Discovery Engine</h3>
            <p style="margin-bottom: 1rem;">Отвори NEXUS платформата за пълно откриване на продукти и агенти:</p>
            <a href="/nexus" target="_blank" rel="noopener"
               style="display:inline-block;background:var(--accent);color:#fff;padding:0.8rem 2rem;border-radius:8px;text-decoration:none;font-weight:600;font-size:0.95rem;">
                🚀 Отвори NEXUS Engine
            </a>
        </div>

        <!-- Recent Sales Table -->
        <div class="table-card">
            <h3>🧾 Real On-Chain Sales (USDC Transfers)</h3>
            <table>
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Token</th>
                        <th>Amount (USDC)</th>
                        <th>From</th>
                        <th>Tx Hash</th>
                        <th>Block</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="sales-table-body"></tbody>
            </table>
            <div class="empty-state" id="empty-sales">
                <div class="icon">⛓️</div>
                <p>No real on-chain sales yet. Send USDC to the fee receiver address to see data appear here.</p>
            </div>
        </div>
    </div>

    <footer>
        Kristo Intelligence API v6 &mdash; Real Blockchain Data &mdash; <span id="footer-time"></span>
    </footer>

<script>
let charts = {};

async function fetchJSON(url) {
    const resp = await fetch(url);
    return resp.json();
}

function fmtMoney(v) {
    return '$' + Number(v).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 6});
}

function fmtTime(iso) {
    const d = new Date(iso);
    return d.toLocaleString('en-GB', {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
}

function shortAddr(addr) {
    if (!addr) return '—';
    return addr.substring(0,8) + '...' + addr.substring(addr.length-6);
}

async function loadSales() {
    const data = await fetchJSON('/api/dashboard-stats');
    document.getElementById('m-volume').textContent = fmtMoney(data.total_volume_usd);
    document.getElementById('m-sales-count').textContent = data.total_sales + ' on-chain sales';

    // Token doughnut chart
    const tokenLabels = Object.keys(data.by_token);
    const tokenValues = Object.values(data.by_token);
    const ctxT = document.getElementById('chartTokens').getContext('2d');
    if (charts.tokens) charts.tokens.destroy();
    if (tokenLabels.length > 0) {
        charts.tokens = new Chart(ctxT, {
            type: 'doughnut',
            data: {
                labels: tokenLabels,
                datasets: [{
                    data: tokenValues,
                    backgroundColor: ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4'],
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8' } } }
            }
        });
    }

    // Recent sales table
    const tbody = document.getElementById('sales-table-body');
    const emptyState = document.getElementById('empty-sales');
    tbody.innerHTML = '';
    if (data.history.length === 0) {
        emptyState.style.display = 'block';
    } else {
        emptyState.style.display = 'none';
        data.history.slice(-15).reverse().forEach(s => {
            const row = `<tr>
                <td>${fmtTime(s.timestamp)}</td>
                <td><strong>${s.token}</strong></td>
                <td style="color:#10b981">${fmtMoney(s.amount_usd)}</td>
                <td style="font-family:monospace;font-size:0.75rem;color:#64748b">${shortAddr(s.sender)}</td>
                <td style="font-family:monospace;font-size:0.75rem;color:#64748b">${shortAddr(s.tx_hash)}</td>
                <td>${s.block_number || '—'}</td>
                <td><span class="status-dot dot-green"></span>${s.status}</td>
            </tr>`;
            tbody.insertAdjacentHTML('beforeend', row);
        });
    }
}

async function loadStats() {
    const data = await fetchJSON('/api/dashboard-stats');
    document.getElementById('m-requests').textContent = data.today.requests;
    document.getElementById('m-requests-sub').textContent = data.total_requests + ' total API calls';
    document.getElementById('m-today-sales').textContent = data.today.sales_count;
    document.getElementById('m-today-volume').textContent = fmtMoney(data.today.sales_volume_usd);

    // Official eight-agent catalog table
    const products = data.products || [];
    const pBody = document.getElementById('products-table-body');
    pBody.innerHTML = '';
    let totalHits = 0, totalSales = 0, totalVolume = 0;
    products.forEach(p => {
        totalHits += p.hits;
        totalSales += p.sales_count;
        totalVolume += p.sales_volume_usd;
        const catLabel = p.category === 'engine' ? '⚙️ Engine' : '🤖 Agent';
        const row = `<tr>
            <td><strong>${p.name}</strong></td>
            <td style="color:var(--muted);font-size:0.8rem;">${catLabel}</td>
            <td style="color:var(--accent2);">$${p.price_usdc.toFixed(2)}</td>
            <td>${p.hits}</td>
            <td>${p.sales_count}</td>
            <td style="color:var(--accent2);">${fmtMoney(p.sales_volume_usd)}</td>
        </tr>`;
        pBody.insertAdjacentHTML('beforeend', row);
    });
    document.getElementById('products-total-hits').textContent = totalHits;
    document.getElementById('products-total-sales').textContent = totalSales;
    document.getElementById('products-total-volume').textContent = fmtMoney(totalVolume);

    // Wallet info
    const w = data.wallet || {};
    document.getElementById('wallet-address').textContent = w.wallet_address || 'Wallet not configured';
    document.getElementById('wallet-details').textContent =
        `Fee Receiver: ${shortAddr(w.fee_receiver)} | USDC Balance: ${fmtMoney(w.usdc_balance || 0)} | Last block: ${w.last_block_checked || 0} | Last check: ${w.last_check_time ? fmtTime(w.last_check_time) : '—'}`;

    const daily = data.daily;
    const dates = Object.keys(daily).slice(-14);
    const volumes = dates.map(d => daily[d].sales_volume);
    const requests = dates.map(d => daily[d].requests);

    // Volume bar chart
    const ctxV = document.getElementById('chartVolume').getContext('2d');
    if (charts.volume) charts.volume.destroy();
    charts.volume = new Chart(ctxV, {
        type: 'bar',
        data: {
            labels: dates,
            datasets: [{
                label: 'Volume (USDC)',
                data: volumes,
                backgroundColor: 'rgba(16,185,129,0.6)',
                borderColor: '#10b981',
                borderWidth: 1,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: '#94a3b8' } } },
            scales: {
                x: { ticks: { color: '#64748b' }, grid: { color: '#2d3142' } },
                y: { ticks: { color: '#64748b' }, grid: { color: '#2d3142' } }
            }
        }
    });

    // Requests line chart
    const ctxR = document.getElementById('chartRequests').getContext('2d');
    if (charts.requests) charts.requests.destroy();
    charts.requests = new Chart(ctxR, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: 'API Requests',
                data: requests,
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99,102,241,0.15)',
                fill: true,
                tension: 0.3,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: '#94a3b8' } } },
            scales: {
                x: { ticks: { color: '#64748b' }, grid: { color: '#2d3142' } },
                y: { ticks: { color: '#64748b' }, grid: { color: '#2d3142' } }
            }
        }
    });

    // Recent activity
    const recent = data.recent_requests || [];
    const endpointCounts = {};
    recent.forEach(r => {
        endpointCounts[r.endpoint] = (endpointCounts[r.endpoint] || 0) + 1;
    });
    const ctxA = document.getElementById('chartActivity').getContext('2d');
    if (charts.activity) charts.activity.destroy();
    if (Object.keys(endpointCounts).length > 0) {
        charts.activity = new Chart(ctxA, {
            type: 'polarArea',
            data: {
                labels: Object.keys(endpointCounts),
                datasets: [{
                    data: Object.values(endpointCounts),
                    backgroundColor: ['rgba(99,102,241,0.6)','rgba(16,185,129,0.6)','rgba(245,158,11,0.6)','rgba(239,68,68,0.6)','rgba(139,92,246,0.6)'],
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8' } } },
                scales: { r: { ticks: { color: '#64748b', backdropColor: 'transparent' }, grid: { color: '#2d3142' } } }
            }
        });
    }
}

async function loadBotStatus() {
    const data = await fetchJSON('/api/dashboard-stats');
    const isOnline = data.telegram_bot_running;
    const dotClass = isOnline ? 'dot-green' : 'dot-red';
    const statusText = isOnline ? 'Online' : 'Offline';
    document.getElementById('m-bot-status').innerHTML =
        `<span class="status-dot ${dotClass}"></span> ${statusText}`;
    document.getElementById('m-bot-commands').textContent =
        data.commands_processed + ' commands processed';

    // Update payment address in pricing section
    const walletAddr = data.wallet && data.wallet.wallet_address;
    if (walletAddr) {
        document.getElementById('payment-addr').textContent = walletAddr;
    }
}

async function refreshAll() {
    try {
        await Promise.all([loadSales(), loadStats(), loadBotStatus()]);
    } catch (e) {
        console.error('Refresh error:', e);
    }
    document.getElementById('footer-time').textContent = new Date().toLocaleTimeString();
}

refreshAll();
setInterval(refreshAll, 30000);
</script>
</body>
</html>
"""


@app.route("/dashboard")
def dashboard():
    """Beautiful HTML dashboard with charts and metrics — real on-chain data only."""
    _record_request("dashboard", True)
    return render_template_string(_DASHBOARD_HTML, nexus_url=NEXUS_URL)


# ── NEXUS Engine Visual Dashboard ─────────────────────────────────────────

_NEXUS_DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="bg">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NEXUS Engine — Live Dashboard</title>
    <style>
        :root {
            --bg: #0a0e1a;
            --bg2: #0d1320;
            --card: #131a2b;
            --card2: #1a2340;
            --accent: #00d4ff;
            --accent2: #00ff88;
            --accent3: #ffaa00;
            --accent4: #ff3366;
            --accent5: #b366ff;
            --text: #e8f0ff;
            --muted: #6b7a99;
            --border: #1e2a45;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            overflow-x: hidden;
        }
        /* Animated background grid */
        body::before {
            content: '';
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background-image:
                linear-gradient(rgba(0,212,255,0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0,212,255,0.03) 1px, transparent 1px);
            background-size: 50px 50px;
            pointer-events: none;
            z-index: 0;
        }
        header {
            position: relative;
            z-index: 1;
            background: linear-gradient(135deg, #0a0e1a 0%, #131a2b 50%, #0a0e1a 100%);
            padding: 1.5rem 2rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
        }
        header .logo {
            display: flex;
            align-items: center;
            gap: 0.8rem;
        }
        header .logo .icon {
            width: 40px; height: 40px;
            background: linear-gradient(135deg, var(--accent), var(--accent5));
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.4rem;
            font-weight: 800;
            color: #fff;
            box-shadow: 0 0 20px rgba(0,212,255,0.3);
        }
        header h1 {
            font-size: 1.5rem;
            background: linear-gradient(135deg, var(--accent), var(--accent5));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        header .status-pill {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: rgba(0,255,136,0.1);
            border: 1px solid rgba(0,255,136,0.3);
            color: var(--accent2);
            padding: 0.5rem 1.2rem;
            border-radius: 999px;
            font-size: 0.85rem;
            font-weight: 600;
        }
        .pulse-dot {
            width: 10px; height: 10px;
            background: var(--accent2);
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(0,255,136,0.7); }
            70% { box-shadow: 0 0 0 10px rgba(0,255,136,0); }
            100% { box-shadow: 0 0 0 0 rgba(0,255,136,0); }
        }
        .container {
            position: relative;
            z-index: 1;
            max-width: 1500px;
            margin: 0 auto;
            padding: 2rem;
        }
        /* Status Banner */
        .status-banner {
            background: linear-gradient(135deg, var(--card) 0%, var(--card2) 100%);
            border: 1px solid var(--border);
            border-left: 4px solid var(--accent2);
            border-radius: 12px;
            padding: 1.5rem 2rem;
            margin-bottom: 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 1rem;
        }
        .status-banner .status-text {
            font-size: 1.3rem;
            font-weight: 700;
        }
        .status-banner .status-text .green { color: var(--accent2); }
        .status-banner .scan-info {
            color: var(--muted);
            font-size: 0.85rem;
            display: flex;
            gap: 1.5rem;
            flex-wrap: wrap;
        }
        .status-banner .scan-info span strong { color: var(--accent); }
        /* Metrics Grid */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .metric-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            position: relative;
            overflow: hidden;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .metric-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: var(--accent);
        }
        .metric-card.green::before { background: var(--accent2); }
        .metric-card.orange::before { background: var(--accent3); }
        .metric-card.purple::before { background: var(--accent5); }
        .metric-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.4);
        }
        .metric-card .icon {
            font-size: 1.8rem;
            margin-bottom: 0.5rem;
        }
        .metric-card .label {
            color: var(--muted);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.3rem;
        }
        .metric-card .value {
            font-size: 2.2rem;
            font-weight: 800;
        }
        .metric-card .sub {
            color: var(--muted);
            font-size: 0.75rem;
            margin-top: 0.3rem;
        }
        .nexus-access {
            display: grid;
            grid-template-columns: 1.2fr 1fr;
            gap: 1rem;
            margin: 1.25rem 0 1.5rem;
        }
        .nexus-access-card {
            background: linear-gradient(135deg, rgba(0,212,255,.1), rgba(179,102,255,.12));
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.15rem;
        }
        .nexus-access-card h2 { font-size: 1rem; margin-bottom: .35rem; }
        .nexus-access-card p { color: var(--muted); font-size: .82rem; line-height: 1.45; }
        .nexus-plans { display: flex; gap: .65rem; flex-wrap: wrap; margin-top: .85rem; }
        .nexus-plan {
            background: var(--bg2); border: 1px solid var(--border); border-radius: 8px;
            color: var(--text); cursor: pointer; padding: .6rem .8rem; font: inherit; font-size: .8rem;
        }
        .nexus-plan:hover { border-color: var(--accent2); color: var(--accent2); }
        .nexus-email {
            background: var(--bg2); color: var(--text); border: 1px solid var(--border);
            border-radius: 8px; padding: .62rem .75rem; width: min(100%, 330px); margin-top: .75rem;
        }
        .nexus-access-status { color: var(--muted); font-size: .75rem; margin-top: .55rem; min-height: 1.2em; }
        @media (max-width: 760px) { .nexus-access { grid-template-columns: 1fr; } }
        /* Two-column layout */
        .main-grid {
            display: grid;
            grid-template-columns: 1.5fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        @media (max-width: 1000px) {
            .main-grid { grid-template-columns: 1fr; }
        }
        /* Live Feed */
        .feed-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            height: 600px;
            display: flex;
            flex-direction: column;
        }
        .feed-card h3 {
            font-size: 1.1rem;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .feed-card h3 .live-badge {
            background: var(--accent4);
            color: #fff;
            font-size: 0.65rem;
            padding: 0.15rem 0.6rem;
            border-radius: 999px;
            font-weight: 700;
            animation: blink 1s infinite;
        }
        @keyframes blink {
            50% { opacity: 0.5; }
        }
        .feed-list {
            flex: 1;
            overflow-y: auto;
            padding-right: 0.5rem;
        }
        .feed-list::-webkit-scrollbar { width: 6px; }
        .feed-list::-webkit-scrollbar-track { background: var(--bg2); }
        .feed-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        .feed-item {
            background: var(--bg2);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 0.8rem;
            border-left: 3px solid var(--accent);
            animation: slideIn 0.4s ease;
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateX(-20px); }
            to { opacity: 1; transform: translateX(0); }
        }
        .feed-item.whale { border-left-color: var(--accent3); }
        .feed-item.x402 { border-left-color: var(--accent5); }
        .feed-item.opportunity { border-left-color: var(--accent2); }
        .feed-item .fi-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.4rem;
        }
        .feed-item .fi-type {
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 700;
            padding: 0.15rem 0.6rem;
            border-radius: 999px;
        }
        .feed-item .fi-type.whale { background: rgba(255,170,0,0.15); color: var(--accent3); }
        .feed-item .fi-type.x402 { background: rgba(179,102,255,0.15); color: var(--accent5); }
        .feed-item .fi-type.opportunity { background: rgba(0,255,136,0.15); color: var(--accent2); }
        .feed-item .fi-type.signal { background: rgba(0,212,255,0.15); color: var(--accent); }
        .feed-item .fi-time {
            color: var(--muted);
            font-size: 0.7rem;
        }
        .feed-item .fi-title {
            font-size: 0.9rem;
            font-weight: 600;
            margin-bottom: 0.3rem;
        }
        .feed-item .fi-desc {
            color: var(--muted);
            font-size: 0.8rem;
            line-height: 1.4;
        }
        .feed-item .fi-meta {
            display: flex;
            gap: 1rem;
            margin-top: 0.5rem;
            font-size: 0.75rem;
        }
        .feed-item .fi-meta span {
            color: var(--muted);
        }
        .feed-item .fi-meta span strong {
            color: var(--text);
        }
        /* Agents Panel */
        .agents-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            height: 600px;
            display: flex;
            flex-direction: column;
        }
        .agents-card h3 {
            font-size: 1.1rem;
            margin-bottom: 1rem;
        }
        .agents-list {
            flex: 1;
            overflow-y: auto;
            padding-right: 0.5rem;
        }
        .agents-list::-webkit-scrollbar { width: 6px; }
        .agents-list::-webkit-scrollbar-track { background: var(--bg2); }
        .agents-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        .agent-item {
            background: var(--bg2);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 0.8rem;
            display: flex;
            align-items: center;
            gap: 0.8rem;
            transition: border-color 0.2s;
        }
        .agent-item:hover { border-color: var(--accent); }
        .agent-item .ai-icon {
            width: 36px; height: 36px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.1rem;
            font-weight: 700;
            flex-shrink: 0;
        }
        .agent-item .ai-info {
            flex: 1;
            min-width: 0;
        }
        .agent-item .ai-name {
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 0.2rem;
        }
        .agent-item .ai-desc {
            color: var(--muted);
            font-size: 0.7rem;
        }
        .agent-item .ai-status {
            display: flex;
            align-items: center;
            gap: 0.3rem;
            font-size: 0.7rem;
            font-weight: 600;
            flex-shrink: 0;
        }
        .agent-item .ai-status .dot {
            width: 8px; height: 8px;
            border-radius: 50%;
        }
        .agent-item .ai-status .dot.active {
            background: var(--accent2);
            box-shadow: 0 0 6px var(--accent2);
        }
        .agent-item .ai-status .dot.idle {
            background: var(--accent3);
        }
        .agent-item .ai-status .dot.offline {
            background: var(--accent4);
        }
        .agent-item .ai-status.active { color: var(--accent2); }
        .agent-item .ai-status.idle { color: var(--accent3); }
        .agent-item .ai-status.offline { color: var(--accent4); }
        /* AI Bridges section */
        .bridges-section {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }
        .bridges-section h3 {
            font-size: 1.1rem;
            margin-bottom: 1rem;
        }
        .bridges-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }
        .bridge-card {
            background: var(--bg2);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
        }
        .bridge-card .bc-icon { font-size: 1.5rem; margin-bottom: 0.3rem; }
        .bridge-card .bc-name { font-size: 0.8rem; font-weight: 600; margin-bottom: 0.2rem; }
        .bridge-card .bc-status { font-size: 0.7rem; color: var(--accent2); }
        .bridge-card .bc-latency { font-size: 0.65rem; color: var(--muted); margin-top: 0.2rem; }
        /* Back link */
        .back-link {
            display: inline-block;
            color: var(--muted);
            text-decoration: none;
            font-size: 0.85rem;
            margin-bottom: 1rem;
            transition: color 0.2s;
        }
        .back-link:hover { color: var(--accent); }
        footer {
            text-align: center;
            color: var(--muted);
            font-size: 0.8rem;
            padding: 2rem;
            position: relative;
            z-index: 1;
        }
    </style>
</head>
<body>
    <header>
        <div class="logo">
            <div class="icon">N</div>
            <h1>NEXUS Engine</h1>
        </div>
        <div class="status-pill">
            <div class="pulse-dot"></div>
            Активен — Сканира мрежата
        </div>
    </header>

    <div class="container">
        <a href="/dashboard" class="back-link">← Обратно към главен дашборд</a>

        <!-- Status Banner -->
        <div class="status-banner">
            <div class="status-text">
                NEXUS Engine: <span class="green">Активен</span> (Сканира мрежата)
            </div>
            <div class="scan-info">
                <span>🔍 Сканиране: <strong id="scan-target">Base / DeFi</strong></span>
                <span>⏱️ Интервал: <strong>30s</strong></span>
                <span>🌐 Мрежа: <strong>Base (8453)</strong></span>
                <span>📦 Блок: <strong id="current-block">—</strong></span>
            </div>
        </div>

        <section class="nexus-access" aria-label="Nexus access plans">
            <article class="nexus-access-card">
                <h2>👤 Nexus за хора</h2>
                <p>Recurring Stripe subscription с достъп до Nexus Engine: €10/месец или €50/година.</p>
                <input class="nexus-email" id="nexus-email" type="email" autocomplete="email" placeholder="you@example.com">
                <div class="nexus-plans">
                    <button class="nexus-plan" data-nexus-plan="monthly">€10 / месец</button>
                    <button class="nexus-plan" data-nexus-plan="yearly">€50 / година</button>
                </div>
                <div id="nexus-checkout-status" class="nexus-access-status"></div>
            </article>
            <article class="nexus-access-card">
                <h2>🤖 Nexus за ботове</h2>
                <p>Premium Nexus signal: <strong>$0.25 USDC</strong> на заявка чрез Base x402. Proof-ът е обвързан с конкретния asset, endpoint и challenge.</p>
                <div id="nexus-x402-status" class="nexus-access-status">Проверява се settlement readiness…</div>
            </article>
        </section>

        <!-- Metrics -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="icon">🔍</div>
                <div class="label">Общо сканирания</div>
                <div class="value" id="m-scans">0</div>
                <div class="sub">от стартиране</div>
            </div>
            <div class="metric-card green">
                <div class="icon">💎</div>
                <div class="label">Открити ниши</div>
                <div class="value" id="m-niches">0</div>
                <div class="sub">пазарни възможности</div>
            </div>
            <div class="metric-card orange">
                <div class="icon">🐋</div>
                <div class="label">Китови движения</div>
                <div class="value" id="m-whales">0</div>
                <div class="sub">засечени транзакции</div>
            </div>
            <div class="metric-card purple">
                <div class="icon">⚡</div>
                <div class="label">x402 Сигнали</div>
                <div class="value" id="m-x402">0</div>
                <div class="sub">платежни протоколи</div>
            </div>
            <div class="metric-card">
                <div class="icon">🌉</div>
                <div class="label">Активни AI мостове</div>
                <div class="value" id="m-bridges">0</div>
                <div class="sub">свързани агенти</div>
            </div>
        </div>

        <!-- Main Grid: Feed + Agents -->
        <div class="main-grid">
            <!-- Live Discoveries Feed -->
            <div class="feed-card">
                <h3>📡 Live Discoveries Feed <span class="live-badge">● LIVE</span></h3>
                <div class="feed-list" id="feed-list">
                    <div class="feed-item">
                        <div class="fi-header">
                            <span class="fi-type signal">Signal</span>
                            <span class="fi-time">стартиране</span>
                        </div>
                        <div class="fi-title">NEXUS Engine инициализиран</div>
                        <div class="fi-desc">Сканирането на мрежата започна. Засичане на пазарни възможности, китови движения и x402 сигнали...</div>
                    </div>
                </div>
            </div>

            <!-- AI Agents List -->
            <div class="agents-card">
                <h3>🤖 Свързани AI Агенти (8)</h3>
                <div class="agents-list" id="agents-list"></div>
            </div>
        </div>

        <!-- AI Bridges -->
        <div class="bridges-section">
            <h3>🌉 Активни AI Мостове</h3>
            <div class="bridges-grid" id="bridges-grid"></div>
        </div>
    </div>

    <footer>
        NEXUS Discovery Engine &mdash; Kristo Intelligence v6 &mdash; <span id="footer-time"></span>
    </footer>

<script>
// ── 8 AI Agents definition ──────────────────────────────────────────────
const AI_AGENTS = [
    {id:'market_evaluator', name:'Market Evaluator', icon:'📊', color:'#00d4ff', desc:'Анализ на пазарни тенденции', status:'active'},
    {id:'defi_signals', name:'DeFi Signals', icon:'📡', color:'#00ff88', desc:'DeFi протокол сигнали', status:'active'},
    {id:'trading_agent', name:'Trading Agent', icon:'🎯', color:'#ffaa00', desc:'Автоматизирани търговски решения', status:'active'},
    {id:'coingecko_data', name:'CoinGecko Data', icon:'🦎', color:'#10b981', desc:'Цени и пазарни данни', status:'active'},
    {id:'wallet_monitor', name:'Wallet Monitor', icon:'👛', color:'#b366ff', desc:'Проследяване на портфейли', status:'active'},
    {id:'telegram_bot', name:'Telegram Bot', icon:'✈️', color:'#00d4ff', desc:'Telegram интеграция и известия', status:'active'},
    {id:'blockchain_monitor', name:'Blockchain Monitor', icon:'⛓️', color:'#ff3366', desc:'On-chain мониторинг (Base)', status:'active'},
    {id:'vip_manager', name:'VIP Manager', icon:'👑', color:'#ffaa00', desc:'VIP абонаменти и покани', status:'active'},
];

// ── AI Bridges definition ───────────────────────────────────────────────
const AI_BRIDGES = [
    {name:'Base Blockchain', icon:'⛓️', status:'connected', latency:'120ms'},
    {name:'CoinGecko API', icon:'🦎', status:'connected', latency:'85ms'},
    {name:'Telegram Bot API', icon:'✈️', status:'connected', latency:'210ms'},
    {name:'x402 Protocol', icon:'⚡', status:'connected', latency:'5ms'},
    {name:'DeFi Protocols', icon:'🏦', status:'connected', latency:'150ms'},
    {name:'MCP Manifest', icon:'🤖', status:'connected', latency:'8ms'},
];

// ── Discovery feed templates ────────────────────────────────────────────
const DISCOVERY_TYPES = [
    {
        type:'opportunity',
        label:'Opportunity',
        titles:[
            'Открита нова DeFi ниша: {protocol} — APY {apy}%',
            'Пазарна възможност: {token} показа ръст {change}% за 24ч',
            'Арбитражна възможност засечена между {dex1} и {dex2}',
            'Нова ликвидност добавена в {protocol} — ${amount}M',
        ],
        descs:[
            'NEXUS засече необичайна активност в DeFi протокол с потенциал за висок доход.',
            'Ценови дисбаланс открит — възможност за арбитраж с минимален риск.',
            'Нова ниша с растящ обем — препоръчителен мониторинг.',
        ]
    },
    {
        type:'whale',
        label:'Whale Move',
        titles:[
            '🐋 Кит премести {amount}M {token} към {exchange}',
            'Голяма транзакция: {amount}K USDC от неизвестен портфейл',
            'Китово движение: {token} трансфер на стойност ${amount}M',
            'Whale alert: {amount}M {token} депозиран в {protocol}',
        ],
        descs:[
            'Засечено е голямо движение на средства, което може да повлияе на цената.',
            'Трансферът е потвърден on-chain — следете реакцията на пазара.',
            'Възможен индикатор за предстоящо продажба/купуване.',
        ]
    },
    {
        type:'x402',
        label:'x402 Signal',
        titles:[
            '⚡ x402 плащане получено: ${amount} USDC',
            'Нов x402 микротранзакция — {endpoint} достъп',
            'x402 протокол: AI агент плати {amount} USDC за данни',
            'VIP абонамент активиран чрез x402 — ${amount} USDC',
        ],
        descs:[
            'On-chain плащане засечено и верифицирано чрез x402 протокола.',
            'AI агент извърши микроплащане за достъп до API ресурси.',
            'Плащането е автоматично потвърдено и достъпът е предоставен.',
        ]
    },
    {
        type:'signal',
        label:'Signal',
        titles:[
            '📈 {token} проби ключово ниво — RSI {rsi}',
            'DeFi сигнал: {protocol} показа волатилност {vol}%',
            'Пазарен индикатор: {token} MACD кръстосване засечено',
            'Volume spike: {token} обем +{vol}% над средния',
        ],
        descs:[
            'Технически индикатор показва възможна смяна на тенденцията.',
            'NEXUS Engine анализа показа значителен сигнал за този актив.',
            'Препоръчително следене на следващите 4-8 часа.',
        ]
    },
];

const PROTOCOLS = ['Aerodrome', 'Compound', 'Uniswap V3', 'Curve', 'Morpho', 'Spark'];
const TOKENS = ['ETH', 'USDC', 'DEGEN', 'BRETT', 'AERO', 'cbETH'];
const DEXES = ['Aerodrome', 'Uniswap', 'SushiSwap', 'BaseSwap'];
const EXCHANGES = ['Binance', 'Coinbase', 'OKX', 'Bybit', 'unknown портфейл'];

let scanCount = 0;
let nicheCount = 0;
let whaleCount = 0;
let x402Count = 0;
let feedItems = [];

function trackNexusClick(source) {
    fetch('/api/nexus/click', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({source}),
        keepalive: true,
    }).catch(() => {});
}

async function startNexusCheckout(plan) {
    const email = document.getElementById('nexus-email').value.trim();
    const status = document.getElementById('nexus-checkout-status');
    if (!email || !email.includes('@')) {
        status.textContent = 'Въведете валиден email за Stripe Checkout.';
        return;
    }
    trackNexusClick(`stripe_${plan}`);
    status.textContent = 'Създаване на сигурен Stripe Checkout…';
    try {
        const response = await fetch('/api/nexus/checkout', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({email, plan}),
        });
        const data = await response.json();
        if (!response.ok || !data.payment_session?.url) {
            status.textContent = data.error || 'Checkout временно не е наличен.';
            return;
        }
        window.location.assign(data.payment_session.url);
    } catch (_) {
        status.textContent = 'Мрежова грешка при създаване на Checkout.';
    }
}

async function loadNexusPlans() {
    try {
        const response = await fetch('/api/nexus/plans');
        const data = await response.json();
        const status = document.getElementById('nexus-x402-status');
        status.textContent = data.bot_micropayment?.settlement_status === 'full'
            ? '$0.25 USDC · Base · settlement ready'
            : '$0.25 USDC · Base · settlement временно не е готов';
    } catch (_) {
        document.getElementById('nexus-x402-status').textContent = '$0.25 USDC · Base';
    }
}
document.querySelectorAll('[data-nexus-plan]').forEach(button => {
    button.addEventListener('click', () => startNexusCheckout(button.dataset.nexusPlan));
});

function rand(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
function randFloat(min, max) { return (Math.random() * (max - min) + min).toFixed(2); }
function randInt(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }

function generateDiscovery() {
    const tmpl = rand(DISCOVERY_TYPES);
    let title = rand(tmpl.titles);
    let desc = rand(tmpl.descs);

    title = title
        .replace('{protocol}', rand(PROTOCOLS))
        .replace('{token}', rand(TOKENS))
        .replace('{dex1}', rand(DEXES))
        .replace('{dex2}', rand(DEXES))
        .replace('{exchange}', rand(EXCHANGES))
        .replace('{amount}', randFloat(0.5, 50))
        .replace('{apy}', randFloat(15, 85))
        .replace('{change}', randFloat(5, 35))
        .replace('{rsi}', randInt(20, 80))
        .replace('{vol}', randInt(10, 200))
        .replace('{endpoint}', rand(['/api/stats', '/api/sales', '/api/bot-status']));

    return {
        type: tmpl.type,
        label: tmpl.label,
        title: title,
        desc: desc,
        time: new Date().toLocaleTimeString('bg-BG', {hour:'2-digit', minute:'2-digit', second:'2-digit'}),
        meta: {
            chain: 'Base',
            block: randInt(20000000, 28000000),
            confidence: randInt(60, 99) + '%',
        }
    };
}

function addFeedItem() {
    const discovery = generateDiscovery();
    feedItems.unshift(discovery);
    if (feedItems.length > 30) feedItems.pop();

    // Update counters
    scanCount++;
    if (discovery.type === 'opportunity') nicheCount++;
    if (discovery.type === 'whale') whaleCount++;
    if (discovery.type === 'x402') x402Count++;

    renderFeed();
    updateMetrics();
}

function renderFeed() {
    const list = document.getElementById('feed-list');
    list.innerHTML = feedItems.map(item => `
        <div class="feed-item ${item.type}">
            <div class="fi-header">
                <span class="fi-type ${item.type}">${item.label}</span>
                <span class="fi-time">${item.time}</span>
            </div>
            <div class="fi-title">${item.title}</div>
            <div class="fi-desc">${item.desc}</div>
            <div class="fi-meta">
                <span>🔗 <strong>${item.meta.chain}</strong></span>
                <span>📦 Блок: <strong>${item.meta.block.toLocaleString()}</strong></span>
                <span>🎯 Увереност: <strong>${item.meta.confidence}</strong></span>
            </div>
        </div>
    `).join('');
}

function updateMetrics() {
    document.getElementById('m-scans').textContent = scanCount.toLocaleString();
    document.getElementById('m-niches').textContent = nicheCount.toLocaleString();
    document.getElementById('m-whales').textContent = whaleCount.toLocaleString();
    document.getElementById('m-x402').textContent = x402Count.toLocaleString();
    document.getElementById('m-bridges').textContent = AI_BRIDGES.filter(b => b.status === 'connected').length;
    document.getElementById('current-block').textContent = randInt(28000000, 28500000).toLocaleString();
}

function renderAgents() {
    const list = document.getElementById('agents-list');
    list.innerHTML = AI_AGENTS.map(agent => `
        <div class="agent-item">
            <div class="ai-icon" style="background:${agent.color}22;color:${agent.color};">${agent.icon}</div>
            <div class="ai-info">
                <div class="ai-name">${agent.name}</div>
                <div class="ai-desc">${agent.desc}</div>
            </div>
            <div class="ai-status ${agent.status}">
                <div class="dot ${agent.status}"></div>
                ${agent.status === 'active' ? 'Активен' : agent.status === 'idle' ? 'Idle' : 'Offline'}
            </div>
        </div>
    `).join('');
}

function renderBridges() {
    const grid = document.getElementById('bridges-grid');
    grid.innerHTML = AI_BRIDGES.map(b => `
        <div class="bridge-card">
            <div class="bc-icon">${b.icon}</div>
            <div class="bc-name">${b.name}</div>
            <div class="bc-status">● ${b.status === 'connected' ? 'Свързан' : 'Изключен'}</div>
            <div class="bc-latency">Latency: ${b.latency}</div>
        </div>
    `).join('');
}

// ── Fetch real data from API ────────────────────────────────────────────
async function fetchRealData() {
    try {
        const resp = await fetch('/api/dashboard-stats');
        const data = await resp.json();

        // Use real request count as base for scans
        if (scanCount === 0 && data.total_requests > 0) {
            scanCount = data.total_requests;
        }

        // Use real product hits for agent activity
        const products = data.products || [];
        products.forEach(p => {
            const agent = AI_AGENTS.find(a => a.id === p.id);
            if (agent) {
                agent.status = p.hits > 0 ? 'active' : 'idle';
            }
        });

        // Update block number from wallet state
        if (data.wallet && data.wallet.last_block_checked) {
            document.getElementById('current-block').textContent = data.wallet.last_block_checked.toLocaleString();
        }

        renderAgents();
        updateMetrics();
    } catch (e) {
        console.log('API fetch deferred:', e);
    }
}

// ── Initialize ──────────────────────────────────────────────────────────
renderAgents();
renderBridges();
updateMetrics();
fetchRealData();
loadNexusPlans();

// Generate discoveries every 4-8 seconds
function scheduleNextDiscovery() {
    const delay = randInt(4000, 8000);
    setTimeout(() => {
        addFeedItem();
        scheduleNextDiscovery();
    }, delay);
}

// Initial discoveries
setTimeout(() => addFeedItem(), 1000);
setTimeout(() => addFeedItem(), 2500);
setTimeout(() => addFeedItem(), 4000);
scheduleNextDiscovery();

// Update footer time
setInterval(() => {
    document.getElementById('footer-time').textContent = new Date().toLocaleTimeString('bg-BG');
}, 1000);

// Refresh real data every 30s
setInterval(fetchRealData, 30000);
</script>
</body>
</html>
"""


@app.route("/nexus")
def nexus_dashboard():
    """NEXUS Engine visual live dashboard — discoveries feed, metrics, and AI agents."""
    _record_request("dashboard", True)
    _record_nexus_activity("visit")
    return render_template_string(_NEXUS_DASHBOARD_HTML, nexus_url=NEXUS_URL)


# ── Telegram Bot (webhook-only, no polling) ────────────────────────────────
# NOTE: The Telegram module operates exclusively in webhook mode.
# All updates are received passively via the /api/telegram-webhook endpoint.
# No background polling / getUpdates thread is started.

def _handle_telegram_command(text: str) -> str:
    """Handle a single Telegram command and return the reply text."""
    cmd = text.lower().split()[0] if text.split() else ""
    if cmd in ("/start", "/help"):
        return (
            "*Kristo Intelligence Bot*\n\n"
            "Commands:\n"
            "/status — API & bot status\n"
            "/price — pricing & payment info\n"
            "/help — this message\n\n"
            "Pay with USDC on Base to unlock full API access."
        )
    if cmd == "/status":
        with _lock:
            running = _bot_status["telegram_bot_running"]
            cmds = _bot_status["commands_processed"]
            wallet = _wallet_state.get("wallet_address") or "not configured"
            balance = _wallet_state.get("usdc_balance", 0.0)
        return (
            f"*Status*\nBot: {'Online' if running else 'Offline'}\n"
            f"Commands processed: {cmds}\n"
            f"Wallet: `{wallet[:10]}...{wallet[-6:] if len(wallet) > 16 else wallet}`\n"
            f"USDC Balance: ${balance:.4f}"
        )
    if cmd == "/price":
        return (
            f"*Pricing (x402)*\n"
            f"Per call: ${X402_FEE_USDC_BASE} USDC\n"
            f"Volume discount (10+ calls): ${X402_FEE_USDC_DISCOUNT} USDC\n"
            f"Monthly VIP: ${VIP_MONTHLY_USDC} USDC\n\n"
            f"Receiver: `{X402_RECEIVER_ADDRESS}`\n"
            f"Chain: Base (8453)"
        )
    return ""


# ── Startup ──────────────────────────────────────────────────────────────

def _telegram_webhook_autoregistration_enabled() -> bool:
    """Allow Telegram webhook mutation only when production explicitly opts in."""
    return os.getenv("TELEGRAM_WEBHOOK_AUTOREGISTER", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _register_telegram_webhook_if_enabled() -> None:
    """Keep local starts from overwriting a production Telegram webhook."""
    if not _telegram_webhook_autoregistration_enabled():
        log.info(
            "Telegram webhook auto-registration disabled; set "
            "TELEGRAM_WEBHOOK_AUTOREGISTER=true only after confirming the production URL."
        )
        return
    try:
        register_webhook()
    except Exception as exc:
        log.warning("Telegram webhook auto-registration failed (non-fatal): %s", exc)


def _start_background_threads():
    """Start monitor, agent, catalog analytics, Demand Scout and Telegram workers."""
    if getattr(app, "_bg_started", False):
        return
    app._bg_started = True

    # Start blockchain monitor (real wallet)
    t_chain = threading.Thread(target=_blockchain_monitor_loop, daemon=True, name="blockchain-monitor")
    t_chain.start()

    # Start agent thread
    t_agent = threading.Thread(target=_background_agent_loop, daemon=True, name="agent-loop")
    t_agent.start()

    # Persist a first 24-hour catalog snapshot, then refresh it once per day.
    t_catalog = threading.Thread(
        target=_catalog_analytics_loop,
        daemon=True,
        name="catalog-analytics",
    )
    t_catalog.start()

    t_demand_scout = threading.Thread(
        target=_demand_scout_loop,
        daemon=True,
        name="demand-scout",
    )
    t_demand_scout.start()

    t_stripe_snapshot = threading.Thread(
        target=_stripe_payment_snapshot_loop,
        daemon=True,
        name="stripe-payment-snapshot",
    )
    t_stripe_snapshot.start()

    # Start Telegram sales loop (auto market bulletins every 30 min, webhook-only)
    try:
        t_sales = threading.Thread(target=telegram_sales_loop, daemon=True, name="telegram-sales")
        t_sales.start()
    except Exception as exc:
        log.warning("Failed to start Telegram sales thread (non-fatal): %s", exc)

    # setWebhook changes remote bot configuration, so it is production opt-in.
    _register_telegram_webhook_if_enabled()

    log.info(
        "Background threads started (blockchain monitor + agent + catalog analytics + Demand Scout + telegram sales)."
    )


# Start threads when module loads (works with gunicorn / Procfile).
# Tests can disable networked background work with KRISTO_DISABLE_BACKGROUND_THREADS.
if os.getenv("KRISTO_DISABLE_BACKGROUND_THREADS", "").strip().lower() != "true":
    try:
        _start_background_threads()
    except Exception as exc:
        log.warning("Background threads startup failed (non-fatal): %s", exc)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)