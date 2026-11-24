# AUDIT: Listing channels (07.09, read-only)

Document-reading audit + live checks (GitHub API, Glama, GitHub web).
Zero code changes. payTo/endpoint untouched. 164/164 PASS.

## 0. Update 22.09 — Glama (newer than the audit below)

| Ticket | Status (22.09) | What it awaits |
|---|---|---|
| 🎫 **#130688574** (initial Glama) | The listing is **live** — connectors **Hosted, rated A**; servers **claimed + released, rated A**, 3 tools + remotes published | — (closed in substance) |
| 🎫 **#135407945** (22.09) | **Frank joined in himself** after the build errors. Our diagnosis, accepted in the ticket: the server is registered under **"Runs from source"** by mistake → the correct type is **"Hosted endpoint"** (our `/mcp` on Render). A **type change/reset** was requested | A reply from Glama (type change or reset) |
| **PR #13219** (punkpeye/awesome-mcp-servers) | The badge added in the requested format (`OWNER/REPO` immediately after the link); bot label `missing-glama` → **`has-glama`** | Merge from Frank |

**Important:** the **rated A** badge, tools and release are live as of **21.09** and are
**not lost** when the type changes — a type change only stops the broken build path
(HTTP `/mcp` does not pass the stdio introspection test of their container).

## 1. Inventory: PRs — exact numbers and statuses (GitHub API, 07.09)

| PR | Where | Status (exact) | Opened | Closed | Why/by whom |
|---|---|---|---|---|---|
| **#11557** "Add Kristo Intelligence — DeFi intelligence MCP server" | punkpeye/awesome-mcp-servers | **CLOSED, not merged** | 05.08 | **07.09** | punkpeye: "Closing this PR due to inactivity. The last author activity was 32 days ago… (the server needs to be submitted to Glama, claimed, and have a quality score evaluated)" |
| **#12799** "Add Kristo Intelligence v6 — DeFi trading signals API" | punkpeye/awesome-mcp-servers | **CLOSED, not merged** | 24.08 | **29.08** | punkpeye: "this PR adds multiple servers. Please submit one server per PR" |
| **#13219** "Add Kristo Intelligence v6 — DeFi trading signals API" | punkpeye/awesome-mcp-servers | **OPEN** ✅ | 30.08 | — | A clean PR: 1 file, 1 line, Finance & Fintech, alphabetical. Bot labels: has-emoji, has-glama, valid-name. No maintainer review |
| **#1308** "Add Kristo Intelligence v6 — DeFi Trading Signals API" | xpaysh/awesome-x402 | **OPEN** ✅ | 24.08 | — | No review (1 participant, 0 comments). Adds v6 to "AI Agent Integration" |
| **#1081** "Add Kristo Intelligence — x402 DeFi Intelligence API" | xpaysh/awesome-x402 | **OPEN** ✅ | 31.07 | — | The entry for kristo-travel-api (a bonus find — it was not in our documents) |

### Corrections to old claims from our documents
- "PR #12799 Open" (DISTRIBUTION_STATUS/VISIBILITY_PLAN) — **FALSE**: #12799 was
  closed on 29.08. Replaced by #13219 (which the documents do not mention at all!).
- "PR #1308 Open" — **TRUE**.
- The claim in the old PR #11557: "15 tools… 0.10 USDC/call… Listed on
  official MCP registry (registry.modelcontextprotocol.io)" — **unconfirmed and
  incompatible with today's product** (v6: 3 MCP tools, prices from $0.003).

## 2. PR #11557 — analysis (why the bot mentions kristo-travel-api)

- **Content:** a request to add "Kristo Intelligence" to the Finance &
  Fintech section. The bot (github-actions) labelled it has-emoji / has-glama /
  valid-name and wrote: "Thank you for adding the Glama badge! Please make
  sure the server has been evaluated by Glama and has a quality score."
- **Which repo/link the PR body points to:**
  GitHub → `hristovdimitri2-hub/kristo-travel-api` (NOT -6!),
  MCP URL → `https://kristo-intelligence.vercel.app/mcp` (Vercel, not Render).
- **Why the bot/maintainer mentions kristo-travel-api:** because the PR body
  points to exactly the kristo-travel-api repo. The author's explanation in #12799:
  "the branch was based on our fork main, which carried the kristo-travel-api
  entry" — the fork carried both entries and the first PR mixed them up.
