# -*- coding: utf-8 -*-
import urllib.request, urllib.error, json

try:
    r = urllib.request.urlopen("https://kristo-intelligence-api.onrender.com/api/v1/signal", timeout=30)
    print("HTTP", r.status)
    print(r.read().decode()[:400])
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    body = json.loads(e.read().decode())
    acc = (body.get("accepts") or [{}])[0]
    print("challenge amount:", acc.get("amount"), "| network:", acc.get("network"),
          "| extra:", acc.get("extra"))
    print("payTo:", acc.get("payTo"))
    print("x402Version:", body.get("x402Version"))