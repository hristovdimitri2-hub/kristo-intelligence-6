"""
Telegram Sales Bot — micro-transactions via x402 on Base
=========================================================

This module provides:
  * `send_market_bulletin()` — sends a market bulletin to a Telegram chat,
    including the current Fear & Greed index and ETH/DEGEN prices fetched
    from `services.market_data.py`.  Every message includes an inline
    keyboard button: "🔓 Отключи пълен VIP анализ за <VIP_PRICE_USDC> USDC"
    (the amount is read from config.KRISTO_VIP_ANALYSIS_PRICE, never typed).
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
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from services.market_data import get_market_snapshot
from services.ai_engine import generate_market_bulletin

# ── Central configuration (bound wallet address) ───────────────────────────
from config import get_base_fee_receiver
from config import KRISTO_VIP_ANALYSIS_PRICE

log = logging.getLogger("kristo.v6.telegram_sales")

# ── x402 Payment constants (mirrors main.py) ────────────────────────────────
# Receiver address is bound via config.get_base_fee_receiver() (hard fallback)
X402_RECEIVER_ADDRESS = get_base_fee_receiver()
X402_USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
X402_CHAIN = "base"
X402_CHAIN_ID = 8453
VIP_PRICE_USDC = KRISTO_VIP_ANALYSIS_PRICE
# (was a literal 0.10; now the single source in config.py feeds both this price
# and main.VIP_THRESHOLD_USDC, so the bot's button and /price can never drift)

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


def _send_text(
    token: str,
    chat_id: str,
    text: str,
    *,
    reply_markup: Optional[dict] = None,
    reply_to_message_id: Optional[int] = None,
) -> Optional[dict]:
    """Send a message and retry as plain text if Markdown rendering is rejected."""
    safe_text = text if len(text) <= 4096 else f"{text[:4093]}..."
    if len(text) > 4096:
        log.warning("Telegram reply truncated from %d characters.", len(text))
    payload = {"chat_id": chat_id, "text": safe_text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    result = _api_call("sendMessage", token, payload)
    if result is not None:
        return result

    fallback_payload = {"chat_id": chat_id, "text": safe_text}
    if reply_markup:
        fallback_payload["reply_markup"] = reply_markup
    # 18.09: the fallback used to KEEP reply_to_message_id. Telegram answers
    # "Bad Request: message to be replied not found" when the quoted message is
    # gone (deleted, or too old), so BOTH attempts failed and the reply was never
    # delivered at all — a buyer tapping an old button got silence. The quote is
    # cosmetic; the text is the product. Retry without it.
    return _api_call("sendMessage", token, fallback_payload)


def _service_unavailable_reply() -> str:
    """Short user-facing fallback for external market or AI service failures."""
    return (
        "🤖 Kristo Intelligence е онлайн, но пазарните данни временно не са налични.\n\n"
        "Опитайте отново след малко или използвайте /price за VIP информация."
    )


def _market_freshness_notice(snapshot: dict) -> str:
    """Explain CoinGecko cache freshness without presenting stale data as live."""
    freshness = (snapshot.get("freshness") or {}).get("coingecko") or {}
    state = freshness.get("state", "unavailable")
    age_seconds = freshness.get("age_seconds")
    age_text = (
        f"{max(1, round(age_seconds / 60))} мин."
        if isinstance(age_seconds, (int, float))
        else "неизвестна възраст"
    )

    if state == "live":
        return "🦎 *CoinGecko*: live данни"
    if state == "cached":
        return f"🦎 *CoinGecko*: кеширан snapshot ({age_text})"
    if state == "stale":
        return f"⚠️ *CoinGecko*: кеширани данни ({age_text}); live обновяването е временно ограничено."
    return "⚠️ *CoinGecko*: live данните временно не са налични."


# ── Auto setWebhook on startup ──────────────────────────────────────────────

# Public URL where Telegram can deliver updates.
# Telegram will POST updates to: <WEBHOOK_PUBLIC_URL>/api/telegram-webhook
WEBHOOK_PUBLIC_URL = (
    os.getenv("WEBHOOK_PUBLIC_URL")
    or os.getenv("APP_PUBLIC_URL")
    or ""
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
    webhook_secret = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    if not webhook_secret:
        log.warning("register_webhook: no webhook secret — skipping unsafe registration.")
        return None
    if not WEBHOOK_PUBLIC_URL:
        log.warning("register_webhook: no public URL — skipping.")
        return None

    payload = {
        "url": WEBHOOK_ENDPOINT,
        "secret_token": webhook_secret,
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
    Generate a payment payload pointing to the Base USDC receiver address,
    with instructions a human can actually follow.

    Returns a dict with:
      * receiver_address  — Base USDC address
      * amount_usdc       — the VIP price from the single source
                            (config.VIP_PRICE_USDC), never a literal
      * chain / chain_id   — base / 8453
      * token_contract    — USDC on Base
      * instructions      — human-readable payment + claim steps
      * explorer_link     — a REAL, verifiable page for the receiver address

    HISTORY (18.09): this returned a `deep_link` of
    `https://wallet.pay/base/<USDC>/transfer?address=…&uint256=…` — a domain
    that does not exist (the owner, testing as a buyer, landed on
    DNS_PROBE_FINISHED_NXDOMAIN). The payload was an EIP-681 URI body
    (`address=` + `uint256=`) with a fabricated HTTPS host glued on: there is no
    "wallet.pay" product, and no HTTPS wallet-transfer URL exists either — a
    wallet transfer needs the `ethereum:` scheme, which desktop Telegram cannot
    open and which most wallets only accept as a QR code. So the link is gone
    instead of being replaced with another guess. What a buyer needs at that
    moment is the exact amount, the address, and a way to VERIFY the address —
    that is what is here now (basescan.org, already used by our own dashboard).
    """
    return {
        "receiver_address": X402_RECEIVER_ADDRESS,
        "amount_usdc": VIP_PRICE_USDC,
        "chain": X402_CHAIN,
        "chain_id": X402_CHAIN_ID,
        "token_contract": X402_USDC_CONTRACT,
        "instructions": (
            f"1. Отворете вашия портфейл (който поддържа Base) и изпратете "
            f"точно {VIP_PRICE_USDC:.2f} USDC към адреса по-горе.\n"
            f"2. Изчакайте on-chain потвърждение (~2 секунди на Base).\n"
            f"3. Нашият on-chain монитор засича преводите към този адрес и "
            f"записва плащането като продажба (това не е x402 маршрут — "
            f"пращате ръчно от собствения си портфейл).\n"
            f"4. Ако не получите VIP покана след потвърждението, изпратете tx "
            f"хеша на бота — поканата ще ви бъде изпратена насаме."
        ),
        "explorer_link": f"https://basescan.org/address/{X402_RECEIVER_ADDRESS}",
    }


