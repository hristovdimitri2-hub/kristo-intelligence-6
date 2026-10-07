# -*- coding: utf-8 -*-
"""Read-only diagnostics:
1) Render env vars (TELEGRAM_CHAT_ID only, tokens masked).
2) Telegram getUpdates WITHOUT offset (no ack = no state change) to find the
   04.10 alert message text/date. Telegram discards unconfirmed updates after
   ~24h, so only recent ones can be returned — 04.10 11:24 should still be in.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6"
KEY = open(ROOT + r"\secrets\render_api_key.txt",
           encoding="utf-8").read().strip()
H = {"Authorization": "Bearer " + KEY, "Accept": "application/json"}
BASE = "https://api.render.com/v1"
SERVICE = "srv-d9maroe7bikc73adkaug"

# 1) Render env (read-only list).
try:
    r = requests.get(f"{BASE}/services/{SERVICE}/env-vars",
                     params={"limit": "200"}, headers=H, timeout=60)
    print("ENV HTTP", r.status_code)
    if r.status_code == 200:
        for it in r.json():
            ev = it.get("envVar") or {}
            k = ev.get("key", "")
            if k.startswith("TELEGRAM"):
                v = ev.get("value") or ""
                shown = v if k == "TELEGRAM_CHAT_ID" else v[:6] + "***"
                print("  ", k, "=", shown)
except Exception as exc:
    print("ENV ERR", exc)

# 2) Telegram getUpdates — NO offset => confirmation only, non-destructive.
TOKEN = open(r"C:\Users\AlienWare\Desktop\проекти\проекти\kristo-sentinel\.env",
             encoding="utf-8").read().split("TELEGRAM_BOT_TOKEN=", 1)[1]\
    .splitlines()[0].strip()
try:
    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates",
                     timeout=60)
    d = r.json()
    print("GETUPDATES ok=", d.get("ok"), "n=", len(d.get("result", [])))
    for u in d.get("result", []):
        up = u.get("channel_post") or u.get("message") or {}
        txt = (up.get("text") or up.get("caption") or "").replace("\n", " | ")
        date = up.get("date")
        when = (datetime.fromtimestamp(date, timezone.utc).isoformat()
                if date else "?")
        chat = up.get("chat") or {}
        print(f"   upd={u.get('update_id')} {when} "
              f"chat={chat.get('id')}/{chat.get('title') or chat.get('type')} "
              f"| {txt[:220]}")
except Exception as exc:
    print("GETUPDATES ERR", exc)
print("DONE", flush=True)