- **Context of the kristo-travel-api repo:** this is the OLD "Kristo
  Intelligence" codebase (Next.js + FastAPI, 51 commits), whose README
  points to **the same Render URL** (kristo-intelligence-api.onrender.com) and shows
  **a different wallet address** (`0xd4cdA980…Cfd88f` — not our payTo
  `0xd4cdA900…c6fd08f`) and old prices (0.01 USDC). = A risk of brand confusion and
  of divergence from the real payTo.
- **It was closed on 07.09** with the maintainer's explicit requirements:
  **(1) submission to Glama, (2) claim, (3) an evaluated quality score** — only then
  can a PR with a Glama badge be merged.

## 3. Inventory: repos under hristovdimitri2-hub (public: 14)

⚠ Through the GitHub API ONLY the public repos are visible — private ones, if any, are
not visible from here (the local remote is https://github.com/hristovdimitri2-hub/
kristo-intelligence-6.git).

| Repo | Kind | Last push | Status |
|---|---|---|---|
| **kristo-intelligence-6** | original, the API (Render) | **06.09 (today)** | 🟢 **THE ACTIVE ONE** — everything leads to us |
| thd-ice | original | 31.08 | neutral (side project) |
| awesome-mcp-servers | **fork** (for the PRs) | 30.08 | 🟡 working fork — carries the add-kristo-intelligence-v6 branches |
| nexus | original | 30.08 | neutral (NEXUS source) |
| foresight-oracle | original | 30.08 | neutral |
| autonomous-agent-x402-usdc-example | original (demo) | 25.08 | neutral; homepage points to the Render API |
| awesome-x402 | **fork** (for PR #1308) | 24.08 | 🟡 working fork |
| **kristo-travel-api** | original (the old base) | 18.08 | 🔴 inactive, but public; the README points to THE SAME Render API + a foreign wallet address → confusing; it sits in the closed #11557 |
| kristo | original | 16.08 | old/dormant |
| kristo-inteligents | original | 16.08 | old/dormant |
| base44-projekti | original | 15.08 | old/dormant |
| corten-landing, Setas, My-protect-1 | original | Feb–March | dormant |
| — | none is archived | — | — |

**Conclusion:** only `kristo-intelligence-6` is alive and tied to production.
`kristo-travel-api` is the only problematic one — public, linked to one
closed PR, and it points to our Render URL with a WRONG wallet address in the README.

## 4. Glama: what "claim" means and where we stand (ticket #130688574)

### How Glama works (verified live on 07.09)
- The directory has **83 219 servers**; entries come from automatic
  indexing of GitHub + manual "Add Server".
- **Claim = confirming ownership of a listing.** "Claimed" is an official
  attribute (filter) — 3 986 servers are claimed. It is done by logging into Glama
  **with the GitHub account** (OAuth) — that is how Glama links the account to the repo.
  The claim unlocks management of the listing (editing, status) and is a PREREQUISITE
  for the quality score badge.
- **Quality score** = an A/B/C rating on three axes (license / quality / maintenance),
  computed by Glama after review. The badge in the README (which the bot of
  awesome-mcp-servers asks for) points to exactly this score → hence the order is:
  **submission → approval → claim → score → badge → PR merge.**

### Our state in Glama (verified)
- A search for "kristo" in glama.ai/mcp/servers → **0 results from us** (there are only
  other "kristo" servers). The slugs `hristovdimitri2-hub/kristo-intelligence-6`
  and `hristovdimitri2-hub/kristo-travel-api` → 404. **We are NOT listed.**
- **Ticket #130688574** = our submission ("Add Server") for human review.
  There is already one rejection: "the README does not contain enough information". A prepared
  reply is in `docs/GLAMA_REPLY.md` (an expanded README + links; the rule: zero wallet
  addresses in the email; it is sent ONLY after a live check of POST /mcp).
- **What remains after the approval of #130688574:** the listing appears in
  the directory → we log in with GitHub at glama.ai → we **claim** the listing →
  we wait for/check the quality score (A/B/C) → we take the badge URL from
  Glama → only then is the badge in the README of -6 "real".

## 5. Summary table: channel → status → what it awaits → whose action

| Channel | Status (07.09) | What it awaits | Whose action |
|---|---|---|---|
| **PayAPI Market** | Listed; band "unscored/baseline" | Chet's compute to run an evaluation (band/score) | ⏳ Chet/market — not ours |
| **Glama** (ticket #130688574) | Submitted; 1 rejection (README); reply prepared | Human review; if "OK" → claim + score | **Owner**: (1) live check of POST /mcp, (2) send GLAMA_REPLY.md, (3) then claim with GitHub at glama.ai |
| **awesome-mcp-servers** | #11557 closed; #12799 closed; **#13219 OPEN** | Glama listing + claimed + quality score → badge in the README → PR update | **Owner** (the Glama steps) → then **we**: update #13219 |
| **awesome-x402** | #1308 OPEN (v6); #1081 OPEN (travel) | Review by the maintainer (xpaysh); low priority — 286 stars | ⏳ maintainer; we — only if they request a change |
| **MCP Registry (official)** | Requested "through PayAPI" (the claim in #11557 is unconfirmed) | PayAPI approval → automatic publication | ⏳ Chet/market |
| **PulseMCP / Smithery** | 🛑 PulseMCP: submissions STOPPED since 03.09 (verified live on 07.09); Smithery: published ✅ | PulseMCP: to reopen; a future option — Official MCP Registry (no execution) | **Owner** — watch for the reopening; the Registry is decided later |

## 6. Draft plan (no execution): a clean PR to awesome-mcp-servers

**Important clarification: there is NO need for a "new" PR — #13219 already IS the clean PR**
(1 file, 1 line, opened on 30.08, with no remarks from the maintainer). The plan is
to **finish** it, not to open a fourth one. Note: the last activity
on #13219 is 30.08 → under the 32-day rule (as with #11557) the risk of
auto-closing is around **01.10**. Activity before that date.

**Prerequisites (in order):**
1. Ticket #130688574 approved → the listing live at glama.ai.
2. Claim with the GitHub account of hristovdimitri2-hub.
3. Quality score evaluated (A/B/C) → we take the official badge URL from
   the server page in Glama.
4. README of -6: the Glama badge + current facts (3 MCP tools, prices from
   $0.003, Base mainnet, Streamable HTTP at /mcp). No wallet addresses.

**PR content (a ready recipe):**
- Branch: a new one from **upstream/main** of punkpeye (never from a fork main — that
  drowned #12799).
- **1 file, 1 line** in README.md, section Finance & Fintech, alphabetical
  (after HuggingAGI/mcp-baostock-server, before hypeprinter007-stack/
  anchor-x402-mcp — the position has already been verified in #13219).
- A sample line: `- [Kristo Intelligence](https://github.com/hristovdimitri2-hub/kristo-intelligence-6) - [ badges ] DeFi trading signals API for AI agents on Base — x402 pay-per-call (from $0.003), no signup, real on-chain sales` (the exact format — following the example of the neighbouring lines).
- **Includes:** the Glama badge (only after a real score!), a link to the repo.
- **Excludes:** a wallet address, claims about the "official MCP registry" (they are
  unconfirmed), Vercel links, old prices (0.10 USDC), "15 tools".
- PR description: 3–4 lines (what/why/transport/payment) + a link to
  the Glama listing; zero wallet addresses in the description as well.
- After opening: a reply within 48 h to every maintainer question
  (anti-"inactivity close").

**In parallel (recommendation):** for kristo-travel-api — we do NOT revive #11557 until
the repo is either cleaned up (README: correct wallet/links or an explicit
"separate legacy project"), or made private. One repo with a foreign (wrong)
wallet address, pointing to our API, is a trust risk even before we are
listed. The decision is the owner's.

> ✅ **DONE (07.09):** `kristo-travel-api` was made **private** through the
> GitHub API with the owner account (confirmed: an anonymous GET → 404; 0 stars/forks/
> watchers — no one was affected). Recorded in PROJECT_STATUS.md.
> Consequence: PR #11557 remains closed and pointless; open PR awesome-x402
> #1081 (the travel-api entry) now points to a hidden repo — the maintainer will probably
> close it himself, or the owner closes it explicitly (a decision is pending).
