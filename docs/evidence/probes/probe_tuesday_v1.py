# -*- coding: utf-8 -*-
"""Local-only: derive v1required body (drop required:true from info)."""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

temp = os.environ.get("TEMP") or "."
src = os.path.join(temp, "kristo_tuesday_body.json")
dst = os.path.join(temp, "kristo_tuesday_body_v1required.json")
orig_path = (r"C:\Users\AlienWare\Downloads"
             r"\returncheck-reverse-test (4).json")

raw = open(src, "rb").read()
print(f"src body: size={len(raw)} sha={hashlib.sha256(raw).hexdigest()}")

# byte-level removal, scoped to the appended extensions section
marker = raw.find(b'"extensions":')
assert marker != -1
target = b'"required":true,'
pos = raw.find(target, marker)
occ_total = raw.count(target)
occ_after = raw.count(target, marker)
assert pos != -1 and occ_after == 1, (pos, occ_total, occ_after)
new = raw[:pos] + raw[pos + len(target):]

# the required top-key shape must now be exact
tail = new[new.find(b'"extensions":'):]
print("tail =", tail.decode("ascii"))

with open(dst, "wb") as fh:
    fh.write(new)

# validate from DISK
b = open(dst, "rb").read()
doc = json.loads(b.decode("utf-8-sig"))
orig = json.loads(open(orig_path, "rb").read().decode("utf-8-sig"))
print(f"v1required: size={len(b)} sha256={hashlib.sha256(b).hexdigest()}")
print("keys =", list(doc.keys()))
assert list(doc.keys()) == list(orig.keys()) + ["extensions"]
same = all(doc[k] == orig[k] for k in orig)
print("original 10 keys & values unchanged =", same)
assert doc["extensions"] == {"payment-identifier": {
    "info": {"id": "<ВРЕМЕНЕН-PLACEHOLDER>"}}}, doc["extensions"]
print("extensions shape OK (info has only id, no required)")
print("DONE", flush=True)