#: Attribution footer on EVERY bulletin (17.09 — the bot's "second screen" role).
#: The link is a LIVE 402 demonstration: opening it in a browser shows the real
#: x402 challenge (exact USDC amount + receiver) — the product itself, not a
#: landing page. No signup, no keys, nothing to install.
SOURCE_FOOTER = (
    "Source: Kristo Intelligence API — on-chain data, x402\n"
    "https://kristo-intelligence-api.onrender.com/api/v1/signal"
)

#: THE command menu — and by construction the commands this module handles.
#: getMyCommands used to return an empty list: /start worked, but Telegram's menu
#: button showed NOTHING, so a new user had to guess the commands. Every entry
#: here must be handled by `process_webhook_update`
#: (tests/test_telegram_dashboard.py asserts menu == handlers, both ways).
BOT_COMMANDS: list[dict] = [
    {"command": "start", "description": "Пазарен бюлетин + VIP оферта"},
    {"command": "help", "description": "Списък с командите"},
    {"command": "price", "description": "Цена и плащане (x402)"},
    {"command": "bulletin", "description": "Пазарен бюлетин в момента"},
    {"command": "whale", "description": "Последните китове (USDC ≥ прага)"},
    {"command": "status", "description": "Състояние на API и бота"},
    {"command": "vip", "description": "Пълен VIP анализ — как се отключва"},
]


def register_bot_commands() -> Optional[list]:
    """Publish the command menu with setMyCommands (runs on every deploy).

    Safe to call repeatedly — Telegram overwrites the previous menu. Without
    this the bot answers commands it never advertises.
    """
    token = _get_token()
    if not token:
        log.warning("register_bot_commands: no bot token — skipping.")
        return None
    result = _api_call("setMyCommands", token, {"commands": BOT_COMMANDS})
    if result is not None:
        log.info("Telegram command menu registered: %s",
                 ", ".join("/" + entry["command"] for entry in BOT_COMMANDS))
    return result


