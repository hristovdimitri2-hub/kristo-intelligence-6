# VISIBILITY & TRAFFIC STRATEGY — kristo-intelligence-6

**Analysis date:** 2026-11-03 · **Time:** 12:20–12:40 (Europe/Sofia) · **HEAD:** `66a0ce4` (2026-11-02)
**Target:** `https://kristo-intelligence-api.onrender.com` · `https://github.com/hristovdimitri2-hub/kristo-intelligence-6`
**Document type:** diagnosis + distribution plan. **Read-only** — not a single file of code, x402 headers,
prices, `payTo`, protected configs or `secrets/` was changed. No `git add/commit/push`. Every step below is a
**proposed action**, not a change that has been made.

> **Why this is a separate document from the technical audit:** the audit answered "is the software stable".
> This document answers "is it visible and does it sell". The conclusion is that the problem **is not a lack of
> channels** — it is that there are many channels, almost none is carried to completion, none is measurable, and
> the machine-readable specs that aggregators actually read contain wrong data.

---

## 0. Executive summary (read only this if you have 2 minutes)

**The platform is technically stable and already "found" — but only by machines that do not buy.**

The claims "zero visibility" and "we are not in the catalogs" are **partially false**. Verified live on 03.11:

| Fact | Evidence |
|---|---|
| There is a real, indexed web presence | DuckDuckGo `site:` returns **1 page** (the landing page), with an accurately extracted meta description |
| There is a listing on mcp.so | `mcp.so/servers/kristo-intelligence` is live (but "Authentication: not confirmed" and stale metadata) |
| There is an entry in the official MCP Registry | 2 entries, `isLatest` = version 6.0.0 |
| There is a published npm package | `kristo-x402-client@1.0.0`, **37 downloads** over the last 30 days (peak 119 on the day of publication) |
| BuiltWith has indexed our MCP tools | 3 separate tool pages (`get_market_stats`, `get_onchain_sales`, …) |
| There is 1 confirmed merge into an awesome list | `awesome-remote-mcp-servers` PR #10 |
| There is **real** paid traffic from an external source | `nohumans.directory` → 3 × $0.005 from `nohumans-scout` on 30.10 |

**The real diagnosis:** the software is invisible to **buyers**, because:

1. **The paid product is free** at two other entry points — three of the six SKUs are obtained for $0 (see the
   technical audit, F-01/F-02). Anyone who finds us has no reason to pay.
2. **The machine-readable specs lie** — `.well-known/x402` advertises 6 endpoints, `agents.json` — 5 (the
   `/api/v1/whaleflow` is missing), the README — "11 resources", the code — 6. An aggregator that crawls us
   gets contradictory data and/or drops out at validation.
3. **There is not a single measurable channel** — zero third-party analytics in the entire codebase;
   `/f/<channel>` exists, but **zero** published links use it. After ~350 commits nobody can say which channel
   brought a buyer.
4. **The commercial path is blocked by perfectionism** — 10 ready outreach messages sit under embargo because of
   "PR #13219 merged AND F1 gate", and F1 is just a funded demo wallet. The strongest asset (ready copy) has
   not been used for months.
5. **The best channel is underrated** — the only confirmed external paid traffic comes from an **agent-facing
   directory**, while the effort is thrown into human channels (Reddit/HN/Product Hunt) that have never been
   used.
6. **There is no Open Graph / Twitter Card / canonical / JSON-LD in any of the 9 templates** — every share on
   X/Discord/Reddit/Telegram renders as a bare URL. This kills CTR before it has even started.
7. **The market is microscopic** (self-measured: the leader in PayAPI makes ~$1.2/month; 2–4 buyers). Traffic
   by itself solves nothing — you need **the exact small amount** of traffic: agents and operators who pay.

**A realistic goal for 90 days:** not "mass traffic", but **10 external payers**, **3 confirmed listings in
directories that agents read**, **1 organic page in the top 50 for a long-tail query** and **full attribution**
for every dollar. This is achievable with ~20–30 hours of work and almost zero budget.

---

## 1. Methodology and scope of the verification

### 1.1 What was verified live (03.11.2026)

