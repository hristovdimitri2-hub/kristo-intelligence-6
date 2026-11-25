# -*- coding: utf-8 -*-
r"""Refresh CDP Bazaar's copy of our MCP tool declarations with one paid call each.

WHY A ROW NEEDS A PAID CALL AT ALL. CDP's Bazaar row for an MCP tool carries the
`extensions` the BUYER echoed on the last paid call, so the row is a record of
that call, not a crawl of the server. Changing a tool's description on `/mcp`
therefore changes nothing in the index until somebody pays through that tool.
Walking the row is the only way to publish new text on that surface.

WHY IT LOOKED BROKEN, measured 25.11.2026. The first attempts reported "not
delivered" and cost nothing, which looked like a payment defect. It was not: the
live log named the real cause —

    x402 payment NOT taken: endpoint=/api/v1/signal ip=127.0.0.1
      - the route has nothing to deliver right now, so nothing is settled

The MCP tool forwards the buyer's own header to the HTTP route it paid for
(`app.blueprints.discovery._serve_paid_mcp_tool`), and that route refuses BEFORE
settlement while its signal engine is cold — which it is for a while after every
deploy. So a failure here is usually timing, not plumbing: retry rather than
debug the rail. Two facts make that safe to do blindly: a refused attempt settles
nothing, and each attempt signs a fresh nonce (never reuse a header — the rail's
replay lock will refuse it and the nonce is burned).

Handshake measured from the live server: an unpaid `tools/call` answers HTTP 200
with a JSON-RPC result whose content[0].text is the x402 challenge (not a 402
status), so the challenge is parsed out of the result.

    --tool NAME     refresh one tool (default: list only)
    --all           refresh all seven
    --dry-run       print the challenge and the price, sign nothing

Read the row back with `--verify`, which polls CDP's merchant index until the
row's description contains the text now served by /mcp. A row that still carries
the old text means the paid call did not land.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from demo_sponsored_pay import build_signature, echo_extensions  # noqa: E402

MCP = "https://kristo-intelligence-api.onrender.com/mcp"
RECEIVER = "0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844"
INDEX = ("https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant"
         "?payTo=%s&limit=100&offset=0" % RECEIVER)

TOOLS = {
    "get_market_stats": {},
    "get_onchain_sales": {},
    "get_bot_status": {},
    "get_arbitrage_opportunities": {},
    "get_trading_signal": {},
    "get_whale_flow": {},
    "verify_seller_receiver": {"receiver": RECEIVER, "days": 7},
}

HEADERS = {"Content-Type": "application/json",
           "Accept": "application/json, text/event-stream",
           "User-Agent": "kristo-intelligence-owner/1.0"}


def call(tool: str, arguments: dict, payment: str | None = None):
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }, separators=(",", ":")).encode("utf-8")
    headers = dict(HEADERS)
    if payment:
        headers["PAYMENT-SIGNATURE"] = payment
    req = urllib.request.Request(MCP, data=payload, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(getattr(exc, "headers", {}) or {}), \
            exc.read().decode("utf-8", "replace")
    except Exception as exc:                                   # noqa: BLE001
        return 0, {}, "%s: %s" % (type(exc).__name__, exc)


def challenge_from(text: str):
    """The x402 challenge lives inside the JSON-RPC result content."""
    try:
        envelope = json.loads(text)
    except Exception:                                          # noqa: BLE001
        return None
    result = envelope.get("result") or {}
    for item in result.get("content") or []:
        blob = item.get("text") or ""
        if '"payment_required"' not in blob:
            continue
        try:
            return json.loads(blob)
        except Exception:                                      # noqa: BLE001
            return None
    return None


def served_description(tool: str) -> str:
    """What /mcp now serves for one tool, so the index can be compared with it."""
    _status, _headers, text = call(tool, TOOLS.get(tool, {}))
    challenge = challenge_from(text)
    if not challenge:
        return ""
    for item in ((json.loads(text).get("result") or {}).get("content") or []):
        blob = item.get("text") or ""
        if '"payment_required"' not in blob:
            continue
        info = (((json.loads(blob).get("extensions") or {}).get("bazaar") or {})
                .get("info") or {}).get("input") or {}
        return info.get("description") or ""
    return ""


def index_rows():
    req = urllib.request.Request(INDEX, headers={"Accept": "application/json",
                                                 "User-Agent": "kristo-audit/1.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        doc = json.load(resp)
    return doc.get("items") or doc.get("resources") or doc.get("data") or []


def verify(tool: str, attempts: int = 6) -> int:
    """Poll the index until its row for `tool` carries what /mcp serves."""
    want = served_description(tool)
    for attempt in range(1, attempts + 1):
        for item in index_rows():
            info = (((item.get("extensions") or {}).get("bazaar") or {})
                    .get("info") or {}).get("input") or {}
            if info.get("toolName") != tool:
                continue
            have = info.get("description") or ""
            same = bool(want) and have.strip() == want.strip()
            print("row %s updated=%s identical=%s"
                  % (item.get("resource"), item.get("lastUpdated"), same))
            if same:
                return 0
            print("  index  : %s" % have[:300])
            print("  served : %s" % want[:300])
        print("attempt %d: no identical row yet" % attempt)
        time.sleep(30)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="do not pay; compare the index row with what /mcp serves")
    args = ap.parse_args()

    if args.verify:
        return verify(args.tool or "get_trading_signal")

    names = list(TOOLS) if args.all else ([args.tool] if args.tool else [])
    if not names:
        print("tools: %s" % ", ".join(TOOLS))
        return 0

    key = (os.getenv("DEMO_PRIVATE_KEY") or "").strip()
    if not key and not args.dry_run:
        print("DEMO_PRIVATE_KEY missing")
        return 1

    spent = 0
    report = []
    for name in names:
        status, _hdrs, text = call(name, TOOLS[name])
        challenge = challenge_from(text)
        if not challenge:
            print("%-30s no challenge (HTTP %s) %s" % (name, status, text[:160]))
            report.append((name, "no-challenge", 0, ""))
            continue
        acc = (challenge.get("accepts") or [{}])[0]
        amount = int(acc.get("amount") or 0)
        print("%-30s price %s atomic  payTo %s  extensions=%s"
              % (name, acc.get("amount"), acc.get("payTo"),
                 sorted((challenge.get("extensions") or {}).keys())))
        if args.dry_run:
            report.append((name, "dry-run", amount, ""))
            continue

        # ONE signing pass: the authorization and the signature must share a nonce.
        authorization, payer, _domain, _types, _message, signed = build_signature(acc, key)
        sig_hex = signed.signature.hex()
        payment = {
            "x402Version": int(challenge.get("x402Version", 2)),
            "accepted": dict(acc),
            "payload": {"signature": sig_hex if sig_hex.startswith("0x") else "0x" + sig_hex,
                        "authorization": authorization},
        }
        payment = echo_extensions(payment, challenge)
        header = base64.urlsafe_b64encode(
            json.dumps(payment, separators=(",", ":")).encode("utf-8")
        ).decode("ascii").rstrip("=")

        # A single POST: a retry must re-sign, because the rail's replay lock
        # refuses a reused nonce and reports it as undelivered.
        status, hdrs, text = call(name, TOOLS[name], payment=header)

        receipt = next((v for k, v in hdrs.items()
                        if k.lower() == "payment-response"), "")
        tx = ""
        if receipt:
            try:
                settle = json.loads(base64.b64decode(receipt + "=" * (-len(receipt) % 4)))
                tx = str(settle.get("transaction") or "")
            except Exception:                                  # noqa: BLE001
                pass
        ok = status == 200 and challenge_from(text) is None
        if ok:
            spent += amount
        print("%-30s HTTP %s  %s  tx=%s"
              % (name, status, "DELIVERED" if ok else "not delivered", tx or "-"))
        if not ok:
            print("    response: %s" % text[:600].replace("\n", " "))
            print("    if the log says 'nothing to deliver right now', the signal")
            print("    engine is still cold after a deploy: wait a minute and pay again.")
        report.append((name, "ok" if ok else "fail", amount if ok else 0, tx))

    print("\nspent %s atomic = %s USDC" % (spent, spent / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
