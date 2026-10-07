# -*- coding: utf-8 -*-
"""Read-only fixture check: raw SHA-256 + size, JSON structure, GET x402."""
from __future__ import annotations

import hashlib
import json
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PATH = (r"C:\Users\AlienWare\Downloads"
        r"\returncheck-reverse-test (4).json")
EXPECT_SHA = ("5c42b2fee283b157e30047c011f3c408"
              "13639d99c213bc5be5fefd93539b8587")
EXPECT_SIZE = 4114

raw = open(PATH, "rb").read()
sha = hashlib.sha256(raw).hexdigest()
crlf = raw.count(b"\r\n")
lf_only = raw.count(b"\n") - crlf
cr_only = raw.count(b"\r") - crlf
norm = raw.replace(b"\r\n", b"\n")
sha_norm = hashlib.sha256(norm).hexdigest()

print(f"size={len(raw)} (expect {EXPECT_SIZE}) match={len(raw)==EXPECT_SIZE}")
print(f"sha_raw={sha}")
print(f"sha_raw_match={sha == EXPECT_SHA}")
print(f"line_endings: CRLF={crlf} LF_only={lf_only} CR_only={cr_only}")
print(f"sha_LFnormalized={sha_norm}"
      f" match={sha_norm == EXPECT_SHA}")

text = raw.decode("utf-8-sig")
data = json.loads(text)
print("JSON: valid; top-level keys =", list(data.keys()))
print("as_of =", repr(data.get("as_of")))

# recursive key scan
all_keys: set[str] = set()
flat: list[tuple[str, object]] = []


def walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            all_keys.add(k)
            flat.append((f"{path}.{k}", v))
            walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{path}[{i}]")


walk(data)
lc = {k.lower() for k in all_keys}
print("has 'extensions' key (any level):", "extensions" in lc)
banned = [k for k in all_keys
          if k.lower() in {"payment", "payto", "amount", "network"}]
print("banned keys payment/payTo/amount/network:", banned or "NONE")
low = text.lower()
print("'payment-identifier' in text:", "payment-identifier" in low,
      "| 'paymentidentifier':", "paymentidentifier" in low,
      "| 'identifier' in any key:",
      any("identifier" in k.lower() for k in all_keys))
print("all distinct keys:", sorted(all_keys))

# GET the discovery document
url = ("https://returncheck.m-angelmartinez-fer.workers.dev"
       "/.well-known/x402")
r = requests.get(url, timeout=30,
                 headers={"User-Agent": "readonly-probe"})
print("\nGET", url, "->", r.status_code)
body = r.text
print("RAW BODY:")
print(repr(body))
try:
    d = r.json()
except Exception:  # noqa: BLE001
    d = None
if isinstance(d, dict):
    print("discovery top keys:", list(d.keys()))

    def find(obj, field, path=""):
        out = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() == field.lower():
                    out.append((f"{path}.{k}", v))
                out.extend(find(v, field, f"{path}.{k}"))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                out.extend(find(v, field, f"{path}[{i}]"))
        return out

    for fld in ("payTo", "amount", "maxAmountRequired", "asset",
                "network", "scheme", "version", "x402Version",
                "resource", "mimeType"):
        hits = find(d, fld)
        for p2, v in hits[:6]:
            print(f"  {p2} = {v!r}")
    blob = json.dumps(d).lower()
    print("discovery mentions payment-identifier:",
          ("payment-identifier" in blob)
          or ("paymentidentifier" in blob)
          or ("identifier" in blob))
print("DONE", flush=True)