| Check | Tool | Result |
|---|---|---|
| GitHub metadata | `api.github.com/repos/...` | 2 stars, 0 forks, 0 issues, 10 topics, MIT, homepage set, **no** Pages/Wiki/Discussions/Releases, 351 commits, created 19.08.2026 |
| `robots.txt` | HTTP GET | `Allow: /`, `Disallow: /api/admin/`, `Sitemap:` — **ok** |
| `sitemap.xml` | HTTP GET | 11 URLs, **no `lastmod`**, includes `/dashboard`, `/nexus`, `/launch` |
| `llms.txt` | HTTP GET | Live; **documents only the legacy `X-Payment-Proof` rail** |
| `/` (landing) | HTTP GET | Has `<title>`, `<meta description>`, `<h1>`; **no OG/Twitter/canonical/JSON-LD** |
| 6 `/sample` routes | HTTP GET | Return a real JSON schema example (`/api/v1/signal/sample` = 200, ~600 B) |
| `.well-known/x402` | HTTP GET | 6 resources; mentions both `X-PAYMENT` (v2) and `X-Payment-Proof` |
| `agents.json` | HTTP GET | **5 endpoints** (without whaleflow); `free_tier_limit: 0`; `monthly_vip_usdc: 29.0` |
| `README.md` | local file | "11 resources on x402scan" (:112), "zero payment incidents" (:111), "Rug-risk checks" (:21) — **false/unproven** |
| `templates/*.html` | grep | **0 matches** for `og:`, `twitter:`, `canonical`, `application/ld+json` |
| npm downloads | `api.npmjs.org` | **37** over 30 days (04.10–02.11); peak **119** on 25.08; then 0–5/day |
| npm registry | `registry.npmjs.org` | The package exists; the README inside says "$0.05", "1 free call", "$29 VIP" — **all stale** |
| MCP Registry | `registry.modelcontextprotocol.io` | 2 entries; `isLatest` = 6.0.0; **active** |
| mcp.so | HTTP GET | Listing live; "Authentication: not confirmed"; description "whale-wallet signals" (old positioning) |
| CDP Bazaar | `api.cdp.coinbase.com/.../resources` | First page: **46 resource entries, 12 providers**; **no** kristo/onrender/our `payTo` |
| Search engine | DuckDuckGo `site:` | **1 result** (only the landing page); "No more results found" |
| BuiltWith | DDG result | 3 MCP tool pages with our tools → **crawlers do find us** |
| Smithery | HTTP GET | Listing **404**; the Smithery proxy is stopped 31.10.2026 |
| Glama API | HTTP GET | `401` — requires an API key; cannot be checked programmatically without a key |

### 1.2 What was NOT verified (and why)

- **Google Search Console / Bing Webmaster** — no access; indexing was measured only indirectly through
  DuckDuckGo (a different index from Google).
- **The full CDP Bazaar catalog** — the API returns a paginated list; only the first page was checked
  (~100 KB, 46 entries). Its absence there **does not prove** absence in the whole catalog.
- **The Glama server entry** — the documentation says "deleted", the live badge says "claimed, rated A".
  Ambiguous; it requires an API key for a definitive check.
- **Real sales and traffic in production** — no access to Render logs, database or metrics. All traffic numbers
  come from `docs/TRAFFIC_AUDIT.md` (11.09) and from the code.
- **Paid testing of the x402 path** — not performed (it requires a wallet with real USDC); the analysis is
  static + documentary.

> **Reading rule:** the document marks `[VERIFIED]` (I checked it live/in the code), `[DOCUMENTED]` (it comes
> from a document in the repo, without independent verification) and `[UNVERIFIED]` (I could not confirm it).

---

## 2. Diagnosis: why the platform is invisible

### 2.1 Search engines — technical readiness exists, but almost zero content to index

**What works `[VERIFIED]`:**
- `robots.txt` is correct and even hints at the sitemap.
- `sitemap.xml` is valid and is served with the correct Content-Type.
- The landing page has `<title>`, `<meta name="description">` and `<h1>` — that is, it is **not** an "empty"
  page.
- There are 6 free `/sample` routes that return a real sample JSON — potentially indexable content.
- BuiltWith has managed to crawl the MCP endpoint and has created tool pages → **the server's crawlability is
  not the problem**.

**What is missing `[VERIFIED]`:**
1. **Zero Open Graph / Twitter Card / canonical / JSON-LD** in all 9 templates (`grep` = 0 matches). Every
   share on X, Discord, Reddit, Telegram, LinkedIn shows a bare URL with no title, description or image. This
   is the cheapest and most impactful SEO/social fix.
2. **There is not a single HTML page with content.** The whole product is JSON + one landing. There is no
   `/pricing`, `/docs`, `/api-reference`, `/how-it-works`, `/blog`, `/status`, `/use-cases`, `/compare`. The
   search engine has only 1 URL to index.
3. **The paid routes return 402 to a crawler** — that is correct for a paywall, but it means the 6 "product"
   pages are **unindexable by definition**. The whole SEO potential has to come from the free surfaces
   (landing, `/dashboard`, `/agents`, `/launch`, `/llms.txt`, `/openapi.json`), and they are either internal or
   in Bulgarian.
4. **A subdomain of `onrender.com` instead of a domain of your own** — weak brand reputation, a domain shared
   with free/spam sites, no brand search, no email domain for outreach.
5. **Sitemap without `lastmod`** and with priority 0.9 for `/dashboard` (an operational dashboard, not a
   marketing page) — it dilutes crawl budget.
6. **Mixed language:** `/dashboard` has a Bulgarian title ("Operations dashboard"), `/launch` is an entirely
   Bulgarian VIP page for traders — **another product, another ICP** — while the landing is in English for
   agents. The crawler sees three unrelated offers on one domain.
7. **No GSC/Bing verification** — `MARKETING_KIT.md:127-128` lists them as "⬜ manual"; zero meta verification
   tags, zero `google-site-verification` file.

**Effect:** `site:kristo-intelligence-api.onrender.com` returns **1 result** `[VERIFIED]`. That is, of the 11
URLs in the sitemap, 1 is indexed. Even assuming Google is more favourable than DuckDuckGo, the lack of content
and of internal links makes realistic indexing single-digit.

### 2.2 Aggregators and the x402 ecosystem — we are listed where nobody buys

