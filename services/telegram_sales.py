"""
Telegram Sales Bot — micro-transactions via x402 on Base
=========================================================

This module provides:
  * `send_market_bulletin()` — sends a market bulletin to a Telegram chat,
    including the current Fear & Greed index and ETH/DEGEN prices fetched
    from `services.market_data.py`.  Every message includes an inline
    keyboard button: "🔓 Отключи пълен VIP анализ за 0.10 USDC".
  * `generate_payment_link()` — generates a payment link pointing to the
    Base USDC receiver address with x402 verification instructions.
  * `handle_callback_query()` — processes inline-button callbacks so users
    receive the payment link when they tap the VIP button.
  * `telegram_sales_loop()` — background loop that sends automatic market
    bulletins (and checks for new payments) every 30 minutes.

All Telegram API calls use the lightweight `requests` library (no
additional heavy dependencies required).
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from services.market_data import get_market_snapshot
from services.ai_engine import generate_market_bulletin

# ── Central configuration (bound wallet address) ───────────────────────────
from config import get_base_fee_receiver

log = logging.getLogger("kristo.v5.telegram_sales")

# ── x402 Payment constants (mirrors main.py) ────────────────────────────────
# Receiver address is bound via config.get_base_fee_receiver() (hard fallback)
X402_RECEIVER_ADDRESS = get_base_fee_receiver()
X402_USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
X402_CHAIN = "base"
X402_CHAIN_ID = 8453
VIP_PRICE_USDC = 0.10

# Telegram Bot API base
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_token() -> str:
    """Return the Telegram bot token supplied through the runtime secret store."""
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def _get_chat_id() -> str:
    """Return the default chat/channel to send bulletins to."""
    return os.getenv("TELEGRAM_VIP_CHAT_ID", "").strip() or os.getenv("TELEGRAM_CHAT_ID", "").strip()


def _api_call(method: str, token: str, payload: dict, timeout: int = 15) -> Optional[dict]:
    """Make a Telegram Bot API call and return the parsed JSON result."""
    url = TELEGRAM_API_BASE.format(token=token, method=method)
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        data = resp.json()
        if not data.get("ok"):
            log.warning("Telegram API %s returned error: %s", method, data.get("description"))
            return None
        return data.get("result")
    except Exception as exc:
        log.warning("Telegram API %s failed: %s", method, exc)
        return None


# ── Auto setWebhook on startup ──────────────────────────────────────────────

# Public Render URL where the webhook endpoint is exposed.
# Telegram will POST updates to: <WEBHOOK_PUBLIC_URL>/api/telegram-webhook
WEBHOOK_PUBLIC_URL = os.getenv(
    "WEBHOOK_PUBLIC_URL",
    "https://kristo-intelligence-api.onrender.com",
).rstrip("/")

WEBHOOK_ENDPOINT = f"{WEBHOOK_PUBLIC_URL}/api/telegram-webhook"


def register_webhook() -> Optional[dict]:
    """
    Automatically register the Telegram webhook on startup.

    Calls the Telegram Bot API setWebhook method so that all incoming
    updates are delivered to:
        https://kristo-intelligence-api.onrender.com/api/telegram-webhook

    This runs on every deploy, eliminating the need for manual webhook
    registration.  Safe to call repeatedly — Telegram simply overwrites
    the previous webhook URL.

    Returns the Telegram API result dict on success, or None on failure.
    """
    token = _get_token()
    if not token:
        log.warning("register_webhook: no bot token — skipping.")
        return None

    payload = {
        "url": WEBHOOK_ENDPOINT,
        "allowed_updates": json.dumps([
            "message",
            "callback_query",
            "edited_message",
            "channel_post",
        ]),
        "drop_pending_updates": False,
    }

    try:
        url = TELEGRAM_API_BASE.format(token=token, method="setWebhook")
        resp = requests.post(url, json=payload, timeout=15)
        data = resp.json()
        if data.get("ok"):
            log.info("✅ Telegram webhook registered: %s", WEBHOOK_ENDPOINT)
            return data.get("result")
        else:
            log.warning(
                "❌ Telegram setWebhook failed: %s (description: %s)",
                data.get("description"),
                data.get("error_code"),
            )
            return None
    except Exception as exc:
        log.warning("register_webhook request failed: %s", exc)
        return None


# ── Payment link generation ─────────────────────────────────────────────────

def generate_payment_link() -> dict:
    """
    Generate a payment link/payload pointing to the Base USDC receiver
    address with x402 verification instructions.

    Returns a dict with:
      * receiver_address  — Base USDC address
      * amount_usdc       — 0.10
      * chain / chain_id   — base / 8453
      * token_contract    — USDC on Base
      * instructions      — human-readable x402 verification steps
      * deep_link         — optional wallet deep link (erc20 transfer)
    """
    amount_raw = int(VIP_PRICE_USDC * 10 ** 6)  # USDC has 6 decimals on Base
    deep_link = (
        f"https://wallet.pay/base/{X402_USDC_CONTRACT}/transfer"
        f"?address={X402_RECEIVER_ADDRESS}&uint256={amount_raw}"
    )
    return {
        "receiver_address": X402_RECEIVER_ADDRESS,
        "amount_usdc": VIP_PRICE_USDC,
        "chain": X402_CHAIN,
        "chain_id": X402_CHAIN_ID,
        "token_contract": X402_USDC_CONTRACT,
        "instructions": (
            f"1. Изпратете точно {VIP_PRICE_USDC:.2f} USDC в мрежата Base "
            f"към адрес:\n`{X402_RECEIVER_ADDRESS}`\n"
            f"2. Изчакайте on-chain потвърждение (~2 секунди на Base).\n"
            f"3. Платежната система x402 автоматично ще засече транзакцията "
            f"и ще отключи пълния VIP анализ.\n"
            f"4. Алтернативно, върнете се в бота и натиснете бутона отново — "
            f"достъпът ще бъде предоставен веднага след потвърждение."
        ),
        "deep_link": deep_link,
    }


def _build_vip_inline_keyboard() -> dict:
    """Build the inline keyboard markup with the VIP unlock button."""
    return {
        "inline_keyboard": [[
            {
                "text": f"🔓 Отключи пълен VIP анализ за {VIP_PRICE_USDC:.2f} USDC",
                "callback_data": "unlock_vip_analysis",
            }
        ]]
    }


# ── Market bulletin ──────────────────────────────────────────────────────────

def _format_bulletin_text(snapshot: dict) -> str:
    """Format the market bulletin message text from a market snapshot."""
    fng = snapshot.get("fear_greed_index", {}) or {}
    fng_value = fng.get("value", "N/A")
    fng_class = fng.get("classification", "N/A")

    tokens = snapshot.get("tokens", {}) or {}
    eth = tokens.get("eth", {})
    degen = tokens.get("degen", {})

    eth_price = eth.get("price_usd")
    eth_change = eth.get("change_24h")
    degen_price = degen.get("price_usd")
    degen_change = degen.get("change_24h")

    def _fmt(val, suffix=""):
        if val is None:
            return "N/A"
        if isinstance(val, float):
            return f"{val:,.4f}{suffix}"
        return f"{val}{suffix}"

    def _fmt_change(val):
        if val is None:
            return "N/A"
        arrow = "🟢" if val >= 0 else "🔴"
        return f"{arrow} {val:+.2f}%"

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return (
        f"📊 *Kristo Market Bulletin*\n"
        f"_{now_str}_\n\n"
        f"😱🤑 *Fear & Greed Index*: `{fng_value}` ({fng_class})\n\n"
        f"💎 *ETH*: ${_fmt(eth_price)} ({_fmt_change(eth_change)})\n"
        f"🪙 *DEGEN*: ${_fmt(degen_price)} ({_fmt_change(degen_change)})\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Искате ли по-задълбочен анализ, DeFi сигнали и trading решения?\n"
        f"Натиснете бутона по-долу 👇"
    )


def send_market_bulletin(chat_id: Optional[str] = None) -> Optional[dict]:
    """
    Send a market bulletin to a Telegram chat.

    The bulletin includes the current Fear & Greed index and ETH/DEGEN
    prices (from `market_data.get_market_snapshot()`), plus an inline
    button: "🔓 Отключи пълен VIP анализ за 0.10 USDC".

    Returns the Telegram API result dict on success, or None on failure.
    """
    token = _get_token()
    if not token:
        log.info("Market bulletin skipped — TELEGRAM_BOT_TOKEN not configured.")
        return None

    target_chat = chat_id or _get_chat_id()
    if not target_chat:
        log.info("Market bulletin skipped — no TELEGRAM_VIP_CHAT_ID / TELEGRAM_CHAT_ID configured.")
        return None

    snapshot = get_market_snapshot()
    text = _format_bulletin_text(snapshot)
    keyboard = _build_vip_inline_keyboard()

    result = _api_call("sendMessage", token, {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard,
    })

    if result:
        log.info("Market bulletin sent to chat %s (msg_id=%s)", target_chat, result.get("message_id"))
    return result


# ── Callback query handling (inline button) ──────────────────────────────────

def handle_callback_query(callback_data: str, chat_id: str, message_id: int) -> Optional[dict]:
    """
    Handle an inline keyboard callback query.

    When the user taps "🔓 Отключи пълен VIP анализ за 0.10 USDC",
    we reply with the payment link and x402 verification instructions.
    """
    token = _get_token()
    if not token:
        return None

    if callback_data == "unlock_vip_analysis":
        payment = generate_payment_link()
        reply_text = (
            f"🔓 *Отключи пълен VIP анализ*\n\n"
            f"Цена: *{payment['amount_usdc']:.2f} USDC* (Base мрежа)\n"
            f"Получател: `{payment['receiver_address']}`\n\n"
            f"*Инструкции за x402 верификация:*\n{payment['instructions']}\n\n"
            f"🔗 *Wallet deep link*:\n{payment['deep_link']}"
        )
        return _api_call("sendMessage", token, {
            "chat_id": chat_id,
            "text": reply_text,
            "parse_mode": "Markdown",
            "reply_to_message_id": message_id,
        })

    log.debug("Unknown callback_data: %s", callback_data)
    return None


def answer_callback_query(callback_query_id: str) -> Optional[dict]:
    """Acknowledge a callback query so Telegram doesn't show a loading spinner."""
    token = _get_token()
    if not token:
        return None
    return _api_call("answerCallbackQuery", token, {
        "callback_query_id": callback_query_id,
        "text": "Платежният линк е генериран ✅",
    })


