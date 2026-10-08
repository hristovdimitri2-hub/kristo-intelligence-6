# -*- coding: utf-8 -*-
"""
scripts/demo_sponsored_pay.py — sponsored (EIP-3009) x402 payment client, DRY RUN.

Ported from the kristo-v6 prototype and adapted for THIS repo:

  1. Fetch the canonical x402 v2 402 challenge:
         GET https://kristo-intelligence-api.onrender.com/api/v1/signal
  2. Load the EXISTING payer key from secrets/demo_private_key.txt
     (read-only: this script NEVER generates, writes or prints a key).
  3. Sign an EIP-3009 TransferWithAuthorization (EIP-712 typed data) with
     domain (USD Coin v2, chain 8453, Base USDC) taken from the challenge
     itself. The signed payload is meant for the PAYMENT-SIGNATURE header
     (paywall Rail 1, main.py:3118-3125 -> connectors.py:611-666); the
     settlement relayer pays the gas, so the payer needs NO ETH.
  4. DRY RUN (default): STOP before sending anything and verify:
        - amount      = 3000 atomic
        - payTo       = 0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f
        - signer      = 0xE50c5212e8211639C49276dA190E248B83935763
        - the signature recovers back to that signer
        - every signed field matches the fetched challenge

Usage:
    python scripts/demo_sponsored_pay.py [base_url] [--send]

    --send   transmit the PAYMENT-SIGNATURE header (NOT part of the dry run;
             a real settlement happens server-side — never use it here).

Output contract:
    stdout: EXACTLY one line — 'READY - command: <exact command>' or
            'FAILED - <reason>'.
    stderr: diagnostics (the private key is NEVER printed or logged).
"""
from __future__ import annotations

import base64
import copy
import json
import os
import secrets as py_secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Task constants ───────────────────────────────────────────────────────────
DEFAULT_BASE = "https://kristo-intelligence-api.onrender.com"
CHALLENGE_PATH = os.getenv("KRISTO_CHALLENGE_PATH", "/api/v1/signal")
PAYMENT_HEADER = "PAYMENT-SIGNATURE"          # Rail 1 (standard x402 v2 header)
EXPECTED_AMOUNT_ATOMIC = "3000"               # 0.003 USDC (6 decimals)
EXPECTED_PAYTO = "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"
EXPECTED_SIGNER = "0xE50c5212e8211639C49276dA190E248B83935763"
EXPECTED_NETWORK = "eip155:8453"              # Base mainnet (CAIP-2)
CHAIN_ID = 8453

ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = ROOT / "secrets" / "demo_private_key.txt"
SELF_COMMAND = "python scripts/demo_sponsored_pay.py"


def log(msg: str) -> None:
    """Diagnostics go to stderr — stdout stays a single verdict line."""
    print(msg, file=sys.stderr, flush=True)


def fail(reason: str) -> None:
    print(f"FAILED - {reason}")
    sys.exit(1)


def ready() -> None:
    print(f"READY - command: {SELF_COMMAND}")
    sys.exit(0)


# ── Step 1: fetch the 402 challenge ──────────────────────────────────────────
def fetch_challenge(base: str) -> tuple[dict, dict]:
    url = base.rstrip("/") + CHALLENGE_PATH
    log(f"[1/4] GET {url}")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except Exception as exc:  # unreachable host, TLS, timeout, ...
        fail(f"cannot reach server at {base} ({exc.__class__.__name__}: {exc})")

    if status != 402:
        hint = " (free tier still available — set KRISTO_FREE_TIER_LIMIT=0)" if status == 200 else ""
        fail(f"expected HTTP 402 challenge from GET {CHALLENGE_PATH}, got HTTP {status}{hint}")

    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        fail(f"GET {CHALLENGE_PATH} returned 402 but the body is not JSON")

    if body.get("error") != "payment_required":
        fail(f"unexpected challenge error: {body.get('error')!r} (expected 'payment_required')")
    accepts = body.get("accepts") or body.get("accepts[]") or []
    if not accepts or not isinstance(accepts[0], dict):
        fail("challenge has no accepts[] payment requirements")
    acc = accepts[0]
    if "x402Version" in body and body["x402Version"] != 2:
        fail(f"challenge x402Version={body['x402Version']!r}, expected 2")

    log(f"      challenge: x402Version={body.get('x402Version')} error={body.get('error')}")
    log(f"      amount={acc.get('amount')} atomic  payTo={acc.get('payTo')}")
    log(f"      network={acc.get('network')}  asset={acc.get('asset')}  extra={acc.get('extra')}")
    return body, acc