| Channel | State | Evidence |
|---|---|---|
| **CDP Bazaar** (Coinbase — the main x402 index) | **Unconfirmed presence** | `[VERIFIED]` first page of `/platform/v2/x402/discovery/resources` = 46 entries, 12 providers; our `payTo` is missing. `[DOCUMENTED]` 15.09: the index had 16 035 entries and **0 of ours** (`AP2_RADAR.md:89`). The listing trigger commit is only from 02.11 (`66a0ce4`) |
| **x402scan** | **Unconfirmed** | `[DOCUMENTED]` "11 resources, 0 errors" (`DISTRIBUTION_STATUS.md:11,62`), but `AP2_RADAR.md:90` (15.09) says "origin page exists, **0 resources shown**". Registration requires a SIWX signature (`AP2_RADAR.md:93`) |
| **PayAPI Market** | **LIVE** | `[DOCUMENTED]` blurb accepted 03.09 19:29 UTC; band=established 69.7; **but** "PayAPI has no automatic recrawl" (`PROJECT_STATUS.md:599`) → the ranking is frozen on old copy |
| **mcp.so** | **LIVE, but weak** | `[VERIFIED]` the page exists; "Authentication: not confirmed"; the description is old ("whale-wallet signals") |
| **MCP Registry** | **LIVE** | `[VERIFIED]` 2 entries, `isLatest` 6.0.0 — but this is an index, not a storefront; buyers do not browse it |
| **Glama (connector)** | **LIVE** | `[DOCUMENTED]` claimed, TDQS 4.7, 3 tools, lastTested 22.09 |
| **Glama (servers dir)** | **AMBIGUOUS** | `[DOCUMENTED]` the entry is "deleted" at "FIXED" on 23.09 (`PROJECT_STATUS.md:496-501`); `[VERIFIED]` the live badge claims "claimed, rated A" |
| **Smithery** | **DEAD** | `[VERIFIED]` listing URL → **HTTP 404**; the Smithery proxy is stopped 31.10.2026 |
| **PulseMCP** | **MISSING** | `[DOCUMENTED]` "submissions temporarily paused" since 03.09 (`PROJECT_STATUS.md:2438`); 17.09 check "we are NOT there"; `[UNVERIFIED]` 03.11 → Cloudflare 403 |
| **nohumans.directory** | **LIVE AND WORKING** | `[DOCUMENTED]` 3× verified; **real paid traffic 3 × 0.005 USDC on 30.10** (`discovery.py:340-342`) |
| **x402 Trust** | **LIVE** | `[DOCUMENTED]` profile `/endpoint/139372`, **grade B, "proceed"** |
| **mcprush** | **PRESUMED** | `[VERIFIED]` badge in `README.md:4`; `[DOCUMENTED]` no submission record in the repo |

**The conclusion about aggregators:** we are present in 6+ catalogs, but **not one of them is the place where
an agent makes a purchase decision**. The aggregators that actually lead to payment (CDP Bazaar → x402scan;
nohumans.directory) are exactly the ones that are unconfirmed or only just triggered.

### 2.3 MCP directories — 3 tools, but diverging names

- `[VERIFIED]` the MCP server is real: 3 tools (`get_market_stats`, `get_onchain_sales`, `get_bot_status`) in
  `app/blueprints/discovery.py:522/541/561`, exposed through `/mcp` (streamable HTTP) and `/mcp/sse`.
- `[DOCUMENTED]` The second catalog in `discovery.py:1061-1110` calls the same tool **`get_sales_history`**
  instead of `get_onchain_sales` — a divergence that confuses both an agent and a catalog.
- `[VERIFIED]` `/mcp/sse` **is not in sitemap.xml** and is not mentioned in `llms.txt`; `/mcp` either.
- `[VERIFIED]` `server.json` is correct per the MCP Registry schema
  (`io.github.hristovdimitri2-hub/kristo-intelligence`, v6.0.0, two remotes) — this is the strongest
  machine-readable asset we have.

### 2.4 Developers — almost no trace of human activity

`[VERIFIED]` 2 stars, 0 forks, 0 open issues, 0 releases, 0 discussions, 0 PRs in the repo. **There is no
`.github/` directory** → no CI badge, no issue/PR templates, no social preview, no dependabot, no
SECURITY.md/CHANGELOG.md/CONTRIBUTING.md. There is no `CHANGELOG`, no release with notes.

`[VERIFIED]` the npm package has **37 downloads/month** and **119 on the day of publication** — that is,
almost the entire volume is from the publication itself and from our own checks, not from organic interest.
The package **is not advertised anywhere** except in the README and the landing page; the README inside the
package contains stale prices ($0.05 instead of $0.003–0.005, "1 free call" when the production free tier is
0) — anyone who installs it gets wrong information.

`[VERIFIED]` the repo README is 136 lines and starts with two badges and a long list — there is no
screenshot/GIF of the demo in the first 10 lines, no "one-command" block before the middle.

### 2.5 Lack of attribution — there is no way to tell which channel works

`[DOCUMENTED]`:
- The `/f/<channel>` attribution hop has existed since 03.09 (`main.py:2242-2252`), but **grep across the whole
  repo: zero published links use it**. Channel attribution is empty by construction.
- **Zero third-party analytics**: grep for
  `umami|plausible|googletagmanager|gtag(|analytics.js|matomo|posthog|mixpanel|segment` in all `*.py` and
  `*.html` → **0 matches**.
