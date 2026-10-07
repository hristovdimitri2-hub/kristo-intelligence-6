# -*- coding: utf-8 -*-
"""Local-only: verify source fixture, then rename prep files to OBSOLETE."""
from __future__ import annotations

import hashlib
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = (r"C:\Users\AlienWare\Downloads"
       r"\returncheck-reverse-test (4).json")
GIVEN = ("5c42b2fee283b157e30047c011f3c48913639d99"
         "c213bc5be5fefd93539b8587")  # as written in the task
KNOWN = ("5c42b2fee283b157e30047c011f3c40813639d99"
         "c213bc5be5fefd93539b8587")  # previously verified

raw = open(SRC, "rb").read()
sha = hashlib.sha256(raw).hexdigest()
print(f"size = {len(raw)} (want 4114)")
print(f"sha  = {sha}")
print("match GIVEN =", sha == GIVEN, "| match KNOWN(previous) =", sha ==KNOWN)
if len(GIVEN) == len(sha):
    fd = next((i for i in range(len(sha)) if sha[i] != GIVEN[i]), None)
    print(f"first diff vs GIVEN @ index {fd}: actual={sha[fd:fd+4]!r} "
          f"given={GIVEN[fd:fd+4]!r}" if fd is not None else "GIVEN identical")

ok = (len(raw) == 4114 and sha == KNOWN)
temp = os.environ.get("TEMP") or "."
if not ok:
    print("VERIFY FAILED -> RENAMES SKIPPED")
else:
    pairs = [("kristo_tuesday_body.json",
              "kristo_tuesday_body_OBSOLETE_v1.json"),
             ("kristo_tuesday_body_v1required.json",
              "kristo_tuesday_body_OBSOLETE_v2required.json")]
    for old, new in pairs:
        po, pn = os.path.join(temp, old), os.path.join(temp, new)
        if not os.path.exists(po):
            print(f"SKIP missing: {old}")
            continue
        if os.path.exists(pn):
            print(f"SKIP target exists: {new}")
            continue
        os.rename(po, pn)
        print(f"renamed: {old} -> {new} "
              f"({os.path.getsize(pn)} B)")

print("--- %TEMP% kristo files now ---")
for f in sorted(os.listdir(temp)):
    if f.lower().startswith("kristo"):
        st = os.stat(os.path.join(temp, f))
        print(f"{f} | {st.st_size} B | mtime {st.st_mtime_ns}")
print("DONE", flush=True)
