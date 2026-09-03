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
from flask import Flask, g, jsonify, redirect, render_template, request, session

# ── Central configuration (bound wallet address, GLM, etc.) ────────────────
from config import (
    BASE_CHAIN_ID,
    BASE_RPC_URL,
    get_base_fee_receiver,
    BASE_FEE_AMOUNT_USDC,
    KRISTO_STATS_PRICE,
    KRISTO_SALES_PRICE,
    KRISTO_ARB_PRICE,
    KRISTO_RUG_PRICE,
    KRISTO_WHALE_PRICE,
    KRISTO_SIGNAL_PRICE,
)

# ── Real-time market data integration ─────────────────────────────────────
from services.market_data import get_coingecko_cache_status, get_market_snapshot

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

# ── Dynamic Pricing (Volume Discount) ──────────────────────────────────────
# Prices are defined ONCE in config.py (KRISTO_*_PRICE constants) and wired
# here through X402_PRICE_MAP. Do NOT hardcode prices in this file.
X402_FEE_USDC_BASE = BASE_FEE_AMOUNT_USDC  # Standard per-call price (fallback)
X402_FEE_USDC_DISCOUNT = 0.01   # Discounted price for high-volume callers
X402_VOLUME_THRESHOLD = 10      # After 10 paid calls, price drops to $0.01
X402_FEE_USDC = X402_FEE_USDC_BASE  # Backward-compat alias (used in manifests)

# Per-endpoint x402 price map — single source of truth from config.py.
# Endpoints not listed here fall back to BASE_FEE_AMOUNT_USDC.
X402_PRICE_MAP = {
    "/api/stats": KRISTO_STATS_PRICE,
    "/api/sales": KRISTO_SALES_PRICE,
    "/api/bot-status": KRISTO_STATS_PRICE,
    "/api/arb/opportunities": KRISTO_ARB_PRICE,
    "/api/v1/signal": KRISTO_SIGNAL_PRICE,
}

# ── NEXUS Discovery Engine URL ──────────────────────────────────────────────
# Public Render URL for the NEXUS Discovery Engine (Next.js platform).
# Falls back to relative "/" so links work even if NEXUS is served from same domain.
NEXUS_URL = "/nexus"

# Free-tier limit per client. Default 1 free call for casual evaluation.
# Set KRISTO_FREE_TIER_LIMIT=0 in production for STRICT x402 semantics:
# every unpaid request returns the canonical 402 payment challenge
# (required by x402 marketplaces/verifiers such as PayAPI.market).
FREE_TIER_LIMIT = max(0, int(os.getenv("KRISTO_FREE_TIER_LIMIT", "1")))

# Endpoints that require x402 payment (after free tier exhausted)
X402_PAID_ENDPOINTS = {"/api/sales", "/api/stats", "/api/bot-status",
                       "/api/arb/opportunities", "/api/v1/signal"}

# Endpoints that are always free (discovery, health, dashboard, manifest)
X402_FREE_ENDPOINTS = {
    "/", "/health", "/dashboard", "/nexus", "/api/mcp/manifest",
    "/.well-known/x402.json", "/.well-known/ai-plugin.json", "/openapi.json",
    "/llms.txt", "/agents.json", "/robots.txt", "/sitemap.xml",
    "/mcp.json", "/api/telegram-webhook", "/api/dashboard-stats",
    "/api/connectors", "/api/v1/quickstart", "/favicon.ico", "/favicon.svg",
}

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("kristo.v6.main")

app = Flask(__name__)
# ── Reverse-proxy awareness (Render / nginx / docker-compose) ────────────────
# Render terminates TLS and forwards plain HTTP, so Flask would otherwise
# build http:// URLs in every discovery spec (x402.json, openapi.json,
# llms.txt, mcp.json). ProxyFix honors X-Forwarded-Proto/X-Forwarded-Host
# so request.host_url returns the correct https:// public URL.
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=1)
# NOTE: x_for=0 is deliberate — X-Forwarded-For is client-controllable, so
# remote_addr is NOT rewritten. Free-tier identity spoofing protection in
# _get_client_ip() stays intact (see test_v6_launch.py).
app.config["SECRET_KEY"] = os.getenv("SESSION_SECRET", "") or secrets.token_urlsafe(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# ── Request-body size cap (protects free-tier resources) ─────────────────────
# Bodies larger than this are rejected with 413 before any route handler runs,
# so oversized payloads cannot consume worker memory or upstream API quota.
# Override via env only if a legitimate larger payload is ever introduced.
app.config["MAX_CONTENT_LENGTH"] = int(
    os.getenv("KRISTO_MAX_CONTENT_LENGTH_BYTES", str(512 * 1024))  # 512 KB
)


@app.errorhandler(413)
def _payload_too_large(_error):
    """Return a JSON 413 when a client exceeds MAX_CONTENT_LENGTH."""
    return jsonify({"ok": False, "error": "payload_too_large"}), 413

# ── Runtime sales integration layer ───────────────────────────────────────
from integrations.crm_store import LeadRecord, create_crm_store
from integrations.catalog_store import CATALOG_SEED, create_catalog_store
from integrations.research_store import create_research_store
from integrations.payment_integration import SalesCheckout
from integrations.telegram_flow import TelegramSalesFlow
from integrations.stripe_checkout import StripeCheckoutService

CRM_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "crm_sales.db")
CATALOG_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "agent_catalog.db")
RESEARCH_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "research_insights.db")
crm_store = create_crm_store(CRM_DATA_FILE)
catalog_store = create_catalog_store(CATALOG_DATA_FILE)
research_store = create_research_store(RESEARCH_DATA_FILE)
checkout_store = SalesCheckout()
telegram_flow = TelegramSalesFlow(os.getenv("TELEGRAM_BOT_TOKEN", ""))
stripe_checkout = StripeCheckoutService()

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
    "receiver_usdc_balance": 0.0,
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
# Per-API-call price comes from config (single source of truth).
MICRO_FEE_USDC = BASE_FEE_AMOUNT_USDC  # Per API call
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


def _activate_stripe_vip_access(
    paid_lead: dict,
    event_data: dict,
    plan_key: str,
    already_paid: bool,
) -> dict:
    """Grant durable VIP access from the persisted paid lead exactly once."""
    if not _is_vip_plan(plan_key):
        return {"status": "not_eligible"}
    if already_paid:
        return {"status": "already_active"}

    metadata = event_data.get("metadata", {}) or {}
    chat_id = (paid_lead.get("telegram_chat_id") or metadata.get("telegram_chat_id") or "").strip()
    checkout_id = str(event_data.get("id") or "")
    return telegram_flow.deliver_vip_invite(chat_id, checkout_id, "Pro")


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