- UTM fields exist only in the legacy VIP/Stripe CRM table (`main.py:4259-4261, 5234-5236`;
  `integrations/crm_store.py:27-29`), not in the x402 API.
- The only real measurements: persistent `request_log` in Postgres (`main.py:2208-2216`), the
  `/api/dashboard/data` requests section (`main.py:5454-5470`) and on-chain truth (`payment_guards`,
  `onchain_sales`, `external_payers`).
- `docs/TRAFFIC_AUDIT.md` (11.09): 13 792 requests/day, but `/health` = 42 097 is **our own keep-alive
  noise**; "402 challenges → paid: **1 → 0**"; "Today 100% of the traffic is indexers, monitoring and our own
  keep-alive noise" (`:58-61`). Two hits from `ClaudeBot/1.0`.

### 2.6 The human channels are blocked by perfectionism

`[DOCUMENTED]` `docs/OUTREACH_WAVE1.md:3-4` holds 10 ready messages under embargo because of "PR #13219
merged AND F1 gate closed". F1 is a "funded demo wallet" — one human decision for a few dollars. Result: the
Reddit, HN, Product Hunt, dev.to, Discord posts are written and **never published**, while the market is
~$1.2/month.

### 2.7 The market is microscopic — this changes the whole strategy

`[DOCUMENTED]` `PROJECT_STATUS.md:50-54`: "The real reasons payments 'stop' are a microscopic market (2–4
buyers) + zero outreach — not a technical failure". `PROJECT_STATUS.md:2596`: "the PayAPI leader makes
~$1.2/MONTH … we are all at zero". `docs/MARKET_WRITEUP.md:40-52` gives the methodology for this measurement.

**Consequence:** a "mass traffic" strategy is the wrong frame. The right goal is **to be found by the few
agents/operators who buy**, and to have a verifiable trace for every dollar. That is why the priority is
machine-readable surfaces + attribution, not viral campaigns.

---

## 3. Distribution and listing strategy

### 3.1 Principles (so that the past does not repeat itself)

1. **One channel = one completed task.** Do not open a second PR until the first is closed/merged.
2. **No listing without machine-readable correctness.** First fix `agents.json`, `llms.txt`,
   `.well-known/x402`, `server.json` — then submit.
3. **Every public link goes through `/f/<channel>`.** Otherwise the channel is invisible forever.
4. **No listing without an internal check:** a validator that confirms the endpoint returns 402 with a correct
   challenge.
5. **Do not repeat a rejected request without removing the cause.** #11557 died because of a missing Glama
   quality score; #13219 was opened **before** the score existed and died by the same rule.
6. **Do not record success before you have verified it.** "Smithery PUBLISHED 30.09" is a 404 today. "#12799
   Open" was closed on 29.08. The documents are already a liability, not an asset.

### 3.2 Prioritized channels (Tier 1 = makes money / indexes)

#### TIER 1 — High priority. They make money or they index for agents.

| # | Channel | What exactly to do | Expected effect | Effort | Risk |
|---|---|---|---|---|---|
| 1 | **CDP Bazaar → x402scan** | 1) Confirm that `/api/stats` returns a valid v2 challenge with `extensions` echo (the commit from 02.11 triggers it). 2) Wait for the crawl (the index is pull-based). 3) If after 7 days there is no entry — open Listing Request #1270 with the ready text from `SCAN_LISTING_EN.md`. 4) Check the presence with a script (Appendix B.1) | **Highest.** This is the index that x402scan and most x402 agents read | 2–3 h + 7 days of waiting | Low |
| 2 | **nohumans.directory** | It already works. Keep the listing, add `/f/nohumans` to the URL in the profile and check whether the scout pays again. Do not touch anything else | Confirmed paid traffic | 30 min | Low |
| 3 | **Glama connector** | It is live. Add `/f/glama` to the connector URL/description if the field allows it; keep `lastTested` fresh | Indexed MCP client | 20 min | Low |
| 4 | **Glama servers dir** | 1) Fix the cause: the license is "F" because after the MIT text there is an added "COMMERCIAL USE NOTICE" after `---` (`PROJECT_STATUS.md:576-579`) → remove it from `LICENSE` (or put it in a separate file). 2) Make sure it is registered as a **Hosted endpoint**, not "Runs from source". 3) Submit again with a full README. 4) Do not open a new ticket while the old one (#135407945) is not closed | Restoring the #1 position for "defi" | 3–4 h | Medium (depends on Glama) |
| 5 | **mcp.so** | 1) Claim the listing (the "Claim" button is on the page). 2) Update the description from "whale-wallet signals" to the current positioning (6 routes, x402, no signup). 3) Fill in "Authentication: x402 pay-per-call" instead of "not confirmed" | Fixes the most visible MCP listing | 30 min | Low |
| 6 | **x402 Trust** | Live, grade B. Submit again for re-evaluation **after** you fix the metadata divergences (see §4) — the grade is affected by them | A higher trust tier | 1 h | Low |
| 7 | **PayAPI Market** | 1) Pay for/request a recrawl (the listing is frozen on old copy, `PROJECT_STATUS.md:599`). 2) Add `/f/payapi` to the URL. 3) Send 1 new canary settlement to bring the "settlement-verified" badge up to date | Restores "settlement-verified" trust | 1–2 h | Low |

