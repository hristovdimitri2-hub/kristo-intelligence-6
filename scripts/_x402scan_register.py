# -*- coding: utf-8 -*-
"""Стъпка 1 (read-only): намира API endpoint-а на x402scan register формата."""
import re

import requests

BASE = "https://www.x402scan.com"
sys_html = requests.get(BASE + "/resources/register", timeout=30).text
scripts = re.findall(r'src="([^"]+\.js[^"]*)"', sys_html)

any_pat = re.compile(r'["\'`](/?[a-z0-9\-_/\.]*?(?:regist|resource|submit|add[-_]?server)'
                     r'[a-z0-9\-_/\.]*)["\'`]', re.IGNORECASE)
for s in scripts:
    url = s if s.startswith("http") else BASE + s
    try:
        js = requests.get(url, timeout=30).text
    except Exception:
        continue
    if "regist" not in js.lower():
        continue
    hits = sorted(set(m.group(1) for m in any_pat.finditer(js)))
    if hits:
        print("CHUNK", url.split("/")[-1].split("?")[0])
        for h in hits[:15]:
            print("   ->", h)