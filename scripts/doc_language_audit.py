# -*- coding: utf-8 -*-
"""Audit the repository's documents for language and for facts lost in translation.

Two jobs, both mechanical:

1. LANGUAGE (default): count Cyrillic characters in every tracked text file and
   print the ones that still have any. The owner's rule is that every document
   in the repository is English; this is the command that enforces it. Exit 1 if
   any markdown file still contains Cyrillic, except the generated owner-facing
   files listed in OWNER_FACING_GENERATED below.

2. FACTS (--diff): compare every modified markdown file against its HEAD version
   and report any identifier that vanished — hex tokens, URLs, numbers, code
   fences. A loss is a hard failure. This is the check used when the repository
   was translated on 24 November 2026; it caught one real loss (a gist comment
   id that lost a digit) among many false positives.

Usage:
    python scripts/doc_language_audit.py            # language audit
    python scripts/doc_language_audit.py --diff     # facts lost vs HEAD
    python scripts/doc_language_audit.py --all      # both

Exit 0 = clean, 1 = something to fix.
"""

import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CYRILLIC = re.compile("[\u0400-\u04FF]")
HEX = re.compile(r"0x[0-9a-fA-F]{4,}")
URL = re.compile(r"https?://[^\s\)\]\>\"'`]+")
NUM = re.compile(r"\b[\d,\.]{2,}\b")
FENCE = re.compile(r"^```", re.M)
HEAD = re.compile(r"^(#{1,6})\s", re.M)

BINARY = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".pdf", ".zip", ".gz", ".exe", ".dll", ".so", ".pyc",
}

# The one acknowledged exception to the English rule.
#
# `docs/AP2_RADAR.md` is not a repository document that happens to be Bulgarian —
# it is generated from scratch by `scripts/ap2_radar.py` on every radar run, and
# it is a report to the owner, which the rule keeps in Bulgarian on purpose.
#
# It was translated on 24.11.2026, and the radar overwrote it 16 minutes past the
# next run on the same day: the generator's strings are Bulgarian, so the
# translation cannot survive. Recorded here instead of being translated a second
# time and lost again. The file is still counted and printed below, so it stays
# visible; it is only exempt from failing the exit code.
OWNER_FACING_GENERATED = {
    "docs/AP2_RADAR.md",
}


def tracked():
    r = subprocess.run(["git", "ls-files"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8")
    return [f.strip() for f in r.stdout.splitlines() if f.strip()]


def read_bytes(path):
    with open(os.path.join(ROOT, path), "rb") as fh:
        return fh.read()


def read_text(path):
    try:
        return read_bytes(path).decode("utf-8")
    except UnicodeDecodeError:
        return None


def language_audit():
    """Every tracked text file: how many Cyrillic characters does it hold?"""
    by_ext = {}
    not_utf8 = []
    for path in tracked():
        ext = os.path.splitext(path)[1].lower()
        if ext in BINARY:
            continue
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full):
            continue
        raw = read_bytes(path)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            not_utf8.append(path)
            continue
        n = len(CYRILLIC.findall(text))
        if n:
            by_ext.setdefault(ext or "(none)", []).append((n, path))

    total = sum(len(v) for v in by_ext.values())
    print("=== files that still contain Cyrillic: %d ===" % total)
    for ext in sorted(by_ext, key=lambda e: -sum(n for n, _ in by_ext[e])):
        rows = by_ext[ext]
        print("\n--- %s: %d files, %d characters ---"
              % (ext, len(rows), sum(n for n, _ in rows)))
        for n, path in sorted(rows, reverse=True)[:40]:
            print("%7d  %s" % (n, path))

    md_bad = [p for rows in by_ext.values() for _, p in rows
              if p.lower().endswith(".md") and p not in OWNER_FACING_GENERATED]
    if not_utf8:
        print("\n=== files that are not valid UTF-8: %d ===" % len(not_utf8))
        for p in not_utf8:
            print("  " + p)
    print("\nmarkdown files with Cyrillic: %d" % len(md_bad))
    # One machine-readable line per real offender. The per-file table above also
    # lists exempt files, so CI must not scrape that table — it would annotate a
    # file the rule deliberately allows.
    for p in sorted(md_bad):
        print("not-English: %s" % p)
    exempt = sorted(p for rows in by_ext.values() for _, p in rows
                    if p in OWNER_FACING_GENERATED)
    if exempt:
        print("exempt (generated owner-facing, Bulgarian by design): %s"
              % ", ".join(exempt))
    return 1 if (md_bad or not_utf8) else 0


def git_show(path):
    r = subprocess.run(["git", "show", "HEAD:" + path], cwd=ROOT,
                       capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", "replace")


def modified_md():
    r = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8")
    out = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().strip('"')
        if path.lower().endswith(".md") and os.path.isfile(os.path.join(ROOT, path)):
            out.append(path)
    return out


def tokens(text):
    return {
        "hex": set(HEX.findall(text)),
        "url": set(URL.findall(text)),
        "num": set(NUM.findall(text)),
    }


def facts_audit():
    """Modified markdown vs HEAD: did any identifier vanish?"""
    files = modified_md()
    bad = []
    for path in files:
        old = git_show(path)
        if old is None:
            continue
        new = read_text(path)
        if new is None:
            continue
        to, tn = tokens(old), tokens(new)
        lost = []
        for kind in ("hex", "url", "num"):
            missing = to[kind] - tn[kind]
            if missing:
                lost.append((kind, sorted(missing)[:6]))
        fo, fn = len(FENCE.findall(old)), len(FENCE.findall(new))
        if fo != fn:
            lost.append(("fences", ["%d -> %d" % (fo, fn)]))
        if lost:
            bad.append((path, lost))

    print("=== modified markdown files: %d ===" % len(files))
    print("=== files with a lost identifier: %d ===" % len(bad))
    for path, lost in bad:
        print("\n" + path)
        for kind, items in lost:
            print("    %-6s %s" % (kind, ", ".join(items)))
    return 1 if bad else 0


def main(argv):
    if "--diff" in argv:
        return facts_audit()
    if "--all" in argv:
        return max(language_audit(), facts_audit())
    return language_audit()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
