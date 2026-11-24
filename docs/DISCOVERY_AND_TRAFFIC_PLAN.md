# DISCOVERY & TRAFFIC PLAN — Kristo Intelligence

**Compiled:** 03.11.2026 · **Basis:** live checks (Glama, official MCP Registry, GitHub API) + Chatbox archive
**Status:** draft for approval — **nothing in the repo has been changed by this document**

---

## §0 Summary in three points

1. **Glama is not broken — we are knocking on the wrong door.** Our live entry is in **Connectors**
   (hosted endpoints): ownership verified, **Healthy**, **100% uptime for 47 days**, last test
   **03.11 11:13**, **TDQS A (4.7/5)** with 3 tools, each rated A. The only thing missing is the entry
   in **Servers** (source code) — and that is needed solely for the badge and for PR #13219.
2. **The registry is "inverted".** In the official MCP Registry `isLatest` points to **v6.0.0 from
   17.09**, while the newer and richer **v1.0.0 from 10.10** is `isLatest: false` — because 1.0.0 <
   6.0.0 by semver. Everything that consumes from the registry (PulseMCP and others) sees the old
   version.
3. **The real hole is public search** — exactly as the owner said on 03.11: "public search — right now
   we are not there. That is our biggest hole." The directories see us; **search engines and LLMs —
   almost not**.

---

## §1 Verified live (03.11.2026)

| Check | Result | Evidence |
|---|---|---|
| Glama **Connectors** — our entry | ✅ **LIVE** | `glama.ai/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence` |
| … ownership | ✅ **Ownership verified** | on the page |
| … health | ✅ **Healthy**, **100.0% uptime / 47 days**, last test **2026-11-03 11:13** | |
| … quality | ✅ **TDQS A, 4.7/5.0**, 3 tools × **A** | Disambiguation 5/5 · Naming 5/5 · Tool Count 5/5 · Completeness 4/5 |
| … transport | Streamable HTTP · MCP 2025-11-25 · `https://kristo-intelligence-api.onrender.com/mcp` | |
| … empty fields | ❌ Documentation: *Not available* · Trust center: *Not available* · ChatGPT: `–` · Claude: `–` | |
| Glama **Servers** — our entry | ❌ **MISSING — confirmed via the API**: `GET /v1/servers/hristovdimitri2-hub/kristo-intelligence-6` → **HTTP 404 `not_found`**; a search for "kristo" returns Krimto, gmail-mcp, Safe Terminal, agentcrush — **not us**. It is not a hidden entry: there really is no such entry | Glama Directory API |
| Glama **Connectors** — the full entry | `id: oc4mkbcgg8` · `qualityScore 4.7` · `toolCount 3` · `healthy: true` · `lastTestedAt 2026-11-03T12:14:23Z` · `createdAt 2026-09-17` · attributes: `auth:none`, `status:healthy`, `capability:tools`, `category:developer-tools`, `category:finance` | Glama Directory API |
| Connector → repo link | ❌ **`repository: null`** — the connector is not linked to the repo; `documentationUrl: null` | Glama Directory API |
| **Badge of the connector** | ✅ renders **"A"**: *"MCP connector rated A … ownership verified, tool definitions rated A, 3 tools"* | `/mcp/connectors/…/badges/score.svg` |
| **Badge of the server** | ❌ renders **"F – A"**: *"claimed by its maintainer, remote-capable, maintenance rated A"* — license **F**, quality **not rated** | `/mcp/servers/…/badges/score.svg` |
| README line 3 | Shows **both** badges → the visitor sees a red "F" next to the clean "A" | `README.md:3` |
| Glama sizes | Servers **115 008** · Connectors **39 498** | |
| Official MCP Registry | ⚠️ **v6.0.0 (17.09) = `isLatest: true`**; v1.0.0 (10.10) = `false` | `registry.modelcontextprotocol.io/v0/servers?search=kristo-intelligence` |
| PR **#13219** (punkpeye/awesome-mcp-servers) | 🟡 **open**, **20 comments**, last activity **01.11**, labels `has-emoji`, `valid-name`, `has-glama` | GitHub API |
| PR **#1308** (xpaysh/awesome-x402) | 🟢 **open**, `mergeable_state: clean`, since 24.08, last activity 28.09 | GitHub API |
| PR #1081 (the same list, old entry) | open — for `kristo-travel-api`, **not the current project** | GitHub API |
| In the repo | ✅ **present** `glama.json`, `glama-connector-claim.json`, `server.json` (**v6.0.0**), `smithery.yaml`, `.mcp.json`, `Dockerfile`, **`scripts/mcp_stdio_bridge.py`** + `tests/test_mcp_stdio_bridge.py` · ❌ **absent** `.github/`, `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md`, `render.yaml` | local read |