#### TIER 2 — Medium. Low effort, but they require something first.

| # | Channel | Precondition | Steps | Effort |
|---|---|---|---|---|
| 8 | **PulseMCP** | They are waiting to open (paused since 03.09). The ready package is in `PULSEMCP_SUBMISSION_READY.md` | 1) Set up a watcher (Appendix B.2) that checks `/submit` for a 200 and a text change. 2) When they open — submit the ready package **after** removing the "1 free call"/"$0.05" phantoms (`:101-102`) | 1 h + waiting |
| 9 | **awesome-x402** PR #1308 | Open since 24.08, zero comments, deadline 08.10 has passed | 1) Comment a polite nudge with 1 sentence and a link to `/llms.txt`. 2) If there is no answer within 14 days — close it yourself and open a new PR with **one** added device | 30 min |
| 10 | **awesome-mcp-servers** PR #13219 | Open, labels `has-emoji`/`valid-name`/`has-glama`, rebased 22.09, deadline 01.10 passed | 1) Nudge comment. 2) Make sure the Glama score exists (otherwise it will die again by the 32-day rule) | 30 min |
| 11 | **mcprush** | Badge in the README, but there is no submission record | 1) Check whether the listing is real (fetch the badge URL). 2) If not — submit; if yes — add `/f/mcprush` | 20 min |
| 12 | **MCP Registry** | Already active | 1) Publish `server.json` v6.0.0 with **current** descriptions (they are ok now, but check whether `paid_endpoints` match the 6). 2) Add `websiteUrl` (it is there) | 20 min |

#### TIER 3 — Low/Medium. Human channels — only after there is something to show.