# ── Step 2a: load the EXISTING key (strict — never generated, never printed) ──
def load_key() -> str:
    if not KEY_FILE.exists():
        fail(f"{KEY_FILE} not found — refusing to generate a new key")
    key = KEY_FILE.read_text(encoding="utf-8").strip()
    if not key:
        fail(f"{KEY_FILE} is empty")
    if not key.startswith("0x"):
        key = "0x" + key
    if len(key) != 66 or not all(c in "0123456789abcdefABCDEF" for c in key[2:]):
        fail(f"invalid private key format in {KEY_FILE} (expected 0x + 64 hex chars)")
    log(f"[2/4] existing payer key loaded from {KEY_FILE} (format ok, contents not shown)")
    return key


# ── Step 2b: EIP-3009 TransferWithAuthorization signature ────────────────────
def build_signature(acc: dict, key: str) -> tuple[dict, str, dict, dict, dict, object]:
    from eth_account import Account

    payer = Account.from_key(key).address
    extra = acc.get("extra") or {}
    domain_name, domain_version = extra.get("name"), extra.get("version")
    if not domain_name or not domain_version:
        fail("challenge accepts[0].extra lacks the EIP-712 domain (name/version)")

    value = int(acc["amount"])
    valid_after = 0
    valid_before = int(time.time()) + 55   # б2: прозорец ≤60s (precheck + maxTimeoutSeconds)
    nonce_bytes = py_secrets.token_bytes(32)

    domain = {
        "name": domain_name,
        "version": domain_version,
        "chainId": CHAIN_ID,
        "verifyingContract": acc["asset"],
    }
    types = {
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ]
    }
    message = {
        "from": payer,
        "to": acc["payTo"],
        "value": value,
        "validAfter": valid_after,
        "validBefore": valid_before,
        "nonce": nonce_bytes,
    }

    try:
        signed = Account.sign_typed_data(
            key, domain_data=domain, message_types=types, message_data=message
        )
    except Exception as exc:
        fail(f"EIP-3009 signing failed ({exc.__class__.__name__}: {exc})")

    sig_hex = signed.signature.hex()
    if not sig_hex.startswith("0x"):
        sig_hex = "0x" + sig_hex
    log(f"[3/4] EIP-3009 TransferWithAuthorization signed for payer {payer}")
    log(f"      domain: {domain_name} v{domain_version} chain {CHAIN_ID} token {acc['asset']}")
    log(f"      value={value} validAfter={valid_after} "
        f"validBefore={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(valid_before))} "
        f"nonce=0x{nonce_bytes.hex()[:8]}… signature={len(sig_hex)} chars")

    authorization = {
        "from": payer,
        "to": acc["payTo"],
        "value": str(value),
        "validAfter": str(valid_after),
        "validBefore": str(valid_before),
        "nonce": "0x" + nonce_bytes.hex(),
    }
    return authorization, payer, domain, types, message, signed


# ── Step 3: verify (DRY RUN — nothing is transmitted) ────────────────────────
def verify_recovery(domain: dict, types: dict, message: dict, signed, payer: str) -> None:
    """Signature sanity: recover the signer from the typed data (key never exposed)."""
    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data
        signable = encode_typed_data(
            copy.deepcopy(domain), copy.deepcopy(types), copy.deepcopy(message)
        )
        recovered = Account.recover_message(signable, signature=signed.signature)
    except Exception as exc:
        fail(f"signature recovery check failed ({exc.__class__.__name__}: {exc})")
    if recovered.lower() != payer.lower():
        fail(f"signature recovery mismatch: recovered {recovered}, signer {payer}")
    log(f"      [ok] signature recovers to signer {recovered}")