def _fetch_receiver_usdc_balance():
    """
    On-chain USDC balance of the FEE RECEIVER (0xd4cdA900…08f) — where client
    payments land. Distinct from the gas-payer wallet's balance: PayAPI's
    review correctly flagged that the dashboard showed an empty hot-wallet
    balance next to a receiver that had just been paid.
    Returns float | None on any failure.
    """
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(
            os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
            request_kwargs={"timeout": 20}))
        if not w3.is_connected():
            return None
        usdc = os.getenv("BASE_USDC_CONTRACT",
                         "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
        receiver = get_base_fee_receiver()
        selector = "0x70a08231"  # balanceOf(address)
        padded = receiver.lower().replace("0x", "").rjust(64, "0")
        result = w3.eth.call({"to": Web3.to_checksum_address(usdc),
                              "data": selector + padded})
        return int(result.hex(), 16) / 1e6
    except Exception as exc:
        log.debug("receiver USDC balance fetch: %s", exc)
        return None


# ── Blockchain monitor: detect incoming USDC transfers ───────────────────
def _blockchain_monitor_loop():
    """
    Background thread that monitors the Base blockchain for real incoming
    USDC transfers to our fee receiver address. When a transfer is detected,
    it is recorded as a real sale.

    Uses the ERC-20 Transfer event log to find incoming transfers.

    If the RPC is unreachable at startup (the public mainnet.base.org
    endpoint rate-limits with 429s), the thread retries indefinitely
    instead of exiting — otherwise payment detection would never start.
    """
    log.info("Blockchain monitor thread started.")
    poll_interval = int(os.getenv("BLOCKCHAIN_POLL_INTERVAL", "30"))
    retry_interval = max(60, int(os.getenv("BLOCKCHAIN_RETRY_INTERVAL", "120")))

    wallet = None
    while wallet is None:
        wallet = _init_wallet()
        if wallet is None:
            log.warning(
                "Blockchain monitor: wallet unavailable (RPC down / rate-limited) "
                "— retrying in %ds.",
                retry_interval,
            )
            time.sleep(retry_interval)
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

            # Update the FEE RECEIVER's USDC balance (the meaningful figure:
            # this is where client payments land — the gas-payer wallet is
            # incidental and shows 0.0, which PayAPI's review flagged).
            try:
                receiver_balance = _fetch_receiver_usdc_balance()
                if receiver_balance is not None:
                    with _lock:
                        _wallet_state["receiver_usdc_balance"] = round(
                            receiver_balance, 6)
            except Exception as exc:
                log.debug("Receiver balance fetch failed: %s", exc)

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
        # Avoid duplicates: check if tx_hash already recorded (case-insensitive —
        # settle path and blockchain monitor may format the hash differently,
        # which caused the dashboard to double-count PayAPI's first payment).
        tx_norm = (tx_hash or "").lower()
        for s in _sales_history:
            if (s.get("tx_hash") or "").lower() == tx_norm:
                log.debug("Duplicate tx %s — skipping.", tx_norm)
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
# Latest live agent signals (populated by the background agent loop, served
# by GET /api/v1/signal — PayAPI's reviewer asked for a cheap route that
# returns an actual SIGNAL instead of operational stats).
_latest_signals: dict = {"generated_at": None, "signals": []}


def _publish_agent_signals(decisions) -> None:
    """Map raw trading-agent decisions into the published signal schema for
    GET /api/v1/signal.

    PayAPI reviewer feedback (second verified route, 2026-02):
      * `price_usd` must be a real number, not null — an agent should not
        have to parse "price=$2387.7800" out of the note string.
      * each signal carries a one-line `reasoning` naming the main driver,
        so the buyer gets something /api/stats never offered.
    """
    published = []
    for token, d in (decisions or {}).items():
        d = d if isinstance(d, dict) else {}
        price = d.get("price_usd")
        published.append({
            "token": token,
            "action": d.get("final_action") or d.get("action", "monitor"),
            "confidence": d.get("confidence"),
            "price_usd": float(price) if price is not None else None,
            "reasoning": (d.get("reasoning") or "").strip(),
            "note": d.get("note") or d.get("reason") or "",
        })
    published.sort(key=lambda s: (s.get("confidence") or 0), reverse=True)
    with _lock:
        _latest_signals["generated_at"] = datetime.now(
            timezone.utc).isoformat()
        _latest_signals["signals"] = published


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

            # Publish the latest decisions for GET /api/v1/signal.
            _publish_agent_signals(decisions)

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


# ── x402 Free Tier Tracking ────────────────────────────────────────────────
# Tracks free API calls per client (by IP address).
# After FREE_TIER_LIMIT (1) free picks, x402 payment is required.
_free_tier_usage: Dict[str, int] = {}  # ip -> count of free calls used
_catalog_click_lock = threading.Lock()
_catalog_recent_clicks: Dict[tuple[str, str], datetime] = {}
CATALOG_CLICK_COOLDOWN_SECONDS = max(
    60, int(os.getenv("CATALOG_CLICK_COOLDOWN_SECONDS", "900"))
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

# Tracks PAID API calls per client (for volume discount pricing).
_paid_calls_usage: Dict[str, int] = {}  # ip -> count of paid calls made


def _is_private_or_loopback(ip: str) -> bool:
    """True for loopback / RFC1918 / CGNAT addresses (Render's internal proxies).

    Deliberately NARROWER than ipaddress.is_private: the IANA special-purpose
    ranges (TEST-NET 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24, ...) are
    NOT treated as private here, so they remain valid public client
    identities. This matters because is_private would silently reclassify
    documented public clients as proxies.
    """
    import ipaddress as _ipa
    try:
        addr = _ipa.ip_address(ip)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    if addr.version == 4:
        return (
            addr in _ipa.ip_network("10.0.0.0/8")
            or addr in _ipa.ip_network("172.16.0.0/12")
            or addr in _ipa.ip_network("192.168.0.0/16")
            or addr in _ipa.ip_network("100.64.0.0/10")  # CGNAT (shared space)
        )
    return addr in _ipa.ip_network("fc00::/7")  # private IPv6


def _get_client_ip() -> str:
    """Resolve the real client IP for free-tier / discount accounting.

    On Render every request arrives through Render's internal proxy, so
    remote_addr is a ROTATING private address (10.x.x.x). Without XFF
    resolution the free tier would be counted per PROXY IP — clients could
    harvest a fresh free call every time the proxy rotates.

    Trust model: when the immediate peer is a private/loopback address, the
    request must have traversed our platform proxy, which appends the real
    client IP to X-Forwarded-For. Client-supplied spoofed entries sit
    EARLIER in the chain, so we walk from the END and use the last PUBLIC
    IP. When the peer is a public address (direct access / tests),
    remote_addr is used as-is and X-Forwarded-For is IGNORED (anti-spoofing).
    """
    peer = request.remote_addr or "unknown"
    fwd = request.headers.get("X-Forwarded-For", "").strip()
    if fwd and _is_private_or_loopback(peer):
        entries = [e.strip() for e in fwd.split(",") if e.strip()]
        for entry in reversed(entries):
            if not _is_private_or_loopback(entry):
                return entry
        # All entries private (multi-hop internal) — best effort: last entry.
        if entries:
            return entries[-1]
    return peer


# ── Lightweight request rate limiting (per client IP, per scope) ─────────────
# Protects auth, payment and lead-capture routes from brute force and spam
# without external dependencies. In-memory sliding-window counters keyed by
# (scope, client IP); stale buckets are pruned opportunistically.
_RATE_LIMIT_DEFAULTS = {
    "admin_login": (20, 300),      # 20 token attempts / 5 min
    "checkout": (30, 300),         # 30 checkout submissions / 5 min
    "leads": (30, 300),            # lead capture / 5 min
    "funnel_track": (90, 300),     # analytics beacons / 5 min
    "agent_checkout": (60, 300),   # catalog Stripe checkout / 5 min
    "stripe_webhook": (240, 300),  # signature-verified, but bounded
    "telegram_webhook": (240, 300),  # secret-verified, but bounded
    "public_activity": (120, 300),  # public proof-of-traction feed, bounded
}

_rate_limit_lock = threading.Lock()
_rate_limit_hits: Dict[tuple, deque] = {}


def _check_rate_limit(scope: str) -> Optional[int]:
    """
    Sliding-window rate limiter keyed by (scope, client IP).

    Returns None when the request is allowed (and records the hit),
    otherwise the number of seconds after which the client may retry.
    Limits are overridable via KRISTO_RATE_<SCOPE>_MAX and
    KRISTO_RATE_<SCOPE>_WINDOW_SECONDS environment variables.
    """
    default_max, default_window = _RATE_LIMIT_DEFAULTS[scope]
    max_requests = int(os.getenv(f"KRISTO_RATE_{scope.upper()}_MAX", str(default_max)))
    window = int(os.getenv(f"KRISTO_RATE_{scope.upper()}_WINDOW_SECONDS", str(default_window)))
    key = (scope, _get_client_ip())
    now = time.time()
    with _rate_limit_lock:
        hits = _rate_limit_hits.setdefault(key, deque())
        while hits and hits[0] <= now - window:
            hits.popleft()
        if len(hits) >= max_requests:
            return max(1, int(window - (now - hits[0])))
        hits.append(now)
        # Opportunistic memory bound: drop fully-stale buckets.
        if len(_rate_limit_hits) > 10_000:
            for stale_key, stale_hits in list(_rate_limit_hits.items()):
                if not stale_hits or stale_hits[-1] <= now - window:
                    _rate_limit_hits.pop(stale_key, None)
    return None


def _rate_limited_response(scope: str):
    """Return a 429 JSON response when the scope limit is exceeded, else None."""
    retry_after = _check_rate_limit(scope)
    if retry_after is None:
        return None
    return jsonify({
        "ok": False,
        "error": "rate_limited",
        "scope": scope,
        "retry_after_seconds": retry_after,
    }), 429


def _get_dynamic_price(ip: str, endpoint: str = "") -> float:
    """
    Per-endpoint dynamic pricing with volume discount.

    The base price for each endpoint comes from X402_PRICE_MAP (wired to
    config.py KRISTO_*_PRICE constants — single source of truth).
    After X402_VOLUME_THRESHOLD (10) paid calls, the price drops to
    X402_FEE_USDC_DISCOUNT to incentivize batch/frequent on-chain usage.
    """
    base = X402_PRICE_MAP.get(endpoint, BASE_FEE_AMOUNT_USDC)
    with _lock:
        paid_count = _paid_calls_usage.get(ip, 0)
    if paid_count >= X402_VOLUME_THRESHOLD:
        # Volume discount never exceeds the base price
        return min(X402_FEE_USDC_DISCOUNT, base)
    return base


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


def _x402_challenge_core(endpoint: str, amount: float, description: str = ""):
    """
    Canonical x402 v2 challenge pieces: accepts + resource + extensions.

    Mirrors x402scan's v2 zod schema (apps/scan/src/lib/x402/v2/schema.ts and
    its schema.test.ts fixtures):
      * x402Version: 2 (integer literal)
      * accepts[]: scheme, network in CAIP-2 form ("eip155:8453" = Base),
        `amount` in TOKEN ATOMIC UNITS as string (USDC on Base has 6
        decimals, so 0.005 USDC -> "5000"), payTo, asset, maxTimeoutSeconds
      * resource: { url, description, mimeType? }
      * extensions.bazaar.info.input: the HTTP request structure that makes
        the route "invocable" instead of skipped
    """
    resource_url = request.host_url.rstrip("/") + (
        endpoint if endpoint.startswith("/") else "/" + endpoint
    )
    desc = description or f"Kristo Intelligence - paid API data ({endpoint})"
    accepts = [
        {
            "scheme": "exact",
            "network": "eip155:8453",
            "amount": str(int(round(float(amount) * 1_000_000))),
            "payTo": X402_RECEIVER_ADDRESS,
            "asset": X402_USDC_CONTRACT,
            "maxTimeoutSeconds": 60,
            # EIP-712 token domain: Base USDC reports name() = "USD Coin" —
            # PayAPI Market's validator requires this exact value here.
            "extra": {"name": "USD Coin", "version": "2"},
        }
    ]
    resource = {
        "url": resource_url,
        "description": desc,
        "mimeType": "application/json",
    }
    # Bazaar discovery extension: `info` carries the HTTP request structure,
    # `schema` carries the JSON-Schema view. The agentcash/x402scan audit
    # extracts the input schema from schema.properties.input.properties
    # .body|.queryParams and the output schema from schema.properties.output
    # .properties.example — both must be present or the route fails with
    # SCHEMA_INPUT_MISSING / SCHEMA_OUTPUT_MISSING (severity: error).
    extensions = {
        "bazaar": {
            "info": {
                "input": {"type": "http", "method": "GET"},
            },
            "schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "input": {
                        "type": "object",
                        "properties": {
                            "queryParams": {"type": "object", "properties": {}}
                        },
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "example": {
                                "type": "object",
                                "description": "Paid JSON response payload",
                            }
                        },
                    },
                },
            },
        }
    }
    return accepts, resource, extensions