def _whale_reply(limit: int = 5) -> str:
    """The last whales from the PERSISTENT store, with the honest scan state.

    Reads `main.dashboard_db.whaleflow_summary()` — the same numbers the paid
    /api/v1/whaleflow route serves (Postgres, survives deploys). The watermark
    line is MANDATORY: "scanned until block X" while the scanner runs, or the
    owner's pause with its timestamp when it does not. An empty list must never
    read as "no whales exist" — that is the same class of lie as a phantom price.
    """
    try:
        import main as main_module

        summary = main_module.dashboard_db.whaleflow_summary(limit=limit)
    except Exception as exc:
        log.warning("Telegram /whale failed: %s", exc)
        return _service_unavailable_reply()

    whales = summary.get("whales") or []
    threshold = summary.get("threshold_usdc") or 0.0
    lines = ["🐋 *Китове — мрежови USDC ≥ $%s*" % f"{threshold:,.0f}", ""]
    if whales:
        for w in whales:
            frm = w.get("from_label") or (w.get("from") or "")[:10] + "…"
            to = w.get("to_label") or (w.get("to") or "")[:10] + "…"
            ts = str(w.get("ts") or "")[:16].replace("T", " ")
            lines.append("• *%s %s* · блок %s"
                         % (f"{float(w.get('amount_usdc') or 0):,.0f}",
                            w.get("token") or "USDC", w.get("block")))
            lines.append("  `%s` → `%s`" % (frm, to))
            lines.append("  %s UTC" % ts)
    else:
        lines.append("_В прозореца няма трансфер над прага._")
    # The all-time count is REAL and verified (18.09): the live Postgres showed
    # 1,043,954 rows / 1,043,954 distinct (tx_hash, log_index) — ZERO duplicates
    # — and 3/3 sampled rows matched actual USDC transfers on-chain to the cent.
    # That volume came from a NETWORK-WIDE ≥$50k filter (~227k/day on Base),
    # which the owner replaced with ≥$5M on 18.09 (~53/day): the numbers were
    # never wrong, "whale" simply meant something too small.
    lines.append("")
    lines.append("Всичко за всички времена: %s · последен: %s"
                 % (summary.get("all_time_count", 0),
                    str(summary.get("last_event_at") or "—")[:16].replace("T", " ")))
    if summary.get("state") == "scan_paused_by_owner":
        lines.append("⚠️ Сканът е *спрян от собственика* — данните са до блок %s. "
                     "(Състоянието е проверено при последния старт: %s UTC — "
                     "watermark-ите живеят в локалния файл, затова датата не е "
                     "историческата.)"
                     % (summary.get("scanned_until_block") or "—",
                        str(summary.get("paused_at") or "—")[:16].replace("T", " ")))
    else:
        # Telegram's legacy Markdown treats `_` as the italic marker, and a SINGLE
        # one ("live_data") is unbalanced → "can't parse entities" → the message
        # fell back to plain text on every /whale (seen live 18.09). The state is
        # data, not formatting: show it with spaces.
        lines.append("Сканирано до блок %s (състояние: %s)."
                     % (summary.get("scanned_until_block") or "—",
                        str(summary.get("state") or "—").replace("_", " ")))
    lines.append("")
    lines.append(SOURCE_FOOTER)
    return "\n".join(lines)


def _status_reply() -> str:
    """Live status for /status — reads the same state the API serves.

    Imported lazily: main imports this module, so a module-level import would be
    circular. The numbers come from main's own bot/wallet state, never guessed.
    """
    try:
        import main as main_module

        with main_module._lock:                      # noqa: SLF001 (same process)
            running = main_module._bot_status.get("telegram_bot_running")
            processed = main_module._bot_status.get("commands_processed", 0)
            wallet = main_module._wallet_state.get("wallet_address") or ""
            balance = main_module._wallet_state.get("usdc_balance", 0.0)
        wallet_line = (f"{wallet[:10]}…{wallet[-6:]}" if len(wallet) > 16
                       else (wallet or "not configured"))
        return (
            f"*Състояние*\n"
            f"Бот: {'онлайн' if running else 'офлайн'}\n"
            f"Обработени команди: {processed}\n"
            f"Портфейл: `{wallet_line}`\n"
            f"USDC баланс: ${float(balance or 0):.4f}"
        )
    except Exception as exc:                         # pragma: no cover
        log.warning("Telegram /status degraded: %s", exc)
        return _service_unavailable_reply()


