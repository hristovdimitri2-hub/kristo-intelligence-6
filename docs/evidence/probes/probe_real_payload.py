# -*- coding: utf-8 -*-
"""Local-only REAL signer for the Tuesday x402 PaymentPayload.

EDITED 2026-10-06 (Miguel-envelope skeleton); STILL NEVER EXECUTED —
verified with py_compile ONLY. Runs ONLY on explicit "OK".
  * reads the private key from <repo>/secrets/demo_private_key.txt and
    NEVER prints/logs it (stripped from memory right after use);
  * builds the EIP-3009 authorization (fresh nonce on every run) and
    signs TransferWithAuthorization via eth_account typed-data signing
    (domain: USD Coin / 2 / chainId 8453 / Base USDC contract);
  * assembles the MIGUEL-ENVELOPE — exactly four top-level keys
    {x402Version, accepted, payload, extensions}; accepted is parsed
    programmatically from the recorded 402 body; writes standard
    base64 to %TEMP%.
NOTHING is sent; wallet used only as signer, no RPC touched.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sys
import time

from eth_account import Account
from eth_account.messages import encode_typed_data

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6"
KEY_PATH = os.path.join(REPO, "secrets", "demo_private_key.txt")
TEMP = os.environ.get("TEMP") or "."
ID_PATH = os.path.join(TEMP, "kristo_tuesday_id.txt")
OUT_PATH = os.path.join(TEMP, "kristo_tuesday_payment_header_real.txt")
SHA_PATH = os.path.join(TEMP, "kristo_tuesday_header_sha.txt")

# Recorded live 402 challenge (source of the flat `accepted` object).
CHALLENGE_PATH = os.path.join(TEMP, "kristo_miguel_402_v2.txt")

# bazaar enters the envelope ONLY after Miguel's reply — one flag, nothing else.
INCLUDE_BAZAAR = False

# Public chain data (from the live 402 challenge / wallet audit):
FROM = "0xE50c5212e8211639C49276dA190E248B83935763"
TO = "0xbF428071027402E9b0cE85e22146EDdc028cEB3b"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # main.py:75

# --- a) identifier (same extensions as probe_tuesday_payload.py) ---
ident = open(ID_PATH, "r", encoding="ascii").read().strip()
if not re.fullmatch(r"[a-zA-Z0-9_-]{16,128}", ident):
    raise SystemExit("identifier missing/invalid in kristo_tuesday_id.txt")

# --- key: read once, never printed, never logged ---
if not os.path.exists(KEY_PATH):
    raise SystemExit("key file not found (path suppressed)")
_key_raw = open(KEY_PATH, "r", encoding="utf-8").read().strip()
_pk = _key_raw[2:] if _key_raw[:2].lower() == "0x" else _key_raw
del _key_raw
if not re.fullmatch(r"[0-9a-fA-F]{64}", _pk):
    raise SystemExit("key file invalid (hex64 expected) — value not shown")

# --- fresh authorization (new nonce every run) ---
now = int(time.time())
auth = {
    "from": FROM,
    "to": TO,
    "value": "20000",
    "validAfter": "0",
    # utcnow + 21600 s (6 h) so the window survives tonight's gates;
    # kept as a STRING exactly like attempt No.1 (value/validAfter/validBefore/nonce).
    "validBefore": str(now + 21600),
    "nonce": "0x" + secrets.token_hex(32),
}

# --- EIP-712: EIP-3009 TransferWithAuthorization, Base mainnet USDC ---
domain = {
    "name": "USD Coin",
    "version": "2",
    "chainId": 8453,
    "verifyingContract": USDC,
}
types = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ],
}
message = {
    "from": FROM,
    "to": TO,
    "value": int(auth["value"]),
    "validAfter": int(auth["validAfter"]),
    "validBefore": int(auth["validBefore"]),
    "nonce": bytes.fromhex(auth["nonce"][2:]),
}

signed = Account.sign_typed_data(_pk, domain, types, message)
signature = signed.signature.hex()
if not signature.startswith("0x"):
    signature = "0x" + signature
del _pk  # key material out of scope from here on

# self-check (public data only): recovered signer == from
signable = encode_typed_data(domain_data=domain,
                             message_types=types, message_data=message)
recovered = Account.recover_message(signable, signature=signed.signature)
sig_ok = recovered.lower() == FROM.lower()
if not sig_ok:
    # Self-check gate: never emit a header file for a signature that does
    # not recover to FROM (task rule: FAIL -> stop, do not write).
    raise SystemExit("SELF-CHECK FAIL (recover != from) — header NOT written")

# --- Miguel-ENVELOPE (live 402, 06.10.2026) — exactly FOUR top keys ---
# accepted  = accepts[0] parsed PROGRAMMATICALLY from the recorded challenge
#             body (flat object: amount stays a STRING, maxTimeoutSeconds
#             stays a NUMBER; no array, no brackets);
# payload   = flat {signature, authorization} — NO scheme/network anywhere;
# extensions = payment-identifier at the CURRENT path
#             extensions["payment-identifier"].info = {"required": true, "id": …}
# INCLUDE_BAZAAR=False -> extensions.bazaar added ONLY after Miguel's reply.
_ch_raw = open(CHALLENGE_PATH, "r", encoding="utf-8").read()
_sep = _ch_raw.find("\r\n\r\n")
_adv = 4
if _sep < 0:
    _sep = _ch_raw.find("\n\n")
    _adv = 2
if _sep < 0:
    raise SystemExit("challenge body separator not found (path suppressed)")
_challenge = json.loads(_ch_raw[_sep + _adv:].strip())
accepted = _challenge["accepts"][0]      # flat object, verbatim
exts = {"payment-identifier": {"info": {"required": True, "id": ident}}}
if INCLUDE_BAZAAR:
    exts["bazaar"] = _challenge["extensions"]["bazaar"]
payload = {
    "x402Version": 2,
    "accepted": accepted,
    "payload": {"signature": signature, "authorization": auth},
    "extensions": exts,
}

raw = json.dumps(payload, separators=(",", ":")).encode()
hdr = base64.b64encode(raw).decode()  # STANDARD base64 + padding (SDK form)
open(OUT_PATH, "w", encoding="ascii").write(hdr)
hdr_sha = hashlib.sha256(open(OUT_PATH, "rb").read()).hexdigest()
open(SHA_PATH, "w", encoding="ascii").write(hdr_sha)

print("identifier      :", ident)
print("authorization   :", json.dumps(auth))
print("domain          :", json.dumps(domain))
print("signature       :", signature[:22] + f"… (len {len(signature)})")
print("recover == from :", sig_ok, f"({recovered})")
print("header file     :", OUT_PATH, f"({len(hdr)} chars)")
print("header sha256   :", hdr_sha, "->", SHA_PATH)
print("NOTE: nothing sent — artifact written for review only.")
print("DONE", flush=True)