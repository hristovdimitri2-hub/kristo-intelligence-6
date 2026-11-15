# -*- coding: utf-8 -*-
r"""
scripts/phase1_paid_call.py — Phase-1 micro-payment helper.

Makes ONE x402 paid call and prints EXACTLY ONE final stdout line as JSON:
    {"ok":true,"path":"...","usd":0.003,"tx":"0x..."}
    {"ok":false,"error":"reason"}

REUSE (per task order b/c): the proven Rail-1 handshake from
scripts/demo_sponsored_pay.py (import-safe: it has def main + __main__ guard):
  GET 402 -> sign EIP-3009 -> echo extensions+resource -> retry with
  PAYMENT-SIGNATURE header -> HTTP 200 = paid call delivered.

RULES honored:
  - exit 0 ONLY when the endpoint returned HTTP 200 after the x402 payment
  - NEVER prints key material or .env secrets; NEVER opens files under secrets\*
    (the payer key comes ONLY from env: DEMO_PRIVATE_KEY or WALLET_PRIVATE_KEY)
  - network only to --base (+ nothing else; settlement relayer pays gas)
  - no new dependencies (uses repo's venv: eth_account/web3 stack)
  - git untouched
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Reuse of the proven signing/echo helpers (no side effects on import).
from demo_sponsored_pay import (  # noqa: E402
    build_signature,
    echo_extensions,
)


def get_challenge(base: str, path: str) -> tuple[dict, dict]:
    """Free GET -> (402 body, accepts[0]); mirrors demo.fetch_challenge but
    takes an explicit path (demo's uses its own CHALLENGE_PATH constant).
    NOTE: urllib raises HTTPError for 402 — catch it (same as demo does)."""
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:      # 402 lands here
        status, raw = exc.code, exc.read()
    if status != 402:
        raise RuntimeError("expected HTTP 402, got %s" % status)
    body = json.loads(raw.decode("utf-8"))
    acc = (body.get("accepts") or body.get("accepts[]")
           or body.get("x402_accepts") or [{}])[0]
    if not acc:
        raise RuntimeError("402 body has no accepts[]")
    return body, acc


def emit(obj: dict) -> None:
    print(json.dumps(obj, separators=(",", ":")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="api base url")
    ap.add_argument("--path", required=True, help="endpoint path, e.g. /api/v1/signal")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    path = args.path

    # 1) 402 challenge (free GET, no payment header)
    try:
        body, acc = get_challenge(base, path)
    except Exception as exc:
        emit({"ok": False, "error": "challenge failed: %s" % exc})
        return 1

    # 2) payer key: ENV ONLY — files under secrets\ are never opened here
    key = (os.getenv("DEMO_PRIVATE_KEY") or os.getenv("WALLET_PRIVATE_KEY") or "").strip()
    if not key:
        emit({"ok": False, "error": "payer key env missing (DEMO_PRIVATE_KEY or WALLET_PRIVATE_KEY)"})
        return 1

    # 3) sign EIP-3009 authorization (local; relayer pays gas)
    try:
        authorization, payer, domain, types, message, signed = build_signature(acc, key)
    except Exception as exc:
        emit({"ok": False, "error": "sign failed: %s" % exc})
        return 1

    sig_hex = signed.signature.hex()
    payload = {
        "x402Version": int(body.get("x402Version", 2)),
        "accepted": dict(acc),
        "payload": {
            "signature": sig_hex if sig_hex.startswith("0x") else "0x" + sig_hex,
            "authorization": authorization,
        },
    }
    # same echo as the proven --send path (extensions + resource from the 402)
    payload = echo_extensions(payload, body)
    header_value = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")

    # 4) retry the SAME request with PAYMENT-SIGNATURE
    try:
        req = urllib.request.Request(
            base + path,
            headers={"Accept": "application/json", "PAYMENT-SIGNATURE": header_value},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            status = resp.status
            hdrs = dict(resp.headers)
            resp_body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        hdrs = dict(getattr(exc, "headers", {}) or {})
        resp_body = exc.read().decode("utf-8", "replace")
    except Exception as exc:
        emit({"ok": False, "error": "retry failed: %s" % exc})
        return 1

    if status != 200:
        err = "http %s" % status
        try:
            j = json.loads(resp_body)
            err = str(j.get("error") or j.get("reason") or err)
        except Exception:
            pass
        emit({"ok": False, "error": err})
        return 1

    # 5) extract tx from PAYMENT-RESPONSE header (base64 json) if present
    tx = ""
    pr = next((v for k, v in hdrs.items() if k.lower() == "payment-response"), "")
    if pr:
        try:
            pad = "=" * (-len(pr) % 4)
            prj = json.loads(base64.b64decode(pr + pad))
            tx = str(prj.get("transaction") or prj.get("tx") or "")
        except Exception:
            tx = ""
    usd = round(int(acc.get("amount", 0)) / 1e6, 6)
    emit({"ok": True, "path": path, "usd": usd, "tx": tx})
    return 0


if __name__ == "__main__":
    sys.exit(main())