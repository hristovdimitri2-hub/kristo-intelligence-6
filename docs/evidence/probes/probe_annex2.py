# -*- coding: utf-8 -*-
"""Read-only: annex pay_to vs live, identifier paths, protocol facts."""
from __future__ import annotations

import json
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LIVE_PAYTO = "0xbF428071027402E9b0cE85e22146EDdc028cEB3b"
PATH = (r"C:\Users\AlienWare\Downloads"
        r"\returncheck-reverse-test (2).json")

raw = open(PATH, "rb").read()
print("size =", len(raw), "(expect 7519)")
doc = json.loads(raw.decode("utf-8-sig"))
print("top keys:", list(doc.keys()))


def deep_get(node, *names):
    if isinstance(node, dict):
        for n in names:
            if n in node and not isinstance(node[n], (dict, list)):
                return node[n]
        for v in node.values():
            r = deep_get(v, *names)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = deep_get(v, *names)
            if r is not None:
                return r
    return None


pay = doc.get("payment") if isinstance(doc.get("payment"), dict) else {}
pt = pay.get("pay_to")
if pt is None:
    pt = deep_get(doc, "pay_to", "payTo")
print("payment.pay_to =", repr(pt))
print("len =", len(pt) if isinstance(pt, str) else "n/a")
if isinstance(pt, str):
    e, g = LIVE_PAYTO, pt
    diff = next((i for i, (a, b) in enumerate(zip(e, g)) if a != b),
                None)
    print("equal_sign_by_sign =", e == g,
          "| len", len(e), "vs", len(g),
          "| first_diff@", diff,
          "| casefold_equal =", e.lower() == g.lower())
print("has 'extensions' key:", "extensions" in doc,
      "| payment keys:", list(pay.keys()) if pay else "?")

r = requests.get("https://returncheck.m-angelmartinez-fer"
                 ".workers.dev/.well-known/x402",
                 timeout=30, headers={"User-Agent": "readonly-probe"})
d = r.json()
pi = d.get("payment_instructions") or {}
print("\nidentifier_path       =", repr(pi.get("identifier_path")))
print("legacy_identifier_path =", repr(pi.get("legacy_identifier_path")))
print("identifier_required   =", repr(pi.get("identifier_required")),
      "| legacy_supported =", repr(pi.get("legacy_supported")))
print("extensions keys       =", list((d.get("extensions") or {}).keys()))
print("DONE", flush=True)
