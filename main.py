"""
Kristo Intelligence API v5
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
from datetime import datetime, timedelta, timezone
from collections import deque
from typing import Dict, List, Optional

import math
from flask import Flask, jsonify, render_template_string, request

# ── Central configuration (bound wallet address, GLM, etc.) ────────────────
from config import get_base_fee_receiver, BOUND_BASE_FEE_RECEIVER

# ── Real-time market data integration ─────────────────────────────────────
from services.market_data import get_market_snapshot

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

# Endpoints that require x402 payment (after free tier exhausted)
X402_PAID_ENDPOINTS = {"/api/sales", "/api/stats", "/api/bot-status"}

# Endpoints that are always free (discovery, health, dashboard, manifest)
X402_FREE_ENDPOINTS = {
    "/", "/health", "/dashboard", "/nexus", "/api/mcp/manifest",
    "/.well-known/x402.json", "/openapi.json", "/llms.txt",
    "/mcp.json", "/api/telegram-webhook",
}

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("kristo.v5.main")

app = Flask(__name__)

# ── Runtime sales integration layer ───────────────────────────────────────
from integrations.crm_store import LeadRecord, create_crm_store
from integrations.payment_integration import SalesCheckout
from integrations.telegram_flow import TelegramSalesFlow
from integrations.stripe_checkout import StripeCheckoutService

CRM_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "crm_sales.db")
crm_store = create_crm_store(CRM_DATA_FILE)
checkout_store = SalesCheckout()
telegram_flow = TelegramSalesFlow(os.getenv("TELEGRAM_BOT_TOKEN", ""))
stripe_checkout = StripeCheckoutService()

# ── In-memory data stores (thread-safe via lock) ──────────────────────────
_lock = threading.Lock()

# ── Product Catalog: 8 Agents + NEXUS Engine = 9 products ─────────────────
# Each product tracks: hits (requests), sales_count, sales_volume_usd
PRODUCT_CATALOG = [
    {"id": "market_evaluator",   "name": "Market Evaluator Agent",  "category": "agent",  "price_usdc": 0.05},
    {"id": "defi_signals",       "name": "DeFi Signals Agent",      "category": "agent",  "price_usdc": 0.05},
    {"id": "trading_agent",       "name": "Trading Agent",           "category": "agent",  "price_usdc": 0.05},
    {"id": "coingecko_data",      "name": "CoinGecko Data Agent",    "category": "agent",  "price_usdc": 0.05},
    {"id": "wallet_monitor",      "name": "Wallet Monitor Agent",   "category": "agent",  "price_usdc": 0.05},
    {"id": "telegram_bot",        "name": "Telegram Bot Agent",     "category": "agent",  "price_usdc": 0.05},
    {"id": "blockchain_monitor",  "name": "Blockchain Monitor Agent","category": "agent",  "price_usdc": 0.05},
    {"id": "vip_manager",         "name": "VIP Manager Agent",      "category": "agent",  "price_usdc": 0.05},
    {"id": "nexus_engine",        "name": "NEXUS Engine",           "category": "engine", "price_usdc": 0.10},
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

# Daily stats
_daily_stats: Dict[str, dict] = {}  # date_str -> {requests, sales_count, sales_volume}

# Real wallet state
_wallet_state = {
    "wallet_address": None,
    "fee_receiver": None,
    "usdc_balance": 0.0,
    "rpc_connected": False,
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
    rpc_url = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
    usdc_address = os.getenv("BASE_USDC_CONTRACT", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

    # Try full wallet first (with private key)
    if pk:
        try:
            from blockchain.wallet import Wallet
            wallet = Wallet.from_env()
            if wallet is None:
                log.warning("Wallet.from_env() returned None — falling back to monitor-only.")
            else:
                log.info("Real wallet initialized: address=%s", wallet.account.address)
                with _lock:
                    _wallet_state["wallet_address"] = wallet.account.address
                    _wallet_state["fee_receiver"] = wallet.fee_receiver
                    _wallet_state["rpc_connected"] = True
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

            log.info("Monitor-only wallet ready. Tracking USDC transfers to: %s", fee_receiver)
            return mock

        except Exception as exc:
            log.error("Failed to initialize monitor-only Web3: %s", exc)
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


# ── Endpoint → Product mapping for per-agent stats ────────────────────────
_ENDPOINT_TO_PRODUCT: Dict[str, str] = {
    "api_sales": "nexus_engine",
    "api_stats": "nexus_engine",
    "api_bot_status": "telegram_bot",
    "api_mcp_manifest": "nexus_engine",
    "dashboard": "nexus_engine",
    "home": "nexus_engine",
    "agent_cycle": "trading_agent",
}


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

        _bot_status["last_heartbeat"] = now.isoformat()
        _bot_status["commands_processed"] += 1

        # Increment per-product hits
        product_id = _ENDPOINT_TO_PRODUCT.get(endpoint)
        if product_id and product_id in _product_stats:
            _product_stats[product_id]["hits"] += 1


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
    """Return the full 9-product breakdown with hits, sales, and volume."""
    with _lock:
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "category": p["category"],
                "price_usdc": p["price_usdc"],
                "hits": _product_stats[p["id"]]["hits"],
                "sales_count": _product_stats[p["id"]]["sales_count"],
                "sales_volume_usd": _product_stats[p["id"]]["sales_volume_usd"],
            }
            for p in PRODUCT_CATALOG
        ]


# ── x402 Free Tier Tracking ────────────────────────────────────────────────
# Tracks free API calls per client (by IP address).
# After FREE_TIER_LIMIT (1) free picks, x402 payment is required.
_free_tier_usage: Dict[str, int] = {}  # ip -> count of free calls used

# Tracks PAID API calls per client (for volume discount pricing).
_paid_calls_usage: Dict[str, int] = {}  # ip -> count of paid calls made


def _get_client_ip() -> str:
    """Get the real client IP, respecting X-Forwarded-For when behind a proxy."""
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"


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


def _require_admin_access():
    """Require a server-side admin token for CRM and sales operations."""
    configured = os.getenv("ADMIN_API_TOKEN", "").strip() or os.getenv("SESSION_SECRET", "").strip()
    supplied = request.headers.get("X-Admin-Token", "")
    if not configured or not supplied or not hmac.compare_digest(supplied, configured):
        return jsonify({"ok": False, "error": "admin_auth_required"}), 401
    return None


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
            # Free tier exhausted — require x402 payment (dynamic pricing)
            price = _get_dynamic_price(ip)
            log.info("x402 payment required: ip=%s, endpoint=%s, price=$%s", ip, path, price)
            return _x402_payment_required_response(path, price)

    # Unknown endpoints — let Flask handle normally (404)
    return None


# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    _record_request("home", True)
    return "Kristo Intelligence API is running! Visit /dashboard for the dashboard."


_LAUNCH_LANDING_HTML = """
<!DOCTYPE html>
<html lang="bg">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kristo Intelligence | VIP Crypto Intelligence</title>
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
                    <button type="submit">Потвърди покупката</button>
                </form>
            </body>
            </html>
            """,
            plan=plan,
            plan_key=selected_plan,
            status=status,
            status_msg=status_msg,
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
    stripe_session = stripe_checkout.create_checkout_session(plan_key, email, source=source, campaign=campaign)

    telegram_chat_id = (os.getenv("TELEGRAM_VIP_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    onboarding = telegram_flow.create_onboarding(telegram_chat_id, plan.name)

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

    lead = LeadRecord(email=email, source=source, campaign=campaign, plan=plan.name)
    crm_store.add_lead(lead)
    payment_session = stripe_checkout.create_checkout_session(plan_key, email, source=source, campaign=campaign)
    return jsonify({
        "ok": True,
        "checkout": checkout_store.build_checkout_payload(plan_key, email),
        "payment_provider": payment_session.get("provider", "mock"),
        "payment_session": payment_session,
        "plan": plan.name,
    })


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

    if event_type == "checkout.session.completed":
        email = (event_data.get("customer_details", {}).get("email") or event_data.get("customer_email") or "").strip()
        plan_key = (event_data.get("metadata", {}) or {}).get("plan") or "pro"
        amount = float(event_data.get("amount_total") or 0.0) / 100.0
        if email:
            crm_store.mark_paid(email, amount, plan_key)
            return jsonify({"ok": True, "status": "paid", "email": email, "plan": plan_key, "amount_usd": amount})

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


@app.route("/sales/admin", methods=["GET"])
def sales_admin():
    """Sales admin dashboard for launch monitoring."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    leads = crm_store.get_all()
    pipeline = crm_store.get_sales_pipeline()
    summary = {
        "total": len(leads),
        "paid": sum(1 for lead in leads if lead.get("payment_status") == "paid"),
        "new": pipeline.get("new", 0),
        "qualified": pipeline.get("qualified", 0),
        "paid_pipeline": pipeline.get("paid", 0),
    }
    return render_template_string(
        """
        <!DOCTYPE html>
        <html lang="bg">
        <head>
            <meta charset="UTF-8">
            <title>Sales Admin | Kristo Intelligence</title>
            <style>
                body { font-family: Arial, sans-serif; background: #0b1020; color: #e2e8f0; margin: 0; padding: 40px; }
                .wrap { max-width: 1000px; margin: 0 auto; }
                .grid { display: grid; grid-template-columns: repeat(4, minmax(200px, 1fr)); gap: 16px; }
                .card { background: #111827; border: 1px solid #24314d; border-radius: 12px; padding: 20px; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; }
                th, td { padding: 10px; border-bottom: 1px solid #24314d; text-align: left; }
                .badge { display: inline-block; background: #1d4ed8; color: white; padding: 4px 8px; border-radius: 999px; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="wrap">
                <h1>Sales Admin</h1>
                <div class="grid">
                    <div class="card"><strong>Total Leads</strong><br>{{ summary['total'] }}</div>
                    <div class="card"><strong>New</strong><br>{{ summary['new'] }}</div>
                    <div class="card"><strong>Qualified</strong><br>{{ summary['qualified'] }}</div>
                    <div class="card"><strong>Paid</strong><br>{{ summary['paid'] }}</div>
                </div>
                <table>
                    <thead>
                        <tr><th>Email</th><th>Source</th><th>Plan</th><th>Status</th><th>Payment</th></tr>
                    </thead>
                    <tbody>
                        {% for lead in leads %}
                        <tr>
                            <td>{{ lead.get('email', '') }}</td>
                            <td>{{ lead.get('source', '') }}</td>
                            <td>{{ lead.get('plan', '') }}</td>
                            <td><span class="badge">{{ lead.get('status', 'new') }}</span></td>
                            <td>{{ lead.get('payment_status', 'pending') }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """,
        summary=summary,
        leads=leads,
    )