# ── Webhook payload processing ───────────────────────────────────────────────

def process_webhook_update(update: dict) -> Optional[dict]:
    """
    Process a single Telegram Update object received via webhook.

    Handles:
      * `message` — text commands (/start, /bulletin, /help)
      * `callback_query` — inline button taps (unlock_vip_analysis)

    Returns a dict describing the action taken, or None if no action.
    """
    token = _get_token()
    if not token:
        return {"handled": False, "reason": "no_token"}

    # ── Callback query (inline button) ──
    cb = update.get("callback_query")
    if cb:
        cb_id = cb.get("id", "")
        data = cb.get("data", "")
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        message_id = cb.get("message", {}).get("message_id")
        answer_callback_query(cb_id)
        if chat_id and message_id:
            handle_callback_query(data, str(chat_id), message_id)
        return {"handled": True, "type": "callback_query", "data": data}

    # ── Text message ──
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return {"handled": False, "reason": "no_text"}

    cmd = text.lower().split()[0] if text.split() else ""

    if cmd in ("/start", "/help"):
        # ── Fetch real-time market snapshot (CoinGecko + DEXScreener + Fear & Greed) ──
        snapshot = get_market_snapshot()

        # ── Generate AI bulletin via GLM model (with offline fallback) ──
        ai_bulletin = generate_market_bulletin(snapshot)

        # ── Build the reply: AI analysis + market data + payment button ──
        keyboard = _build_vip_inline_keyboard()

        reply = (
            f"🤖 *Kristo Intelligence Bot*\n\n"
            f"_{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 *AI анализ (GLM)*:\n{ai_bulletin}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Пазарни данни (DEXScreener + CoinGecko)*:\n"
        )

        # Append top DEX pairs from Base
        dex_pairs = snapshot.get("dex_pairs_base", []) or []
        if dex_pairs:
            for pair in dex_pairs[:3]:
                base_token = pair.get("base_token", "N/A")
                dex = pair.get("dex", "N/A")
                price = pair.get("price_usd")
                vol = pair.get("volume_24h")
                reply += f"  • {base_token} ({dex}): ${price} | 24h vol: ${vol}\n"
        else:
            reply += "  _Няма налични DEX двойки в момента._\n"

        # Append Fear & Greed index
        fng = snapshot.get("fear_greed_index", {}) or {}
        fng_value = fng.get("value", "N/A")
        fng_class = fng.get("classification", "N/A")
        reply += f"\n😱🤑 *Fear & Greed Index*: `{fng_value}` ({fng_class})\n"

        reply += (
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *Команди*:\n"
            f"/bulletin — пазарен бюлетин\n"
            f"/price — информация за плащане (x402)\n"
            f"/help — това съобщение\n\n"
            f"🔓 Натиснете бутона по-долу, за да отключите пълен VIP анализ за 0.10 USDC."
        )

        _api_call("sendMessage", token, {
            "chat_id": chat_id,
            "text": reply,
            "parse_mode": "Markdown",
            "reply_markup": keyboard,
        })
        return {"handled": True, "type": "command", "cmd": cmd}

    if cmd == "/bulletin":
        send_market_bulletin(chat_id=str(chat_id))
        return {"handled": True, "type": "bulletin_sent"}

    if cmd == "/price":
        payment = generate_payment_link()
        reply = (
            f"*Цена и плащане (x402)*\n"
            f"VIP анализ: {payment['amount_usdc']:.2f} USDC\n"
            f"Мрежа: Base ({payment['chain_id']})\n"
            f"Получател: `{payment['receiver_address']}`\n\n"
            f"{payment['instructions']}"
        )
        _api_call("sendMessage", token, {
            "chat_id": chat_id, "text": reply, "parse_mode": "Markdown",
        })
        return {"handled": True, "type": "price_info"}

    return {"handled": False, "reason": "unknown_command"}


