"""Generate `server.json` for the OFFICIAL MCP Registry — from our own price source.

WHY a generator instead of a hand-written file: the entry that exists today
(published 2026-08-05) advertises the LEGACY product — a Vercel endpoint that
answers **405** to `initialize`, 15 tools, `$0.10` per call — because its numbers
were typed by hand from the v5 server. Re-typing is how that drift happened, so
every price below is read at build time from **X402_PRICE_MAP** (itself built from
`config.KRISTO_*_PRICE`), and every tool name comes from the MCP tool definitions
the service actually serves.

Schema facts, verified against the live schema (2025-12-11) rather than assumed:

  * required top-level fields are exactly `name`, `description`, `version`;
  * `remotes` is an array of transports (`streamable-http` / `sse`, each requiring
    `type` + `url`) — a remote-only server needs NO package, npm account or Docker;
  * `version` must not be a range (`^1.2.3`, `>=`, `1.x` are rejected);
  * there is **no `price` field in the schema at all**. The only legitimate place
    for pricing is `_meta["io.modelcontextprotocol.registry/publisher-provided"]`,
    which is free-form (`additionalProperties: true`). Nothing here invents a field.

Usage:
    python -X utf8 scripts/build_registry_server_json.py            # write
    python -X utf8 scripts/build_registry_server_json.py --check    # verify only
Exit code 0 when the file on disk equals what the price source produces.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Importing main boots the app; the background workers must stay off in a build
# step (the same switch the test suite uses).
os.environ.setdefault("KRISTO_DISABLE_BACKGROUND_THREADS", "true")

BASE_URL = "https://kristo-intelligence-api.onrender.com"
SERVER_NAME = "io.github.hristovdimitri2-hub/kristo-intelligence"
VERSION = "6.0.0"
SCHEMA = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
PUBLISHER_KEY = "io.modelcontextprotocol.registry/publisher-provided"
OUT_PATH = os.path.join(ROOT, "server.json")


def _usd(value) -> float:
    return round(float(value), 6)


def build(version: str = VERSION) -> dict:
    """Assemble the document from the app's own sources of truth.

    `version` is a parameter (CLI: `--version 6.0.1`) so a future release does not
    need a code edit — bumping the version and republishing is the whole ritual.
    """
    import main
    from app.blueprints.discovery import _mcp_tools

    price_map = main.X402_PRICE_MAP                      # {endpoint: price}
    routes = {r["endpoint"]: r for r in main.REAL_X402_ROUTES}
    tools = _mcp_tools(BASE_URL)

    paid_endpoints = [
        {
            "endpoint": endpoint,
            "price_usd": _usd(price),
            "name": routes.get(endpoint, {}).get("name", ""),
        }
        for endpoint, price in sorted(price_map.items())
    ]
    tool_rows = []
    for tool in tools:
        endpoint = (tool.get("x402") or {}).get("endpoint", "")
        path = "/" + endpoint.split(BASE_URL, 1)[-1].lstrip("/")
        tool_rows.append({
            "name": tool["name"],
            "description": tool["description"],
            "endpoint": path,
            # the price of the route the tool actually calls, from the map
            "price_usd": _usd(price_map.get(path, main.X402_FEE_USDC)),
        })

    prices = [row["price_usd"] for row in paid_endpoints]
    return {
        "$schema": SCHEMA,
        "name": SERVER_NAME,
        "title": "Kristo Intelligence",
        "description": (
            "Pay-per-call DeFi intelligence for AI agents on Base — x402, USDC, "
            "no keys."),
        "version": version,
        "websiteUrl": BASE_URL,
        "repository": {
            "url": "https://github.com/hristovdimitri2-hub/kristo-intelligence-6",
            "source": "github",
        },
        "icons": [{
            "src": BASE_URL + "/favicon.svg",
            "mimeType": "image/svg+xml",
            "sizes": ["any"],
        }],
        "remotes": [
            {"type": "streamable-http", "url": BASE_URL + "/mcp"},
            {"type": "sse", "url": BASE_URL + "/mcp/sse"},
        ],
        "_meta": {
            PUBLISHER_KEY: {
                "protocol": "x402",
                "pricing": {
                    "model": "pay-per-call",
                    "asset": "USDC",
                    "chain_id": main.X402_CHAIN_ID,
                    "network": "base",
                    "min_usd": min(prices),
                    "max_usd": max(prices),
                    "note": ("Every unpaid call answers HTTP 402 with the canonical "
                             "x402 challenge; the amount in that response is the "
                             "price. No free tier, no signup, no API keys."),
                },
                "tools": tool_rows,
                "paid_endpoints": paid_endpoints,
                "discovery": {
                    "mcp": BASE_URL + "/mcp",
                    "mcp_sse": BASE_URL + "/mcp/sse",
                    "mcp_manifest": BASE_URL + "/api/mcp/manifest",
                    "x402": BASE_URL + "/.well-known/x402",
                    "openapi": BASE_URL + "/openapi.json",
                    "llms_txt": BASE_URL + "/llms.txt",
                },
            },
        },
    }


#: The schema's own limits, read from the live schema on 2025-12-11 and quoted
#: here so a future edit cannot regress them. A 320-character description looked
#: perfectly reasonable and would have failed `mcp-publisher publish` — the real
#: schema caps `description` (and `title`) at 100 characters.
_LIMITS = {
    "name": (3, 200, r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$"),
    "title": (1, 100, None),
    "description": (1, 100, None),
    "version": (None, 255, None),
}


def validate(doc: dict) -> list:
    """The schema's own rules, checked locally (so `publish` cannot surprise us)."""
    problems = []
    for field in ("name", "description", "version"):
        if not doc.get(field):
            problems.append("missing required field: %s" % field)
    # The registry REJECTS version ranges ("^1.2.3", "~1.2.3", ">=1.2.3", "1.x"),
    # so a `--version` typo must be caught here rather than by `publish`.
    version = str(doc.get("version") or "")
    if version and not re.fullmatch(r"\d+\.\d+\.\d+", version):
        problems.append("version must be plain semver, never a range: %r" % version)
    for field, (low, high, pattern) in _LIMITS.items():
        value = doc.get(field)
        if value is None:
            continue
        if low is not None and len(str(value)) < low:
            problems.append("%s shorter than %d: %r" % (field, low, value))
        if high is not None and len(str(value)) > high:
            problems.append("%s longer than %d (%d): %r"
                            % (field, high, len(str(value)), value))
        if pattern and not re.fullmatch(pattern, str(value)):
            problems.append("%s does not match %s: %r" % (field, pattern, value))
    if not re.fullmatch(r"io\.github\.hristovdimitri2-hub/.+", doc.get("name", "")):
        problems.append("name must sit in the authenticated GitHub namespace")
    for icon in doc.get("icons", []):
        if len(str(icon.get("src", ""))) > 255:
            problems.append("icon src longer than 255 characters")
    repository = doc.get("repository") or {}
    if not repository.get("url") or not repository.get("source"):
        problems.append("repository needs both url and source")
    for remote in doc.get("remotes", []):
        if remote.get("type") not in ("streamable-http", "sse"):
            problems.append("bad remote type: %r" % remote.get("type"))
        if not re.fullmatch(r"https?://[^\s]+", remote.get("url", "")):
            problems.append("bad remote url: %r" % remote.get("url"))
    if not any(r.get("type") == "streamable-http" for r in doc.get("remotes", [])):
        problems.append("the registry wants a streamable-http remote")
    return problems


