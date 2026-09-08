"""Fork branch prep: add Kristo Intelligence to awesome-remote-mcp-servers README.

Creates branch `add-kristo-intelligence` in the fork and commits the one-entry
addition. Does NOT open the PR (owner gives the final go).
"""
import base64
import json
import subprocess

import requests


def gh(*args) -> str:
    return subprocess.check_output(["gh", *args], text=True).strip()


TOKEN = gh("auth", "token")
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}
FORK = "hristovdimitri2-hub/awesome-remote-mcp-servers"
UPSTREAM = "punkpeye/awesome-remote-mcp-servers"
BRANCH = "add-kristo-intelligence"

# 1. Base SHA from upstream main
base_sha = gh("api", f"repos/{UPSTREAM}/branches/main", "--jq", ".commit.sha")
print("upstream main:", base_sha)

# 2. Create branch in fork
r = requests.post(
    f"https://api.github.com/repos/{FORK}/git/refs",
    headers=H,
    json={"ref": f"refs/heads/{BRANCH}", "sha": base_sha},
    timeout=30,
)
print("branch create:", r.status_code, "(422 = already exists — ok)")
if r.status_code not in (201, 422):
    print(r.text[:300])
    raise SystemExit(1)

# 3. Read README from the fork branch
r = requests.get(
    f"https://api.github.com/repos/{FORK}/contents/README.md",
    headers=H, params={"ref": BRANCH}, timeout=30,
)
file_sha = r.json()["sha"]
readme = base64.b64decode(r.json()["content"]).decode("utf-8")

# 4. Insert the entry before Octagon (alphabetical: Fruit Stand < Kristo < Octagon)
ENTRY = (
    "- [Kristo Intelligence](https://kristo-intelligence-api.onrender.com) "
    "`https://kristo-intelligence-api.onrender.com/mcp`\n"
    "  ⚡ 🔓 💰 - DeFi trading signals and market intelligence for agents on "
    "Base; x402 pay-per-call in USDC, no signup.\n"
)
anchor = "- [Octagon](https://octagonagents.com)"
assert anchor in readme, "Octagon anchor not found!"
if "Kristo Intelligence" in readme:
    print("entry already present — no double insert")
    new_readme = readme
else:
    new_readme = readme.replace(anchor, ENTRY + anchor, 1)

# 5. Commit
r = requests.put(
    f"https://api.github.com/repos/{FORK}/contents/README.md",
    headers=H,
    json={
        "message": "Add Kristo Intelligence — DeFi trading signals MCP server (x402 on Base)",
        "content": base64.b64encode(new_readme.encode()).decode(),
        "sha": file_sha,
        "branch": BRANCH,
    },
    timeout=30,
)
print("commit:", r.status_code, r.json().get("commit", {}).get("sha", "")[:12])

# 6. Verify: fetch the branch file and show the Finance section
r = requests.get(
    f"https://raw.githubusercontent.com/{FORK}/{BRANCH}/README.md", timeout=30
)
lines = r.text.splitlines()
start = next(i for i, ln in enumerate(lines) if ln.startswith("### ") and "Finance" in ln)
end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("### "))
print("\n=== FINANCE SECTION (fork branch) ===")
for i in range(start, end):
    print(lines[i])
