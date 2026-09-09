"""AP2 radar — read-only watch over the PUBLIC Agent Payments Protocol artifacts.

Monthly protocol, ROW 5 (after recon and listing_monitor):
    python scripts/ap2_radar.py

What it watches (all public, no identities, nothing sent anywhere):
  * commits since the previous check in the official AP2 repos
    (google-agentic-commerce/AP2, .../a2a-x402) + new releases/tags
  * new public repos matching the AP2 working-group patterns
    (wg-domain-discovery, wg-tax, ap2-wg...) — WG repos may become public
    at any time; the search re-runs on every check
  * new documents/drafts by keywords: discovery manifest, acceptedNetworks,
    buyer-side declarations, census
  * numeric census series (e.g. "1265 hosts") — date + number, month over month

Output: docs/AP2_RADAR.md ("what changed since last time" + census growth).
State: docs/AP2_RADAR_STATE.json (previous snapshot; safe to delete — the
next run rebuilds from scratch with a full report).

NOTE: the AP2 Slack (wg-tax, wg-domain-discovery) is PRIVATE and is NOT
scanned — the owner reads it by eye. This script only watches public GitHub
artifacts, unauthenticated, read-only.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

H = {"Accept": "application/vnd.github+json", "User-Agent": "ap2-radar"}
API = "https://api.github.com"
MONITORED = [
    "google-agentic-commerce/AP2",
    "google-agentic-commerce/a2a-x402",
]
WG_PATTERNS = ["wg-domain-discovery", "wg-tax", "ap2-wg", "ap2-working-group"]
KEYWORDS = ["discovery", "manifest", "acceptednetworks", "buyer", "census",
            "tax", "draft"]
CENSUS_RE = re.compile(r"(\d[\d,]{2,})\s*(hosts|merchants|agents|providers)",
                       re.IGNORECASE)
ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "docs" / "AP2_RADAR_STATE.json"
REPORT_PATH = ROOT / "docs" / "AP2_RADAR.md"


def _get(url: str) -> requests.Response:
    return requests.get(url, headers=H, timeout=30)


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"repos": {}, "known_wg_repos": [], "census": [], "last_check": None}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(
        json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")


def _repo_commits(full: str, since_sha: str | None) -> list[dict]:
    """New commits since the remembered sha (newest first from the API,
    reversed to oldest-first for the report)."""
    r = _get(f"{API}/repos/{full}/commits?per_page=15")
    if r.status_code != 200:
        return [{"error": f"HTTP {r.status_code}"}]
    commits = r.json()
    out = []
    for c in commits:
        sha = c["sha"]
        if since_sha and sha == since_sha:
            break  # everything below this is already seen
        detail = _get(f"{API}/repos/{full}/commits/{sha}")
        files = []
        if detail.status_code == 200:
            files = [f["filename"] for f in detail.json().get("files", [])][:20]
        out.append({
            "sha": sha[:10],
            "date": c["commit"]["committer"]["date"],
            "message": c["commit"]["message"].splitlines()[0][:120],
            "files": files,
        })
    return list(reversed(out))


def _releases(full: str, seen_tags: set[str]) -> list[dict]:
    r = _get(f"{API}/repos/{full}/releases?per_page=5")
    out = []
    for rel in r.json() if r.status_code == 200 else []:
        tag = rel.get("tag_name", "")
        if tag and tag not in seen_tags:
            out.append({"tag": tag, "date": rel.get("published_at"),
                        "name": rel.get("name", "")})
    return out


def _search_new_wg_repos(known: list[str]) -> list[dict]:
    """Public repos that look like AP2 working-group artifacts."""
    found = []
    for pattern in WG_PATTERNS:
        r = _get(f"{API}/search/repositories?q={pattern}&per_page=10")
        for it in (r.json() or {}).get("items", []):
            if it["full_name"] not in known:
                found.append({
                    "full_name": it["full_name"],
                    "pushed": it["pushed_at"][:10],
                    "description": str(it["description"] or "")[:90],
                    "pattern": pattern,
                })
    seen, uniq = set(), []
    for f in found:
        if f["full_name"] not in seen:
            seen.add(f["full_name"])
            uniq.append(f)
    return uniq


def _census_scan(full: str, tree_paths: list[str]) -> list[dict]:
    """Extract numeric census values (e.g. '1265 hosts') from candidate files."""
    found = []
    for path in tree_paths:
        low = path.lower()
        if any(k in low for k in ("census", "hosts", "merchants", "adoption")) \
                and low.endswith((".json", ".md", ".txt", ".csv")):
            raw = _get(f"https://raw.githubusercontent.com/{full}/main/{path}")
            if raw.status_code != 200:
                continue
            for m in CENSUS_RE.finditer(raw.text):
                found.append({
                    "value": int(m.group(1).replace(",", "")),
                    "unit": m.group(2).lower(),
                    "source": f"{full}:{path}",
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                })
    return found


def main() -> int:
    now = datetime.now(timezone.utc)
    state = _load_state()
    lines = [
        "# AP2 RADAR — какво се промени от миналия път",
        "",
        f"Проверено: {now.strftime('%Y-%m-%d %H:%M UTC')} · "
        "read-only, публични артефакти, без идентичности.",
        "",
        "## Промени по мониторирани repos",
        "",
    ]
    anything = False

    for full in MONITORED:
        since = state.get("repos", {}).get(full, {}).get("last_commit_sha")
        lines.append(f"### {full}")
        lines.append("")
        commits = _repo_commits(full, since)
        if commits and "error" in commits[0]:
            lines.append(f"- (API грешка: {commits[0]['error']})")
        elif not commits:
            lines.append("- Няма нови комити от миналата проверка.")
        else:
            anything = True
            for c in commits:
                kw = [k for k in KEYWORDS
                      if k in (c["message"] + " " + " ".join(c["files"])).lower()]
                marker = f" ← КЛЮЧОВИ ДУМИ: {', '.join(kw)}" if kw else ""
                lines.append(f"- `{c['sha']}` {c['date'][:10]} — {c['message']}{marker}")
                for f in c["files"][:6]:
                    lines.append(f"  - файл: {f}")
        lines.append("")

        rels = _releases(full, set(state.get("repos", {}).get(full, {})
                                   .get("seen_tags", [])))
        if rels:
            anything = True
            for rel in rels:
                lines.append(f"- 🏷 НОВ РЕЛИЙЗ: `{rel['tag']}` ({rel['date']}) — {rel['name']}")
            state.setdefault("repos", {}).setdefault(full, {}).setdefault(
                "seen_tags", []).extend(rel["tag"] for rel in rels)
        lines.append("")

    lines += ["## Нови публични WG repos (търсене при всяка проверка)", ""]
    new_wg = _search_new_wg_repos(state.get("known_wg_repos", []))
    if new_wg:
        anything = True
        for w in new_wg:
            lines.append(f"- 🆕 `{w['full_name']}` (pushed {w['pushed']}) — {w['description']}")
        state.setdefault("known_wg_repos", []).extend(
            w["full_name"] for w in new_wg)
    else:
        lines.append("- Нищо ново публично по WG патерните.")
    lines.append("")

    lines += ["## Цензус серия (растеж през месеците)", ""]
    tree = _get(f"{API}/repos/{MONITORED[0]}/git/trees/main?recursive=1")
    tree_paths = [x["path"] for x in (tree.json() or {}).get("tree", [])]
    new_census = _census_scan(MONITORED[0], tree_paths)
    for c in new_census:
        known_values = [(e.get("value"), e.get("source")) for e in state.get("census", [])]
        if (c["value"], c["source"]) not in known_values:
            state.setdefault("census", []).append(c)
            anything = True
            lines.append(f"- 📈 НОВ цензус: **{c['value']} {c['unit']}** ({c['source']}, {c['date']})")
    series = state.get("census", [])
    if series:
        lines.append("")
        lines.append("| Дата | Число | Източник |")
        lines.append("|---|---|---|")
        for e in series:
            lines.append(f"| {e['date']} | {e['value']} {e['unit']} | {e['source']} |")
    else:
        lines.append("- Още няма публикуван цензус в мониторирани repos.")
    lines.append("")

    if not anything:
        lines.insert(4, "**ТИХО — няма нови комити, релийзи, WG repos или цензус.**")
        lines.insert(5, "")

    lines.append("---")
    lines.append("Slack каналите (wg-tax, wg-domain-discovery) са ЧАСТНИ и НЕ се")
    lines.append("сканират — чете ги собственикът на око, месечно.")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    state["last_check"] = now.isoformat()
    for full in MONITORED:
        latest = _get(f"{API}/repos/{full}/commits?per_page=1")
        if latest.status_code == 200 and latest.json():
            state.setdefault("repos", {}).setdefault(full, {})[
                "last_commit_sha"] = latest.json()[0]["sha"]
    _save_state(state)

    print(f"AP2 radar: докладът е обновен -> {REPORT_PATH}")
    print(f"  нови комити/релийзи/WG/цензус: {'ДА' if anything else 'ТИХО'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