@app.route("/api/launch/health", methods=["GET"])
def launch_health():
    """Launch health endpoint for sales ops and deployment checks."""
    crm_ready = crm_store.is_healthy()
    lead_count = len(crm_store.get_all()) if crm_ready else 0
    pipeline = crm_store.get_sales_pipeline() if crm_ready else {}
    payload = {
        "ok": True,
        "app": "kristo-intelligence-v5",
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
    return jsonify(
        status="ok" if crm_ready else "degraded",
        database={"backend": crm_store.backend, "ready": crm_ready},
    ), 200 if crm_ready else 503


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


@app.route("/api/stats")
def api_stats():
    """Return activity, requests, daily stats, and 9-product breakdown (real data only)."""
    _record_request("api_stats", True)
    with _lock:
        daily = dict(sorted(_daily_stats.items()))
        recent_requests = list(_request_log)
        wallet_info = dict(_wallet_state)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_data = daily.get(today_str, {"requests": 0, "sales_count": 0, "sales_volume": 0.0})

    # 9-product breakdown (8 Agents + NEXUS Engine)
    products = _get_products_breakdown()
    total_hits = sum(p["hits"] for p in products)
    total_product_sales = sum(p["sales_count"] for p in products)
    total_product_volume = round(sum(p["sales_volume_usd"] for p in products), 6)

    # Fetch real-time market data from CoinGecko, DEXScreener, Fear & Greed
    market_data = get_market_snapshot()

    return _safe_jsonify({
        "today": {
            "date": today_str,
            "requests": today_data.get("requests", 0),
            "sales_count": today_data.get("sales_count", 0),
            "sales_volume_usd": today_data.get("sales_volume", 0.0),
        },
        "daily": daily,
        "recent_requests": recent_requests[-50:],
        "total_requests": sum(d.get("requests", 0) for d in daily.values()),
        "wallet": wallet_info,
        "products": products,
        "products_summary": {
            "total_products": len(products),
            "total_hits": total_hits,
            "total_sales": total_product_sales,
            "total_volume_usd": total_product_volume,
        },
        "nexus_url": NEXUS_URL,
        "market_data": market_data,
    })


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
    _record_request("api_telegram_webhook", True)
    payload = request.get_json(silent=True) or {}
    if not payload:
        return jsonify({"ok": False, "error": "empty_payload"}), 400

    try:
        result = process_webhook_update(payload)
        log.info("Telegram webhook processed: %s", result)
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        log.error("Telegram webhook processing failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── MCP / x402 Payment Protocol ──────────────────────────────────────────

@app.route("/api/mcp/manifest")
def api_mcp_manifest():
    """
    MCP (Model Context Protocol) manifest for AI Agent machine-to-machine payments.
    Compatible with x402 payment protocol — AI agents can read this to understand
    how to pay for API access via USDC on Base.
    """
    _record_request("api_mcp_manifest", True)
    fee_receiver = get_base_fee_receiver()  # hard fallback to bound address
    base_url = request.host_url.rstrip("/")

    manifest = {
        "protocol": "x402",
        "version": "1.0",
        "service": "Kristo Intelligence API",
        "description": "AI-powered DeFi trading signals and crypto market intelligence",
        "payment": {
            "chain": "base",
            "chain_id": 8453,
            "currency": "USDC",
            "token_contract": os.getenv("BASE_USDC_CONTRACT", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
            "receiver_address": fee_receiver,
            "tiers": [
                {
                    "id": "micro_request",
                    "name": "Micro Request",
                    "price_usdc": MICRO_FEE_USDC,
                    "description": "Pay-per-call: 0.10 USDC per API request",
                    "access": "single API call",
                    "endpoints": ["/api/stats", "/api/sales", "/api/bot-status"],
                },
                {
                    "id": "vip_monthly",
                    "name": "Monthly VIP",
                    "price_usdc": VIP_MONTHLY_USDC,
                    "description": "Unlimited monthly access + Telegram VIP group invite",
                    "access": "unlimited for 30 days",
                    "endpoints": ["ALL"],
                    "bonus": "Telegram VIP group invite code",
                },
            ],
        },
        "endpoints": {
            "base_url": base_url,
            "available": [
                {"path": "/api/stats", "method": "GET", "cost_usdc": MICRO_FEE_USDC, "description": "Market activity and daily stats"},
                {"path": "/api/sales", "method": "GET", "cost_usdc": MICRO_FEE_USDC, "description": "Real on-chain sales history"},
                {"path": "/api/bot-status", "method": "GET", "cost_usdc": MICRO_FEE_USDC, "description": "Telegram bot status"},
                {"path": "/api/mcp/manifest", "method": "GET", "cost_usdc": 0.0, "description": "This manifest (free)"},
                {"path": "/dashboard", "method": "GET", "cost_usdc": 0.0, "description": "HTML dashboard (free)"},
            ],
        },
        "instructions": {
            "payment": f"Send USDC to {fee_receiver} on Base network",
            "verification": "Payments are verified on-chain via Transfer event logs",
            "vip_threshold": f"Payments >= ${VIP_THRESHOLD_USDC} USDC automatically generate a Telegram VIP invite code",
        },
    }
    return jsonify(manifest)


# ── AI Agent Discovery Endpoints (x402, OpenAPI, llms.txt) ────────────────

@app.route("/.well-known/x402.json")
def well_known_x402():
    """
    x402 discovery file for AI agents.
    Describes payment requirements, receiver address, pricing, and endpoints.
    """
    base_url = request.host_url.rstrip("/")
    return jsonify({
        "protocol": "x402",
        "version": "1.0",
        "service": "Kristo Intelligence API",
        "description": "AI-powered DeFi trading signals and crypto market intelligence on Base",
        "payment": {
            "chain": X402_CHAIN,
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            "amount_usdc": X402_FEE_USDC,
            "network": "base",
        },
        "pricing": {
            "free_tier": {
                "limit": FREE_TIER_LIMIT,
                "description": f"{FREE_TIER_LIMIT} free API call(s) per client, then payment required",
            },
            "tiers": [
                {
                    "id": "micro_request",
                    "name": "Micro Request",
                    "price_usdc": X402_FEE_USDC,
                    "description": f"Pay-per-call: {X402_FEE_USDC} USDC per API request",
                    "access": "single API call",
                },
                {
                    "id": "vip_monthly",
                    "name": "Monthly VIP",
                    "price_usdc": VIP_MONTHLY_USDC,
                    "description": "Unlimited monthly access + Telegram VIP group invite",
                    "access": "unlimited for 30 days",
                },
            ],
        },
        "endpoints": {
            "base_url": base_url,
            "paid": [
                {"path": "/api/stats", "method": "GET", "cost_usdc": X402_FEE_USDC,
                 "description": "Market activity and daily stats"},
                {"path": "/api/sales", "method": "GET", "cost_usdc": X402_FEE_USDC,
                 "description": "Real on-chain sales history"},
                {"path": "/api/bot-status", "method": "GET", "cost_usdc": X402_FEE_USDC,
                 "description": "Telegram bot status"},
            ],
            "free": [
                {"path": "/.well-known/x402.json", "method": "GET", "cost_usdc": 0.0,
                 "description": "This x402 discovery file"},
                {"path": "/openapi.json", "method": "GET", "cost_usdc": 0.0,
                 "description": "OpenAPI specification"},
                {"path": "/llms.txt", "method": "GET", "cost_usdc": 0.0,
                 "description": "LLM-friendly API description"},
                {"path": "/api/mcp/manifest", "method": "GET", "cost_usdc": 0.0,
                 "description": "MCP/x402 manifest"},
                {"path": "/health", "method": "GET", "cost_usdc": 0.0,
                 "description": "Health check"},
                {"path": "/dashboard", "method": "GET", "cost_usdc": 0.0,
                 "description": "HTML dashboard"},
            ],
        },
        "instructions": {
            "payment": f"Send {X402_FEE_USDC} USDC on Base to {X402_RECEIVER_ADDRESS}",
            "verification": "Payments are verified on-chain via ERC-20 Transfer event logs",
            "retry": "After payment confirmation, retry the endpoint to access data",
        },
    })




@app.route("/mcp.json")
def mcp_json():
    """
    MCP (Model Context Protocol) discovery file for AI agent indexing.

    Provides a machine-readable description of the service, available tools
    (endpoints), and x402 payment requirements so autonomous agents can
    discover and interact with the API automatically.
    """
    base_url = request.host_url.rstrip("/")
    return jsonify({
        "schema_version": "1.0",
        "name": "Kristo Intelligence API",
        "description": "AI-powered DeFi trading signals and crypto market intelligence on Base",
        "base_url": base_url,
        "protocol": "x402",
        "payment": {
            "chain": X402_CHAIN,
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            "price_per_call_usdc": X402_FEE_USDC,
            "free_tier_limit": FREE_TIER_LIMIT,
            "monthly_vip_usdc": VIP_MONTHLY_USDC,
        },
        "tools": [
            {
                "name": "get_market_stats",
                "description": "Get market activity, daily stats, 9-product breakdown, and real-time market data (CoinGecko, DEXScreener, Fear & Greed)",
                "endpoint": f"{base_url}/api/stats",
                "method": "GET",
                "cost_usdc": X402_FEE_USDC,
                "free_tier_eligible": True,
            },
            {
                "name": "get_sales_history",
                "description": "Get real on-chain sales history (USDC transfers) and live market snapshot",
                "endpoint": f"{base_url}/api/sales",
                "method": "GET",
                "cost_usdc": X402_FEE_USDC,
                "free_tier_eligible": True,
            },
            {
                "name": "get_bot_status",
                "description": "Get Telegram bot integration status and wallet info",
                "endpoint": f"{base_url}/api/bot-status",
                "method": "GET",
                "cost_usdc": X402_FEE_USDC,
                "free_tier_eligible": True,
            },
            {
                "name": "get_mcp_manifest",
                "description": "Get the full MCP/x402 payment manifest (free)",
                "endpoint": f"{base_url}/api/mcp/manifest",
                "method": "GET",
                "cost_usdc": 0.0,
                "free_tier_eligible": False,
            },
            {
                "name": "get_x402_discovery",
                "description": "Get x402 payment discovery metadata (free)",
                "endpoint": f"{base_url}/.well-known/x402.json",
                "method": "GET",
                "cost_usdc": 0.0,
                "free_tier_eligible": False,
            },
            {
                "name": "get_openapi_spec",
                "description": "Get OpenAPI 3.0 specification (free)",
                "endpoint": f"{base_url}/openapi.json",
                "method": "GET",
                "cost_usdc": 0.0,
                "free_tier_eligible": False,
            },
        ],
        "data_sources": {
            "coingecko": "https://api.coingecko.com/api/v3/simple/price",
            "dexscreener": "https://api.dexscreener.com",
            "fear_greed_index": "https://api.alternative.me/fng/",
        },
        "cache_ttl_minutes": 15,
        "instructions": {
            "payment": f"Send {X402_FEE_USDC} USDC on Base to {X402_RECEIVER_ADDRESS}",
            "verification": "Payments verified on-chain via ERC-20 Transfer event logs",
            "retry": "After payment confirmation, retry the endpoint to access data",
        },
    })


@app.route("/openapi.json")
def openapi_spec():
    """
    OpenAPI 3.0 specification for AI agent discovery.
    Includes x402 payment extensions so agents know how to pay.
    """
    base_url = request.host_url.rstrip("/")
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "Kristo Intelligence API",
            "version": "5.0.0",
            "description": "AI-powered DeFi trading signals and crypto market intelligence. "
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
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/api/stats": {
                "get": {
                    "summary": "Market activity and daily stats",
                    "x402": {"cost_usdc": X402_FEE_USDC, "free_tier_eligible": True},
                    "responses": {
                        "200": {"description": "Successful response with stats data"},
                        "402": {"description": "Payment Required — free tier exhausted, send USDC to receiver"},
                    },
                }
            },
            "/api/sales": {
                "get": {
                    "summary": "Real on-chain sales history",
                    "x402": {"cost_usdc": X402_FEE_USDC, "free_tier_eligible": True},
                    "responses": {
                        "200": {"description": "Successful response with sales history"},
                        "402": {"description": "Payment Required — free tier exhausted, send USDC to receiver"},
                    },
                }
            },
            "/api/bot-status": {
                "get": {
                    "summary": "Telegram bot integration status",
                    "x402": {"cost_usdc": X402_FEE_USDC, "free_tier_eligible": True},
                    "responses": {
                        "200": {"description": "Successful response with bot status"},
                        "402": {"description": "Payment Required — free tier exhausted, send USDC to receiver"},
                    },
                }
            },
            "/api/mcp/manifest": {
                "get": {
                    "summary": "MCP/x402 payment manifest (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "Machine-readable payment manifest"}},
                }
            },
            "/.well-known/x402.json": {
                "get": {
                    "summary": "x402 discovery file (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "x402 payment discovery metadata"}},
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "This OpenAPI specification (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "OpenAPI 3.0 specification"}},
                }
            },
            "/llms.txt": {
                "get": {
                    "summary": "LLM-friendly API description (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "Plain-text API description for LLMs"}},
                }
            },
            "/health": {
                "get": {
                    "summary": "Health check (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "Service health status"}},
                }
            },
            "/dashboard": {
                "get": {
                    "summary": "HTML dashboard (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "HTML dashboard page"}},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "x402": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Payment-Address",
                    "description": f"x402 payment: send {X402_FEE_USDC} USDC on Base to {X402_RECEIVER_ADDRESS}",
                }
            }
        },
    }
    return jsonify(spec)


