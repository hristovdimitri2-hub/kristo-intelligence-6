# -*- coding: utf-8 -*-
"""
PHASE 2 — verify-only test against the PayAI facilitator. NO PAYMENT.

Flow (всичко read/verify; никакви пари се движат):
  1. GET  /api/v1/signal  (без payment хедър) -> 402 challenge  [free, no money]
  2. Sign EIP-3009 authorization  (reuse: demo_sponsored_pay.build_signature)
  3. Assemble canonical v2 payload exactly like the --send path (L302-309),
     then payload = echo_extensions(payload, body)  [reuse, СЪЩАТА логика]
  4. POST https://facilitator.payai.network/verify  {paymentPayload,
     paymentRequirements}   — НИКОГА /settle, НИКОГА към платения endpoint
  5. Записва scripts/phase2_verify_result.json (HTTP статус + целия отговор)

Guards (твърди):
  - никой request към нашия API не носи PAYMENT-SIGNATURE
  - само endpoint: facilitator.payai.network/verify
  - ключ: само чрез load_key() на клиента (никога не се печата)
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Клиентът има def main() + __main__ guard (L403) => import без странични ефекти.
from demo_sponsored_pay import (  # noqa: E402
    DEFAULT_BASE,
    echo_extensions,
    fetch_challenge,
    build_signature,
    load_key,
)

VERIFY_URL = "https://facilitator.payai.network/verify"  # docs.x402 §7.1; base = our FACILITATOR_URL
RESULT_PATH = HERE / "phase2_verify_result.json"


def main() -> int:
    # 1) free GET -> 402 (само получаване; никакъв payment хедър)
    print("[1/4] free GET /api/v1/signal -> 402 challenge ...", file=sys.stderr)
    body, acc = fetch_challenge(DEFAULT_BASE)

    # 2) sign (същата функция като do_send)
    print("[2/4] signing EIP-3009 authorization (local, no network) ...", file=sys.stderr)
    authorization, payer, domain, types, message, signed = build_signature(acc, load_key())
    sig_hex = signed.signature.hex()
    payload = {
        "x402Version": int(body.get("x402Version", 2)),
        "accepted": dict(acc),
        "payload": {
            "signature": sig_hex if sig_hex.startswith("0x") else "0x" + sig_hex,
            "authorization": authorization,
        },
    }

    # 3) echo — СЪЩАТА логика като --send пътя (reuse на echo_extensions)
    payload = echo_extensions(payload, body)
    has_ext = isinstance(payload.get("extensions"), dict) and bool(payload["extensions"])
    print(f"[3/4] payload assembled; extensions echoed: {has_ext} "
          f"(keys: {sorted(payload.get('extensions') or {})})", file=sys.stderr)

    # paymentRequirements = нашият accepts[0] + resource (x402 verify shape)
    payment_requirements = dict(acc)
    if isinstance(body.get("resource"), dict):
        payment_requirements["resource"] = body["resource"]

    verify_body = json.dumps({
        "x402Version": int(body.get("x402Version", 2)),
        "paymentPayload": payload,
        "paymentRequirements": payment_requirements,
    }).encode("utf-8")

    # 4) САМО POST /verify — никакъв /settle, никакъв платен endpoint
    print(f"[4/4] POST {VERIFY_URL} (verify only) ...", file=sys.stderr)
    req = urllib.request.Request(
        VERIFY_URL,
        data=verify_body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "kristo-phase2-verify/1.0"},
        method="POST",
    )
    status, resp_text = 0, ""
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = resp.status
            resp_text = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        resp_text = e.read().decode("utf-8", "replace")

    # 5) запис на резултата (untracked, локален)
    result = {
        "verify_url": VERIFY_URL,
        "challenge_path": "/api/v1/signal",
        "extensions_echoed": has_ext,
        "extensions_keys": sorted(payload.get("extensions") or []),
        "http_status": status,
        "response_text": resp_text,
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print(f"HTTP {status}", file=sys.stderr)
    print(f"result -> {RESULT_PATH}", file=sys.stderr)
    print(f"RESPONSE: {resp_text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())