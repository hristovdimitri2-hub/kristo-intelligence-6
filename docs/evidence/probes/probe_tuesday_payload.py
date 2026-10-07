# -*- coding: utf-8 -*-
"""Local-only REVIEW builder for the Tuesday x402 PaymentPayload.

Reads the identifier, builds the v2 payload dict with a TOP-KEY
extensions["payment-identifier"].info.id (placeholder signature/auth),
writes base64 header + raw body SHA-256 to %TEMP%.
NOTHING is sent; wallet untouched. Values redacted in the printout.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEMP = os.environ.get("TEMP") or "."
ID_PATH = os.path.join(TEMP, "kristo_tuesday_id.txt")
HDR_PATH = os.path.join(TEMP, "kristo_tuesday_payment_header.txt")
SHA_PATH = os.path.join(TEMP, "kristo_tuesday_body_sha.txt")
BODY = r"C:\Users\AlienWare\Downloads\returncheck-reverse-test (4).json"
# Live discovery payTo (public challenge data), exact case as served:
PAYTO = "0xbF428071027402E9b0cE85e22146EDdc028cEB3b"

# a) identifier
ident = open(ID_PATH, "r", encoding="ascii").read().strip()
pat_ok = bool(re.fullmatch(r"[a-zA-Z0-9_-]{16,128}", ident))
print(f"identifier: {ident}")
print(f"len={len(ident)} pattern_ok={pat_ok}")

# b) PaymentPayload dict — structure from connectors.decode/precheck +
# mystery_agent.py STAGE 5 flat shape + TOP-KEY extensions
payload = {
    "x402Version": 2,
    "scheme": "exact",
    "network": "eip155:8453",
    "payload": {
        "signature": "0x" + "0" * 64,                      # PLACEHOLDER
        "authorization": {                                 # EIP-3009
            "from": "0x0000000000000000000000000000000000000001",  # PLACEHOLDER
            "to": PAYTO,
            "value": "5000",                               # atomic units, USDC 6-dec
            "validAfter": "0",
            "validBefore": "99999999999",                  # PLACEHOLDER
            "nonce": "0x" + "0" * 64,                      # PLACEHOLDER
        },
    },
    "extensions": {                                        # ТОП-КЛЮЧ
        "payment-identifier": {"info": {"id": ident}},
    },
}

raw = json.dumps(payload, separators=(",", ":")).encode()
hdr = base64.b64encode(raw).decode()  # STANDARD base64 + padding (SDK form)
open(HDR_PATH, "w", encoding="ascii").write(hdr)
print(f"header written: {HDR_PATH} ({len(hdr)} chars)")

# c) raw body SHA-256
body_raw = open(BODY, "rb").read()
body_sha = hashlib.sha256(body_raw).hexdigest()
open(SHA_PATH, "w", encoding="ascii").write(body_sha)
print(f"body sha written: {SHA_PATH} ({len(body_raw)} B)")
print(f"body sha256     : {body_sha}")

# d) structure printout — signature/authorization VALUES redacted
redacted = {
    "x402Version": payload["x402Version"],
    "scheme": payload["scheme"],
    "network": payload["network"],
    "payload": {
        "signature": "<PLACEHOLDER>",
        "authorization": {k: "<PLACEHOLDER>" for k in
                          payload["payload"]["authorization"]},
    },
    "extensions": payload["extensions"],
}
print("=== payload structure (auth/signature values redacted) ===")
print(json.dumps(redacted, indent=2, ensure_ascii=False))
print("base64 (first 80 chars):", hdr[:80], "...")
print("DONE", flush=True)
