# -*- coding: utf-8 -*-
"""
Integration connector registry for Kristo Intelligence.

One place that knows every external network / protocol / marketplace the
system is wired to, exposes live status for the dashboard, and implements
the standard-x402 (EIP-3009 / X-PAYMENT) inbound rail through a facilitator.

Connectors:
  base-usdc-receiver      inbound   Base/USDC on-chain settlement (monitor)
  x402-challenge-v2       inbound   canonical x402 v2 challenge builders
  x402-eip3009            inbound   STANDARD X-PAYMENT rail via facilitator
  x402-outbound-buyer     outbound  pay OTHER x402 APIs (packages/x402-client)
  l402-lightning          outbound  L402 (Lightning macaroon/preimage) bridge
  mcp-sse                 inbound   MCP clients (Claude Desktop, Cursor, …)
  marketplace-x402scan    outbound  listing/distribution
  marketplace-payapi      outbound  listing/distribution
  marketplace-nohumans    outbound  listing/distribution
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

# ── Activity ledger (in-memory, per-process) ────────────────────────────────
_ACTIVITY = {}  # conn_id -> ISO timestamp of last real use


def touch(conn_id: str) -> None:
    """Record a real interaction with a connector (call it on every use)."""
    _ACTIVITY[conn_id] = datetime.now(timezone.utc).isoformat()


def last_activity(conn_id: str):
    return _ACTIVITY.get(conn_id)


# ── Standard x402 (EIP-3009) facilitator rail ───────────────────────────────
FACILITATOR_URL = os.getenv(
    "X402_FACILITATOR_URL",
    "https://api.cdp.coinbase.com/platform/v2/x402",
).rstrip("/")
FACILITATOR_TIMEOUT = float(os.getenv("X402_FACILITATOR_TIMEOUT", "15"))


def _facilitator_post(endpoint: str, body: dict):
    """POST JSON to the x402 facilitator; returns parsed dict or None."""
    url = f"{FACILITATOR_URL}/{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=FACILITATOR_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def verify_standard_payment(payment_header: str, requirements: dict):
    """
    Verify a STANDARD x402 X-PAYMENT header (EIP-3009 payload) through the
    facilitator. Returns (ok: bool, payer: str | None, detail: str).
    """
    body = {
        "x402Version": 2,
        "paymentHeader": payment_header,
        "paymentRequirements": requirements,
    }
    resp = _facilitator_post("verify", body)
    if not isinstance(resp, dict):
        touch("x402-eip3009")
        return False, None, "facilitator_unreachable"
    if resp.get("isValid") is True:
        touch("x402-eip3009")
        return True, resp.get("payer"), "verified"
    return False, resp.get("payer"), resp.get("invalidReason", "invalid_payment")


def settle_standard_payment(payment_header: str, requirements: dict):
    """
    Settle a verified standard x402 payment through the facilitator.
    Returns (tx_hash: str | None, detail: str).
    """
    body = {
        "x402Version": 2,
        "paymentHeader": payment_header,
        "paymentRequirements": requirements,
    }
    resp = _facilitator_post("settle", body)
    if not isinstance(resp, dict):
        return None, "facilitator_unreachable"
    if resp.get("success") is True and resp.get("transaction"):
        touch("base-usdc-receiver")
        return resp["transaction"], "settled"
    return None, resp.get("errorReason", "settle_failed")


# ── L402 (Lightning) outbound bridge ────────────────────────────────────────
def l402_parse_challenge(www_authenticate: str):
    """
    Parse an L402 challenge: 'L402 macaroon=<b64>, invoice=<bolt11>'.
    Returns {'macaroon': …, 'invoice': …} or None. Parsing is always
    available; SETTLEMENT additionally requires a Lightning node
    (L402_LND_ADDRESS / L402_LND_MACAROON env vars) — see l402_ready().
    """
    if not www_authenticate or "L402" not in www_authenticate:
        return None
    out = {}
    # Strip the scheme prefix ("L402 macaroon=..." / "L402 macaroon=...")
    for part in www_authenticate.replace("L402", "", 1).split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip().lower()] = v.strip().strip('"')
    if "macaroon" in out and "invoice" in out:
        return {"macaroon": out["macaroon"], "invoice": out["invoice"]}
    return None


def l402_ready() -> bool:
    """Lightning settlement is available only with node credentials set."""
    return bool(os.getenv("L402_LND_ADDRESS")) and bool(os.getenv("L402_LND_MACAROON"))


# ── Registry status (consumed by /api/connectors + dashboard) ───────────────
def registry_status(wallet_state: dict) -> list:
    """Build the live connector list for the dashboard / API."""
    now_iso = datetime.now(timezone.utc).isoformat()
    wallet_addr = wallet_state.get("wallet_address")
    receiver = wallet_state.get("fee_receiver")
    monitor_ready = bool(receiver) and bool(wallet_state.get("fee_receiver"))

    entries = [
        {
            "id": "base-usdc-receiver",
            "name": "Base / USDC settlement",
            "protocol": "ERC-20 Transfer monitor (Base mainnet)",
            "direction": "inbound",
            "status": "active" if monitor_ready else "inactive",
            "detail": f"receiver={receiver}" if receiver else "no receiver bound",
        },
        {
            "id": "x402-challenge-v2",
            "name": "x402 v2 challenge builders",
            "protocol": "x402 v2 (CAIP-2, atomic units, bazaar schema)",
            "direction": "inbound",
            "status": "active",
            "detail": "canonical challenges on all paid routes",
        },
        {
            "id": "x402-eip3009",
            "name": "Standard x402 client rail (X-PAYMENT / EIP-3009)",
            "protocol": "x402 v2 via facilitator verify+settle",
            "direction": "inbound",
            "status": "active" if FACILITATOR_URL else "inactive",
            "detail": f"facilitator={FACILITATOR_URL}",
        },
        {
            "id": "x402-outbound-buyer",
            "name": "x402 outbound buyer",
            "protocol": "x402 client (packages/x402-client)",
            "direction": "outbound",
            "status": "active" if wallet_addr else "inactive",
            "detail": f"payer wallet={wallet_addr}" if wallet_addr else "no WALLET_PRIVATE_KEY loaded",
        },
        {
            "id": "l402-lightning",
            "name": "L402 / Lightning bridge",
            "protocol": "L402 (macaroon + bolt11 invoice, preimage retry)",
            "direction": "outbound",
            "status": "active" if l402_ready() else "inactive",
            "detail": "settlement ready" if l402_ready()
            else "challenge parsing active; settlement needs L402_LND_ADDRESS + L402_LND_MACAROON",
        },
        {
            "id": "mcp-sse",
            "name": "MCP client gateway",
            "protocol": "Model Context Protocol (SSE)",
            "direction": "inbound",
            "status": "active",
            "detail": "/mcp/sse + /api/mcp/manifest live",
        },
        {
            "id": "marketplace-x402scan",
            "name": "x402scan directory",
            "protocol": "x402scan discovery spec",
            "direction": "outbound",
            "status": "active",
            "detail": "11 resources listed (2026-08-28)",
        },
        {
            "id": "marketplace-payapi",
            "name": "PayAPI Market directory",
            "protocol": "settlement-verified listings",
            "direction": "outbound",
            "status": "active",
            "detail": "resubmission in review (2026-08-29)",
        },
        {
            "id": "marketplace-nohumans",
            "name": "nohumans.directory",
            "protocol": "agent directory",
            "direction": "outbound",
            "status": "active",
            "detail": "3x VERIFIED",
        },
    ]
    for e in entries:
        e["last_activity"] = _ACTIVITY.get(e["id"], now_iso)
    return entries

