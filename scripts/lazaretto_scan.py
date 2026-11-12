"""Buy one fresh Lazaretto scan of our own MCP endpoint.

$0.03 in USDC on Base, over x402, from the demo wallet. The owner approved it
explicitly ("да") after the free registry lookup came back clean but STALE — it
saw 3 tools on 2026-10-29, while the live server serves 7.

Lazaretto answers on two rails: a v1 body (`maxAmountRequired`, `network: base`)
and a v2 `PAYMENT-REQUIRED` header. This pays the v2 header, which is the
canonical one, exactly as the Lumiere call does.

Dry run first, always: this prints what it is about to spend and only sends when
the signature is built.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(
    r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6\scripts")))
from demo_sponsored_pay import build_signature, echo_extensions  # noqa: E402

URL = "https://lazaretto.dev/v1/scan"
TARGET = "https://kristo-intelligence-api.onrender.com/mcp"
# Their Bazaar schema enumerates the accepted target types, and the body needs
# `target`, not `url` — the first attempt paid nothing and answered
# 400 invalid_request {"path":"target","message":"Required"}, which is the free
# error path they document ("an errored scan is free") and which we verified on
# chain: zero outgoing USDC from the demo wallet in the whole window.
BODY = json.dumps({
    "target": {"type": "mcp_server", "ref": TARGET},
    "depth": "full",
}).encode()
HEADERS = {"Content-Type": "application/json",
           "User-Agent": "kristo/1.0", "Accept": "application/json"}


def challenge():
    req = urllib.request.Request(URL, data=BODY, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r), dict(r.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        headers = dict(getattr(exc, "headers", {}) or {})
        pr = next((v for k, v in headers.items()
                   if k.lower() == "payment-required"), None)
        header_body = None
        if pr:
            header_body = json.loads(base64.b64decode(pr + "=" * (-len(pr) % 4)))
        try:
            body = json.loads(raw.decode())
        except Exception:
            body = None
        return exc.code, (header_body or body), headers


status, body, _ = challenge()
print("challenge status:", status)
if status != 402 or not body:
    print("unexpected:", json.dumps(body)[:400] if body else status)
    sys.exit(1)

print("envelope x402Version:", body.get("x402Version"))
acc = (body.get("accepts") or [{}])[0]
amount = acc.get("amount") or acc.get("maxAmountRequired")
print("price   :", int(amount) / 1e6, "USDC")
print("payTo   :", acc.get("payTo"))
print("network :", acc.get("network"))
print("scheme  :", acc.get("scheme"))

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

print("\n--- DRY RUN OK: about to spend", int(amount) / 1e6, "USDC ---")
req = urllib.request.Request(
    URL, data=BODY, method="POST",
    headers=dict(HEADERS, **{"PAYMENT-SIGNATURE": header}))
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        print("PAID status:", r.status)
        raw = r.read().decode("utf-8", "replace")
        try:
            print(json.dumps(json.loads(raw), indent=1)[:2600])
        except Exception:
            print(raw[:2600])
except urllib.error.HTTPError as exc:
    print("PAID status:", exc.code)
    print(exc.read().decode("utf-8", "replace")[:1200])
