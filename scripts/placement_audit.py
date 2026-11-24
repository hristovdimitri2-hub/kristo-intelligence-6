# -*- coding: utf-8 -*-
"""Placement audit — is our record present, and is it current, everywhere we appear?

Read-only GETs against public endpoints. Nothing is submitted, nothing is edited.

Two groups:
  * `REGISTRY` — the places we deliberately placed ourselves.
  * `DISCOVERED` — the directories and monitors that the request log proved are
    already talking to us; we never submitted to most of them, so the question is
    whether they carry a listing or only probe us.

Every target is fetched and searched for the hostname or the receiver address. A
presence check is not a quality check — it answers "do we exist there", and the
report says so.

Usage:
    python scripts/placement_audit.py
"""
from __future__ import annotations

import concurrent.futures as futures
import json
import re
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "kristo-intelligence-api.onrender.com"
RECEIVER = "0xb4fcf8ef52b5dc275924aed2bae94fe6cb7fc844"
RETIRED = "0xd4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"
UA = {"User-Agent": "placement-audit/1.0 (+kristo-intelligence)"}

# (name, url, needle) — needle overrides the default hostname/receiver search.
REGISTRY = [
    ("CDP Bazaar (current payTo)",
     "https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant"
     "?payTo=0xB4FcF8ef52b5DC275924AeD2BAe94FE6cb7fC844&limit=100&offset=0", None),
    ("CDP Bazaar (retired payTo)",
     "https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant"
     "?payTo=0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f&limit=100&offset=0", None),
    ("MCP Registry (search kristo)",
     "https://registry.modelcontextprotocol.io/v0/servers?search=kristo", None),
    ("Glama connector",
     "https://glama.ai/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence", None),
    ("Glama servers search",
     "https://glama.ai/mcp/servers?q=kristo", None),
    ("x402scan server page",
     "https://www.x402scan.com/server/" + HOST, None),
    ("PayAPI listing API",
     "https://payapi.market/api/listings?status=all&limit=200", HOST),
    # Our own published discovery surfaces — if one of these is wrong, every
    # catalogue downstream of it is wrong too.
    ("our /.well-known/x402", "https://%s/.well-known/x402" % HOST, None),
    ("our /.well-known/agent-card.json", "https://%s/.well-known/agent-card.json" % HOST, None),
    ("our /openapi.json", "https://%s/openapi.json" % HOST, None),
    ("our /llms.txt", "https://%s/llms.txt" % HOST, None),
    ("our /api/mcp/manifest", "https://%s/api/mcp/manifest" % HOST, None),
    ("our /robots.txt", "https://%s/robots.txt" % HOST, None),
    ("our /sitemap.xml", "https://%s/sitemap.xml" % HOST, None),
    ("our /.well-known/x402list.txt", "https://%s/.well-known/x402list.txt" % HOST, None),
]

# Derived from `request_log`: every user agent or referer that identified a third
# party this service has never heard of. We did not submit to these; they found us.
DISCOVERED = [
    ("agent402.tools", "https://agent402.tools/"),
    ("x402station.io", "https://x402station.io/"),
    ("x402-list.com", "https://x402-list.com/"),
    ("x402-trust.com", "https://x402-trust.com/trust"),
    ("mcpbeat.com", "https://mcpbeat.com/"),
    ("mcptry.com", "https://mcptry.com/"),
    ("alalanet.com", "https://alalanet.com/"),
    ("nohumans.directory", "https://nohumans.directory/"),
    ("PayAI Bazaar", "https://docs.payai.network/x402/facilitators/bazaar"),
    ("mekler.ai", "https://mekler.ai/"),
    ("toolvet.app", "https://toolvet.app/"),
    ("botsrated.com", "https://botsrated.com/"),
    ("kertivo.com", "https://kertivo.com/status"),
    ("lumierepaycheck.org", "https://lumierepaycheck.org/"),
    ("agenteconomy.report", "https://agenteconomy.report/s/" + HOST),
    ("agentlair.dev", "https://agentlair.dev/"),
    ("brick.blue", "https://brick.blue/agent/25a3abfeef67d1e4"),
    ("agenstry.com", "https://agenstry.com/"),
    ("ai-powered.com", "https://ai-powered.com/"),
    ("easy402", "https://easy402.com/"),
    ("addrbook.com", "https://addrbook.com/"),
    ("nitrograph.com", "https://api.nitrograph.com/"),
    ("carbon-cashmere.de", "https://carbon-cashmere.de/"),
    ("glimind.com", "https://glimind.com/"),
    ("x402-router (railway)", "https://router-production-ab89.up.railway.app/"),
    ("zero.xyz", "https://zero.xyz/"),
]

FIND = re.compile(re.escape(HOST) + "|" + re.escape(RECEIVER), re.I)
DATE = re.compile(r"20\d\d-\d\d-\d\d")


def check(item):
    if len(item) == 3:
        name, url, needle = item
    else:
        name, url = item
        needle = None
    pat = re.compile(re.escape(needle), re.I) if needle else FIND
    row = {"name": name, "url": url}
    try:
        r = requests.get(url, headers=UA, timeout=30, allow_redirects=True)
        row["status"] = r.status_code
        row["bytes"] = len(r.content)
        text = r.text
        row["present"] = bool(pat.search(text))
        dates = DATE.findall(text)
        row["dates_seen"] = sorted(set(dates))[-3:] if dates else []
        if row["present"]:
            m = pat.search(text)
            row["context"] = text[max(0, m.start() - 90):m.start() + 130].replace("\n", " ")
    except Exception as exc:
        row["status"] = "ERR"
        row["error"] = str(exc)[:120]
        row["present"] = False
    return row


def main() -> int:
    rows = []
    with futures.ThreadPoolExecutor(max_workers=10) as pool:
        for row in pool.map(check, REGISTRY + DISCOVERED):
            rows.append(row)
    grouped = {"registry": rows[:len(REGISTRY)], "discovered": rows[len(REGISTRY):]}
    print(json.dumps(grouped, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
