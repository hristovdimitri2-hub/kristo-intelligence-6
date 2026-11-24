# INSTRUCTIONS: Registrations in the MCP directories (manual Bulgarian, no jargon)

> 📦 **NEW:** A ready registration packet with verified URLs and exact text for
> copy-paste: **`docs/MCP_REGISTRATION_PACKET.md`** — use THAT one (this file
> remains as a general reference). Verified live on 05.09: Glama/our endpoints
> work; PulseMCP and Smithery have bot protection against scripts — in a human
> browser they are OK.

**What we will do:** we upload our API to three public catalogs (phone
books for AI agents). Each registration = you open a site, create a free
account with your email, paste ready text (I have it). About ~30 minutes total.

**Before you start — prepare these three things (write them down on a sheet):**
1. Your email address: `<contact-email>`
2. Your GitHub profile: `hristovdimitri2-hub` (if you don't have a password for
   it — do "Forgot password" from github.com)
3. Description of the API (you copy it from `docs/MCP_SUBMISSIONS.md`, section
   "Common fields" — or below):
   > Paid DeFi intelligence API on Base: trading-agent signals (action,
   > confidence, price, reasoning for ETH/ONDO/KAITO/DEGEN), cross-DEX
   > arbitrage spreads, whale USDC tracking, rug-risk checks. x402-native:
   > agents pay per call in USDC, from $0.003 — no signup, no API keys.
   - URL: `https://kristo-intelligence-api.onrender.com/mcp/sse`
   - Listing: `https://payapi.market/api/kristo-intelligence-defi-signals-api`

---

## STEP 1 — PulseMCP (the easiest one, start with it)
1. Open in the browser: **https://www.pulsemcp.com**
2. Look for the button **"Submit a Server"** or **"Add your server"** (usually at the top).
3. It will ask you to sign in → choose **Sign in with GitHub** (easier than email).
   Enter your GitHub user and password, click "Authorize".
4. The form asks for name/URL/description → you paste from the block above:
   - Name: `kristo-intelligence`
   - URL: `https://kristo-intelligence-api.onrender.com/mcp/sse`
   - Description: the description above
   - Category (if it asks): Finance / Market Data
5. Click **Submit**. Done — they index it in a day or two, they ask nothing else.

## STEP 2 — Glama
1. Open: **https://glama.ai/mcp/servers**
2. Look for **"Add server"** → again **Sign in with GitHub**.
3. You paste the same fields. If asked about transport, choose **SSE**.
4. For tags write: `base, defi, x402, crypto, signals`
5. Submit → done.

## STEP 3 — Smithery
1. Open: **https://smithery.ai**
2. "Publish server" → **Sign in with GitHub**.
3. Their form may ask for an additional file in the project code
   (it is called `smithery.yaml`). If the form asks for it — STOP here and tell me
   "Smithery wants a yaml file" — I prepare it in 5 minutes and you come back
   to finish.
4. If it asks nothing special — the same fields, Submit.

---

## After each registration — tell me just one thing:
"PulseMCP — sent", "Glama — sent", "Smithery — sent" (or what
error it gave you). I check after 2–3 days whether the server is already visible
in the catalog (that is my job, not yours).

## Why the 30 minutes are worth it
These are the catalogs where AI agents (our clients) actually look for what
to buy. The only channel that one of our people from the platform called
"the path that matters". One registration = our API becomes visible to
that whole crowd, forever and for free.

**ERRORS THAT ARE NOT A PROBLEM:** if the site does not look the way I described
(they change often) — look for the "Submit"/"Add"/"Publish" buttons and the fields
will be the same. If anything is unclear to you — take a screenshot and show it to me.