def _x402_payment_required_response(endpoint: str, price_usdc: Optional[float] = None):
    """
    Build a standard HTTP 402 Payment Required response for the x402 protocol.
    Includes the exact Base USDC receiver address and price.

    If price_usdc is provided, uses dynamic pricing; otherwise uses base price.
    """
    amount = price_usdc if price_usdc is not None else X402_FEE_USDC
    # Canonical x402 v2 challenge (parsed by x402scan) + atomic-unit amount.
    accepts, resource, extensions = _x402_challenge_core(endpoint, amount)
    body = {
        "x402Version": 2,
        "error": "payment_required",
        "accepts": accepts,
        "accepts[]": accepts,
        "x402_accepts": accepts,
        "resource": resource,
        "extensions": extensions,
        "x402_version": "2.0",
        # Canonical x402_* top-level fields — self-contained for LLM agents:
        # a model that receives ONLY this JSON can construct the payment
        # and the retry request without reading llms.txt or the docs.
        "x402_network": "base-mainnet",
        "x402_chain_id": X402_CHAIN_ID,
        "x402_token": "USDC",
        "x402_token_contract": X402_USDC_CONTRACT,
        "x402_amount": str(amount),
        "x402_recipient": X402_RECEIVER_ADDRESS,
        # accepts / accepts[] / x402_accepts are defined at the top of the
        # body (canonical x402 v1 payment requirements, x402scan-parseable).
        "x402_retry_instructions": (
            "STANDARD x402 clients: sign the challenge below (EIP-3009 / "
            "exact scheme) and repeat this request with the base64url payload "
            "in the 'PAYMENT-SIGNATURE' header — settlement runs through the "
            "x402 facilitator automatically and the call returns 200 with "
            "data. MANUAL fallback: send the amount in USDC on Base to "
            "x402_recipient, then repeat this request with header "
            "'X-Payment-Proof: base64url(JSON({payer, transaction_hash, "
            "amount_usdc}))'."
        ),
        "message": (
            f"Payment required. Send {amount} USDC on Base to "
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
        "payment_proof": {
            "header": "X-Payment-Proof",
            "format": "base64url(JSON({payer, transaction_hash, amount_usdc}))",
            "retry": (
                "After your USDC transfer is confirmed on Base, retry this "
                "endpoint with the X-Payment-Proof header to gain access."
            ),
        },
        "instructions": (
            f"Send exactly {amount} USDC (Base network) to "
            f"{X402_RECEIVER_ADDRESS}. After payment is confirmed on-chain, "
            f"retry this endpoint."
        ),
    }
    resp = jsonify(body)
    resp.status_code = 402
    resp.headers["X-Payment-Required"] = "x402"
    resp.headers["X-Payment-Address"] = X402_RECEIVER_ADDRESS
    resp.headers["X-Payment-Amount-USDC"] = str(amount)
    resp.headers["X-Payment-Chain"] = X402_CHAIN
    resp.headers["X-Payment-Token-Contract"] = X402_USDC_CONTRACT
    # WWW-Authenticate per HTTP 402 conventions — some verifiers look for it.
    resp.headers["WWW-Authenticate"] = (
        f'x402 realm="kristo-intelligence", '
        f'chain="{X402_CHAIN}", chain_id="{X402_CHAIN_ID}", '
        f'token="USDC", token_contract="{X402_USDC_CONTRACT}", '
        f'receiver="{X402_RECEIVER_ADDRESS}", amount="{amount}", '
        f'accepts="tx_hash"'
    )
    # x402 v2 spec: the canonical PaymentRequired payload rides in the
    # PAYMENT-REQUIRED response header (base64url JSON). Spec clients read
    # this header (not the body) to build their PAYMENT-SIGNATURE retry.
    payment_required_payload = json.dumps({
        "x402Version": 2,
        "error": "payment_required",
        "accepts": accepts,
        "resource": resource,
        "extensions": extensions,
    })
    resp.headers["PAYMENT-REQUIRED"] = base64.urlsafe_b64encode(
        payment_required_payload.encode()
    ).decode().rstrip("=")
    return resp


def _is_dashboard_request() -> bool:
    """Deprecated compatibility shim; client headers are not authorization."""
    return False


def _get_admin_token() -> str:
    """Return the normalized admin credential without exposing its value."""
    token = (os.getenv("ADMIN_API_TOKEN", "") or "").strip()
    if token:
        return token
    fallback = (os.getenv("SESSION_SECRET", "") or "").strip()
    if fallback:
        log.warning(
            "ADMIN_API_TOKEN is not set — falling back to SESSION_SECRET. "
            "Set an explicit ADMIN_API_TOKEN in production."
        )
    return fallback


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


def _catalog_x402_payment_required_response(product: dict):
    """Return a transparent upgrade payload for an exhausted per-agent playground."""
    price = round(float(product.get("price_x402") or X402_FEE_USDC), 6)
    # Canonical x402 v2 challenge (x402scan-parseable) + atomic-unit amount.
    accepts, resource, extensions = _x402_challenge_core(
        request.path,
        price,
        description=f"Kristo Intelligence agent data ({product['id']})",
    )
    payload = {
        "x402Version": 2,
        "error": "agent_demo_limit_reached",
        "accepts": accepts,
        "accepts[]": accepts,
        "resource": resource,
        "extensions": extensions,
        "ok": False,
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
            "settlement_status": "discovery_only",
        },
        "upgrade": {
            "stripe_checkout": f"/api/v1/agents/{product['id']}/checkout",
            "entitlement_access": f"/api/v1/agents/{product['id']}/access",
            "note": "x402 settlement is not enabled in this preview. Stripe creates a 30-day agent entitlement.",
        },
    }
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