def main_cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=VERSION,
                    help="the registry version to publish (default %s)" % VERSION)
    ap.add_argument("--check", action="store_true",
                    help="do not write; fail if the file is out of date")
    args = ap.parse_args()

    doc = build(args.version)
    problems = validate(doc)
    if problems:
        print("x server.json would be INVALID:")
        for problem in problems:
            print("   -", problem)
        return 2

    payload = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    existing = ""
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH, encoding="utf-8") as handle:
            existing = handle.read()

    if args.check:
        if existing != payload:
            print("x server.json is OUT OF DATE - run the generator without --check")
            return 1
        print("OK server.json matches the price source")
    else:
        with open(OUT_PATH, "w", encoding="utf-8") as handle:
            handle.write(payload)
        print("OK wrote server.json (%d bytes)" % len(payload))

    meta = doc["_meta"][PUBLISHER_KEY]
    print("  name/version : %s  v%s" % (doc["name"], doc["version"]))
    print("  remote       : %s" % doc["remotes"][0]["url"])
    print("  price range  : $%.3f - $%.3f" % (meta["pricing"]["min_usd"],
                                              meta["pricing"]["max_usd"]))
    for row in meta["paid_endpoints"]:
        print("   %-26s $%.3f" % (row["endpoint"], row["price_usd"]))
    for row in meta["tools"]:
        print("   tool %-22s -> %-16s $%.3f"
              % (row["name"], row["endpoint"], row["price_usd"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())