# ── Step 3b: Bazaar discovery extension ─────────────────────────────────────
def echo_extensions(payload: dict, challenge: dict) -> dict:
    """
    x402 v2 rule: when the server's 402 carried `extensions`, the client MUST
    copy them verbatim into the payment payload — that is how the facilitator
    (PayAI) learns our Bazaar declaration and can auto-list the endpoint.

    Server-side this is safe by construction: precheck_payment_payload and
    _local_recover_signer read only `accepted`/`payload` keys (connectors.py
    :147-148,199-200) and never reject an unknown top-level key.
    """
    ext = challenge.get("extensions")
    if isinstance(ext, dict) and ext:
        payload = dict(payload)
        payload["extensions"] = ext
        log(f"      echoing extensions: {sorted(ext)} "
            f"(Bazaar declaration travels with the payment)")
    return payload


def read_extension_responses(hdrs: dict) -> None:
    """
    Settlement receipts may carry an EXTENSION-RESPONSES header — base64
    JSON per extension, e.g. {"bazaar": {"status": "listed", ...}}. Log it
    so the auto-listing outcome is visible in the demo output.
    """
    er = next((v for k, v in hdrs.items()
               if k.lower() == "extension-responses"), "")
    if not er:
        log("      EXTENSION-RESPONSES: absent (facilitator sent no extension receipt)")
        return
    try:
        decoded = json.loads(base64.b64decode(er + "=" * (-len(er) % 4))
                             .decode("utf-8"))
        log(f"      EXTENSION-RESPONSES: {json.dumps(decoded)[:200]}")
        bazaar = (decoded.get("bazaar") or {}) if isinstance(decoded, dict) else {}
        if isinstance(bazaar, dict) and bazaar.get("status"):
            log(f"      bazaar status: {bazaar.get('status')}"
                + (f" tx={bazaar.get('tx')}" if bazaar.get("tx") else ""))
    except Exception as exc:
        log(f"      EXTENSION-RESPONSES present but undecodable: {exc}")