def _run_catalog_agent_demo(product: dict, user_input: str) -> dict:
    """Run a bounded, transparent demo adapter rather than presenting invented market data."""
    normalized = user_input.strip()
    input_type = "contract_or_wallet" if normalized.startswith("0x") and len(normalized) == 42 else "asset_or_topic"
    fingerprint = hashlib.sha256(normalized.lower().encode()).hexdigest()[:12]
    category = product.get("category", "intelligence")
    demo_steps = {
        "market": ["Normalize market identifier", "Check narrative and liquidity inputs"],
        "risk": ["Normalize target identifier", "Prepare risk-screen workflow"],
        "defi": ["Normalize asset or pool identifier", "Prepare yield/risk comparison"],
        "execution": ["Normalize route target", "Prepare gas and route comparison"],
        "security": ["Normalize contract target", "Prepare static security triage"],
        "distribution": ["Normalize signal topic", "Prepare channel publication draft"],
    }
    checks = demo_steps.get(category, ["Normalize request", "Prepare agent workflow"])
    return {
        "mode": "playground_demo",
        "agent_id": product["id"],
        "agent_name": product["name"],
        "input_type": input_type,
        "input_fingerprint": fingerprint,
        "checks_completed": checks,
        "result": (
            "Demo workflow completed. This verifies the agent input path and records one call; "
            "it does not claim a live trading recommendation or x402 settlement."
        ),
        "upgrade_required_for_live_access": True,
    }


def _build_x402_discovery(base_url: str) -> dict:
    """Build x402 discovery from the durable 8-SKU catalog, not legacy in-memory products."""
    agents = []
    for product in catalog_store.get_catalog():
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
            "settlement_status": "discovery_only",
        },
        "agents": agents,
        "note": "Discovery metadata is live from the catalog. Base mainnet facilitator settlement is not enabled.",
    }


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
    except Exception:
        # Observability must never affect the application response.
        pass
    return response


# ── x402 payment proof verification (completes the payment handshake) ───────
# A paying client retries with header X-Payment-Proof:
#   base64url(JSON({payer, transaction_hash, amount_usdc, ...}))
# The server verifies the proof ON-CHAIN (ERC-20 Transfer to our receiver),
# records the sale, and grants access for exactly one call.
_verified_payments: set = set()          # tx hashes that already granted access
_payment_verify_lock = threading.Lock()
_payment_verify_w3 = None

_TRANSFER_EVENT_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)


def _get_verify_web3():
    """Lazily build a lightweight Web3 provider for on-demand proof checks."""
    global _payment_verify_w3
    with _payment_verify_lock:
        if _payment_verify_w3 is None:
            from web3 import Web3
            _payment_verify_w3 = Web3(
                Web3.HTTPProvider(BASE_RPC_URL, request_kwargs={"timeout": 15})
            )
        return _payment_verify_w3


def _decode_payment_proof(header_value: str) -> Optional[dict]:
    """Decode and sanity-check the X-Payment-Proof header payload."""
    import base64 as _b64
    import binascii as _binascii
    try:
        padded = header_value + "=" * (-len(header_value) % 4)
        payload = json.loads(_b64.urlsafe_b64decode(padded.encode()).decode())
        if not isinstance(payload, dict):
            return None
        tx_hash = str(payload.get("transaction_hash") or "").strip().lower()
        payer = str(payload.get("payer") or "").strip().lower()
        if not tx_hash.startswith("0x") or len(tx_hash) != 66:
            return None
        if not payer.startswith("0x") or len(payer) != 42:
            return None
        return {
            "tx_hash": tx_hash,
            "payer": payer,
            "amount_usdc": float(payload.get("amount_usdc") or 0.0),
        }
    except (ValueError, TypeError, _binascii.Error, Exception):
        return None


def _verify_payment_onchain(tx_hash: str, payer: str, min_amount_usdc: float):
    """
    Verify via RPC that tx_hash is a confirmed USDC Transfer from payer to
    our fee receiver with at least min_amount_usdc. Returns the verified
    amount, or None if the proof does not hold.
    """
    try:
        w3 = _get_verify_web3()
        receipt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception:
        # Unknown tx, RPC hiccup, or not mined yet — treat as not verified;
        # the client may retry in a few seconds.
        return None
    try:
        if int(receipt.get("status", 0)) != 1:
            return None
        usdc_addr = os.getenv(
            "BASE_USDC_CONTRACT", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        ).lower()
        receiver = X402_RECEIVER_ADDRESS.lower()
        for log_entry in receipt.get("logs", []):
            try:
                address = str(log_entry.get("address") or "").lower()
                topics = log_entry.get("topics") or []
                if address != usdc_addr or len(topics) < 3:
                    continue
                topic0 = topics[0].hex() if hasattr(topics[0], "hex") else str(topics[0])
                if topic0.lower() != _TRANSFER_EVENT_TOPIC:
                    continue
                from_topic = topics[1].hex() if hasattr(topics[1], "hex") else str(topics[1])
                to_topic = topics[2].hex() if hasattr(topics[2], "hex") else str(topics[2])
                from_addr = ("0x" + from_topic[-40:]).lower()
                to_addr = ("0x" + to_topic[-40:]).lower()
                data = log_entry.get("data")
                raw = data.hex() if isinstance(data, (bytes, bytearray)) else str(data)
                amount = int(raw, 16) / 1e6
                if (to_addr == receiver and from_addr == payer
                        and amount + 1e-9 >= min_amount_usdc):
                    return amount
            except Exception:
                continue
        return None
    except Exception:
        return None


