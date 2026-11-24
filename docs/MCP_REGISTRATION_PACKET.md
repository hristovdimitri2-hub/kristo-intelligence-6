# REGISTRATION PACKET — MCP catalogs (verified live: 05.09)

**What we are registering:** our MCP server in 3 public catalogs — the places where
AI agents actually look for what to buy. Each registration = you open an address,
log in with your GitHub profile, paste the ready-made text.

**COPY-PASTE FIELDS (identical for all three):**

| Field | Text |
|---|---|
| `Ime` (Name) | `Kristo Intelligence — DeFi Signals API` |
| `URL na sarvara` (Server URL) | `https://kristo-intelligence-api.onrender.com/mcp/sse` |
| Listing in PayAPI | `https://payapi.market/api/kristo-intelligence-defi-signals-api` |
| `Opisanie` (Description) | `Paid DeFi intelligence API on Base: trading-agent signals (action, confidence, price, reasoning for ETH/ONDO/KAITO/DEGEN), cross-DEX arbitrage spreads, whale USDC tracking, rug-risk checks. x402-native: agents pay per call in USDC, from $0.003 — no signup, no API keys.` |
| `Tagove` (Tags, if asked) | `base, defi, x402, crypto, signals` |
| `Kategoria` (Category, if asked) | Finance / Market Data |
| GitHub | `https://github.com/hristovdimitri2-hub/kristo-intelligence-6` |

---

## ── REGISTRATION 1: PulseMCP (~10 minutes) ──

**Address to open:** https://www.pulsemcp.com/submit-server
*(if the page does not open directly — open pulsemcp.com and look for the
"Submit Server" link at the bottom/top)*

**How to log in:**
1. You open the address.
2. If it asks for a login → **Sign in with GitHub** (enter your GitHub username
   and password, then "Authorize").

**Fields (copy-paste from the table above):**
- `Ime` (Name) → "Ime"
- `URL na sarvara` (Server URL) → "URL na sarvara" (the SSE address)
- `Opisanie` (Description) → "Opisanie"
- `Kategoria` (Category) → Finance / Market Data

**Submit button:** "Submit" / "Submit Server" (at the bottom of the form).

**If you hit a problem:**
- The page returns 403 / does not open → try another browser or incognito;
  if it still does not work — skip PulseMCP for today and tell me.
- If it asks for transport → choose **SSE**.

---

## ── REGISTRATION 2: Glama (~10 minutes) ──

**Address to open:** https://glama.ai/mcp/servers

**How to log in:**
1. You open the address (you see a catalog with 81,000+ servers).
2. At the top there is an **"Add Server"** link/button → you click it.
3. It asks for a login → **Sign Up / Sign in with GitHub** (the top right
   "Sign Up" button).

**Fields (copy-paste from the table above):**
- Name → "Ime"
- Server URL → "URL na sarvara" (the SSE address); for transport choose **SSE**
- Description → "Opisanie"
- Tags → `base, defi, x402, crypto, signals`

**Submit button:** "Submit" / "Add" (at the bottom of the form).

**If you hit a problem:**
- If the form asks only for a GitHub repo (not a URL) → paste
  `https://github.com/hristovdimitri2-hub/kristo-intelligence-6` and tell me
  "Glama wants a repo" — I will prepare whatever is needed.
- If the check is waiting for approval — that is normal, they index manually.

---

## ── REGISTRATION 3: Smithery (~15 minutes, CONDITIONAL) ──

⚠️ **IMPORTANT, changed recently:** Smithery was bought by Arcade.dev and the
new flow is different. It does not want smithery.yaml (confirmed in their
documentation — the file is no longer needed for remote servers). BUT it wants
**Streamable HTTP transport**, while our MCP endpoint is **SSE**. Try it —
it may pass, it may refuse. If it refuses because of the transport: STOP and
tell me "Smithery wants streamable HTTP" — that is a small change to the API
that requires your consent (the payTo/endpoint invariant is NOT touched; only a
new transport path is added).

**Address to open:** https://smithery.ai/new

**How to log in:**
1. You open the address.
2. If it asks for a login → Login (top right corner of smithery.ai) → you log in.

**Fields (copy-paste from the table above):**
- Server URL → "URL na sarvara" (the SSE address)
- Name/Namespace → if it asks for a name: `kristo-intelligence`
- Description → "Opisanie"

**Submit button:** "Publish" / "Create".

**If you hit a problem:**
- "Streamable HTTP required" / a refusal because of transport → STOP, tell me
  the exact error and we move on to the next registration. We decide later
  whether we add the new transport.
- If it wants a CLI (`npx smithery ...`) → do not do it yourself; tell me and I
  will prepare the exact commands.

---

## Final table

| Registration | Address | Time | If you get stuck |
|---|---|---|---|
| PulseMCP | https://www.pulsemcp.com/submit-server | ~10 min | Another browser/incognito; otherwise skip it for today |
| Glama | https://glama.ai/mcp/servers → "Add Server" | ~10 min | If it wants a repo instead of a URL — tell me |
| Smithery | https://smithery.ai/new | ~15 min | If it refuses because of transport — STOP, my job afterwards |

**After each successful registration, say "done [name]" — checking the catalog
is my job.** (After 2–3 days I check whether our server is already visible in
their search and report back.)
