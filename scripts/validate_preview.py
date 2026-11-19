#!/usr/bin/env python3
"""Preview what CDP's Bazaar will index for a route, without paying for it.

WHY THIS EXISTS
---------------
`POST https://api.cdp.coinbase.com/platform/v2/x402/validate` needs no API key
and, besides saying "valid", returns the `bazaarExtension` object CDP intends to
publish for the route: the declared `input.method`, the `input.queryParams`, and
an `output.example`. That is the listing, shown to us before anyone settles.

Before this we could only learn what the catalogue thought of a route by paying
for it and then waiting to see whether a row appeared. On 16.11 that cost real
time: /api/stats was settled eight times across two rounds and never listed,
and the reason — `extra_name`/`extra_version` in the requirements — took three
isolated settlements to find. A validate call would have shown the difference
in one request, for free.

WHAT IT IS NOT
--------------
`validate` is not `settle`. It checks that the requirements are well formed and
tells us what it would index; it does not prove a payment will go through. Use
it to catch declaration mistakes, not to predict settlement.

Also measured here: an unknown extension block is accepted. Posting the same
requirements with `extensions.moi-authority` added returns 200, so an extension
block is not where CDP refuses. (An unknown key in the REQUIREMENTS object is a
different story — that is what stopped indexing on 16.11.)

USAGE
-----
    python scripts/validate_preview.py                     # the 7 paid routes
    python scripts/validate_preview.py /api/stats /api/v1/signal
    python scripts/validate_preview.py --base https://host --json

Exit code is 1 if any route was rejected, so this can run in CI.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

VALIDATE_URL = "https://api.cdp.coinbase.com/platform/v2/x402/validate"
DEFAULT_BASE = "https://kristo-intelligence-api.onrender.com"

#: The routes the 402 paywall prices. Kept here rather than imported from
#: main.py so this tool runs without booting the app (and without its env).
DEFAULT_ROUTES = [
    "/api/stats",
    "/api/sales",
    "/api/bot-status",
    "/api/arb/opportunities",
    "/api/v1/signal",
    "/api/v1/whaleflow",
    "/api/v1/verify-seller",
]


def _http(url: str, method: str = "GET", body: dict | None = None, timeout: int = 60):
    """Return (status, parsed_or_text). Never raises on an HTTP error status."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:  # noqa: BLE001 - a probe must not die on one route
        return 0, f"{type(e).__name__}: {e}"
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def challenge_of(base: str, route: str):
    """GET the route and return its 402 body, or None with a reason."""
    status, body = _http(base + route)
    if not isinstance(body, dict):
        return None, f"status {status}, body not JSON"
    if "accepts" not in body and "accepts[]" not in body:
        return None, f"status {status}, no accepts in body"
    return body, ""


def validate(base: str, route: str, challenge: dict):
    """Ask CDP to validate this route's requirements; return (status, body)."""
    accepts = challenge.get("accepts") or challenge.get("accepts[]") or []
    if not accepts:
        return 0, "no accepts"
    payload = {
        "x402Version": challenge.get("x402Version", 2),
        "resource": base + route,
        "method": "GET",
        "accepts": accepts,
    }
    # Carry the route's own extension block through, so the preview reflects
    # what the real 402 advertises rather than a stripped-down version.
    if isinstance(challenge.get("extensions"), dict):
        payload["extensions"] = challenge["extensions"]
    return _http(VALIDATE_URL, method="POST", body=payload)


def _declared(challenge: dict) -> dict:
    """Our own bazaar declaration, as the 402 states it."""
    ext = challenge.get("extensions") or {}
    bz = ext.get("bazaar") if isinstance(ext, dict) else None
    if not isinstance(bz, dict):
        return {}
    info = bz.get("info") or {}
    return {
        "method": (info.get("input") or {}).get("method"),
        "queryParams": sorted(((info.get("input") or {}).get("queryParams") or {}).keys()),
        "has_output_example": bool((info.get("output") or {}).get("example")),
    }


def _indexed(response: dict) -> dict:
    """What CDP says it will index, in the same shape as _declared()."""
    bz = response.get("bazaarExtension")
    if not isinstance(bz, dict):
        return {}
    info = bz.get("info") or {}
    inp = info.get("input") or {}
    return {
        "method": inp.get("method"),
        "queryParams": sorted((inp.get("queryParams") or {}).keys()),
        "has_output_example": bool((info.get("output") or {}).get("example")),
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("routes", nargs="*", default=DEFAULT_ROUTES,
                    help="routes to preview (default: the 7 paid routes)")
    ap.add_argument("--base", default=DEFAULT_BASE, help="server base URL")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    base = args.base.rstrip("/")
    rows, failed = [], 0

    for route in args.routes:
        challenge, why = challenge_of(base, route)
        if challenge is None:
            rows.append({"route": route, "ok": False, "why": why})
            failed += 1
            continue
        status, response = validate(base, route, challenge)
        ok = status == 200 and isinstance(response, dict)
        row = {
            "route": route,
            "ok": ok,
            "status": status,
            "declared": _declared(challenge),
            "indexed": _indexed(response) if ok else {},
        }
        if not ok:
            row["why"] = str(response)[:300]
            failed += 1
        rows.append(row)

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 1 if failed else 0

    for row in rows:
        if not row["ok"]:
            print(f"FAIL  {row['route']:32s} {row.get('why', '')[:90]}")
            continue
        d, i = row["declared"], row["indexed"]
        mismatch = []
        if d.get("method") != i.get("method"):
            mismatch.append(f"method {d.get('method')!r} -> {i.get('method')!r}")
        if d.get("queryParams") != i.get("queryParams"):
            mismatch.append(f"queryParams {d.get('queryParams')} -> {i.get('queryParams')}")
        if d.get("has_output_example") and not i.get("has_output_example"):
            mismatch.append("declared output.example dropped")
        tag = "DIFF  " if mismatch else "OK    "
        print(f"{tag}{row['route']:32s} method={i.get('method')} "
              f"queryParams={i.get('queryParams')} "
              f"example={'yes' if i.get('has_output_example') else 'no'}")
        for m in mismatch:
            print(f"        {m}")

    print(f"\n{len(rows) - failed}/{len(rows)} routes validate cleanly")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
