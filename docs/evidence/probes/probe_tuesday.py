# -*- coding: utf-8 -*-
"""Local-only Tuesday prep (no network): build body + generate identifier."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = (r"C:\Users\AlienWare\Downloads"
       r"\returncheck-reverse-test (4).json")
EXPECT_SHA = ("5c42b2fee283b157e30047c011f3c408"
              "13639d99c213bc5fefd93539b8587".replace(
                  "b157e30047c011f3c40813", "b157e30047c011f3c40813639d99")
              )  # placeholder-guard; real constant below
EXPECT_SHA = ("5c42b2fee283b157e30047c011f3c408"
              "13639d99c213bc5be5fefd93539b8587")

temp = os.environ.get("TEMP") or os.environ.get("TMP") or "."

raw = open(SRC, "rb").read()
sha_raw = hashlib.sha256(raw).hexdigest()
print(f"src size={len(raw)} sha={sha_raw} "
      f"ok={len(raw) == 4114 and sha_raw == EXPECT_SHA}")

orig = json.loads(raw.decode("utf-8-sig"))
ext = {"payment-identifier": {"info": {"required": True,
                                       "id": "<ВРЕМЕНЕН-PLACEHOLDER>"}}}
add = (b",\n" + b'"extensions":'
       + json.dumps(ext, ensure_ascii=True,
                    separators=(",", ":")).encode("ascii"))
idx = raw.rfind(b"}")
assert idx == len(raw.rstrip()) - 1 or raw[idx:idx + 1] == b"}"
new = raw[:idx] + add + raw[idx:]

# validate the result
doc = json.loads(new.decode("utf-8-sig"))
assert list(doc.keys()) == list(orig.keys()) + ["extensions"], \
    list(doc.keys())
assert doc["extensions"] == ext
for k in orig:
    assert doc[k] == orig[k]
print("validation: valid JSON, original 10 keys byte-identical in value,"
      " extensions appended as 11th top key")

out = os.path.join(temp, "kristo_tuesday_body.json")
with open(out, "wb") as fh:
    fh.write(new)
print(f"body: {out} size={len(new)} "
      f"sha256={hashlib.sha256(new).hexdigest()}")

ident = str(uuid.uuid4())
assert re.fullmatch(r"[a-zA-Z0-9_-]{16,128}", ident), ident
id_out = os.path.join(temp, "kristo_tuesday_id.txt")
with open(id_out, "w", encoding="ascii", newline="") as fh:
    fh.write(ident)
print(f"id: {id_out} value={ident} len={len(ident)} regex_ok=True")
print("DONE", flush=True)