def main() -> None:
    args = list(sys.argv[1:])
    do_send = "--send" in args
    args = [a for a in args if not a.startswith("--")]
    base = (os.getenv("KRISTO_API_BASE") or (args[0] if args else DEFAULT_BASE)).rstrip("/")

    body, acc = fetch_challenge(base)                                   # step 1
    key = load_key()                                                    # step 2a
    authorization, payer, domain, types, message, signed = build_signature(acc, key)  # step 2b

    # Step 3 (dry run): verify amount, payTo, signer, recovery, field consistency.
    log("[4/4] DRY RUN verification (stopping before any transmission)")
    if acc.get("amount") != EXPECTED_AMOUNT_ATOMIC:
        fail(f"amount mismatch: challenge={acc.get('amount')!r}, expected {EXPECTED_AMOUNT_ATOMIC} atomic")
    log(f"      [ok] amount = {EXPECTED_AMOUNT_ATOMIC} atomic (0.003 USDC)")

    if str(acc.get("payTo", "")).lower() != EXPECTED_PAYTO.lower():
        fail(f"payTo mismatch: challenge={acc.get('payTo')!r}, expected {EXPECTED_PAYTO}")
    log(f"      [ok] payTo = {EXPECTED_PAYTO}")

    if payer.lower() != EXPECTED_SIGNER.lower():
        fail(f"signer mismatch: key derives {payer}, expected {EXPECTED_SIGNER}")
    log(f"      [ok] signer = {EXPECTED_SIGNER}")

    if authorization["value"] != str(acc["amount"]):
        fail(f"signed value {authorization['value']} != challenge amount {acc['amount']}")
    if authorization["to"].lower() != str(acc["payTo"]).lower():
        fail("signed 'to' does not match challenge payTo")
    if domain["verifyingContract"].lower() != str(acc["asset"]).lower():
        fail("signed domain verifyingContract does not match challenge asset")
    if str(acc.get("network")) != EXPECTED_NETWORK or domain["chainId"] != CHAIN_ID:
        fail(f"network mismatch: challenge={acc.get('network')!r}, signed chainId={domain['chainId']}")
    if domain["name"] != (acc.get("extra") or {}).get("name") or \
       domain["version"] != (acc.get("extra") or {}).get("version"):
        fail("signed EIP-712 domain (name/version) does not match challenge extra")
    log("      [ok] signed fields match the challenge (to/value/domain/network/extra)")
    verify_recovery(domain, types, message, signed, payer)

    # Assemble the Rail-1 PAYMENT-SIGNATURE payload — canonical v2 shape:
    # {x402Version, accepted, payload:{signature, authorization}} — exactly what
    # the server's precheck/_local_recover_signer expect (connectors.py:138-225;
    # tests/test_connectors.py _build_signed_payload). `accepted` echoes the
    # challenge requirements we accepted (asset+extra feed the EIP-712 domain).
    payload = {
        "x402Version": int(body.get("x402Version", 2)),
        "accepted": dict(acc),
        "payload": {"signature": signed.signature.hex()
                    if signed.signature.hex().startswith("0x")
                    else "0x" + signed.signature.hex(),
                    "authorization": authorization},
    }

    header_value = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    log(f"      {PAYMENT_HEADER} payload built: {len(header_value)} chars "
        f"(signature + authorization; no private material)")

    # FIX #3: Store signed nonce for verification
    signed_nonce_hex = payload.get("authorization", {}).get("nonce", "")
    
    if do_send:
        # x402 v2 Bazaar rule: echo the 402's extensions into the payment
        # payload so the facilitator can auto-list the endpoint (PayAI).
        payload = echo_extensions(payload, body)
        header_value = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).decode("ascii").rstrip("=")
        # PAID RUN — only with an explicit --send flag. Retries the SAME signed
        # authorization (idempotent: the server adopts an already-settled nonce)
        # while settlement is confirming (HTTP 425 settlement_in_flight).
        log(f"      --send requested: transmitting {PAYMENT_HEADER} …")
        status, body_text, hdrs = 0, "", {}
        for attempt in range(1, 7):
            req = urllib.request.Request(
                base + CHALLENGE_PATH,
                headers={"Accept": "application/json", PAYMENT_HEADER: header_value},
            )
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    status, hdrs = resp.status, dict(resp.headers)
                    body_text = resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:
                status, hdrs = exc.code, dict(exc.headers)
                body_text = exc.read().decode("utf-8", "replace")
            except Exception as exc:
                log(f"      attempt {attempt}: transport error "
                    f"{exc.__class__.__name__}: {exc}")
                time.sleep(5)
                continue
            log(f"      attempt {attempt}: HTTP {status}")
            if status == 200:
                break
            if status == 425:          # settlement_in_flight — paid, not visible yet
                time.sleep(5)
                continue
            break                      # 401/402/… — precise rejection, stop

        # Settlement receipt: PAYMENT-RESPONSE = base64(JSON{success, transaction, …})
        tx = ""
        pr = next((v for k, v in hdrs.items()
                   if k.lower() == "payment-response"), "")
        if pr:
            try:
                settle = json.loads(
                    base64.b64decode(pr + "=" * (-len(pr) % 4)).decode("utf-8"))
                # FIX #3: Verify returned nonce matches signed nonce (adoption attack prevention)
                returned_nonce = settle.get("nonce", "")
                if returned_nonce and signed_nonce_hex:
                    if returned_nonce.lower() != signed_nonce_hex.lower():
                        fail(f"Nonce mismatch: signed {signed_nonce_hex[:20]}..., got {returned_nonce[:20]}...")
                tx = str(settle.get("transaction") or "")
                log(f"      PAYMENT-RESPONSE: success={settle.get('success')} "
                    f"network={settle.get('network')} payer={settle.get('payer')} "
                    f"tx={tx}")
            except Exception as exc:
                log(f"      PAYMENT-RESPONSE present but undecodable: {exc}")
        # Bazaar auto-listing receipt (EXTENSION-RESPONSES) — see Step 3b.
        read_extension_responses(hdrs)
        if not tx and status in (425, 200):
            try:
                tx = str((json.loads(body_text) or {}).get("transaction") or "")
            except Exception:
                pass
        if status == 200:
            log(f"      delivered body: {body_text[:160]}")
            if tx:
                log(f"      PAID CALL OK — tx {tx}")
            ready()

        reason = ""
        try:
            b = json.loads(body_text) or {}
            reason = str(b.get("reason") or b.get("error") or "")
        except Exception:
            pass
        fail(f"server did not accept the {PAYMENT_HEADER} header "
             f"(HTTP {status}{': ' + reason if reason else ''})")


    log("      DRY RUN complete — nothing was sent, no payment was made.")
    ready()


if __name__ == "__main__":
    main()


