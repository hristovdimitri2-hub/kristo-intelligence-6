# -*- coding: utf-8 -*-
"""Read-only Glama GETs (no writes, nothing sent):
- servers search 'defi' & 'signals' (the script's rank source)
- connectors search 'defi' & 'signals' (does this even exist?)
- object detail: our server + our connector."""
from __future__ import annotations

import json
import os
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://glama.ai/api/mcp"
SERVER_KEY = "hristovdimitri2-hub/kristo-intelligence-6"
CONN_KEY = ("com.onrender.kristo-intelligence-api"
            "/kristo-intelligence")
ROOT = r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6"


def load_key() -> str:
    k = (os.getenv("GLAMA_API_KEY") or "").strip()
    if k:
        return k
    p = os.path.join(ROOT, "secrets", "glama_api_key.txt")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            return fh.read().strip()
    return ""


KEY = load_key()
print("key:", ("present len=" + str(len(KEY))) if KEY else "ABSENT")
H = {"User-Agent": "readonly-probe",
     "Accept": "application/json"}
if KEY:
    H["Authorization"] = f"Bearer {KEY}"


def g(path, params=None):
    try:
        r = requests.get(f"{BASE}{path}", params=params,
                         headers=H, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return None, f"EXC {exc}"
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, r.text[:300]


def items_of(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("servers", "connectors", "items", "results", "edges"):
            v = data.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict) and isinstance(v.get("nodes"), list):
                return v["nodes"]
    return []


def key_of(it):
    if not isinstance(it, dict):
        return "?"
    ns, sl = it.get("namespace"), it.get("slug")
    if ns and sl:
        return f"{ns}/{sl}"
    return (it.get("key") or it.get("id") or it.get("name")
            or json.dumps(it)[:80])


def scan(label, path, term, want):
    st, data = g(path, {"query": term, "first": 25})
    if st is None:
        print(f"\n[{label} q={term}] {data}")
        return
    its = items_of(data)
    total = None
    if isinstance(data, dict):
        total = (data.get("total") or data.get("totalCount")
                 or data.get("count"))
    print(f"\n[{label} q={term}] HTTP {st} items={len(its)} "
          f"total={total}")
    hit = None
    for i, it in enumerate(its, 1):
        k = key_of(it)
        if i <= 8 or k == want:
            mark = " <== OURS" if k == want else ""
            extra = ""
            if isinstance(it, dict):
                extra = (f" | healthy={it.get('healthy')}"
                         f" score={it.get('qualityScore', it.get('score'))}"
                         f" tools={it.get('toolCount', it.get('tool_count'))}")
            print(f"   #{i} {k}{mark}{extra}")
        if k == want and hit is None:
            hit = i
    print(f"   RESULT: ours '{want}' -> "
          f"{'POS ' + str(hit) if hit else 'ABSENT'}")
    return hit


# search: servers vs connectors
scan("servers-search", "/v1/servers", "defi", SERVER_KEY)
scan("connectors-search", "/v1/connectors", "defi", CONN_KEY)
scan("servers-search", "/v1/servers", "signals", SERVER_KEY)
scan("connectors-search", "/v1/connectors", "signals", CONN_KEY)

# object detail (same GETs the script does)
st, d = g(f"/v1/servers/{SERVER_KEY}")
if isinstance(d, dict):
    keep = {k: d.get(k) for k in (
        "namespace", "slug", "qualityScore", "score", "healthy",
        "toolCount", "tools", "attributes", "status", "name",
        "lastCheckedAt", "updatedAt", "createdAt",
        "verification") if k in d}
    print("\n[server detail] HTTP", st, json.dumps(keep,
          default=str)[:700])
else:
    print("\n[server detail] HTTP", st, str(d)[:300])

st, d = g(f"/v1/connectors/{CONN_KEY}")
if isinstance(d, dict):
    keep = {k: d.get(k) for k in (
        "key", "name", "healthy", "qualityScore", "score",
        "toolCount", "tools", "status", "lastCheckedAt",
        "updatedAt", "createdAt") if k in d}
    print("[connector detail] HTTP", st, json.dumps(keep,
          default=str)[:700])
else:
    print("[connector detail] HTTP", st, str(d)[:300])

print("DONE", flush=True)