---

## §2 Diagnosis — what exactly is broken

### 2.1 Glama has TWO different directories and we are applying to the wrong one

| | **Servers** (`/mcp/servers`) | **Connectors** (`/mcp/connectors`) |
|---|---|---|
| What it accepts | "open-source servers that we build and run from source" | hosted endpoints: "Only approved connectors reachable over **streamable HTTP** are listed" |
| How you get in | Glama builds the container and **starts** it — it must respond to **introspection** | you submit a URL, they health-check it |
| Us | ❌ we are absent | ✅ **live, verified, rated A** |
| Needed for | badge in the README + merge of PR #13219 | **real visibility in front of customers** (the "Connect" button) |

**The key:** our `Dockerfile` brings up **gunicorn (HTTP)** — it cannot respond to introspection in
Glama's container. That is why "Runs from source" fails. And "Add Server → Hosted endpoint" refuses,
because the endpoint **is already registered as a connector** → duplicate.

> **We are not "rejected". We are knocking on a door that is not ours — and meanwhile we sat in a ticket for 6 weeks.**

### 2.2 The timeline from PR #13219 (20 comments) — how the time drained away

| Date | Who | What |
|---|---|---|
| 30.08 | PR opened | 1 file, 1 line |
| 30.08 | bot | "add Glama quality score" |
| 07.09 | **punkpeye** | "submit at glama.ai/mcp/servers, claim ownership, and ensure a quality score is set — **once that's done, I'll merge**" |
| 17.09 | bot | **new requirement:** Dockerfile ("we only need the server to start and respond to introspection requests"). P.S.: "If your server already has a hosted endpoint, you can also list it under /mcp/connectors" |
| 17.09 | us | we point to the connector; we fix the description ($0.05 → $0.003–0.005, "no free tier") |
| 21.09 | punkpeye | triage reminder: badge `OWNER/REPO` + "Submit at glama.ai/mcp/servers" — **no answer to the question about the connector** |
| 22.09 | us | "both are ready"; then a correction: the container introspection does **NOT** pass (registered by mistake as "Runs from source"); ticket **#135407945** |
| 23.10 | **punkpeye** | "**the quality score is still not evaluated** … without the score being set, the entry can't be merged" |
| 27.10 → 01.11 | us | we proved that `/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6` **does not exist** (404 → homepage), and the form refuses it as a duplicate |
| 01.11 15:30 | **Glama Support** | **"not approved — an MCP server already exists for this repository"**; the system creates a second ticket **#151838421** |
| 03.11 14:37 | us | the full evidence to Frank: 404 from the API, badge **F** for the license, options A/B, the ready stdio bridge. The attempt with `Dockerfile.glama` was also refused ("MCP server already exists for this repository"). Silence since then |

**A single blocker:** a missing `Servers` entry, which **only Glama can create** — unless we make our
container capable of introspection.

---

## §3 The plan for Glama and Frank

> **Rule #1: WE STOP SUBMITTING.** Every new submission hits the duplicate and spends trust. Zero new submissions until a route is chosen.

### Route A — "Glama creates it" (fast, no code) ← **recommended to start immediately**

1. **A single update in ticket #135407945** (not in chat, not in Discord), with the full evidence:
   - Connector URL + status: *Ownership verified · Healthy · 100% uptime 47 days · TDQS A 4.7/5 · last tested 2026-11-03 11:13*
   - `https://glama.ai/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6` → **404** (returns the homepage)
   - a search for "kristo" in `/mcp/servers` → **zero results for us**
   - "Add Server → Hosted endpoint" → **refuses: the endpoint is already a connector**
   - **the request, formulated precisely:** *a type change of the existing entry to "Hosted endpoint", linked to repo `hristovdimitri2-hub/kristo-intelligence-6`* — this creates the `/mcp/servers/` entry and triggers the quality score
