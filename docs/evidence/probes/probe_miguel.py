# -*- coding: utf-8 -*-
"""Local-only: newest returncheck* in Downloads, hash, prep-file checks."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TARGET = ("5c42b2fee283b157e30047c011f3c408"
          "13639d99c213bc5be5fefd93539b8587")
DL = r"C:\Users\AlienWare\Downloads"
REF = os.path.join(DL, "returncheck-reverse-test (4).json")


def sha_of(path: str) -> tuple[int, str]:
    raw = open(path, "rb").read()
    return len(raw), hashlib.sha256(raw).hexdigest()


def diff_index(a: str, b: str) -> str:
    if a == b:
        return "—"
    n = min(len(a), len(b))
    i = next((k for k in range(n) if a[k] != b[k]), n)
    return (f"first diff @ {i}: a={a[i:i+4]!r} b={b[i:i+4]!r} "
            f"(len {len(a)} vs {len(b)})")


files = []
for name in os.listdir(DL):
    p = os.path.join(DL, name)
    if os.path.isfile(p) and "returncheck" in name.lower():
        st = os.stat(p)
        files.append((st.st_mtime, st.st_size, name, p))
files.sort(reverse=True)  # newest first

print("=== returncheck* files in Downloads (newest first) ===")
for mt, size, name, _ in files:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mt))} | "
          f"{size:>6} B | {name}")

if not files:
    print("NO returncheck* files found in Downloads!")

ref_size, ref_sha = (None, None)
if os.path.exists(REF):
    ref_size, ref_sha = sha_of(REF)
    print(f"\nref (4).json: size={ref_size} sha={ref_sha}")
else:
    print("\nref (4).json NOT FOUND in Downloads")

for mt, size, name, p in files:
    sz, h = sha_of(p)
    print(f"\n--- {name} ---")
    print(f"size={sz} sha={h}")
    print(f"vs TARGET : {'MATCH' if h == TARGET else 'NO MATCH ' + diff_index(h, TARGET)}")
    if ref_sha:
        print(f"vs (4).json: {'MATCH' if h == ref_sha else 'NO MATCH ' + diff_index(h, ref_sha)}")

print("\n=== %TEMP% prep files ===")
temp = os.environ.get("TEMP") or "."
for n in ("kristo_tuesday_body_OBSOLETE_v1.json",
          "kristo_tuesday_body_OBSOLETE_v2required.json",
          "kristo_tuesday_id.txt"):
    p = os.path.join(temp, n)
    ex = os.path.exists(p)
    sz = os.path.getsize(p) if ex else None
    alive = ""
    if n.endswith("_id.txt") and ex:
        v = open(p, "r", encoding="ascii").read()
        alive = f" content_len={len(v)} regex_ok={len(v) >= 16 and v.replace('-','').replace('_','').isalnum()}"
    print(f"{n}: exists={ex} size={sz}{alive}")

repo = r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6"
out = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                     capture_output=True, text=True)
print("\n=== git status --porcelain ===")
print(out.stdout.strip() or "(clean)")
print("DONE", flush=True)