| # | Channel | Condition | Note |
|---|---|---|---|
| 13 | **Product Hunt** | Requires ≥3 social proof points (`VISIBILITY_PLAN.md:88`) | Launch **after** the 3 external payers/listing. Otherwise it will be a quiet failure |
| 14 | **Show HN** | Requires "something new and interesting" | The best angle: "An API that pays for itself with x402 — no keys". Publish **after** the landing has an OG card |
| 15 | **dev.to article** | Ready text in `CONTENT_PACK_1.md` §A | Publish **after** removing the "free tier" contradiction (`:23-30` vs `:82`) |
| 16 | **Reddit** (r/LocalLLaMA, r/LangChain, r/Base, r/mcp, r/AI_Agents) | Ready texts in `OUTREACH_WAVE1.md` §3.1/3.3 | **Only** as an answer to a real question, not as a new post. Otherwise it is spam and you will be banned |
| 17 | **X/Twitter** | 6-tweet thread in `CONTENT_PACK_1.md` §B | The owner has declared it a "dead channel", but 1 post with a video exists. Post **only** with an OG card + `/f/x` link |
| 18 | **Discord** (CDP #agentkit, Base #developers) | Ready texts in `OUTREACH_WAVE1.md` §1.1/1.3 | One post per community, no cross-post. Best angle: a technical note about the Bazaar listing |

### 3.3 Presence automation (concrete)

**A. Presence check script** (`scripts/distribution/check_presence.py`, ~120 lines):
- Reads a list of URLs/APIs (CDP Bazaar, MCP Registry, mcp.so, Glama API, x402scan) and for each returns:
  `present: true/false`, `last_seen`, `metadata_match: true/false`.
- Writes `docs/distribution_state.json` — **one** source of truth instead of 8 scattered documents.
- Runs from a GitHub Action every Monday 08:00 UTC; on a change → opens an issue "Distribution drift
  detected".

**B. Sitemap/IndexNow ping** (`scripts/seo/ping_index.py`):
- `POST` to IndexNow (`https://api.indexnow.org/indexnow`) with a key that is served at `/<key>.txt`.
- Ping Google/Bing sitemap only after `sitemap.xml` gets a `lastmod`.
- Note: IndexNow requires a domain of your own; on `onrender.com` it may not be accepted → the precondition is
  a custom domain (§5, L1).

**C. Channel attribution:**
- All public links go through `/f/<channel>` (it already exists, `main.py:2242-2252`) — e.g. `https://…/f/x`,
  `/f/discord`, `/f/reddit`, `/f/ph`, `/f/mcpso`.
- Every listing field that allows a URL (Glama, mcp.so, PayAPI, nohumans) gets the `/f/<channel>` variant.
- **Without this, step 4 of the principles is unachievable.**

**D. UTM for email/direct:** `?utm_source=…&utm_medium=…&utm_campaign=…` — the code already reads
`referer`/`funnel`; the UTM fields are only in the CRM, so the API path needs an extension (see §4, H7).

---

## 4. Technical steps in the repo (High / Medium / Low)

> Everything below is a **proposal**. It has not been applied. It respects the constraints: it does not touch
> x402 headers/prices/`payTo`, it does not touch `secrets/`, it does not touch the posts from 27.10.

### HIGH — done first (1–3 days, ~8–12 h of work)

**H1. Open Graph + Twitter Card + canonical + JSON-LD in all 9 templates.**
- Files: `templates/landing.html`, `templates/launch_landing.html`, `templates/dashboard.html`, `templates/agent_playground.html`, `templates/public_activity.html`, `templates/checkout.html`, `templates/admin_dashboard.html`, `templates/admin_login.html`, `templates/admin_research.html`.
- Minimum for the public ones (`landing`, `launch_landing`, `dashboard`, `agent_playground`, `public_activity`):
  ```html
  <meta property="og:title" content="…">
  <meta property="og:description" content="…">
  <meta property="og:image" content="{{ url_for('static', filename='og.png', _external=True) }}">
  <meta property="og:url" content="{{ request.url }}">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="canonical" href="{{ request.url }}">
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"SoftwareApplication","name":"Kristo Intelligence","applicationCategory":"FinanceApplication","operatingSystem":"Any","offers":{"@type":"Offer","price":"0.003","priceCurrency":"USDC"}}</script>
  ```
- **Mandatory:** 1 OG image 1200×630 (`static/og.png`) — it can be generated from
  `docs/glama_thumbnails/generate.py` (there are already 3 variants).
- Effect: every share on X/Discord/Reddit/Telegram becomes a card with an image → a CTR jump with no budget.

**H2. Correction of the machine-readable specifications (the most important thing for aggregators).**
- `agents.json` (`app/blueprints/discovery.py:1416`): add the missing `/api/v1/whaleflow` (the 6th route);
  remove `monthly_vip_usdc: 29.0` (VIP unlimited is not implemented — `[DOCUMENTED]` only a $0.10 Telegram
  invite) or mark it as `legacy`; keep `free_tier_limit: 0`.
- `llms.txt` (`discovery.py:1536`): document the **standard** rail (`PAYMENT-SIGNATURE` / `X-PAYMENT`, x402
  v2) as primary and the legacy `X-Payment-Proof` as a fallback. Right now `llms.txt` describes **only** the
  legacy rail — an agent that reads it sends a wrong header.
- `.well-known/x402` vs `.well-known/x402.json` (`discovery.py:914/922`): unify the number of resources (6)
  and the descriptions; right now one gives 6, `agents.json` — 5.
- `server.json`: update `paid_endpoints` so that they match the 6; check whether `_meta` points to something
  old.
- `README.md`: remove "Rug-risk checks" (:21 — there is no such route), "zero payment incidents" (:111 —
  there is an INCIDENT 14.09), "11 resources" (:112 — the code exposes 6). Replace them with verified numbers.
- **Check after the change:** one test that compares the set of `X402_PAID_ENDPOINTS` with
  `REAL_X402_ROUTES` and with `agents.json`/`.well-known/x402` — there is no such test at the moment, and that
  is exactly why they diverge.

**H3. HTML pages with content (indexable).**
- `/pricing` — an HTML table with the 6 routes and the prices (the data is in `REAL_X402_ROUTES`); JSON-LD
  `Offer`.
- `/api-reference` — rendered from `openapi.json` (it already exists at `/openapi.json`,
  `discovery.py:1127`); static HTML with anchors per route.
- `/how-x402-works` — a short explainer (the material is in `docs/GUARD_METHODOLOGY.md` +
  `docs/blog/2026-10-23-x401-x402-one-gate.md`).
- `/changelog` — from git log/manually; it gives a "freshness" signal to crawlers.
- `/status` — a public page with `/health` + the last block scan; it can use the existing
  `/api/launch/health` (`main.py:5198`).
- All of these should go into `sitemap.xml` (`discovery.py:1387`) **with `lastmod`**.

**H4. `.github/` directory (5 files, 1 hour).**
- `.github/workflows/ci.yml` — `pytest` + `python -m compileall`; badge in the README.
- `.github/ISSUE_TEMPLATE/bug.yml`, `feature.yml`.
- `.github/SECURITY.md` — a reporting channel (email, not a public issue).
- `.github/social-preview.png` — 1280×640 (the same OG image).
- `.github/FUNDING.yml` (optional).
- Effect: the repo looks "alive" to a developer; a CI badge is a free trust signal.

**H5. The npm package — a real channel, not a badge.**
- Publish `1.0.1` with a fixed README (`packages/x402-client/README.md`): prices $0.003–0.005, **no** "1 free
  call", **no** "$0.05", **no** "$29 VIP unlimited".
- Add `repository.directory` (it is there), `keywords` (they are there), `homepage` (it is there).
- Add a downloads badge to the repo README (`img.shields.io/npm/dm/kristo-x402-client`).
- **High-impact option:** a Python client on PyPI (`kristo-x402`), because
  `examples/demo_agent/demo_agent.py` is already Python and agent developers are 50/50 JS/Python. This doubles
  the addressable audience.

### MEDIUM — after HIGH (1–2 weeks)

**M1. Comparison and "recipe" pages (organic traffic from long-tail queries).**
- "How to call an x402 API from LangChain / CrewAI / Claude Code" — 3 separate pages, each with a working
  snippet from `packages/x402-client` and `examples/demo_agent`.
- "x402 vs API keys: when pay-per-call wins" — positioning copy.
- "Base DeFi data for AI agents" — keyword-targeted.
- Each page: 600–900 words, 1 working example, 1 CTA to `/f/<channel>`.

**M2. Publishing the content that is already written.**
- `docs/MARKET_WRITEUP.md` → a public post (the methodology is a strong point; it is verifiable).
- `docs/blog/2026-10-23-x401-x402-one-gate.md` → a technical post.
- `docs/CONTENT_PACK_1.md` §A → dev.to (after the H2 corrections).
- **Everything with a `/f/<channel>` link and an OG card.**

**M3. Automation and monitoring.**
- `scripts/distribution/check_presence.py` + a GitHub Action (weekly).
- `scripts/seo/ping_index.py` (IndexNow, after a custom domain).
- `scripts/listing_monitor.py` (it already exists) → extend it to also check the mcp.so/mcprush/Glama badge.

### LOW — nice to have

**L1. A domain of your own** (e.g. `kristo.xyz` / `kristo.dev`) with a 301 from `onrender.com`.
- Reason: brand search, an email for outreach, IndexNow, trust in listings, independence from Render.
- Effort: 1–2 h (DNS + Render custom domain + `ProxyFix` is already configured to follow
  `X-Forwarded-Host`, `main.py:174`).

**L2. README rearrangement:** the first 12 lines = 1 sentence + 1 working `curl` + 1 screenshot/GIF + 3
badges. The details — in `docs/`.

**L3. Repo hygiene:** move `PROJECT_STATUS.md` (272 KB), the diff files, `temp_*.log`, `server_*.log` out of
the public repo; the MP4 files (120 MB + 19.9 MB) → GitHub Release assets, not in git.

---

## 5. A community marketing plan without spam risks

### 5.1 Rules of engagement

1. **Only an answer to a real question.** If nobody has asked "how do I pay an API without a key" or "where do
   I find Base DeFi data for an agent", do not post a link.
2. **One channel = one post per topic.** No cross-posting of identical text; every platform has a different
   format.
3. **No mass DMs.** The BlockRun DM was sent once and got no answer — that is a lesson, not a template.
4. **No fake stars/forks/reviews.** They are easily recognised and they kill trust forever.
5. **Always technical value before a link.** The formula: 1 concrete technical fact (e.g. "Bazaar requires an
   echo of `extensions` from the challenge") + 1 link to `/llms.txt` or `/f/<channel>`.
6. **Transparency about the market.** The numbers from `MARKET_WRITEUP.md` are verifiable — use them; do not
   invent "an $X million market".

### 5.2 Where and how (by priority)

| Community | Type of intervention | Frequency | Angle |
|---|---|---|---|
| **x402 Slack #general** | Answer to a technical question | 1–2/week | The Receipt cross-check methodology (you are already accepted there) |
| **CDP Discord #agentkit** | 1 technical note | once | "What we learned from the Bazaar listing trigger" |
| **Base Discord #developers** | 1 technical note | once | "x402 paywall on Flask — 3 things that bit us" |
| **r/mcp** | Answer to "how do I find an MCP server for finance" | on a real question | The 3 tools + `/llms.txt` |
| **r/LocalLLaMA / r/AI_Agents** | Answer to "how do agents pay for data" | on a real question | x402 vs API keys |
| **HN Show HN** | 1 post | once, after H1/H2 | "An API that pays for itself" |
| **X/Twitter** | 1 thread | once, after H1 | Demo video + OG card + `/f/x` |
| **Product Hunt** | 1 launch | after ≥3 social proof | "Pay-per-call DeFi intelligence for AI agents" |

### 5.3 What NOT to do

- ❌ Posting the same text in 5 subreddits in one day → shadowban.
- ❌ Opening a second PR in awesome-* without a reply to the first → the 32-day rule will close it again.
- ❌ Announcing "PUBLISHED" without a fetch check → the documentation already lies about Smithery/mcp.so.
- ❌ Paying for ads before we have an OG card and `/pricing` → expensive traffic to a broken funnel.
- ❌ Making "free tier" promises when production is `KRISTO_FREE_TIER_LIMIT=0` (`main.py:130`).

---

## 6. 30/60/90 days — execution and KPIs

### Week 1 (Days 1–7) — "Make it machine-correct"
- [ ] H2: fix `agents.json` (6 routes), `llms.txt` (v2 rail), the README false claims. **Without this, any
  listing is harmful.**
- [ ] H1: OG/Twitter/canonical/JSON-LD + `static/og.png`.
- [ ] Check the CDP Bazaar presence (Appendix B.1); if missing → Listing Request #1270 with
  `SCAN_LISTING_EN.md`.
- [ ] mcp.so: claim + description + "Authentication: x402".
- [ ] `/f/<channel>` links in all listings.

**KPI week 1:** `agents.json` == 6 routes; OG card valid (check with opengraph.xyz); 1 listing confirmed by
fetch.

### Weeks 2–4 (Days 8–30) — "Make it findable"
- [ ] H3: `/pricing`, `/api-reference`, `/how-x402-works`, `/status`, `/changelog` + sitemap `lastmod`.
- [ ] H4: `.github/` + CI badge + social preview.
- [ ] H5: npm `1.0.1` with a fixed README + downloads badge.
- [ ] Nudge PR #1308 and #13219; fix the Glama license F + hosted endpoint.
- [ ] GSC + Bing verification; sitemap submission.
- [ ] Enable `/f/<channel>` in every public link.

**KPI day 30:** ≥3 confirmed listings (`check_presence.py`), ≥1 new indexed HTML page in GSC, ≥5 external
visitors/day with attribution, npm ≥60 downloads/month.

### Days 31–60 — "Make it verifiable"
- [ ] M1: 3 recipe/comparison pages.
- [ ] M2: publish MARKET_WRITEUP + 1 dev.to article + 1 thread.
- [ ] M3: automation + a weekly "distribution drift" issue.
- [ ] Product Hunt preparation (≥3 social proof).

**KPI day 60:** ≥1 organic ranking in the top 50 for a long-tail query; ≥1 external paying customer from a new
channel; ≥100 npm downloads/month.

### Days 61–90 — "Make it revenue"
- [ ] Product Hunt launch; HN Show HN.
- [ ] 5 operator conversations (following the model from `MARKET_WRITEUP.md:72-82`).
- [ ] Re-evaluation of x402 Trust; recrawl of PayAPI.
- [ ] Review: which channel produced a payment → concentrate 80% of the effort there.

**KPI day 90:** ≥10 external payers; ≥$0.05 average/day; ≥1 long-term operator contract; 100% of payments with
channel attribution.

---

## 7. What NOT to touch (the owner's constraints)

| Protected | Why |
|---|---|
| x402 headers and the 402 envelope structure | Working and validated; a change breaks compatibility with facilitators |
| Prices ($0.003–$0.005) and `payTo`/fee receiver | Publicly announced and on-chain verified; a change breaks trust |
| `GET /.well-known/x402-trust.txt` | External trust profile; removing it lowers the grade |
| `secrets/` and `.env` | Never opened; not touched |
| The posts from 27.10 | Explicitly forbidden for editing |
| Push to `main` | Auto-deploy on Render → every change is production |

**Rule:** all changes in §4 go through a separate PR + review, not directly into `main`.

---

## 8. Appendices

### Appendix A — Ready URLs and contacts for listing

| Channel | Action | URL |
|---|---|---|
| CDP Bazaar | Presence check | `https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources` |
| x402scan | Listing Request #1270 | `https://github.com/x402scan/x402scan/issues/1270` (check the number) |
| MCP Registry | Publish | `https://registry.modelcontextprotocol.io` |
| Glama | Connector (live) | `https://glama.ai/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence` |
| Glama | Servers dir (problem) | ticket #135407945 |
| mcp.so | Claim | `https://mcp.so/servers/kristo-intelligence` |
| PulseMCP | Watcher | `https://www.pulsemcp.com/submit` |
| awesome-x402 | PR #1308 | `https://github.com/coinbase/x402` (check the repo) |
| awesome-mcp-servers | PR #13219 | `https://github.com/punkpeye/awesome-mcp-servers` |
| PayAPI Market | Listing | `https://payapi.market/api/kristo-intelligence-defi-signals-api` |
| x402 Trust | Profile | `https://x402-trust.com/endpoint/139372` |
| nohumans.directory | Listing | (see `discovery.py:340-342` for the reference entry) |

### Appendix B — Scripts (pseudocode)

**B.1 `scripts/distribution/check_presence.py`**
```python
CHANNELS = {
  "cdp_bazaar": "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources",
  "mcp_registry": "https://registry.modelcontextprotocol.io/v0/servers?search=kristo",
  "mcpso": "https://mcp.so/servers/kristo-intelligence",
  "glama": "https://glama.ai/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6",
}
# for each: GET, look for "kristo" / our payTo / our domain
# writes docs/distribution_state.json with {present, checked_at, evidence_url}
# exit code 1 on a change → GitHub Action opens an issue
```

**B.2 `scripts/seo/ping_index.py`**
```python
# 1) generate a key (uuid) → serve it at /<key>.txt
# 2) POST https://api.indexnow.org/indexnow  {"host": "...", "key": "...", "urlList": [...]}
# 3) requires a domain of your own; on onrender.com it may return 403
```

**B.3 `scripts/distribution/submit_payload.py`**
```python
# generates the ready JSON/Markdown payload for each directory from one source
# (server.json + REAL_X402_ROUTES) → avoids the 5 vs 6 routes divergence
```

### Appendix C — Measurement (without third parties)

- **Server-side:** `request_log` already records `path, source, referer, user_agent, funnel` — add `channel`
  from `/f/<channel>` and `utm_*` query params.
- **Public:** `/api/dashboard/data` already has `by_channel` — as long as the links go through `/f/`.
- **External:** npm downloads API, MCP Registry search, CDP Bazaar page, `check_presence.py`.
- **Search engines:** GSC + Bing (manually, once).
- **On-chain:** `payment_guards` / `onchain_sales` — the truth about revenue; everything else is noise.

---

## 9. One sentence

> The platform is not invisible because channels are missing — it is because there are many channels, none is
> completed, the machine-readable specs lie, and the paid product is given away free at two entry points;
> therefore the next 90 days are not a "marketing campaign" but **finishing 6 listings, fixing 4
> specifications, adding 1 OG card and 1 attribution link on every public surface** — and then measuring every
> dollar.

---

*The document was generated on 2026-11-03 at HEAD `66a0ce4`. All URLs were checked on that date; external
states (Smithery, PulseMCP, CDP Bazaar) change — verify with `check_presence.py`, do not trust the document.*