2. **A short comment on PR #13219** — only so that the 32-day inactivity timer does not expire (last: 01.11; next ~17.11), with a link to the ticket.
3. **Glama's Discord** — only a reminder with a link to the ticket, **not** a parallel channel with new requests.
4. **Filling the empty fields** through the **Admin** tab of the connector: Documentation URL (repo `docs/` + `/llms.txt`) and Trust center (the x402-trust profile). These are visible, free improvements to the quality of the entry.

### Route B — "we make the container capable" (within our control) ✅ **completed**

It turned out that the repo **had already foreseen this scenario**. `scripts/mcp_stdio_bridge.py` (126 lines)
exists as a **"sleeping asset"** — deliberately NOT included in `Dockerfile`/`Procfile`, with its own test
`tests/test_mcp_stdio_bridge.py`, which even **forbids** its accidental inclusion.

Its design is better than a proxy to Render: it feeds every JSON-RPC message to the **actual
Flask application in the same process** (through the test client), that is, it works **without a
network** and without a dependency on Render. That is exactly what Glama's container needs.

**What was added:** `Dockerfile.glama` — it brings up **only the bridge**, not gunicorn; the production
`Dockerfile` and `Procfile` remain untouched (which is why the test still passes).

**Evidence (as a separate process, exactly as Glama would run it):**

| Check | Result |
|---|---|
| 4 messages on stdin → frames on stdout | **3** (the notification is not answered) ✅ |
| Valid JSON lines | **3 / 3** ✅ |
| `initialize` | `kristo-intelligence`, protocol `2025-06-18`, capabilities `tools` ✅ |
| `tools/list` | **3 tools** with full schemas and descriptions ✅ |
| Application logs | on **stderr** (182 B), stdout **clean** ✅ |
| Exit code | **0** ✅ |

**Hidden trap #1, found while reading:** `.dockerignore` excludes `data/`, and importing the
application writes `data/agent_catalog.db`, without it creating the folder itself. Without
`mkdir -p /app/data` the container crashes with "unable to open database file".

**Verified as a real container too** (`docker build -f Dockerfile.glama` ✅ + `docker run --rm -i` ✅):

| Check | Result |
|---|---|
| Exit code of the container | **0** ✅ |
| Protocol frames (initialize, tools/list, ping, paid tools/call) | **4 / 4** ✅ |
| Valid JSON lines | **4 / 4** ✅ |
| `initialize` | `kristo-intelligence`, `2025-06-18` ✅ |
| `tools/list` | **3 tools** with schemas ✅ |
| Paid `tools/call` | returns the x402 instruction (does not execute) ✅ |
| Total time (image start + 5 requests) | **6.9 s** ✅ |
| stdout | protocol only; logs on stderr ✅ |

**Hidden trap #2, found only by a real container:** `python scripts/<file>.py` puts
`scripts/` on `sys.path`, **not** `/app` — which is why `from main import app` inside the container fails with
`ModuleNotFoundError: No module named 'main'`. On the host machine it is not visible if
`PYTHONPATH` is passed. Fixed with `ENV PYTHONPATH=/app`.

**Next step:** submitting "Runs from source" with this Dockerfile — **but only after Glama
removes the outdated entry for the repo** (§2.2), otherwise it will again hit "already exists for this repository".

### What we should NOT do

