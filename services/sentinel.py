"""
Kristo Sentinel — in-app autonomous monitoring & alerting agent
================================================================
Runs as a background thread inside the Kristo Intelligence 6 web service,
watching the service itself, on-chain revenue, and GitHub presence 24/7.
Sends Telegram alerts only when something CHANGES (no spam).

Checks:
  1. API health        — every 10 min   (alert on down / recovery transitions)
  2. On-chain revenue  — every 30 min   (alert on every new USDC payment)
  3. GitHub presence   — every 6 h      (stars/issues + directory PR merges)
  4. Weekly report     — Sundays 18:00  (traffic, revenue, PR status)

Configuration (env):
  TELEGRAM_BOT_TOKEN   — bot token (already used by the sales bot)
  TELEGRAM_CHAT_ID     — recipient chat id for alerts
  KRISTO_API_BASE      — public URL of this service (default: Render URL)
  SENTINEL_ENABLED     — set to 'false' to disable the thread entirely

State is kept in memory: after a restart the first cycle creates a baseline
without alerts, so deploys never produce alert spam.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

import requests

from config import BASE_RPC_URL, BASE_USDC_CONTRACT, get_base_fee_receiver

log = logging.getLogger("kristo.v6.sentinel")

# ── Configuration ────────────────────────────────────────────────────────────
HEALTH_INTERVAL = 10 * 60       # 10 min
REVENUE_INTERVAL = 30 * 60      # 30 min
GITHUB_INTERVAL = 6 * 60 * 60   # 6 h
REPORT_WEEKDAY = 6              # Sunday
REPORT_HOUR = 18                # 18:00 server time

FEE_RECEIVER = get_base_fee_receiver()
REPO = "hristovdimitri2-hub/kristo-intelligence-6"
WATCHED_PRS = [
    ("xpaysh/awesome-x402", 1308),
    ("punkpeye/awesome-mcp-servers", 12799),
]


def sentinel_enabled() -> bool:
    if os.getenv("SENTINEL_ENABLED", "").strip().lower() in {"0", "false", "no"}:
        return False
    return bool(
        (os.getenv("TELEGRAM_BOT_TOKEN", "") or "").strip()
        and (os.getenv("TELEGRAM_CHAT_ID", "") or "").strip()
    )


# ── Telegram ─────────────────────────────────────────────────────────────────
def _tg_send(text: str) -> bool:
    token = (os.getenv("TELEGRAM_BOT_TOKEN", "") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID", "") or "").strip()
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=20,
        )
        return bool(r.json().get("ok"))
    except Exception as exc:
        log.warning("Sentinel Telegram send failed: %s", exc)
        return False


# ── Checks ───────────────────────────────────────────────────────────────────
def _api_base() -> str:
    return (
        os.getenv("KRISTO_API_BASE", "").strip().rstrip("/")
        or os.getenv("APP_PUBLIC_URL", "").strip().rstrip("/")
        or "https://kristo-intelligence-api.onrender.com"
    )


def _check_health(state: dict) -> None:
    now_status, detail = None, ""
    try:
        r = requests.get(f"{_api_base()}/health", timeout=30)
        if r.status_code == 200:
            body = r.json()
            now_status = body.get("status")
            detail = f"blockchain.ready={body.get('blockchain', {}).get('ready')}"
        else:
            now_status, detail = "down", f"HTTP {r.status_code}"
    except Exception as exc:
        now_status, detail = "down", str(exc)[:120]

    prev = state.get("health")
    if prev != now_status and prev is not None:
        icon = "🔴" if now_status == "down" else "🟢"
        _tg_send(
            f"{icon} <b>Kristo API status changed</b>\n"
            f"{prev} → <b>{now_status}</b>\n{detail}\n{_api_base()}/health"
        )
    state["health"] = now_status
    log.info("Sentinel health check: %s (%s)", now_status, detail)


def _check_revenue(state: dict) -> None:
    try:
        padded = FEE_RECEIVER[2:].lower().rjust(64, "0")
        payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                   "params": [{"to": BASE_USDC_CONTRACT,
                               "data": "0x70a08231" + padded}, "latest"]}
        result = requests.post(BASE_RPC_URL, json=payload, timeout=30).json()
        balance = int(result["result"], 16) / 1e6
    except Exception as exc:
        log.warning("Sentinel revenue check failed: %s", exc)
        return

    prev = float(state.get("usdc_balance") or 0.0)
    if balance > prev:
        _tg_send(
            f"💰 <b>New payment received!</b>\n"
            f"+{balance - prev:.2f} USDC\n"
            f"Receiver balance: <b>{balance:.2f} USDC</b>\n"
            f"Chain: Base mainnet"
        )
    state["usdc_balance"] = balance
    log.info("Sentinel revenue check: %.6f USDC", balance)



def _check_github(state: dict) -> None:
    headers = {"Accept": "application/vnd.github+json"}
    try:
        repo = requests.get(f"https://api.github.com/repos/{REPO}",
                             headers=headers, timeout=30).json()
        stars = repo.get("stargazers_count", 0)
        issues = repo.get("open_issues_count", 0)
        prev_s = state.get("stars") or 0
        if stars > prev_s and prev_s > 0:
            _tg_send(f"⭐ <b>New GitHub star!</b>\n{REPO}: {prev_s} → <b>{stars}</b> ⭐")
        if issues > (state.get("open_issues") or 0) and (state.get("open_issues") or 0) > 0:
            _tg_send(f"💬 <b>New GitHub issue</b> on {REPO} ({issues} open)")
        state["stars"] = stars
        state["forks"] = repo.get("forks_count", 0)
        state["open_issues"] = issues
    except Exception as exc:
        log.warning("Sentinel GitHub repo check failed: %s", exc)

    prs_state = state.setdefault("prs", {})
    for full_repo, number in WATCHED_PRS:
        key = f"{full_repo}#{number}"
        try:
            pr = requests.get(
                f"https://api.github.com/repos/{full_repo}/pulls/{number}",
                headers=headers, timeout=30).json()
            status = "merged" if pr.get("merged", False) else pr.get("state", "?")
            prev = prs_state.get(key)
            if prev and prev != status:
                icon = "🎉" if status == "merged" else "ℹ️"
                _tg_send(
                    f"{icon} <b>Directory PR updated</b>\n"
                    f"{key}: {prev} → <b>{status}</b>\n"
                    f"https://github.com/{full_repo}/pull/{number}"
                )
            prs_state[key] = status
        except Exception as exc:
            log.warning("Sentinel PR check failed for %s: %s", key, exc)


def _build_report(state: dict) -> str:
    lines = ["📊 <b>Kristo Sentinel — weekly report</b>",
             f"_{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_", ""]
    try:
        stats = requests.get(f"{_api_base()}/api/dashboard-stats", timeout=30).json()
        today = stats.get("today", {})
        lines.append(f"🌐 API status: <b>{state.get('health')}</b>")
        lines.append(f"📈 Requests today: {today.get('requests', '?')}")
        lines.append(f"🤝 Total sales: {stats.get('total_sales', 0)} "
                     f"(${stats.get('total_volume_usd', 0):.2f})")
    except Exception:
        lines.append("🌐 API stats unavailable")
    lines.append(f"💰 Receiver balance: <b>{state.get('usdc_balance', 0):.2f} USDC</b>")
    lines.append(f"⭐ GitHub: {state.get('stars', 0)} stars, "
                 f"{state.get('open_issues', 0)} open issues")
    if state.get("prs"):
        lines.append("📋 Directory PRs: " + ", ".join(
            f"{k.split('#')[0].split('/')[-1]}: {v}" for k, v in state["prs"].items()))
    lines.append("")
    lines.append(f"🔗 {_api_base()}/dashboard")
    return "\n".join(lines)


# ── Thread loop ──────────────────────────────────────────────────────────────
def sentinel_loop() -> None:
    """Background thread: run checks on their intervals, alert on changes."""
    log.info("Sentinel thread started (health=%ds revenue=%ds github=%ds).",
             HEALTH_INTERVAL, REVENUE_INTERVAL, GITHUB_INTERVAL)
    state: dict = {
        "health": None, "usdc_balance": 0.0, "stars": 0, "forks": 0,
        "open_issues": 0, "prs": {}, "last_report_date": None,
        "last_health_check": 0.0, "last_revenue_check": 0.0,
        "last_github_check": 0.0,
    }
    # Baseline first cycle (no alerts — previous values are unset).
    try:
        _check_health(state)
        _check_revenue(state)
        _check_github(state)
    except Exception as exc:
        log.warning("Sentinel baseline cycle failed: %s", exc)

    _tg_send("🛡️ <b>Kristo Sentinel активен</b> — вграден в приложението, "
             "мониторинг на живо 24/7.")

    while True:
        try:
            now = time.time()
            if now - state["last_health_check"] >= HEALTH_INTERVAL:
                _check_health(state)
                state["last_health_check"] = now
            if now - state["last_revenue_check"] >= REVENUE_INTERVAL:
                _check_revenue(state)
                state["last_revenue_check"] = now
            if now - state["last_github_check"] >= GITHUB_INTERVAL:
                _check_github(state)
                state["last_github_check"] = now
            local = datetime.now()
            today = local.strftime("%Y-%m-%d")
            if (local.weekday() == REPORT_WEEKDAY and local.hour >= REPORT_HOUR
                    and state.get("last_report_date") != today):
                _tg_send(_build_report(state))
                state["last_report_date"] = today
        except Exception as exc:
            log.warning("Sentinel cycle error (non-fatal): %s", exc)
        time.sleep(60)


def start_sentinel_thread() -> None:
    """Start the sentinel daemon thread (no-op when not configured/disabled)."""
    if not sentinel_enabled():
        log.info("Sentinel disabled (TELEGRAM_CHAT_ID/TELEGRAM_BOT_TOKEN not "
                 "set or SENTINEL_ENABLED=false).")
        return
    threading.Thread(target=sentinel_loop, daemon=True, name="kristo-sentinel").start()
