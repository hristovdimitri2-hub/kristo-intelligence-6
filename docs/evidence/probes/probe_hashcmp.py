# -*- coding: utf-8 -*-
"""Local-only: compute SHA-256, compare vs miguel_hash.txt / our_hash.txt."""
from __future__ import annotations

import hashlib
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = (r"C:\Users\AlienWare\Downloads"
       r"\returncheck-reverse-test (4).json")
temp = os.environ.get("TEMP") or "."

raw = open(SRC, "rb").read()
sha = hashlib.sha256(raw).hexdigest()
print(f"file: size={len(raw)} bytes")
print(f"computed SHA-256 = {sha}")


def load(name: str) -> str | None:
    p = os.path.join(temp, name)
    if not os.path.exists(p):
        print(f"{name}: MISSING ({p})")
        return None
    data = open(p, "rb").read()
    text = data.decode("utf-8", errors="replace")
    stripped = text.rstrip("\r\n")  # remove ONLY trailing newline(s)
    print(f"{name}: raw_len={len(text)} stripped_len={len(stripped)} "
          f"had_trailing_nl={text != stripped}")
    return stripped


def compare(label: str, given: str | None) -> None:
    if given is None:
        return
    if given == sha:
        print(f"{label}: MATCH — identical, no diff")
        return
    n = min(len(given), len(sha))
    fd = next((i for i in range(n) if sha[i] != given[i]), None)
    if fd is None:
        fd = n  # pure length difference
    print(f"{label}: NO MATCH — len {len(given)} vs {len(sha)}; "
          f"first diff @ index {fd}: "
          f"computed={sha[fd:fd+4]!r} given={given[fd:fd+4]!r}")


compare("miguel_hash.txt", load("miguel_hash.txt"))
compare("our_hash.txt", load("our_hash.txt"))
print("DONE", flush=True)