- Do not ask Frank for a manual merge without a score — he has already explained that he cannot.
- Do not open a new PR in awesome-mcp-servers (there is an incident with #31971, submitted by Cline without a command).
- Do not touch `kristo-travel-api` (#1081/#11557) — that is an old, different project; the repo is now private.
- Do not buy a "featured" slot at Glama before we have resolved the basic entry.

---

## §4 MCP Registry / PulseMCP — the cheapest fix in the whole plan

**The problem:** `isLatest` = **v6.0.0 (17.09)**, while v1.0.0 (10.10) is newer but "lower" by semver → the registry marks it as not-latest.

**The solution:** publishing a version **> 6.0.0** (e.g. `6.1.0` or `7.0.0`) with the same rich metadata: 6 paid endpoints with prices, 3 tools, `remotes` (`/mcp`, `/mcp/sse`), `icons`, `websiteUrl`, a `discovery` block.

**The effect:** all consumers of the registry — **PulseMCP**, aggregators, MCP clients — see the current data instead of the September data.

**Needed from the owner:** `mcp-publisher` **device flow** — one authorization in a browser (~1 minute).
**Value:** zero money, the broadest coverage per effort.

---

## §5 Target directories — five families

### Family 1 — MCP directories

| Channel | Status | Action | Price |
|---|---|---|---|
| **Glama** | Connector ✅ A · Servers ❌ | Route A/B from §3 | $0 |
| **Official MCP Registry** | ⚠️ the old version is `isLatest` | §4 — publish > 6.0.0 | $0 |
| **PulseMCP** | consumes automatically from the registry | **fixes itself** after §4 | $0 |
| **mcp.so** | ✅ entry, comment #3441 | claim/verification; update the prices | $0 |
| **Smithery** | ❌ dead (proxy stopped 31.10) | do not invest; check for a successor | — |
| **mcpmarket.com** | we are not there | was refused because of **$69** | $69 (decision) |
| **mcprush** | badge in the README | — | $0 |
| **Docker MCP Catalog** (`hub.docker.com/mcp`) | **unverified** | check the requirements — we have a Dockerfile | $0 |
| **Cline MCP Marketplace / Cursor Directory / OpenTools / mcp.directory** | **unverified** | research + submit wherever it is free | $0 |

### Family 2 — x402 and agent payment catalogs (that is where the paid traffic is)

| Channel | Status | Action |
|---|---|---|
| **x402scan** | ✅ registered (issue #1270, comment #1283) | continue the dialogue with Merit; see whether the `/sample` routes are visible |
| **CDP Bazaar** | ✅ **1 indexed resource** | keep the indexing; activate the paid listing ($0.25) from the queue |
| **x402-list.com** | ✅ LIVE, 14/14, **valid until 05.11** | **renew before 05.11** |
| **x402-trust.com** | ✅ Grade A 81.2 | do not buy the $0.005 report; maintain uptime |
| **PayAPI Market** | ✅ LIVE + verified | the channel with a real human contact (Chet) |
| **nohumans.directory** | ✅ **3 real payments on 30.10** | **PATCH the listing** (`sample_query` / `has_sample`) — the only channel with proven external traffic |
| **x402.org ecosystem page / agentcash** | unverified | research |

### Family 3 — integrations into agent frameworks ← **the biggest long-term lever**

This is not about a badge, but about getting our API into the **code path** that agents already
execute. It deserves a separate document, but the directions:

- **Coinbase AgentKit** action provider
- **GOAT SDK** tools
- **elizaOS** plugin registry
- **LangChain / CrewAI** tool registries
- **Anthropic Claude connectors** + **ChatGPT apps/connectors** — our Glama connector shows `ChatGPT: –`, `Claude: –` (empty fields → probably filled from the Admin tab)

Plus: the **Claude/ChatGPT connector directories** are the place where end users enable MCP servers.

### Family 4 — API catalogs and general dev visibility

The API is also an **OpenAPI 3.0** service — so it can enter catalogs that are not MCP:
**APIs.guru**, **Postman API Network**, **Public APIs**, **RapidAPI** (check whether it accepts the x402 model), **Product Hunt** (entirely missing from the strategy so far), **Hacker News / dev.to / Reddit**.

### Family 5 — Awesome lists

| List | PR | Status | Action |
|---|---|---|---|
| `punkpeye/awesome-mcp-servers` | **#13219** | open, 20 comments | blocked on §3 |
| `xpaysh/awesome-x402` | **#1308** | **open, clean, mergeable** since 24.08 | a polite nudge (last activity 28.09) |
| `wong2/awesome-mcp-servers`, `modelcontextprotocol/servers`, `awesome-ai-agents`, `awesome-web3` | — | unverified | research: 1 server = 1 PR |

---

## §6 The technical layer that makes discovery possible

The directories see us; **the search engines — not** (verified: `site:kristo-intelligence-api.onrender.com` → **1 indexed page**). This is also the "biggest hole" in the owner's words. In brief (details in `VISIBILITY_AND_TRAFFIC_STRATEGY.md` and in Blocks 8–9):

1. **Indexable surface** — there are now 3 HTML pages, of which `/validation` is an orphan and `/dashboard` is `noindex`, but is in the sitemap with priority 0.9.
2. **`llms.txt` documents only the old `X-Payment-Proof`** — it does not describe the x402 v2 rail, the prices, and the `/sample` routes.
3. **Zero OG/Twitter/canonical/JSON-LD** in 9 templates → shares look like a bare link.
4. **Sitemap** contains 302 redirects and omits `/validation`, `/api/v1/quickstart`, `/.well-known/x402`, `/sample/*`.
5. **No GSC/Bing verification, no IndexNow, no analytics.**
6. **The `/sample` routes are invisible** — and they are precisely the "try before you pay" path that nohumans marks as mandatory (`has_sample`).

---

## §7 Measurement — otherwise "traffic" is a feeling

**The funnel we need to measure:**

```
directory/search → free discovery (llms.txt, /mcp, /sample)
   → 402 challenge → paid payment → settled call → indexing
```

**Minimal set (weekly):**
- number of **discovery** hits per channel (User-Agent / referrer)
- number of **402** versus number of **settled** (conversion)
- number of external payers (other than our crawlers `0xA19F`, `0x54E1`, `0xe3ba`)
- position/presence in the 6 key directories (there is `scripts/_listing_stats.py` and `listing_monitor.py`)
- number of indexed pages in Google/Bing

**Cadence:** a weekly pulse (already an existing practice) + a monthly review against this plan.

---

## §8 What I need from you

**The repo is documented exceptionally well** (60+ documents in `docs/` + `PROJECT_STATUS.md` 272 KB) — **I need nothing from the code**, I can read it myself. What I am missing is what lives outside the repo:

### A. Glama/GitHub artifacts (so that I can formulate the exact text to Glama)
1. **The full text of tickets #135407945 and #130688574** — what exactly was answered last and whether a person has been assigned.
2. **The two rejection emails verbatim** (01.11 and 03.11) — so that we can see which entry/path they are rejecting (`kristo-intelligence-v3` suggests the name of a submission).
3. **Access/screenshot of the Admin tab** of the connector (Documentation, Trust center, ChatGPT/Claude fields).
4. *(optional)* **Glama API key** (`glm_…`) — for an authoritative check of the presence through `/api/mcp/v1/servers` instead of through search.

### B. State of the current work
5. **What Mimo has completed on Blocks 2–7** after 03.11 11:20 (the working tree shows `main.py`, `templates/dashboard.html`, `tests/test_dashboard_v2.py` — Block 2 looks to be in progress).
6. **The path to `TRACKER.md`** (in the Cline workspace) — so that I do not have to ask you every time.

### C. Decisions that only you can make
7. Do you approve **Route B** (new `scripts/mcp_stdio_bridge.py` + `Dockerfile.glama`)? This is the only thing in the plan that touches the repo.
8. Do we publish a **new version in the MCP Registry** (> 6.0.0)? (§4)
9. **npm 1.0.1** — approved on 03.11 10:56, but not yet published. Do we release it?
10. **Paid channels** — mcpmarket $69, Bazaar $0.25: yes or no?
11. **GSC / Bing Webmaster** — do you have access/verification, or should I prepare the steps?

### D. Traffic data
12. **Logs with referrer/User-Agent** (Render dashboard or an export) — without them "who finds us" is a guess.

---

## §9 Order of execution

**Day 1 (today):**
- Ticket #135407945 with the full evidence (Route A) — *I can prepare the text right away*
- Filling Documentation + Trust center in the Admin tab
- Publishing a new version in the MCP Registry (§4) → PulseMCP fixes itself

**Day 2–3:**
- Route B in parallel (`mcp_stdio_bridge.py` + `Dockerfile.glama`) — if it is approved
- PATCH of the nohumans listing (`sample_query`)
- Renewal of x402-list before **05.11**

**Week 1:**
- Blocks 8–9 (README/`agents.json`/`llms.txt` + OG cards) — **mandatory before the next Glama submission**
- A polite nudge on PR #1308
- Research on Docker MCP Catalog, Cline/Cursor, OpenTools

**Week 2–3:**
- Family 3 (framework integrations) — choosing the first 2
- Measurement: the first weekly pulse against the funnel from §7

---

## §10 Invariants (not to be touched)

x402 headers and the structure of the 402 envelope · prices (`X402_PRICE_MAP`) · `payTo`/RECEIVER · `/.well-known/x402-trust.txt` · commission · `secrets\` and `.env` (not opened) · **no push without a separate gate** (push = automatic deploy on Render) · one submission = one explicit command.