def _vip_reply() -> str:
    """The VIP offer, with the amount read from the single price source."""
    return (
        f"*Пълен VIP анализ — {VIP_PRICE_USDC:.2f} USDC*\n\n"
        f"Отключва пълния сигнал + on-chain анализ за текущия пазар.\n"
        f"Плащане: {VIP_PRICE_USDC:.2f} USDC на Base към\n"
        f"`{get_base_fee_receiver()}`\n\n"
        f"Натиснете бутона по-долу, за да получите инструкциите за плащане."
    )


def _build_vip_inline_keyboard() -> dict:
    """Build a useful inline keyboard for market actions and VIP access."""
    return {
        "inline_keyboard": [
            [
                {"text": "💲 Цени", "callback_data": "price"},
                {"text": "⛽ Gas", "callback_data": "gas"},
            ],
            [
                {"text": "📈 Доходности", "callback_data": "yields"},
                {"text": "🐋 Whales", "callback_data": "whales"},
            ],
            [
                {
                    "text": f"🔓 VIP анализ за {VIP_PRICE_USDC:.2f} USDC",
                    "callback_data": "unlock_vip_analysis",
                }
            ],
        ]
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
        f"{_market_freshness_notice(snapshot)}\n\n"
        f"😱🤑 *Fear & Greed Index*: `{fng_value}` ({fng_class})\n\n"
        f"💎 *ETH*: ${_fmt(eth_price)} ({_fmt_change(eth_change)})\n"
        f"🪙 *DEGEN*: ${_fmt(degen_price)} ({_fmt_change(degen_change)})\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Искате ли по-задълбочен анализ, DeFi сигнали и trading решения?\n"
        f"Натиснете бутона по-долу 👇\n\n"
        f"{SOURCE_FOOTER}"
    )


