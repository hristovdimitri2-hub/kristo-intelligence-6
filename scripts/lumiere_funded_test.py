"""Fund one Lumiere seller test — a POST x402 paid call.

`scripts/phase1_paid_call.py` is GET-only and this route is POST, so this is the
same proven handshake with a POST and a JSON body. The key comes from the
environment and is never printed.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6\scripts")))
from demo_sponsored_pay import build_signature, echo_extensions  # noqa: E402

TARGET = "https://kristo-intelligence-api.onrender.com/api/v1/verify-seller"
URL = ("https://lumierepaycheck.org/v1/seller-test?url="
       + urllib.parse.quote(TARGET) + "&issue=45")
BODY = b"{}"


def challenge():
    req = urllib.request.Request(
        URL, data=BODY, method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "kristo/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.load(r), dict(r.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        headers = dict(getattr(exc, "headers", {}) or {})
        pr = next((v for k, v in headers.items()
                   if k.lower() == "payment-required"), None)
        body = None
        if pr:
            body = json.loads(base64.b64decode(pr + "=" * (-len(pr) % 4)))
        else:
            try:
                body = json.loads(raw.decode())
            except Exception:
                body = None
        return exc.code, body, headers


status, body, headers = challenge()
print("challenge status:", status)
if status != 402 or not body:
    print("unexpected:", json.dumps(body, indent=1)[:600] if body else headers)
    sys.exit(1)

acc = (body.get("accepts") or [{}])[0]
print("price   :", int(acc.get("amount", 0)) / 1e6, "USDC")
print("payTo   :", acc.get("payTo"))
print("network :", acc.get("network"))

key = (os.getenv("DEMO_PRIVATE_KEY") or "").strip()
if not key:
    print("DEMO_PRIVATE_KEY not in env")
    sys.exit(1)

authorization, payer, domain, types, message, signed = build_signature(acc, key)
print("payer   :", payer)

sig = signed.signature.hex()
payload = {
    "x402Version": int(body.get("x402Version", 2)),
    "accepted": dict(acc),
    "payload": {
        "signature": sig if sig.startswith("0x") else "0x" + sig,
        "authorization": authorization,
    },
}
payload = echo_extensions(payload, body)
header = base64.urlsafe_b64encode(
    json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")

req = urllib.request.Request(
    URL, data=BODY, method="POST",
    headers={"Content-Type": "application/json",
             "Accept": "application/json",
             "PAYMENT-SIGNATURE": header,
             "User-Agent": "kristo/1.0"})
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print("\nPAID status:", r.status)
        print(r.read().decode("utf-8", "replace")[:1200])
except urllib.error.HTTPError as exc:
    print("\nPAID status:", exc.code)
    print(exc.read().decode("utf-8", "replace")[:1200])
