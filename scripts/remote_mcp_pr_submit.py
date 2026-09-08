"""Open the PR to punkpeye/awesome-remote-mcp-servers and poll CI checks."""
import json
import time

import requests


def gh(*args) -> str:
    import subprocess
    return subprocess.check_output(["gh", *args], text=True).strip()


TOKEN = gh("auth", "token")
H = {"Authorization": f"Bearer {TOKEN}",
     "Accept": "application/vnd.github+json"}
UP = "punkpeye/awesome-remote-mcp-servers"
HEAD = "hristovdimitri2-hub:add-kristo-intelligence"
BRANCH = "add-kristo-intelligence"

title = "Add Kristo Intelligence — DeFi trading signals MCP server (x402 on Base)"
body = """Adds a single entry to the 💰 Finance section (alphabetical, between Fruit Stand and Octagon).

- **Server:** Kristo Intelligence — DeFi trading signals and market intelligence for AI agents on Base (chain 8453).
- **Endpoint:** `https://kristo-intelligence-api.onrender.com/mcp` (Streamable HTTP; legacy SSE also available at `/mcp/sse`).
- **Tools:** market stats, on-chain sales history, bot/service status.
- **Auth:** none for connection — the endpoint answers MCP `initialize` anonymously.
- **Payments:** per-call x402 (USDC on Base), so the entry carries 💰; tools requiring data return a standard 402 challenge.
- **Markers:** ⚡ 🔓 💰
- No Glama connector badge yet — will be added in a follow-up once the connector listing is live.

One server, one entry, one commit. Happy to adjust wording or placement — thanks!
"""

# 1. Open the PR (skip if already open)
existing = requests.get(
    f"https://api.github.com/repos/{UP}/pulls?head={HEAD}&state=open", headers=H, timeout=30).json()
if existing:
    pr = existing[0]
    print("PR already open:", pr["number"], pr["html_url"])
else:
    r = requests.post(
        f"https://api.github.com/repos/{UP}/pulls",
        headers=H,
        json={"title": title, "body": body, "head": HEAD, "base": "main"},
        timeout=30,
    )
    print("PR create:", r.status_code)
    if r.status_code != 201:
        print(r.text[:400])
        raise SystemExit(1)
    pr = r.json()
    print("PR #%d: %s" % (pr["number"], pr["html_url"]))

num = pr["number"]
head_sha = pr["head"]["sha"]
print("head sha:", head_sha)

# 2. Poll CI (check-runs + statuses) for up to ~4 minutes
print("\n=== CI polling ===")
final = None
for attempt in range(16):
    time.sleep(15)
    checks = requests.get(
        f"https://api.github.com/repos/{UP}/commits/{head_sha}/check-runs",
        headers={**H, "Accept": "application/vnd.github+json"}, timeout=30).json()
    runs = checks.get("check_runs", [])
    statuses = requests.get(
        f"https://api.github.com/repos/{UP}/commits/{head_sha}/status",
        headers=H, timeout=30).json().get("statuses", [])
    rows = [(c["name"], c["status"], c["conclusion"]) for c in runs]
    rows += [(s.get("context") or "status", s["state"], None) for s in statuses]
    print(f"[{attempt * 15 + 15:>3}s]", rows if rows else "(no checks yet)")
    if rows and all(st == "completed" for _, st, _ in rows):
        final = rows
        break

print()
if final is None:
    print("CI: still running after timeout — провери ръчно в PR-а.")
else:
    green = all(c in ("success", "neutral", "skipped") for _, _, c in final)
    print("CI VERDICT:", "GREEN ✅" if green else "RED ❌")
    for name, st, con in final:
        if con not in ("success", "neutral", "skipped", None):
            print("  FAILING:", name, "->", con)
            ann = requests.get(
                f"https://api.github.com/repos/{UP}/commits/{head_sha}/check-runs",
                headers={**H, "Accept": "application/vnd.github+json"}, timeout=30).json()
            for c in ann.get("check_runs", []):
                if c["name"] == name and c.get("output"):
                    print("  output:", str(c["output"].get("summary"))[:400])
                    print("  details:", str(c["output"].get("text"))[:600])