def send_market_bulletin(chat_id: Optional[str] = None) -> Optional[dict]:
    """
    Send a market bulletin to a Telegram chat.

    The bulletin includes the current Fear & Greed index and ETH/DEGEN
    prices (from `market_data.get_market_snapshot()`), plus an inline
    button: "🔓 Отключи пълен VIP анализ за {VIP_PRICE_USDC} USDC" — the amount
    comes from the single price source, so it can never drift from the API.

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

    try:
        snapshot = get_market_snapshot()
        result = _send_text(
            token,
            target_chat,
            _format_bulletin_text(snapshot),
            reply_markup=_build_vip_inline_keyboard(),
        )
    except Exception as exc:
        log.warning("Market bulletin data unavailable: %s", exc)
        result = _send_text(token, target_chat, _service_unavailable_reply())

    if result:
        log.info("Market bulletin sent to chat %s (msg_id=%s)", target_chat, result.get("message_id"))
    return result


# ── Callback query handling (inline button) ──────────────────────────────────

def handle_callback_query(callback_data: str, chat_id: str, message_id: int,
                          user_id: Optional[str] = None) -> Optional[dict]:
    """
    Handle an inline keyboard callback query.

    When the user taps the VIP unlock button (its label carries the price from
    the single source), we reply with the payment instructions. The button lives
    in the PUBLIC channel, so since 18.09 the instructions go to the TAPPING
    USER'S private chat whenever Telegram allows it (they must have started the
    bot); otherwise the channel gets the text plus the honest hint on how to get
    it privately. Nobody's payment steps belong in a public feed.
    """
    token = _get_token()
    if not token:
        return None

    if callback_data in {"price", "prices"}:
        return send_market_bulletin(chat_id=chat_id)

    if callback_data in {"gas", "gas_fees"}:
        return _send_text(
            token,
            chat_id,
            "⛽ *Base Gas мониторинг*\n\nBase обикновено поддържа ниски такси. "
            "Преди трансакция проверете gas оценката във вашия wallet, защото тя се променя в реално време.",
            reply_to_message_id=message_id,
        )

    if callback_data in {"yields", "defi_yields"}:
        return _send_text(
            token,
            chat_id,
            "📈 *DeFi доходности*\n\nИзползвайте /bulletin за актуалния пазарен контекст. "
            "VIP анализът добавя risk-aware DeFi сигнали и следене на възможности.",
            reply_to_message_id=message_id,
        )

    if callback_data in {"whales", "whale_activity"}:
        return _send_text(
            token,
            chat_id,
            "🐋 *Whale activity*\n\nWhale трансакциите са контекст, а не самостоятелен сигнал. "
            "Използвайте /bulletin за текущия пазарен обзор или VIP анализа за по-дълбок контекст.",
            reply_to_message_id=message_id,
        )

    if callback_data == "unlock_vip_analysis":
        try:
            payment = generate_payment_link()
            reply_text = (
                f"🔓 *Отключи пълен VIP анализ*\n\n"
                f"Цена: *{payment['amount_usdc']:.2f} USDC* (Base мрежа)\n"
                f"Получател: `{payment['receiver_address']}`\n\n"
                f"*Инструкции за плащане:*\n{payment['instructions']}\n\n"
                # 18.09: a fabricated `wallet.pay` deep link lived here and led
                # straight to NXDOMAIN. What replaces it is a link that exists
                # and lets the buyer VERIFY the address on-chain (the same
                # explorer our dashboard links to), plus the honest claim path.
                f"🔍 Проверка на адреса: {payment['explorer_link']}"
            )
            # Private first: a tap in the public channel must not publish one
            # buyer's payment steps to the feed.
            if user_id and str(user_id) != str(chat_id):
                dm = _send_text(token, str(user_id), reply_text)
                if dm is not None:
                    return dm
                log.info("VIP instructions could not be DM'd to %s — falling back "
                         "to the channel with a hint.", user_id)
                return _send_text(
                    token, chat_id,
                    "🔒 Инструкциите за плащане се изпращат насаме.\n"
                    "Отворете бота и натиснете /start (или /price) — тогава "
                    "бутонът ще ви отговори в личния чат.",
                    reply_to_message_id=message_id)
            return _send_text(token, chat_id, reply_text, reply_to_message_id=message_id)
        except Exception as exc:
            log.warning("VIP callback failed: %s", exc)
            return _send_text(token, chat_id, _service_unavailable_reply(), reply_to_message_id=message_id)

    log.info("Unknown callback_data: %s", callback_data)
    return _send_text(
        token,
        chat_id,
        "Този бутон вече не е активен. Използвайте /help, за да видите наличните команди.",
        reply_to_message_id=message_id,
    )


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

#: A Base tx hash, as a buyer would paste it out of their wallet.
_TX_HASH_RE = re.compile(r"0x[0-9a-fA-F]{64}")


def _owner_chat_ids() -> set:
    """Chats allowed to run owner-only commands (never a public channel)."""
    return {c.strip() for c in (os.getenv("TELEGRAM_VIP_CHAT_ID", ""),
                                os.getenv("TELEGRAM_CHAT_ID", "")) if c.strip()}


def _is_public_chat(chat_id) -> bool:
    """True when a chat is the PUBLIC channel (where a code must never be posted).

    With TELEGRAM_VIP_CHAT_ID unset our only configured chat IS the public
    channel, so anything secret — the invite code — has to stay out of it.
    """
    vip = os.getenv("TELEGRAM_VIP_CHAT_ID", "").strip()
    return (not vip) and str(chat_id) == os.getenv("TELEGRAM_CHAT_ID", "").strip()


def _handle_owner_invite(text: str, chat_id: str, token: str) -> dict:
    """Owner-only `/invite <chat_id> [tx_hash]` — the human confirmation step.

    The claim path deliberately does NOT auto-issue: a tx hash is public on-chain,
    so handing a code to whoever claims first could hand VIP to a stranger. The
    owner reads the claim, decides, and delivers with this command: the code is
    persisted (durable, so a deploy cannot eat it) and sent to the BUYER's chat.
    """
    if str(chat_id) not in _owner_chat_ids():
        _send_text(token, str(chat_id),
                   "Тази команда е само за собственика.")
        return {"handled": True, "type": "invite_denied", "response_sent": True}

    parts = (text or "").split()
    if len(parts) < 2 or not re.fullmatch(r"-?\d+", parts[1]):
        _send_text(token, str(chat_id),
                   "Употреба: `/invite <chat_id> [tx_hash]`\n"
                   "(chat id-то идва от заявката „🔔 Заявка за VIP покана“.)")
        return {"handled": True, "type": "invite_usage", "response_sent": True}

    target = parts[1]
    tx_hash = parts[2].lower() if len(parts) > 2 else ""
    code = "KRI-VIP-" + secrets.token_hex(4).upper()
    wallet = ""
    stored = False
    try:
        import main as main_module

        if tx_hash:
            sale = main_module.dashboard_db.sale_by_tx(tx_hash)
            wallet = (sale or {}).get("sender") or ""
        stored = main_module.dashboard_db.record_vip_invite(
            code, wallet, tx_hash, chat_id=target, source="manual")
    except Exception as exc:
        log.warning("Manual VIP invite not persisted: %s", exc)

    delivered = _send_text(
        token, str(target),
        "🎉 *VIP достъп отключен*\n\n"
        f"Код: `{code}`\n\n"
        "Запазете кода — той е вашият VIP достъп. Благодарим за плащането!")

    # The receipt for the owner — WITHOUT the code when the only chat we have is
    # the public channel (the code is the product).
    if _is_public_chat(chat_id):
        receipt = ("✅ Покана издадена и изпратена насаме на `%s`.\n"
                   "(Кодът не се публикува тук — задайте TELEGRAM_VIP_CHAT_ID, "
                   "за да го виждате в личния си чат.)" % target)
    else:
        receipt = ("✅ Покана издадена и изпратена насаме.\n"
                   f"Код: `{code}`\nКупувач: `{target}`\n"
                   f"Tx: `{tx_hash or '—'}`\nЗаписана: {'да' if stored else 'НЕ (грешка)'}")
    _send_text(token, str(chat_id), receipt)
    return {"handled": True, "type": "invite_issued", "delivered": bool(delivered),
            "code": code, "target": target, "durable": stored,
            "response_sent": True}


def _handle_vip_claim(text: str, chat_id: str, token: str) -> Optional[dict]:
    """A buyer who already paid sends their tx hash — verify it and tell a human.

    18.09: the payment instructions end with "send the tx hash to the bot", but an
    unrecognised message only got "Не разпознах командата" — a dead end for
    somebody who had just sent money. This makes that step real: the hash is
    checked against `onchain_sales` (Postgres, deploy-proof) and the claim is
    forwarded to the owner, who delivers the invite privately.

    Deliberately NOT auto-issuing: a tx hash is public on-chain, so handing a code
    to whoever claims first would give VIP to a stranger. A human confirms.
    """
    match = _TX_HASH_RE.search(text or "")
    if not match:
        return None
    tx_hash = match.group(0).lower()
    try:
        import main as main_module

        sale = main_module.dashboard_db.sale_by_tx(tx_hash)
    except Exception as exc:
        log.warning("VIP claim lookup failed: %s", exc)
        sale = None

    amount = float((sale or {}).get("amount_usdc") or 0.0)
    sender = (sale or {}).get("sender") or ""
    if sale and amount >= VIP_PRICE_USDC:
        verdict = (f"✅ Записано плащане: {amount:.2f} USDC от "
                   f"{sender[:10]}…{sender[-6:]} (праг {VIP_PRICE_USDC:.2f} USDC).")
    elif sale:
        verdict = (f"⚠️ Плащането е записано ({amount:.2f} USDC), но е под прага "
                   f"{VIP_PRICE_USDC:.2f} USDC за VIP покана.")
    else:
        verdict = ("⚠️ Няма записано плащане с този tx хеш. Ако току-що платихте, "
                   "изчакайте минута (мониторът сканира блокове) и опитайте пак.")

    _send_text(token, str(chat_id),
               "📨 *Заявка за VIP покана*\n\n"
               f"Tx: `{tx_hash}`\n{verdict}\n\n"
               "Поканата се изпраща насаме след проверка.")
    owner_chat = (os.getenv("TELEGRAM_VIP_CHAT_ID", "").strip() or _get_chat_id())
    if owner_chat:
        # The owner decides, so tell them HOW to deliver — never auto-issue.
        _send_text(token, str(owner_chat),
                   "🔔 *Заявка за VIP покана*\n"
                   f"От чат: `{chat_id}`\nTx: `{tx_hash}`\n{verdict}\n\n"
                   f"За издаване: `/invite {chat_id} {tx_hash}`")
    return {"handled": True, "type": "vip_claim", "tx_hash": tx_hash,
            "found": bool(sale), "response_sent": True}


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
        # Who TAPPED it (not where it was tapped): the VIP instructions go to that
        # user's private chat, so a public-channel tap stays private (18.09).
        user_id = (cb.get("from") or {}).get("id")
        try:
            answer_callback_query(cb_id)
            if chat_id and message_id:
                sent = handle_callback_query(data, str(chat_id), message_id,
                                             user_id=user_id)
                return {
                    "handled": True,
                    "type": "callback_query",
                    "data": data,
                    "response_sent": bool(sent),
                }
        except Exception as exc:
            log.warning("Callback processing failed: %s", exc)
            if chat_id:
                sent = _send_text(token, str(chat_id), _service_unavailable_reply())
                return {
                    "handled": True,
                    "type": "callback_query",
                    "data": data,
                    "response_sent": bool(sent),
                    "degraded": True,
                }
        return {"handled": False, "reason": "callback_without_chat"}

    # ── Text message ──
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return {"handled": False, "reason": "no_text"}

    cmd = text.lower().split()[0] if text.split() else ""

    # A buyer who already paid sends their tx hash (step 4 of the payment
    # instructions). Handled BEFORE the command table so it can never fall into
    # the "Не разпознах командата" dead end — but NEVER for commands: `/invite
    # <chat> <tx>` carries a hash too and must reach its own handler.
    if not text.startswith("/"):
        claim = _handle_vip_claim(text, str(chat_id), token)
        if claim:
            return claim

    if cmd in ("/start", "/help"):
        try:
            snapshot = get_market_snapshot()
            ai_bulletin = generate_market_bulletin(snapshot)
        except Exception as exc:
            log.warning("Telegram %s degraded by external service: %s", cmd, exc)
            sent = _send_text(token, str(chat_id), _service_unavailable_reply())
            return {
                "handled": True,
                "type": "command",
                "cmd": cmd,
                "response_sent": bool(sent),
                "degraded": True,
            }

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
        reply += f"\n{_market_freshness_notice(snapshot)}\n"

        reply += (
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *Команди*:\n"
            f"/vip — пълен VIP анализ\n"
            f"/bulletin — пазарен бюлетин\n"
            f"/whale — последните китове\n"
            f"/price — информация за плащане (x402)\n"
            f"/status — състояние на бота\n"
            f"/help — това съобщение\n\n"
            f"🔓 Натиснете бутона по-долу, за да отключите пълен VIP анализ за {VIP_PRICE_USDC:.2f} USDC.\n\n"
            f"{SOURCE_FOOTER}"
        )

        sent = _send_text(token, str(chat_id), reply, reply_markup=keyboard)
        return {"handled": True, "type": "command", "cmd": cmd, "response_sent": bool(sent)}

    if cmd == "/bulletin":
        sent = send_market_bulletin(chat_id=str(chat_id))
        return {"handled": True, "type": "bulletin_sent", "response_sent": bool(sent)}

    if cmd == "/invite":
        # Owner-only confirmation for a claim (item 2 of the 18.09 decisions):
        # the human decides, the bot delivers the durable code to the buyer.
        return _handle_owner_invite(text, str(chat_id), token)

    if cmd == "/price":
        try:
            payment = generate_payment_link()
            reply = (
                f"*Цена и плащане (x402)*\n"
                f"VIP анализ: {payment['amount_usdc']:.2f} USDC\n"
                f"Мрежа: Base ({payment['chain_id']})\n"
                f"Получател: `{payment['receiver_address']}`\n\n"
                f"{payment['instructions']}"
            )
            sent = _send_text(token, str(chat_id), reply)
        except Exception as exc:
            log.warning("Telegram /price failed: %s", exc)
            sent = _send_text(token, str(chat_id), _service_unavailable_reply())
        return {"handled": True, "type": "price_info", "response_sent": bool(sent)}

    if cmd == "/whale":
        sent = _send_text(token, str(chat_id), _whale_reply())
        return {"handled": True, "type": "whale_feed",
                "response_sent": bool(sent)}

    if cmd == "/status":
        sent = _send_text(token, str(chat_id), _status_reply())
        return {"handled": True, "type": "status", "response_sent": bool(sent)}

    if cmd == "/vip":
        sent = _send_text(token, str(chat_id), _vip_reply(),
                          reply_markup=_build_vip_inline_keyboard())
        return {"handled": True, "type": "vip_offer", "response_sent": bool(sent)}

    sent = _send_text(
        token,
        str(chat_id),
        "Не разпознах командата. Използвайте /help за наличните команди.",
    )
    return {"handled": True, "type": "unknown_command", "response_sent": bool(sent)}


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