# ── Background loop (auto bulletins + payment check every 30 min) ───────────

def telegram_sales_loop():
    """
    Background thread that:
      * Sends an automatic market bulletin every 30 minutes.
      * (Payment verification itself is handled by the blockchain monitor
        in main.py — this loop simply triggers bulletins which contain the
        VIP unlock button, driving new micro-transactions.)

    If TELEGRAM_BOT_TOKEN is not configured, the thread exits gracefully.
    """
    token = _get_token()
    if not token:
        log.info("Telegram sales loop: no bot token — thread exiting silently.")
        return

    # Webhook-only mode: if no chat id is configured, do not poll or send anything.
    # The loop exits quietly so no "Unauthorized" or spam errors pollute the logs.
    if not _get_chat_id():
        log.info("Telegram sales loop: no TELEGRAM_CHAT_ID configured — webhook-only mode, thread exiting silently.")
        return

    log.info("Telegram sales loop started (interval=30 min).")
    interval = int(os.getenv("TELEGRAM_SALES_INTERVAL", "1800"))  # 30 minutes

    # Send an initial bulletin shortly after startup
    time.sleep(10)
    try:
        send_market_bulletin()
    except Exception as exc:
        log.warning("Initial market bulletin failed: %s", exc)

    while True:
        try:
            time.sleep(interval)
            send_market_bulletin()
            log.info("Auto market bulletin sent at %s", datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            log.warning("Telegram sales loop cycle failed (non-fatal): %s", exc)