def _try_consume_payment_proof(proof: dict, price: float, ip: str) -> bool:
    """
    Consume a payment proof: verify it (fast path via recorded sales, slow
    path via on-chain receipt), record the sale exactly once, and grant one
    API call. One payment unlocks exactly one call (single-call semantics).
    """
    tx = proof["tx_hash"]
    with _lock:
        if tx in _verified_payments:
            return False  # already consumed — prevents replay

    # Fast path: the background monitor already recorded this transfer.
    amount = None
    with _lock:
        for s in _sales_history:
            if str(s.get("tx_hash", "")).lower() == tx:
                amount = float(s.get("amount_usd", 0.0))
                break

    # Slow path: verify the receipt directly on-chain (instant unlock —
    # no need to wait for the 30s monitor cycle).
    if amount is None:
        amount = _verify_payment_onchain(tx, proof["payer"], price)
        if amount is None:
            return False
        _record_real_sale(
            token="USDC", amount_usd=round(amount, 6), tx_hash=tx,
            sender=proof["payer"],
        )

    if amount + 1e-9 < price:
        return False

    with _lock:
        _verified_payments.add(tx)
        _paid_calls_usage[ip] = _paid_calls_usage.get(ip, 0) + 1
    log.info("x402 payment proof accepted: tx=%s payer=%s amount=$%.2f",
             tx, proof["payer"], amount)
    return True


def _get_standard_payment_header() -> str:
    """
    Read the standard x402 payment payload header.

    x402 v2 spec clients (x402-fetch, x402scan wallet, PayAPI verifier) send
    the signed EIP-3009 payload in the `PAYMENT-SIGNATURE` header; earlier
    ecosystem clients use `X-PAYMENT`. Both are accepted, v2 name first.
    """
    return (
        (request.headers.get("PAYMENT-SIGNATURE") or "").strip()
        or (request.headers.get("X-PAYMENT") or "").strip()
    )


def _try_consume_standard_payment(path: str, price: float, ip: str) -> bool:
    """
    Standard x402 v2 rail: the client sends the signed EIP-3009 payload
    (PAYMENT-SIGNATURE / X-PAYMENT header, base64url) exactly like every
    ecosystem-standard client (x402-fetch, x402scan embedded wallet,
    agentcash router, PayAPI verifier). Verify + settle through the
    facilitator, record the sale, and grant one call. True = paid.

    On success the settlement is stashed on flask.g so the after_request
    hook can emit the spec-compliant PAYMENT-RESPONSE header.
    """
    from services import connectors

    payment_header = _get_standard_payment_header()
    if not payment_header:
        return False
    accepts, resource, _ext = _x402_challenge_core(path, price)
    requirements = dict(accepts[0])
    requirements["resource"] = resource.get("url")
    requirements["description"] = resource.get("description")
    requirements["mimeType"] = resource.get("mimeType")

    ok, payer, detail = connectors.verify_standard_payment(payment_header, requirements)
    if not ok:
        g.x402_reject_reason = detail
        log.info("standard x402 payment rejected: path=%s detail=%s", path, detail)
        return False

    tx_hash, settle_detail = connectors.settle_standard_payment(payment_header, requirements)
    if not tx_hash:
        g.x402_reject_reason = f"settlement_failed: {settle_detail}"
        log.warning("standard x402 settle failed: path=%s detail=%s", path, settle_detail)
        return False

    with _lock:
        _verified_payments.add(tx_hash)
        _paid_calls_usage[ip] = _paid_calls_usage.get(ip, 0) + 1
    # Populate the real block number from the settlement receipt — PayAPI's
    # review flagged history entries reporting block_number 0 (field never
    # populated on the settle path).
    block_number = 0
    try:
        from web3 import Web3 as _W3
        _w3 = _W3(_W3.HTTPProvider(
            os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
            request_kwargs={"timeout": 20}))
        receipt = _w3.eth.get_transaction_receipt(tx_hash)
        block_number = int(receipt.get("blockNumber", 0) or 0)
    except Exception as exc:
        log.info("settlement receipt block fetch failed (non-fatal): %s", exc)
    _record_real_sale(
        token="USDC", amount_usd=round(price, 6), tx_hash=tx_hash,
        sender=payer or "unknown", block_number=block_number,
    )
    connectors.touch("x402-eip3009")
    connectors.touch("base-usdc-receiver")
    # Spec-compliant v2 settlement receipt (emitted by _emit_payment_response).
    g.x402_settlement = json.dumps({
        "success": True,
        "transaction": tx_hash,
        "network": "eip155:8453",
        "payer": payer or "unknown",
    })
    log.info("standard x402 payment settled: tx=%s payer=%s amount=$%.4f",
             tx_hash, payer, price)
    return True


@app.after_request
def _emit_payment_response(response):
    """Emit the x402 v2 PAYMENT-RESPONSE header after a standard-rail settle."""
    settlement = getattr(g, "x402_settlement", None)
    if settlement:
        response.headers["PAYMENT-RESPONSE"] = settlement
    return response