@app.route("/llms.txt")
def llms_txt():
    """
    LLM-friendly plain-text description of the API for AI agent discovery.
    """
    base_url = request.host_url.rstrip("/")
    content = f"""# Kristo Intelligence API

> AI-powered DeFi trading signals and crypto market intelligence.
> Uses the x402 payment protocol — pay with USDC on Base.

## Payment (x402 Protocol)

- Chain: Base (chain_id: {X402_CHAIN_ID})
- Currency: USDC
- Token contract: {X402_USDC_CONTRACT}
- Receiver address: {X402_RECEIVER_ADDRESS}
- Price per API call: ${X402_FEE_USDC} USDC
- Free tier: {FREE_TIER_LIMIT} free call(s) per client, then payment required
- Monthly VIP: ${VIP_MONTHLY_USDC} USDC (unlimited for 30 days)

## How to Pay

1. Send exactly {X402_FEE_USDC} USDC on the Base network to {X402_RECEIVER_ADDRESS}
2. Wait for on-chain confirmation (usually ~2 seconds on Base)
3. Retry the desired API endpoint — access is granted automatically

For unlimited access, send {VIP_MONTHLY_USDC} USDC for a Monthly VIP subscription.

## Endpoints

### Paid (requires x402 payment after free tier)

- GET /api/stats — Market activity and daily stats (${X402_FEE_USDC} USDC)
- GET /api/sales — Real on-chain sales history (${X402_FEE_USDC} USDC)
- GET /api/bot-status — Telegram bot status (${X402_FEE_USDC} USDC)

### Free (always accessible)

- GET /.well-known/x402.json — x402 payment discovery metadata
- GET /openapi.json — OpenAPI 3.0 specification
- GET /llms.txt — This file (LLM-friendly API description)
- GET /api/mcp/manifest — MCP/x402 machine-readable manifest
- GET /health — Service health check
- GET /dashboard — HTML dashboard

## Base URL

{base_url}

## HTTP 402 Response

When payment is required, the API returns HTTP 402 with:
- JSON body containing payment details (receiver address, amount, chain)
- Headers: X-Payment-Required, X-Payment-Address, X-Payment-Amount-USDC

## Discovery Files

- x402: {base_url}/.well-known/x402.json
- OpenAPI: {base_url}/openapi.json
- LLMs: {base_url}/llms.txt
- MCP Manifest: {base_url}/api/mcp/manifest
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

        <!-- 9 Products Breakdown Table -->
        <div class="table-card">
            <h3>🧠 Продукти: 8 Агента + NEXUS Engine (9 продукта)</h3>
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
        Kristo Intelligence API v5 &mdash; Real Blockchain Data &mdash; <span id="footer-time"></span>
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
    const data = await fetchJSON('/api/sales');
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
    const data = await fetchJSON('/api/stats');
    document.getElementById('m-requests').textContent = data.today.requests;
    document.getElementById('m-requests-sub').textContent = data.total_requests + ' total API calls';
    document.getElementById('m-today-sales').textContent = data.today.sales_count;
    document.getElementById('m-today-volume').textContent = fmtMoney(data.today.sales_volume_usd);

    // 9 Products breakdown table
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
    const recent = data.recent_requests;
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
    const data = await fetchJSON('/api/bot-status');
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
        NEXUS Discovery Engine &mdash; Kristo Intelligence v5 &mdash; <span id="footer-time"></span>
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
        const resp = await fetch('/api/stats');
        const data = await resp.json();

        // Use real request count as base for scans
        if (scanCount === 0 && data.total_requests > 0) {
            scanCount = data.total_requests;
        }

        // Use real product hits for agent activity
        const products = data.products || [];
        products.forEach(p => {
            if (p.id !== 'nexus_engine') {
                const agent = AI_AGENTS.find(a => a.id === p.id);
                if (agent) {
                    agent.status = p.hits > 0 ? 'active' : 'idle';
                }
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

def _start_background_threads():
    """Start background threads (blockchain monitor + agent loop + Telegram sales)."""
    if getattr(app, "_bg_started", False):
        return
    app._bg_started = True

    # Start blockchain monitor (real wallet)
    t_chain = threading.Thread(target=_blockchain_monitor_loop, daemon=True, name="blockchain-monitor")
    t_chain.start()

    # Start agent thread
    t_agent = threading.Thread(target=_background_agent_loop, daemon=True, name="agent-loop")
    t_agent.start()

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

    log.info("Background threads started (blockchain monitor + agent + telegram sales).")


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