@app.before_request
def _x402_paywall():
    """
    x402 Paywall middleware.

    Discovery endpoints (health, dashboard, manifest, .well-known, openapi,
    llms.txt) are always free.

    Paid endpoints (/api/sales, /api/stats, /api/bot-status) allow
    FREE_TIER_LIMIT (1) free calls per client IP. After that, HTTP 402
    Payment Required is returned with the exact Base USDC receiver address
    and price.

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
            log.info("Free tier access: ip=%s, used=%d/%d, endpoint=%s",
                     ip, used + 1, FREE_TIER_LIMIT, path)
            return None
        else:
            # Free tier exhausted — accept a valid on-chain payment proof
            # (X-Payment-Proof header) before demanding a new payment.

            # Rail 1: STANDARD x402 clients (EIP-3009 via facilitator) —
            # v2 spec header PAYMENT-SIGNATURE (x402-fetch, x402scan wallet,
            # PayAPI verifier) and legacy X-PAYMENT (v1-era clients).
            std_header = _get_standard_payment_header()
            if std_header:
                price = _get_dynamic_price(ip, path)
                if _try_consume_standard_payment(path, price, ip):
                    return None  # paid via the standard rail — allow through
                return jsonify({
                    "ok": False,
                    "error": "invalid_standard_payment",
                    # Precise cause: precheck problem, signature mismatch, or
                    # the facilitator's structured rejection — full
                    # observability (requested by PayAPI review).
                    "reason": getattr(g, "x402_reject_reason",
                                      "verification_error"),
                    "message": (
                        "The signed payment payload (PAYMENT-SIGNATURE / "
                        "X-PAYMENT header) was not accepted. See 'reason' "
                        "for the exact cause: invalid signature, wrong "
                        "amount/receiver, expired authorization window, "
                        "or insufficient buyer USDC balance."
                    ),
                }), 401

            # Rail 2: legacy self-describing proof (X-Payment-Proof header)
            proof_header = (request.headers.get("X-Payment-Proof") or "").strip()
            if proof_header:
                proof = _decode_payment_proof(proof_header)
                if proof:
                    price = _get_dynamic_price(ip, path)
                    if _try_consume_payment_proof(proof, price, ip):
                        return None  # paid call — allow through

                    # Credential WAS presented but is broken/unusable:
                    # unknown tx, replayed proof, or underpayment. 401 tells
                    # the agent its proof is the problem (vs 402 = "pay now").
                    return jsonify({
                        "ok": False,
                        "error": "invalid_payment_proof",
                        "message": (
                            "The X-Payment-Proof was not accepted: the "
                            "transaction is unknown/unconfirmed on Base, "
                            "already used, or below the required amount."
                        ),
                        "required_amount_usdc": _get_dynamic_price(ip, path),
                        "receiver_address": X402_RECEIVER_ADDRESS,
                        "hint": (
                            "Wait for confirmation (~2s on Base) and retry, "
                            "or make a fresh payment and retry with its proof."
                        ),
                    }), 401

            # No proof at all — demand payment (canonical 402).
            price = _get_dynamic_price(ip, path)
            log.info("x402 payment required: ip=%s, endpoint=%s, price=$%s", ip, path, price)
            return _x402_payment_required_response(path, price)

    # Unknown endpoints — let Flask handle normally (404)
    return None


# ── Register Blueprints (modular route groups) ────────────────────────────
# Discovery routes (x402, OpenAPI, llms.txt, MCP, health) live in the
# app/blueprints/discovery.py module. They use lazy imports to access
# shared state and helpers defined above, avoiding circular imports.
# See audit item #5 (2026-08-24).
from app.blueprints.discovery import discovery_bp
app.register_blueprint(discovery_bp)

# ── Nexus Intelligence Engine ────────────────────────────────────────────────
# Unified autonomous intelligence loop: aggregates x402-catalog performance,
# sales-funnel and processed research intelligence, cross-references it with
# the project parameters (pricing tiers, paid endpoints, free tier) and
# synthesizes strategic briefs for the dashboard. Secure internal read
# endpoint: GET /api/nexus/strategy (admin-authenticated). No background
# threads, no external paid dependencies — the loop builds on demand.
from src.nexus import mount_nexus_engine

mount_nexus_engine(app)


@app.route("/api/arb/opportunities")
def api_arb_opportunities():
    """Live cross-DEX arbitrage spreads on Base (paid via x402).

    Returns the current top arbitrage opportunities from the Arb Radar
    background scanner: pair, buy DEX, sell DEX, spread %, estimated
    profit after gas, and liquidity constraints. Served from an
    in-memory cache — zero additional RPC cost per call.
    """
    _record_request("api_arb_opportunities", True)
    from services.arb_radar import get_opportunities, get_scan_info

    opportunities = get_opportunities()
    scan_info = get_scan_info()

    return _safe_jsonify({
        "opportunities": opportunities,
        "count": len(opportunities),
        "scan_info": scan_info,
        "source": "dexscreener_cross_dex",
        "network": "base",
        "disclaimer": (
            "Spreads computed from DEXScreener aggregated prices. "
            "Estimates are indicative; verify on-chain before executing."
        ),
    })


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
        # The address customers pay to — must always be the bound fee
        # receiver, NOT the operator hot wallet (which is the payer side).
        "payment_receiver": X402_RECEIVER_ADDRESS,
        "fee_receiver": wallet_info.get("fee_receiver") or X402_RECEIVER_ADDRESS,
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


@app.route("/api/connectors")
def api_connectors():
    """Live integration-connector registry (dashboard integrations panel)."""
    with _lock:
        wallet_info = dict(_wallet_state)
    # The fee receiver is ALWAYS bound (config hard fallback) — the receiver
    # connector must never look inactive just because no hot wallet is loaded.
    wallet_info["fee_receiver"] = wallet_info.get("fee_receiver") or X402_RECEIVER_ADDRESS
    from services.connectors import registry_status

    entries = registry_status(wallet_info)
    return _safe_jsonify({
        "count": len(entries),
        "active": sum(1 for e in entries if e["status"] == "active"),
        "connectors": entries,
    })


@app.route("/api/v1/quickstart")
def api_quickstart():
    """Zero-friction onboarding: copy-paste first-call snippets per language.

    BlockRun-style practice — the first call already works: one free GET
    returns the self-describing 402 challenge, payment is a single USDC
    transfer, retry carries the proof. No signup, no keys, no docs needed.
    """
    base_url = request.host_url.rstrip("/")
    return _safe_jsonify({
        "service": "Kristo Intelligence",
        "protocol": "x402 v2",
        "network": "base",
        "usdc_contract": X402_USDC_CONTRACT,
        "receiver": X402_RECEIVER_ADDRESS,
        "cheapest_call": {
            "endpoint": f"{base_url}/api/v1/signal",
            "amount_usdc": 0.003,
            "note": "paid per call — no subscription, no signup, no API key",
        },
        "steps": [
            "GET /api/stats -> 402 challenge (fully self-describing)",
            "send the challenge amount in USDC (Base) to the receiver",
            "retry with X-Payment-Proof: base64url(JSON({payer, transaction_hash, amount_usdc}))",
        ],
        "curl": f"curl -i {base_url}/api/stats   # 402 -> read accepts[0].amount / payTo",
        "python": (
            "import httpx, base64, json\n"
            f"r = httpx.get('{base_url}/api/stats')\n"
            "assert r.status_code == 402\n"
            "req = r.json()['accepts'][0]   # scheme / network / amount / payTo\n"
            "# 1) pay int(req['amount'])/1e6 USDC to req['payTo'] on Base\n"
            "# 2) retry with X-Payment-Proof: base64url(JSON({payer, transaction_hash, amount_usdc}))"
        ),
        "node": (
            "const r = await fetch('" + base_url + "/api/stats');\n"
            "if (r.status === 402) {\n"
            "  const { accepts } = await r.json();\n"
            "  // pay accepts[0].amount raw units (USDC, 6 decimals) to accepts[0].payTo on Base\n"
            "  // then retry with header X-Payment-Proof: base64url(JSON({payer, transaction_hash, amount_usdc}))\n"
            "}"
        ),
        "standard_client": (
            "Any x402 v2 ecosystem client (x402-fetch SDK, x402scan embedded "
            "wallet, agentcash router) works out of the box: the challenge "
            "served here is canonical v2 and the X-PAYMENT rail is verified "
            "and settled through the Coinbase x402 facilitator."
        ),
        "discovery": {
            "well_known": f"{base_url}/.well-known/x402",
            "openapi": f"{base_url}/openapi.json",
            "mcp_manifest": f"{base_url}/api/mcp/manifest",
            "connectors": f"{base_url}/api/connectors",
        },
    })


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
    limited = _rate_limited_response("telegram_webhook")
    if limited:
        return limited
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




# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    """Landing page: an animated terminal demo of the x402 payment flow.

    B2D conversion page — shows developers exactly what the API does in
    10 seconds (call -> 402 -> pay -> 200) with copy-paste curl commands.
    """
    _record_request("home", True)
    return render_template("landing.html")






@app.route("/launch")
def launch_landing():
    """Public sales landing page for live product launch."""
    return render_template("launch_landing.html")


@app.route("/sales/checkout", methods=["GET", "POST"])
def sales_checkout():
    """Checkout and lead capture for the sales funnel."""
    plans = checkout_store.get_all_plans()
    if request.method == "GET":
        selected_plan = request.args.get("plan", "pro")
        plan = checkout_store.get_plan(selected_plan) or checkout_store.get_plan("pro")
        status = request.args.get("status", "")
        status_msg = {
            "success": "Плащането е потвърдено. Системата е готова за onboarding.",
            "cancelled": "Плащането беше отменено. Можете да опитате отново.",
        }.get(status, "")
        return render_template(
            "checkout.html",
            plan=plan,
            plan_key=selected_plan,
            status=status,
            status_msg=status_msg,
        )

    limited = _rate_limited_response("checkout")
    if limited:
        return limited
    email = (request.form.get("email") or "").strip()
    plan_key = (request.form.get("plan") or "pro").strip()
    source = (request.form.get("source") or "website").strip()
    campaign = (request.form.get("campaign") or "launch").strip()
    telegram_chat_id = (request.form.get("telegram_chat_id") or "").strip()
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
        telegram_chat_id=telegram_chat_id,
    )
    saved_lead = crm_store.add_lead(lead)
    checkout_payload = checkout_store.build_checkout_payload(plan_key, email)
    stripe_session = stripe_checkout.create_checkout_session(
        plan_key,
        email,
        source=source,
        campaign=campaign,
        telegram_chat_id=telegram_chat_id,
    )
    if stripe_session.get("status") not in {"checkout_created", "mock_checkout_ready"}:
        return jsonify({"ok": False, "error": stripe_session.get("error", "checkout_unavailable")}), 503

    telegram_chat_id = (os.getenv("TELEGRAM_VIP_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    onboarding = telegram_flow.create_onboarding(telegram_chat_id, plan.name)

    if stripe_session.get("url"):
        return redirect(stripe_session["url"], code=303)

    return jsonify({
        "ok": True,
        "lead": saved_lead,
        "checkout": checkout_payload,
        "payment_provider": stripe_session.get("provider", "mock"),
        "payment_session": stripe_session,
        "sales_automation": {
            "status": "welcome_message_ready",
            "plan": plan.name,
            "telegram_chat_id": telegram_chat_id,
            "welcome_message": onboarding.welcome_message,
            "follow_up_message": onboarding.follow_up_message,
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

    limited = _rate_limited_response("leads")
    if limited:
        return limited
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
    limited = _rate_limited_response("checkout")
    if limited:
        return limited
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    plan_key = (payload.get("plan") or "pro").strip()
    source = (payload.get("source") or "api").strip()
    campaign = (payload.get("campaign") or "launch").strip()
    telegram_chat_id = (payload.get("telegram_chat_id") or "").strip()
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
        telegram_chat_id=telegram_chat_id,
    )
    crm_store.add_lead(lead)
    payment_session = stripe_checkout.create_checkout_session(
        plan_key,
        email,
        source=source,
        campaign=campaign,
        telegram_chat_id=telegram_chat_id,
    )
    if payment_session.get("status") not in {"checkout_created", "mock_checkout_ready"}:
        return jsonify({"ok": False, "error": payment_session.get("error", "checkout_unavailable")}), 503
    return jsonify({
        "ok": True,
        "checkout": checkout_store.build_checkout_payload(plan_key, email),
        "payment_provider": payment_session.get("provider", "mock"),
        "payment_session": payment_session,
        "plan": plan.name,
    })


@app.route("/api/v1/signal", methods=["GET"])
def api_signal():
    """
    Cheap paid route returning an ACTUAL SIGNAL (direction + confidence +
    reasoning) from the live trading-agent engine — PayAPI's reviewer noted
    that /api/stats undersells the signals work. Refreshed every
    AGENT_POLL_INTERVAL seconds by the background agent.
    """
    with _lock:
        snapshot = {
            "generated_at": _latest_signals.get("generated_at"),
            "signals": list(_latest_signals.get("signals") or []),
        }
    return _safe_jsonify({
        "service": "Kristo Intelligence — live agent signal",
        "price_usdc": KRISTO_SIGNAL_PRICE,
        "engine": "8-agent intelligence engine (CoinGecko + DeFi signals + risk overlay)",
        "generated_at": snapshot["generated_at"],
        "signal_count": len(snapshot["signals"]),
        "signals": snapshot["signals"],
        "refresh_note": "Signals refresh automatically every 5 minutes.",
        "disclaimer": "Not financial advice. Auto-execution is disabled "
                      "(AGENT_AUTO_EXECUTE=false) — signals are informational.",
    })


@app.route("/api/v1/agents", methods=["GET"])
def api_agent_catalog():
    """Return the active, payment-ready catalog without exposing internal events."""
    return jsonify({"ok": True, "agents": catalog_store.get_catalog()})


@app.route("/api/v1/agents/<agent_id>", methods=["GET"])
def api_agent_detail(agent_id: str):
    """Return one active agent SKU for a product page or machine client."""
    agent = catalog_store.get_product(agent_id)
    if not agent:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    return jsonify({"ok": True, "agent": agent})


@app.route("/api/v1/agents/<agent_id>/playground", methods=["POST"])
def api_agent_playground(agent_id: str):
    """Allow exactly one bounded interactive demo per client and catalog agent."""
    agent = catalog_store.get_product(agent_id)
    if not agent:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404

    payload = request.get_json(silent=True) or {}
    user_input = (payload.get("input") or "").strip()
    if len(user_input) < 2 or len(user_input) > 256:
        return jsonify(
            {"ok": False, "error": "input_must_be_between_2_and_256_characters"}
        ), 400

    authorization = (request.headers.get("Authorization", "") or "").strip()
    bearer_token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    entitlement = _verify_agent_access_token(bearer_token, agent_id) if bearer_token else None
    result = _run_catalog_agent_demo(agent, user_input)
    if not entitlement and not catalog_store.consume_free_playground_request(
        agent_id, _playground_client_key_hash(_get_client_ip())
    ):
        return _catalog_x402_payment_required_response(agent)
    if entitlement and not catalog_store.record_call(agent_id):
        log.error("Catalog call could not be recorded for agent %s.", agent_id)
        return jsonify({"ok": False, "error": "call_recording_unavailable"}), 503
    return jsonify(
        {
            "ok": True,
            "agent": agent,
            "access": "active_entitlement" if entitlement else "one_free_playground_request",
            "result": result,
        }
    )




@app.route("/agents", methods=["GET"])
def agent_playground_page():
    """Public catalog page for the eight bounded agent demos."""
    return render_template("agent_playground.html")


@app.route("/api/v1/agents/<agent_id>/click", methods=["POST"])
def api_agent_click(agent_id: str):
    """Persist a product-page click for catalog conversion analytics."""
    if not catalog_store.get_product(agent_id):
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
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
    limited = _rate_limited_response("agent_checkout")
    if limited:
        return limited
    agent = catalog_store.get_product(agent_id)
    if not agent:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404

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
    if not catalog_store.get_product(agent_id):
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
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


@app.route("/api/webhooks/stripe", methods=["POST"])
def stripe_webhook_handler():
    """Stripe-compatible webhook handler for payment confirmation."""
    limited = _rate_limited_response("stripe_webhook")
    if limited:
        return limited
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
            already_paid = prior_lead.get("payment_status") == "paid"
            paid_lead = crm_store.mark_paid(email, amount, plan_key)
            if agent_sku:
                catalog_store.confirm_checkout_payment(
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
            else:
                vip_access = _activate_stripe_vip_access(
                    paid_lead or prior_lead,
                    event_data,
                    plan_key,
                    already_paid,
                )
            return jsonify({
                "ok": True,
                "status": "paid",
                "plan": plan_key,
                "amount_usd": amount,
                "vip_access": vip_access["status"],
            })

    return jsonify({"ok": True, "received": True, "event_type": event_type})


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
            "email": lead.get("email", ""),
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
    pending_research = len(research_store.list_insights(status="PENDING", limit=200))
    market_cache = get_coingecko_cache_status()
    market_age = market_cache.get("age_seconds")
    market_detail = market_cache.get("state", "unavailable")
    if market_age is not None:
        market_detail = f"{market_detail} cache, age {market_age}s"
    if market_cache.get("detail"):
        market_detail = f"{market_detail} — {market_cache['detail']}"
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
            "active_agent_entitlements": catalog_store.active_entitlement_count(),
            "research_pending_review": pending_research,
        },
        "payments": displayed_payments[:100],
        "payment_source": "stripe_checkout" if use_stripe_feed else "crm_paid_events",
        "vip_plans": vip_plans[:100],
        "request_log": list(reversed(live_requests)),
        "agent_catalog": catalog_metrics,
        "services": {
            "crm": {"ready": crm_store.is_healthy(), "backend": crm_store.backend},
            "agent_catalog": {
                "ready": catalog_store.is_healthy(),
                "backend": catalog_store.backend,
                "active_agents": len(catalog_metrics["products"]),
                "detail": "24h catalog analytics",
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
    return _safe_jsonify({"ok": True, **catalog_store.get_metrics_24h()})


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








@app.route("/sales/admin/login", methods=["GET", "POST"])
@app.route("/admin/login", methods=["GET", "POST"])
def sales_admin_login():
    """Create a signed browser session from the existing admin token."""
    error = ""
    if request.method == "POST":
        limited = _rate_limited_response("admin_login")
        if limited:
            return limited
        configured = _get_admin_token()
        supplied = (request.form.get("admin_token") or "").strip()
        if configured and supplied and hmac.compare_digest(supplied, configured):
            session.clear()
            session["admin_authenticated"] = True
            return redirect("/sales/admin")
        _log_admin_token_mismatch(configured, supplied)
        error = "Невалиден admin token."
    return render_template("admin_login.html", error=error)


@app.route("/sales/admin/logout", methods=["GET"])
def sales_admin_logout():
    session.clear()
    return redirect("/sales/admin/login")


@app.route("/sales/admin", methods=["GET"])
def sales_admin():
    """Protected browser dashboard for sales, VIP operations and service health."""
    if session.get("admin_authenticated"):
        return render_template("admin_dashboard.html")

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
    return render_template("admin_dashboard.html")


@app.route("/sales/admin/research", methods=["GET"])
def sales_admin_research():
    """Protected browser view for approving or archiving R&D research insights."""
    if session.get("admin_authenticated"):
        return render_template("admin_research.html")
    auth_error = _require_admin_access()
    if auth_error:
        return redirect("/sales/admin/login")
    session["admin_authenticated"] = True
    return render_template("admin_research.html")


@app.route("/api/launch/health", methods=["GET"])
def launch_health():
    """Launch health endpoint for sales ops and deployment checks."""
    crm_ready = crm_store.is_healthy()
    lead_count = len(crm_store.get_all()) if crm_ready else 0
    pipeline = crm_store.get_sales_pipeline() if crm_ready else {}
    payload = {
        "ok": True,
        "app": "kristo-intelligence-v6",
        "status": "live" if crm_ready else "degraded",
        "payment_provider": "stripe" if os.getenv("STRIPE_API_KEY") else "mock",
        "crm_backend": crm_store.backend,
        "crm_ready": crm_ready,
        "lead_count": lead_count,
        "pipeline": pipeline,
        "public_url": os.getenv("APP_PUBLIC_URL", "http://localhost:5000"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return jsonify(payload), 200 if crm_ready else 503


@app.route("/api/funnel/track", methods=["POST"])
def funnel_track():
    """Capture UTM campaign data for conversion analytics."""
    limited = _rate_limited_response("funnel_track")
    if limited:
        return limited
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





# ── Dashboard HTML ────────────────────────────────────────────────────────



@app.route("/dashboard")
def dashboard():
    """Beautiful HTML dashboard with charts and metrics — real on-chain data only."""
    _record_request("dashboard", True)
    return render_template("dashboard.html", nexus_url=NEXUS_URL)


# ── NEXUS Engine Visual Dashboard ─────────────────────────────────────────



@app.route("/nexus")
def nexus_dashboard():
    """NEXUS Engine visual live dashboard — discoveries feed, metrics, and AI agents."""
    _record_request("dashboard", True)
    return render_template("nexus_dashboard.html", nexus_url=NEXUS_URL)


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

# ── Free-tier keep-alive (self-ping) ────────────────────────────────────────
# Render free instances spin down after ~15 minutes without inbound traffic.
# A lightweight self-GET every 10 minutes keeps the service awake 24/7 so AI
# agents can discover and pay for the API at any time, day or night.
KEEPALIVE_INTERVAL_SECONDS = max(300, int(os.getenv("KEEPALIVE_INTERVAL_SECONDS", "600")))


def _keepalive_loop():
    """Periodically ping our own public /health endpoint to prevent spin-down.

    Runs as a daemon thread alongside the other background loops. The target
    URL is resolved from KEEPALIVE_PUBLIC_URL / APP_PUBLIC_URL /
    WEBHOOK_PUBLIC_URL with a hard fallback to the production Render URL.
    Failures are non-fatal — the loop simply retries on the next interval.
    """
    public_url = (
        os.getenv("KEEPALIVE_PUBLIC_URL", "").strip()
        or os.getenv("APP_PUBLIC_URL", "").strip()
        or os.getenv("WEBHOOK_PUBLIC_URL", "").strip()
        or "https://kristo-intelligence-api.onrender.com"
    ).rstrip("/")
    target = f"{public_url}/health"
    log.info(
        "Keep-alive thread started (interval=%ds, target=%s).",
        KEEPALIVE_INTERVAL_SECONDS,
        target,
    )
    # Give the web server time to bind before the very first ping.
    time.sleep(120)
    while True:
        try:
            import requests as _requests
            response = _requests.get(target, timeout=30)
            log.info("Keep-alive ping: %s -> HTTP %d", target, response.status_code)
        except Exception as exc:
            log.warning("Keep-alive ping failed (non-fatal): %s", exc)
        time.sleep(KEEPALIVE_INTERVAL_SECONDS)


def _start_background_threads():
    """Start monitor, agent, catalog-analytics and Telegram background workers.

    Respects two environment flags:
      - KRISTO_DISABLE_BACKGROUND_THREADS=true → never start (web-only mode,
        used when a dedicated scripts.worker process handles background work)
      - KRISTO_WORKER_MODE=true → always start (worker process mode)
    Default (neither flag): start threads inline (legacy single-process mode).
    """
    if getattr(app, "_bg_started", False):
        return
    app._bg_started = True

    worker_mode = os.getenv("KRISTO_WORKER_MODE", "").lower() in ("1", "true", "yes")
    disable_flag = os.getenv("KRISTO_DISABLE_BACKGROUND_THREADS", "").lower() in ("1", "true", "yes")
    if disable_flag and not worker_mode:
        log.info("Background threads disabled (KRISTO_DISABLE_BACKGROUND_THREADS=true). "
                 "Run scripts.worker in a separate process for background work.")
        return
    if worker_mode:
        log.info("Worker mode active (KRISTO_WORKER_MODE=true) — starting all background threads.")

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

    t_stripe_snapshot = threading.Thread(
        target=_stripe_payment_snapshot_loop,
        daemon=True,
        name="stripe-payment-snapshot",
    )
    t_stripe_snapshot.start()

    # Keep-alive self-ping: prevents free-tier spin-down between customer
    # calls so AI agents can reach the API 24/7.
    t_keepalive = threading.Thread(
        target=_keepalive_loop, daemon=True, name="keep-alive"
    )
    t_keepalive.start()

    # Arb Radar: cross-DEX arbitrage spread detection on Base (paid endpoint).
    try:
        from services.arb_radar import start_arb_radar_thread
        start_arb_radar_thread()
    except Exception as exc:
        log.warning("Failed to start Arb Radar thread (non-fatal): %s", exc)

    # Kristo Sentinel: in-app autonomous monitoring & Telegram alerting agent
    # (health transitions, on-chain revenue, GitHub/PR status, weekly report).
    try:
        from services.sentinel import start_sentinel_thread
        start_sentinel_thread()
    except Exception as exc:
        log.warning("Failed to start Sentinel thread (non-fatal): %s", exc)

    # Start Telegram sales loop (auto market bulletins every 30 min, webhook-only)
    try:
        t_sales = threading.Thread(target=telegram_sales_loop, daemon=True, name="telegram-sales")
        t_sales.start()
    except Exception as exc:
        log.warning("Failed to start Telegram sales thread (non-fatal): %s", exc)

    # ── Auto-register Telegram webhook on startup ──
    # Calls setWebhook so Telegram delivers updates to /api/telegram-webhook.
    # Runs on every deploy — no manual action required.
    try:
        register_webhook()
    except Exception as exc:
        log.warning("Telegram webhook auto-registration failed (non-fatal): %s", exc)

    log.info(
        "Background threads started (blockchain monitor + agent + catalog analytics "
        "+ keep-alive + sentinel + telegram sales)."
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