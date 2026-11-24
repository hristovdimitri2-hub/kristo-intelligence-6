# CONTEXT & ROADMAP — kristo-intelligence-6

**Prepared:** 2026-11-03 · **Time:** 13:10–13:35 (Europe/Sofia)
**Revision for which it is valid:** `9089ba5` — "audit-b1: stop key leaks" (2026-11-03 12:56:40 +0200)
**Local root:** `<local-path>`
**Remote:** `github.com/hristovdimitri2-hub/kristo-intelligence-6` · `origin/main` = **`ae216f2`** (2026-11-01)
**Repository:** 352 commits, first `619f005` (2026-08-19) · 29 untracked entries · MIT license

> **Scope and limitations:** this document is **read-only** — a consolidation of work already done. Not a single file related to the code, the x402 headers, the prices, `payTo`, the protected configurations or `secrets/` was changed. There is no `git add/commit/push`. `secrets\` and `.env` were not opened. Every step in §5 is a **proposal**.
>
> **Why this matters:** `main` → auto-deploy on Render. Any change to `main` is a production change. That is why the plan is divided into waves with explicit gates, and not into a "to-do list".

---

## 0. Executive summary

**The project is technically mature but commercially broken for three independent reasons — and all three are fixable.**

| # | Problem | Essence | Severity |
|---|---|---|---|
| 1 | **The paid data is handed out for free** | 3 of 6 paid SKUs are obtainable for $0 via `/api/dashboard-stats` and `/api/dashboard/data`. The paywall is decorative. | 🔴 Blocking for the business model |
| 2 | **The payment signature is not authoritative** | `accepted.amount` (from the client) replaces the signed `authorization.value` → underpayment; when the receipt is unreadable, delivery goes **fail-open**. | 🔴 Financial risk |
| 3 | **The product cannot be found by a buyer** | 3 indexable HTML pages in the whole application; zero OG/Twitter/canonical/JSON-LD; 0 analytics; `/f/<channel>` built but unused. | 🟠 Zero organic traffic |

**Three facts that require a decision today:**

1. **Two commits are not in production.** `origin/main` = `ae216f2` (01.11), while HEAD = `9089ba5`. Unpublished are:
   - `9089ba5` — **stops key leaks** (F-13/F-14/F-15/F-30);
   - `66a0ce4` — **CDP Bazaar listing trigger** (02.11), which is the precondition for getting into the main x402 index.
   Since `push` = auto-deploy, the two go together — an owner decision, not an automatic action.

2. **There is a contradiction about the production server.** `Procfile:1` and `Dockerfile` say `gunicorn --workers 1 --threads 8`; `TASK.md:107` (a snapshot from 30.09) claims that production runs on **`python main.py`** (werkzeug dev server) and that Procfile/gunicorn is **not used**. Both cannot be true. This changes the whole concurrency analysis (§3.4). It requires a check in the Render dashboard.

3. **The financial position is clear and small.** On-chain: **16 rows / $0.052**; of these **3 external human wallets / $0.011**, 7 sampler rows / $0.021, 6 canary rows / $0.020. Stripe: $34.80 refunded, **net $0.00**. The market (self-measured): the leader in PayAPI makes ~$1.2/month with 2–4 buyers. **Traffic by itself decides nothing** — what is needed is the right small traffic: agents and operators that pay.

**The most important conclusion from the whole history:** the only **confirmed external paid traffic** comes from a **machine-readable directory for agents** (`nohumans.directory` → 3 × $0.005 from `nohumans-scout`, 30.10), while the effort was being thrown into human channels (Reddit, HN, Product Hunt) that were **never used**. The strategy should follow what has been proven: **machine surfaces + measurability**, and human channels only once there is something to show.

---

## 1. Sources, scope and methodology

### 1.1 Sources used

| Source | Volume | Status |
|---|---|---|
| `docs/PROJECT_CHRONOLOGY.md` | 264 lines / 23.5 KB | Read. **Stops at 28.09** (marker `<!-- CONT -->`) — does not cover the last ~5 weeks |
| `docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md` | 573 lines / 98 KB | Read in full (index F-01…F-40, §8 plan, §9 limitations, Appendix A) |
| `PROJECT_STATUS.md` | 2633 lines / 272 KB | The current sections were read (02.10 MIGUEL, MARKET RECONSTRUCTION, CURRENT STATE, OPEN ITEMS). The rest is HISTORY |
| `TASK.md` | 107 lines | Read. **Snapshot from 30.09** (`3661419`) — outdated |
| `docs/VISIBILITY_AND_TRAFFIC_STRATEGY.md` | 457 lines / 54 KB | Read (own work from 03.11) |
| `git log` / `git show` | 352 commits | The history 27.09 → 03.11 was extracted (70 commits) + the diff of `9089ba5` |
| Technical SEO audit (parallel agent) | — | Completed; evidence from the code generators |

### 1.2 What could NOT be done

- **`<local-path>` — the directory does NOT exist.** Item 3 of the request (analysis of chat logs/export) is **impossible** on this machine: the path does not exist, there is no export. The alternative was used in full: `PROJECT_STATUS.md` + `docs/PROJECT_CHRONOLOGY.md` + `TASK.md` + `git log` give the same information with higher reliability (the archive rule: "when in doubt versus the chat history, trust HISTORY").
- **Production verification.** There is no access to the Render dashboard/logs/DB. The claims about production come from documents and from the code, marked as `[DOCUMENTED]`.
- **Paid E2E test.** Has not been performed (it requires a funded wallet).

### 1.3 How to read this document

- `[VERIFIED]` — verified in the code/git/live on 03.11.
- `[DOCUMENTED]` — comes from a document in the repo, without independent verification.
- `[TO VERIFY]` — a contradiction between sources; requires human confirmation.

---

## 2. Brief summary of the historical work performed

### 2.1 Project phases

| Period | Phase | What was achieved | Source |
|---|---|---|---|
| **19.08** | Genesis | `619f005` "Initialize Kristo Intelligence Number 6" + importing a sanitized snapshot as an independent project. The idea: a paid DeFi market-intelligence API for AI agents on Base, payment with x402 (402 → USDC → 200), without signup/subscription/keys | git, `TASK.md:11-21` |
| **27.08** | **FREEZE** | The project stops (priority: freelance/CV). `State at freeze` + `Resume checklist` are assembled. Known gaps: receiver key unconfirmed, E2E not run, burned `WALLET_PRIVATE_KEY` | `CHRONOLOGY:12-21` |
| **29.08** | Growth sprint (resume) | Storefront fixes LIVE (receiver, honest micro-prices, favicon); new `services/connectors.py` — a registry of 9 connectors + **STANDARD x402 EIP-3009 rail** through the facilitator + L402 bridge + `/api/connectors` + quickstart. **108/108 tests**. Rule: two AI sessions do not push at the same time | `CHRONOLOGY:23-31` |
| **02.09** | 🏁 **First real sale** | PayAPI canary: **0.005 USDC** from an external tester (`0x7e6b…2b1c`, block 50783187, 13:28:41 UTC). The root-cause chain patched through 5 canaries (CDP JWT claims, CDP body schema, v2 exact). The server accepts both forms. **124/124 tests** | `CHRONOLOGY:33-44` |
| **03.09** | **PHASE COMPLETE** | "Verification only, not a single code change." Announced: **product verified → GO-TO-MARKET**. From here begins the commercial phase, which is also the current problem | `CHRONOLOGY:51-54` |
| **05–08.09** | Rules and channels | "STANDING NOTES" + "Plans on events" were recorded (valid for the whole history). A full audit of the listing channels (`LISTING_CHANNELS_AUDIT.md`). A PR was submitted to `awesome-remote-mcp-servers` | `CHRONOLOGY:56-78` |
| **06.09** | First external client | **`0x4dB7` paid 0.003 USDC** for `/api/v1/signal` — verdict "LAUNCH SIGNAL", fingerprint = a moderate multi-API operator, not a crawler | `CHRONOLOGY:62-68` |
| **13.09** | 🔴 "Day of truth" | Dense on-chain hashes, **2 root-cause bugs**, guards **C1/C2/H2**. `GUARD_METHODOLOGY` published. Audit 2 (Stripe/CRM/entitlements). Dashboard 2.0 | `PROJECT_STATUS:2117-2303` |
| **14–15.09** | 🔴 **INCIDENT** | A paying external client (crawler `e3ba`) was **rejected by the C2 race → HTTP 401** after payment (tx `0x06b4c8f2…58ce7`, block 51313253, $0.003). Fixed in `8bdd45f` on 15.09. The guards have never rejected a **human** client; this is the only rejection | `PROJECT_STATUS:34-46` |
| **16.09** | First human payer | First payment from a human (Starter $29 via Stripe) — a milestone of commercial validation | `[DOCUMENTED]` |
| **20–25.09** | Audits and the F1 gate | Audits #4/#5; the `c2_reorg_detected` loop diagnosed and fixed (`8bdd45f`); the **F1 gate** defined — "the golden step": a real E2E transfer with a demo wallet. A1 live, A2 no-pay E2E green, **only a funded key is missing** | `PROJECT_STATUS:193-288` |
| **27–28.09** | 🔧 Stabilization | Restructuring of `PROJECT_STATUS.md`. Three root fixes: **flaky tests** (`a3d4362` — production threads do not start under pytest), **placeholder-hash** (`9418c8f` — the lag claim never writes `000…0`, with a regression test), **env-guard** (`ad3f642` — stops the double boot → an end to duplicated Telegram alerts). **422/422 tests** | `PROJECT_STATUS:26`, `TASK.md:36-40` |
| **29.09–02.10** | 📊 The numbers become hard | Date corrections (based on the production DB + block timestamps). **Miguel (ReturnCheck)** = **3rd external human payer** (01.10 17:46:35 UTC, 0.003 USDC, block 52043724, direct ERC-20 transfer). Treasury: **16 rows / $0.052** (the on-chain balance matches 1:1). Honest metric: **3 humans + 2 machines**. First business dialogue (reverse test). **426/426 tests** | `PROJECT_STATUS:1-20` |
| **08.10** | 🔒 Security | `54a7ba3` — **9 security hardening fixes** (durability of rejected_signals, coingecko cache, demo nonce, XFF fallback, logging, sentinel atomic, adopt nonce check, arb boundary, pinning) | git |
| **11.10** | ⚡ Performance | `858ad4c` — sargable day window + unified funnel scan + index `idx_request_log_path`: **cold build ~41 s → ~1 s**. `ecd2522` — a 60 s TTL cache for the public dashboard payload. `4fb8c27` — A+ guards: poll receipt 4×2 s, then a fail-open override | git |
| **13–24.10** | 🔧 x402 correctness and trust | `10a3be0` Cache-Control no-store + CORS only on 402; `137b85a` openapi without the x402 securityScheme; `10a3be0`… `12192bb`/`db6c8fc` **envelope-body-mirror** (the 402 body is not sorted, so that it matches the header); `386dc07` canonical EIP-55 `payTo`; `16a3791`/`4c61a8d` **x402 Trust profile, badge, claim 4/4**; `c99be97` Sentinel weekly report with 6 market numbers; `a1eeb79`/`3279f56` certifi bump/pin; `e2dc7ea` mcprush badge; `1912350` blog post x401/x402 | git |
| **30.10–01.11** | 📇 Listings and validation | `c1bbde4` README test count 423 → **550**. `a6004bf` — validation labels (nohumans/organic), input schema in x402.json, 6 free sample routes, **550/550 green**. `648089c`/`6c46745`/`ae216f2` — a temporary `/.well-known/nohumans-claim` challenge (added, rotated, removed after a successful claim) | git |
| **02.11** | 📇 **Bazaar trigger** | `66a0ce4` — "echo extensions + resource in x402 payment payload (CDP bazaar listing trigger)". **NOT in production** (see §0) | git |
| **03.11** | 🔒 **audit-b1** | `9089ba5` — "stop key leaks": `.dockerignore` + `secrets/` + `*.mp4`; `redact_rpc()` on RPC errors; `_redact_tg()` for the Telegram token; masking of env values in `_t2_render_env_check.py`. **NOT in production** | git |

### 2.2 What was actually achieved (the honest reckoning)

**Strengths (real, verifiable):**
- A working x402 payment rail with **two rails** (v2 `PAYMENT-SIGNATURE`/`PAYMENT-REQUIRED` + legacy `X-Payment-Proof`), EIP-3009 `transferWithAuthorization`, a facilitator chain PayAI→CDP with self-broadcast fallback.
- **Confirmed real payments** from external wallets (5 different external addresses), with on-chain evidence and block numbers.
- Built-in **protection against replay** (durable lock in `payment_guards`), EIP-712 computation locally, checks `auth.to == payTo` and `asset`.
- **550 tests**, covering the payment envelope, the guards, reorg detection, secret hygiene.
- Built **machine-readable surfaces**: `/.well-known/x402`, `/.well-known/x402.json`, `agents.json`, `/mcp.json`, `/openapi.json`, `/llms.txt`, `/robots.txt`, `/sitemap.xml`, `server.json` for the official MCP Registry.
- An **MCP server** with 3 tools, listed in the official MCP Registry (active, v6.0.0) and a Glama connector.
- A published **npm package** `kristo-x402-client@1.0.0`.
- Several external confirmations: x402 Trust **grade B**, a PayAPI Market listing, 1 merge into an awesome list.
- **Real paid traffic from a machine** via `nohumans.directory` (3 × $0.005).

**Weaknesses (also real):**
- **Zero commercial validation.** 3 human payers in 2.5 months, $0.011 in total from external human addresses; Stripe net $0.00.
- **The product undercuts itself** — the paid data is available for free (§4, F-01).
- **Visibility almost zero** — 3 indexable HTML pages, 0 OG tags, 0 analytics (§4.4).
- **The documentation runs ahead of reality.** "11 resources", "zero payment incidents", "Rug-risk checks", "$29 VIP unlimited" — all are false or unfulfilled, and they sit on public surfaces.
- **Process mistakes repeated many times:** submitting a PR without a fulfilled precondition (Glama quality score), recording a success before verification (Smithery is a 404 today), blocking ready outreach behind an engineering gate.

---

## 3. Current state

### 3.1 Verified facts (03.11.2026)

| Indicator | Value | Status |
|---|---|---|
| HEAD | `9089ba5` (03.11 12:56) | `[VERIFIED]` |
| `origin/main` | `ae216f2` (01.11) | `[VERIFIED]` |
| Unpublished commits | **2** (`66a0ce4` Bazaar trigger, `9089ba5` key-leak fixes) | `[VERIFIED]` |
| Total commits | 352 (first 19.08.2026) | `[VERIFIED]` |
| Untracked entries | 29 (incl. the two new audit documents, diff files, `kristo-intelligence/`) | `[VERIFIED]` |
| Tests | **550 passed** (confirmed full run, 180.46 s, 1 DeprecationWarning) | `[VERIFIED]` |
| Paid routes | **6**: `/api/v1/signal`, `/api/stats`, `/api/arb/opportunities`, `/api/bot-status`, `/api/sales`, `/api/v1/whaleflow` | `[VERIFIED]` |
| Free routes | 27 in the allow-list + 6 `/sample` routes | `[VERIFIED]` |
| Prices | signal 0.003 · whaleflow 0.003 · arb 0.005 · stats 0.005 · sales 0.005 · bot-status 0.005 (`config.py:75-83`) | `[VERIFIED]` |
| Free tier | `KRISTO_FREE_TIER_LIMIT` default **1** in the code; production relies on env **0** | `[TO VERIFY]` |
| On-chain revenue | **16 rows / $0.052** — 3 external humans / $0.011 · 7 sampler / $0.021 · 6 canary / $0.020 | `[DOCUMENTED]` (02.10) |
| Stripe | $34.80 refunded, net **$0.00** | `[DOCUMENTED]` |
| MCP tools | 3 (`get_market_stats`, `get_onchain_sales`, `get_bot_status`) | `[VERIFIED]` |
| Indexable HTML pages | **3** — `/` (en), `/launch` (bg), `/validation` (orphan) | `[VERIFIED]` |
| Open Graph / Twitter / canonical / JSON-LD | **0 of 9** templates | `[VERIFIED]` |
| Third-party analytics | **0** (no gtag/plausible/umami/posthog etc.) | `[VERIFIED]` |
| npm downloads | **37** / 30 days (peak 119 on the day of publication) | `[VERIFIED]` |
| GitHub | 2 stars, 0 forks, 0 issues, 0 releases, **no `.github/`** | `[VERIFIED]` |
| Indexed pages (DuckDuckGo `site:`) | **1** (the home page) | `[VERIFIED]` |
| CDP Bazaar presence | **Unconfirmed** (first page: 46 entries, 12 providers, without our `payTo`) | `[VERIFIED]` |

### 3.2 On-chain and commercial picture

```
Revenue (on-chain, 16 rows / $0.052)
├── External human payers:   3 wallets / $0.011   ← the real validation
│     ├── 0x4dB7   06.09  $0.003  /api/v1/signal
│     ├── 0x902dcf (standalone, no link to the hub)
│     └── 0xce4fbd 01.10  $0.003  (Miguel / ReturnCheck)
├── Sampler machines:        7 rows / $0.021
│     └── 0x4c29ec (promoted, hub-fed 0x6302; 353 recipients/13 days)
└── Canary (our tests):      6 rows / $0.020
```

- **Miguel (ReturnCheck)** is the only **business dialogue** — he proposed a reverse test (we pay his endpoint), scheduled after the demo wallet is funded.
- **Cluster hypothesis:** `0x6302` is a hub contract, a shared funder of `a19f`, `54e1`, `e3ba`, `4dB7` (weekly micro-amounts, bidirectional) → probably **one operator behind the cluster**. Unconfirmed.
- **The F1 gate** (a real E2E transfer with the demo wallet `0xE50c5212…35763`) remains **open** since 25.09 — it is blocked only by human action: a deposit of ≥ 0.003 USDC + gas.

### 3.3 Discrepancies and outdated information `[TO VERIFY]`

| Claim | Where | Reality |
|---|---|---|
| "Tests 422/422" | `PROJECT_STATUS:26` | **550** (confirmed) |
| "Tests 423/423" | `TASK.md:31` | **550** |
| HEAD = `3661419`, 10 local unpushed commits | `TASK.md:33` | HEAD = `9089ba5`, **2** unpushed |
| HEAD = `66a0ce4`, 351 commits, 29 untracked | audit report:495 | HEAD = `9089ba5`, 352 commits |
| Production runs on the werkzeug dev server (`python main.py`), Procfile/gunicorn is not used | `TASK.md:107` | `Procfile:1` + `Dockerfile` CMD say gunicorn. **Requires a check in Render** |
| "11 resources" | `README.md:112` | **6** in the code (`main.py:2183`) |
| "zero payment incidents" | `README.md:111` | There is an INCIDENT on 14.09 (401 after payment) |
| "Rug-risk checks" | `README.md:21` | No such route (only an unused import) |
| "$29 VIP — unlimited access" | `agents.json`, `/api/mcp/manifest`, npm README | **Not implemented anywhere**; there is only a $0.10 Telegram invite threshold |
| "Free tier: 1 call per client" | npm README, `ai-plugin.json:1511` | Production runs with `KRISTO_FREE_TIER_LIMIT=0` |
| "$0.05 USDC" / "USD 0.01" | npm README | Actually **0.003–0.005** |
| `settlement_status: "discovery_only"` + "settlement is not enabled in this preview" | `main.py:1944`, `main.py:2161`, `docs/x402-client-example.js:26-33` | Contradicts "settled through the Coinbase x402 facilitator" (`main.py:4054-4058`, `discovery.py:1019-1020`) — **a direct contradiction on public surfaces** |
| "whaleflow sample = $0.005" | `discovery.py:440` | `config.py:83` = **0.003** |
| Whale threshold: $50k | `PROJECT_STATUS:2440`, `WHALE_FLOW_SPEC:19` | The code: **$5,000,000** (`dashboard_store.py:98`) |
| Chronology up to "today" | `PROJECT_CHRONOLOGY.md` | Stops at **28.09** (marker `<!-- CONT -->`) |
| ICP: "retail crypto traders" + Meta/Google ads | `marketing/offer-and-ad-strategy.md:6-11`, `launch/launch-plan-30d.md:43` | A different product from the agent-paid API |

### 3.4 Architectural topology (with the open question)

```
[OPTION A — if production uses Procfile/Dockerfile]
  1 process · gunicorn --workers 1 --threads 8 --timeout 120
  → 8 threads = the WHOLE HTTP capacity (every blocking call = −12.5%)
  → + ~11 background threads in the SAME process

[OPTION B — if production uses `python main.py` (the claim in TASK.md:107)]
  1 process · werkzeug dev server, app.run(host, port)
  → Flask passes threaded=True by default → an UNLIMITED number of threads
  → dev server in production: no production hardening, weak resilience
  → the same ~11 background threads in the process

In both cases: ONE process, shared in-RAM state,
and ~11 background loops (monitor, dashboard scan, whale scan, agent, catalog,
stripe snapshot, arbitrage, sentinel, keep-alive, reorg-watch-per-call…).
```

**Consequence:** in both variants the analysis of shared state, the global DB lock and the blocking budgets still holds. The difference is in the capacity of the HTTP layer and in the production-readiness of the server.

### 3.5 Infrastructure inventory

- **Application:** Flask 3.1.3, 44 `@app.route` in `main.py` + 26 blueprint routes, 345 `.py` files, `main.py` = 5859 lines.
- **Dependencies:** web3.py 7.16.0, psycopg[binary] 3.3.4 (Postgres, SQLite fallback), requests 2.34.2, `stripe==15.5.1`, `python-telegram-bot==22.8`, pytest 9.1.1, `cryptography>=42.0.0`.
- **Container:** non-root user `kristo`, HEALTHCHECK every 30 s.
- **Documents:** `docs/` = 89 files / ~0.57 MB (49 in the SEO inventory), 46 `.md`, 26 probe `.py`.
- **Missing artifacts:** `.github/` (entirely), `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `render.yaml`, a `docs/README.md` index, `scripts/seo/`.
- **Dead/unused assets:** `templates/agent_playground.html` (truly dead — `/agents` does a 302 to `/dashboard` and never renders it); `docs/x402-client-example.js` (outdated and misleading); `kristo-intelligence/` (an untracked duplicate); `.kilo/worktrees/believed-dancer/` (a full duplicate worktree, ignored only via `.git/info/exclude`).
  - **CORRECTED (2026-11-12):** `templates/public_activity.html` is NOT dead and must not be deleted. It is rendered by `src/nexus/distribution.py:153` (`/api/public/activity?format=html`), and the blueprint is registered in `src/nexus/__init__.py:125`, called from `main.py:5408 mount_nexus_engine(app)`. It was missed during the audit because `grep render_template main.py` does not see blueprints.

---

## 4. Register of critical defects

> The full evidence (file:line) is in `docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md` §0 (index F-01…F-40).
> **Status:** ✅ = addressed in `9089ba5` (but **not in production**); ⬜ = open.

### 4.1 🔴 P0 — blocking for the business model (without them billing is decorative)

| ID | Defect | Evidence | Status |
|---|---|---|---|
| **F-01** | **The paid data is handed out for free.** `/api/dashboard-stats` differs from the paid `/api/stats` only in `recent_requests[-50:]`; `/api/dashboard/data` serves history + whales + the full `/api/sales` payload. **3 of 6 SKUs are 100% replaceable at $0** | `main.py:142-157, 3427-3428, 3986-3989, 5573-5582` | ⬜ |
| **F-02** | **`accepted.amount` shadows the signed `authorization.value`** → underpayment. Proven: `accepted.amount=5000` + signed `value=1` → precheck returns `[]`; a non-numeric amount skips the check | `services/connectors.py:195-200` | ⬜ |
| **F-03** | **Fail-open on an unreadable receipt.** If an error occurs while reading the receipt, the paid call is **delivered**; `block_number`/`hash` remain `0`/`""`; the `except` in the confirmation check swallows the exception and grants access | `main.py:3082-3110, 3132, 3158-3159` | ⬜ |
| **F-04** | **4 WRITES on a free GET.** `guard_stats()` does INSERT/DELETE in `payment_guards` — the replay-lock table — on an anonymously read route that the dashboard polls every 45 s, under **the same `_pg_lock`** as `claim_payment_tx` | `integrations/dashboard_store.py:1542-1555` | ⬜ |
| **F-05** | **A reorg never reverses a credited payment** — `_detect_reorgs` only logs | `main.py:2631-2690`; `tests/test_reorg_watch.py` pins detection-only | ⬜ |
| **F-06** | **Acceptance by nonce without a depth check** (depth 1) | `main.py:2321-2435, 2484` | ⬜ |
| **F-07** | **Zero rate limit on the payment path**; the gas spend is controlled by an anonymous client; `maxFeePerGas = gas_price*2` with no cap | `main.py:1406-1416, 3431-3523`; `connectors.py:350, 376` | ⬜ |

### 4.2 🟠 P1 — stability, performance, information leakage

| ID | Defect | Evidence | Status |
|---|---|---|---|
| **F-08** | A single RPC provider (`https://mainnet.base.org`), no fallback, no cooldown on 429/`Retry-After` | `config.py:57` | ⬜ |
| **F-09** | One shared DB connection under a global lock, opened **without `connect_timeout`** | `dashboard_store.py:307, 334-340, 342-372` | ⬜ |
| **F-10** | `/health` depends on the DB → returns 503 → Render restarts the only worker → a loop | `discovery.py:32-76` | ⬜ |
| **F-11** | `/mcp/sse` is free and unlimited; it pins 1 of 8 threads for ≥15 s → **a full DoS with a handful of requests** | `discovery.py:665-717` | ⬜ |
| **F-12** | Unbounded thread-per-payment reorg watch + **an unchunked `eth_getLogs(5000 blocks)`** | `main.py:3217, 2321-2435, 2621-2628` | ⬜ |
| **F-13** | The raw RPC text (`rpc_error`) is published on a **free** route | `main.py:643 → 3792 → 3986` | ✅ `redact_rpc()` applied (`main.py:642/645/771/780/1143/1160/1230/1237`) — **in production: no** |
| **F-14** | The Telegram bot token leaks into the logs via `requests` exceptions (the token is in the URL) | `services/telegram_sales.py:72, 80-81, 198-212` | ✅ `_redact_tg()` applied — **in production: no** |
| **F-15** | `secrets/` is baked into the Docker image (`.dockerignore` without an entry) | `Dockerfile:29` | ✅ `secrets/`, `*.mp4`, `kristo_paid_demo_clip*` added — **in production: no** |
| **F-22** | The statistics aggregate: 12 queries, 5 full scans; **528 ms at 46 301 rows** locally; in the code: "~783K rows, ~22 seq scans, measured ~41 s live". There is no cache on `/api/stats` and `/api/dashboard/data` | `main.py:3944-3945` | ⬜ |
| **F-23** | The blocking budgets on the paid path exceed `--timeout 120` | audit §4 | ⬜ |
| **F-24** | Stripe SDK: an 80 s timeout × 3 retries on the request path | audit §4 | ⬜ |
| **F-25** | `_stripe_payment_snapshot_loop` **without `try/except`** — one exception kills the loop | audit §4 | ⬜ |
| **F-26** | `/api/launch/health` without auth | `main.py` | ⬜ |
| **F-27** | `/api/connectors` exposes the hot wallet address, `gas=` and an internal route | `services/connectors.py:950-1034` | ⬜ |
| **F-28** | The Render configuration is **not versioned** (`render.yaml` has never existed) | `git log --all -- render.yaml` → empty | ⬜ |
| **F-29** | The admin token falls back to `SESSION_SECRET` when it has none of its own | audit §6 | ⬜ |
| **F-30** | An operator script prints live env values | `scripts/_t2_render_env_check.py` | ✅ masking added — **in production: no** |
| **F-31** | Missing indexes on `request_log(user_agent)`, `(source)`, `(funnel)`; unbounded in-RAM maps | audit §4/§7 | ⬜ |

### 4.3 🟡 P2 — documentation, claims, hygiene

| ID | Defect | Status |
|---|---|---|
| **F-16** | `X-Payment-Proof` is a replayable bearer token over publicly published data | ⬜ |
| **F-17** | A single payment can deliver twice under concurrency | ⬜ |
| **F-18** | `payment.amount_usdc` returns atomic units under a USDC name (5000 instead of 0.005) | ⬜ |
| **F-19** | The advertised prices drift from the 402 challenge on **5+ surfaces** | ⬜ |
| **F-20** | "$29 VIP — unlimited access" is not implemented anywhere | ⬜ |
| **F-21** | `FREE_TIER_LIMIT` defaults to 1; production relies on an env variable that is not documented | ⬜ |
| **F-32…F-40** | Minor: documentation volume/hygiene, contradictions between documents, dead assets | ⬜ |
| **F-33** | `/validation` publishes live paid addresses and the outdated number `550/550` | ⬜ |

### 4.4 🟠 Visibility — findings from the technical SEO audit

| ID | Defect | Evidence |
|---|---|---|
| **V-01** | **Only 3 indexable HTML pages** in the whole application. There is no `/pricing`, `/docs`, `/faq`, `/about`, `/mcp`, `/changelog`, `/guides`, `/blog`, nor per-route pages | SEO audit §8 |
| **V-02** | **0 Open Graph / Twitter Card / canonical / JSON-LD across 9 templates** — every share is a bare URL | `grep` = 0 matches |
| **V-03** | **The sitemap is broken:** it contains `/dashboard`, which has `<meta name="robots" content="noindex">` (priority 0.9, hourly!), and two 302 redirects (`/agents`, `/nexus` → `/dashboard`); it **omits** `/validation` and `/api/v1/quickstart`; there is no `<lastmod>`; it lists `.txt`/`.json` as pages | `discovery.py:1387-1413`, `dashboard.html:6` |
| **V-04** | **`/validation` is an orphan** — it is not linked from any template and is missing from the sitemap | SEO audit §1 |
| **V-05** | **6 `/sample` routes are invisible** — advertised only as `sample_url` in `/.well-known/x402.json`; missing from the sitemap, openapi, llms.txt and all HTML | SEO audit §2 |
| **V-06** | `llms.txt` documents **only the legacy `X-Payment-Proof`** rail; the list of 402 headers omits `PAYMENT-REQUIRED`/`PAYMENT-SIGNATURE` | `discovery.py:1588-1596, 1617-1621` |
| **V-07** | **`settlement_status: "discovery_only"`** on two public surfaces contradicts "settled through the facilitator" on two others | `main.py:1944, 2161` vs `main.py:4054-4058`, `discovery.py:1019-1020` |
| **V-08** | `agents.json` lists **5** endpoints (missing `/api/v1/whaleflow`), `/.well-known/x402` — 6, README — "11" | `discovery.py:1416-1482` |
| **V-09** | `/mcp.json` gives a **flat price of 0.005** for all 6 tools → it overcharges signal/whaleflow (0.003) | `discovery.py:1026-1126` |
| **V-10** | `/api/mcp/manifest` contains **VIP $29** (a human Stripe tier) in a machine manifest | `discovery.py:874-881` |
| **V-11** | **OPTIONS preflight on the paid routes also gets 402** → it breaks browser-based x402 clients | `main.py:3379-3380` |
| **V-12** | The npm README (in the package itself) contains **outdated prices** ($0.05, $29 VIP, "1 free call") and only the legacy rail → "handles x402 paywalls automatically" is **false for spec clients** | `packages/x402-client/README.md` |
| **V-13** | `examples/demo_agent/demo_agent.py` is fragile: it expects a 402, but with the default `FREE_TIER_LIMIT=1` the first call returns 200 → "UNEXPECTED status 200" and it burns the free call. The dependency on `KRISTO_FREE_TIER_LIMIT=0` is **undocumented** | SEO audit §6 |
| **V-14** | There is no GSC/Bing verification, no analytics, no IndexNow/sitemap ping, no `X-Robots-Tag` | SEO audit §9 |
| **V-15** | One dead template (`agent_playground.html`; `public_activity.html` is ALIVE — see the note in the inventory above) and one misleading example (`docs/x402-client-example.js`, which claims the server does not check proof headers — false) | SEO audit §1/§6 |

---

## 5. Action plan

> Every item is a **proposal**. Changes to production go through the gate "push = auto-deploy".
> **Untouched invariants** (see §8): the x402 headers and the envelope structure, `payTo`/fee receiver, the prices in `config.py`, `/.well-known/x402-trust.txt`, `secrets/` and `.env`.

### 5.1 🔒 Security and payment integrity

**Wave S1 — P0, financial risk (highest priority):**

1. **F-02 — the signature becomes authoritative.** Derive the amount **only** from `auth.value`; reject on a mismatch with `accepted.amount`; reject **non-numeric** amounts instead of skipping the check; re-read the `Transfer` amount from the receipt before granting (the adoption path already does this correctly at `main.py:2419-2421`).
   - *Check:* a test that supplies `accepted.amount=5000` + signed `value=1` → **must return 402/400**, not `[]`.
2. **F-03 — an end to fail-open.** One explicit policy: fail-closed after the poll (401/425 with a tx hash, as the in-flight branch `main.py:3144-3157` does), or an override **only** with independent confirmation. **Never** may an exception in the confirmation check lead to delivery.
   - *Check:* a test with a mock receipt that throws an exception → there must **not** be a 200.
3. **F-07 — rate limit and budget on the payment path.** A limit per IP **and** per signer; a pre-check of the buyer's USDC balance before broadcast; a cap on `maxFeePerGas`; moving settlement out of the request thread.
4. **F-04 — remove the write from the read path.** `guard_stats()` must not do INSERT/DELETE; the liveness probe moves into a background loop, and the route reads the latest result from a cached read model.
5. **F-05 + F-06 — reorg semantics.** Minimum: mark the `onchain_sales` row as `reorged` and exclude it from the totals; add a depth check to the adoption path by nonce.

**Wave S2 — P1, information leakage and protection:**

6. **F-26 + F-27** — an admin guard for `/api/launch/health`; remove `payer wallet=`, `gas=` and the CDP detail from the public `/api/connectors`.
7. **F-28 + F-29** — version the Render configuration (or explicitly document why not); remove the admin token's fallback to `SESSION_SECRET`.
8. **Extend `tests/test_secret_hygiene.py`** to **discover** files by pattern, instead of checking 5 named ones (this is also the audit's recommendation for commit `9089ba5`).
9. **F-16** — `X-Payment-Proof` is replayable; consider binding it to IP/UA or a short TTL (a product decision).

**Already addressed (in `9089ba5`, but NOT in production):** F-13 (redact RPC), F-14 (redact the Telegram token), F-15 (`.dockerignore` + `secrets/`), F-30 (mask env).

### 5.2 ⚡ Performance and resilience

**Wave P1 — bottlenecks (based on audit data):**

1. **F-22 + F-31** — one **cached read model with single-flight** for `/api/dashboard/data`, `/api/dashboard-stats` **and** the paid `/api/stats`; indexes on `request_log(user_agent)`, `(source)`, `(funnel)`; aggregate `payment_guards` in SQL and index `consumed_at`.
   - *Context:* the cold build was ~41 s live at ~783K rows; locally 528 ms at 46 301 rows.
2. **F-09** — `psycopg_pool` + `connect_timeout` + `statement_timeout`; stop holding a single global lock over one shared connection (`dashboard_store.py:624` already shows the correct model).
3. **F-10** — `/health` should be **pure liveness** (no DB); readiness — a separate route. This eliminates the restart loop.
4. **F-11** — isolate and limit `/mcp/sse`: a cap on concurrent sessions **+** a rate limit. A free unlimited SSE that pins a thread for 15 s is the cheapest DoS in the project.
5. **F-23 + F-24 + F-25** — keep every blocking budget on the paid path below `--timeout 120`; explicit Stripe timeouts and `max_network_retries=0` for the request path; wrap the body of `_stripe_payment_snapshot_loop` in `try/except`.
6. **F-08 + F-12** — a list of RPC providers with health rotation + a process-wide cooldown with `Retry-After`; **one bounded** reorg watcher with a queue instead of a thread per payment; chunk `getLogs` through the already existing `_adaptive_get_logs`.
7. **Resolve the server question** (§3.4): confirm the start command in Render. If production really runs on the werkzeug dev server → move to gunicorn (the Procfile is already ready) **or** explicitly document the trade-off.

### 5.3 💰 Product and business model (the root of the problem)

**F-01 is a product decision, not a bug — the paywall cannot be "fixed" while a free copy exists.**

1. **Decide which field is actually being sold** and remove it from the public read model of `/api/dashboard-stats` and `/api/dashboard/data`: the history with `tx_hash`+`sender`, `whales`, the market snapshot.
   - **Option A (recommended):** the dashboard payload stays an aggregate (count, sum, channels), while the transaction history, the identities and the whale feed go **only** through the paid routes.
   - **Option B:** the dashboard payload goes behind an admin/session scope.
   - **Option C:** accept that the dashboard is marketing and not a SKU — but then remove `/api/sales`, `/api/stats` and `/api/v1/whaleflow` from the paid allow-list, so that billing is not decorative.
2. **F-19 — one price, one source.** Generate all public prices from `config.py`/`REAL_X402_ROUTES` instead of duplicating them in `agents.json`, `/mcp.json`, `ai-plugin.json`, openapi, the npm README, `/.well-known/x402`.
3. **F-20 — remove the phantom VIP $29** from `agents.json`, `/api/mcp/manifest` and the npm README (or implement it — but do not advertise it before it exists).
4. **F-18** — rename `payment.amount_usdc` to `amount_atomic` or return real USDC.
5. **F-21** — document `KRISTO_FREE_TIER_LIMIT` in `.env.example` and decide the value in production (0 together with a working demo path, or 1 with an honest description).
6. **Close the F1 gate** — fund the demo wallet (≥0.003 USDC + gas) and run `python scripts/e2e_nopay_probe.py --pay`. This is the **only** thing that has been pending since 25.09 and that blocks the agreed engineering wave.

### 5.4 📈 Visibility and traffic

> The full plan is in `docs/VISIBILITY_AND_TRAFFIC_STRATEGY.md`. Only the condensed version is here, ordered by dependency.

**Wave V1 — machine correctness (before any listing):**

1. **V-07 — bring `settlement_status` into agreement.** This is the most dangerous contradiction: two public surfaces say "discovery_only", two say "settled through facilitator". Every aggregator that reads both gets a contradiction.
2. **V-08 — generate `agents.json` and `/mcp.json` from `REAL_X402_ROUTES`** (6 routes, exact prices). At the moment `agents.json` gives 5, `/mcp.json` — a flat price of 0.005.
3. **V-06 — `llms.txt` should document both rails** (v2 `PAYMENT-SIGNATURE` as primary, legacy as fallback).
4. **V-10 — remove VIP $29 from `/api/mcp/manifest`.**
5. **V-03 — fix the sitemap:** remove the `noindex` `/dashboard` and the 302 redirects; add `/validation` and `/api/v1/quickstart`; add `<lastmod>`.
6. **V-05/V-09 — add the 6 sample routes** to openapi and to the free list in `llms.txt`; fix `whaleflow sample = $0.005` → `0.003` (`discovery.py:440`).
7. **V-12 — fix the npm README** (prices, free tier, both rails) and add `scripts.test`, types, `publishConfig`. Without this, "handles x402 paywalls automatically" is misleading.
8. **V-13 — make the demo path honest** under both free-tier modes (not "UNEXPECTED status 200").
9. **V-11 — fix OPTIONS preflight** on the paid routes (a 402 on preflight breaks browser clients).

**Wave V2 — human/organic surface:**

10. **V-02 — OG/Twitter/canonical/JSON-LD** in the public templates + one OG image 1200×630 (`static/og.png`). The cheapest change with the biggest effect on CTR when sharing.
11. **V-01 — add indexable HTML pages:** `/pricing`, `/api-reference` (rendered from openapi), `/how-x402-works`, `/status`, `/changelog`, + **6 per-route pages** (there is nothing to rank for the product itself). The raw material is available: `CHALLENGE_DESCRIPTIONS` (`main.py:108+`), the route metadata (`main.py:2074-2135`), the 6 sample schemas (`discovery.py:356-505`), the `/validation` facts (`discovery.py:103-204`), `docs/QUICK_START.md`, `ARCHITECTURE.md`.
12. **V-04 — link `/validation`** from the landing page and add it to the sitemap (right now it is an orphan).
13. **V-14 — GSC + Bing verification, an IndexNow key + `scripts/seo/ping_index.py`, sitemap ping.**
14. **Measurability:** lightweight self-hosted analytics **or** extending the existing `request_log` with `channel`/`utm_*`; **every** public link through `/f/<channel>`.
15. **V-15 — clean up the dead assets:** `agent_playground.html`, `docs/x402-client-example.js`. **DO NOT delete `public_activity.html`** — it is alive (see the note in the inventory).

**Wave V3 — distribution (after V1):**

16. **Check the CDP Bazaar presence** (commit `66a0ce4` is the precondition, but it is **not in production**) → if it is absent, a Listing Request with the ready text from `docs/SCAN_LISTING_EN.md`.
17. **Complete the 6 listings:** mcp.so (claim + description + "Authentication: x402"), Glama servers (fix the cause: `license: F` because of a "COMMERCIAL USE NOTICE" added after the MIT text; register as a **Hosted endpoint**), PulseMCP (waiting for the form to open), PayAPI recrawl, nohumans.directory (works — keep it), x402 Trust re-evaluation.
18. **Nudge PR #1308 and #13219**; do not open a new one until the old one is closed.
19. **Restructure the README:** the first 12 lines = 1 sentence + 1 working `curl` + 1 screenshot/GIF + 3 badges.
20. **Human channels — only after V1/V2:** Product Hunt (requires ≥3 social proof), Show HN, dev.to, Reddit (only an answer to a real question), X thread — all with an OG card and `/f/<channel>`.
21. **Lift the embargo** on `docs/OUTREACH_WAVE1.md` — 10 ready messages sit locked behind an engineering gate while the market is ~$1.2/month. Release at least the technical part (x402 Slack, CDP Discord), which does not require a funded wallet.

### 5.5 📚 Documentation and hygiene

1. **Synchronize the outdated material:** `PROJECT_CHRONOLOGY.md` (stops at 28.09), `PROJECT_STATUS.md` CURRENT STATE (28.09) and OPEN ITEMS, `TASK.md` (30.09) — replace them with the current state from §3.
2. **Fix the public claims:** `README.md` "11 resources" → 6; remove "Rug-risk checks" (:21); qualify "zero payment incidents" (:111).
3. **Add `.github/`:** a CI workflow (`pytest`) + badge, issue/PR templates, `SECURITY.md`, `CODEOWNERS`, dependabot, social preview.
4. **Add the missing root files:** `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `docs/README.md` (an index of the 49 flat files).
5. **Decide the fate of the 29 untracked entries** — some are real artifacts (the two audit documents, `TASK.md`), some are noise (`main_py_diff.txt`, `commit_54a7ba3_full.txt`, `kristo-intelligence/`).
6. **The MP4 files** (120 MB + 19.9 MB) — move them to GitHub Release assets, not into git.

---

## 6. Order of execution and gates

```
GATE 0 — owner decision (today, without code)
  ├── Do we publish the 2 commits (9089ba5 key-leaks + 66a0ce4 Bazaar trigger)?
  ├── Do we confirm the start command in Render (gunicorn vs python main.py)?
  └── Do we fund the demo wallet (F1 gate, open since 25.09)?
        │
        ├── if F1 is funded → the agreed engineering wave opens
        └── if not → the P0 fixes can still proceed (they do not depend on F1)

WAVE 1 — P0 payment integrity (highest priority)
  F-02 → F-03 → F-07 → F-04 → F-05/F-06
  Gate: test "accepted.amount=5000 + value=1 → rejection"; test "receipt exception → not 200"
        │
WAVE 2 — P1 resilience
  F-10 (liveness) → F-11 (SSE) → F-09 (pool) → F-22/F-31 (cache+indexes) → F-23/24/25 → F-08/F-12
  Gate: /health does not touch the DB; /mcp/sse has a cap; cold dashboard build under 2 s
        │
WAVE 3 — product (F-01) + machine correctness (V1)
  F-01 (decision on what is sold) → V-07 → V-08 → V-06 → V-03 → V-05/V-09 → V-12 → V-11
  Gate: all public surfaces give the same number of routes and the same prices;
        no "discovery_only" versus "settled" contradiction
        │
WAVE 4 — visibility (V2)
  V-02 (OG) → V-01 (HTML pages) → V-04 → V-14 (GSC/IndexNow/analytics + /f/)
  Gate: a valid OG card; ≥5 new indexable pages; every link with a channel
        │
WAVE 5 — distribution (V3) + hygiene (§5.5)
  Bazaar → 6 listings → PR nudge → README → human channels
  Gate: ≥3 confirmed listings (checked with fetch), ≥1 organic page in GSC
```

**Realistic KPIs (honest, with a market of ~$1.2/month):**

| Horizon | KPI |
|---|---|
| 7 days | 0 P0 defects with a test that catches them; GSC/Bing confirmed; a valid OG card |
| 30 days | ≥3 confirmed listings; ≥5 new indexable pages; npm ≥60 downloads/month; ≥5 external visitors/day with attribution |
| 60 days | ≥1 organic ranking in the top 50 for a long query; ≥1 external paying customer from a new channel; ≥100 npm downloads |
| 90 days | ≥10 external payers; 100% of payments attributed to a channel; ≥1 operator deal |

---

## 7. Open questions and risks

| # | Question | Why it matters | How it is closed |
|---|---|---|---|
| 1 | **`push` = auto-deploy, and 2 commits are not in production** | One stops key leaks; the other is a precondition for the Bazaar index. But the deploy also carries everything else in `main` | Owner decision; if needed — a separate branch/cherry-pick |
| 2 | **gunicorn or `python main.py` in production?** | It changes the capacity of the HTTP layer and production-readiness; a werkzeug dev server in production is a risk in itself | A check in the Render dashboard |
| 3 | **`KRISTO_FREE_TIER_LIMIT` in production = 0 or 1?** | It affects the demo path, all public claims and F-01 | A check in Render Environment (by the variable NAME) |
| 4 | **F-01 is a product decision** | It cannot be "fixed" technically; either you sell something unique, or billing is decorative | Owner decision (§5.3, option A/B/C) |
| 5 | **The market is ~$1.2/month with 2–4 buyers** | Traffic does not solve a structural market problem; the 90-day KPIs must be realistic | Acceptance + focus on machine channels and operator deals |
| 6 | **The F1 gate has blocked the engineering wave since 25.09** | Every "after F1" fix waits for one human action worth ~$0.003 | Funding the demo wallet |
| 7 | **The chronology and the status are 5 weeks behind** | Every new assistant/session reads outdated context and repeats mistakes | Synchronization (§5.5) |
| 8 | **29 untracked entries, incl. real artifacts** | The work exists only locally; a risk of loss; it pollutes `git status` | Classification: commit / delete / `.gitignore` |

---

## 8. Untouched invariants (owner constraints)

| Protected | Why |
|---|---|
| **x402 headers and the 402 envelope structure** | Working and validated (envelope-body-mirror); a change breaks compatibility with facilitators and with the parity tests |
| **Prices in `config.py`** | Publicly announced and verified on-chain |
| **`payTo` / fee receiver / `BOUND_BASE_FEE_RECEIVER`** | An on-chain address; a change breaks trust and revenue |
| **`GET /.well-known/x402-trust.txt`** | An external trust profile (grade B); removing it lowers the grade |
| **`secrets/` and `.env`** | Never opened; not touched |
| **The posts from 27.10** | Explicitly forbidden to edit |
| **`push` to `main`** | Auto-deploy on Render → every change is a production change |
| **Re-submitting the Base Builder Grant** | Explicitly forbidden |

**An additional rule from the history:** *two AI sessions do not push to the same repo at the same time* (`CHRONOLOGY:30-31`).

---

## 9. Appendices

### 9.1 Document map

| Document | Role | Status |
|---|---|---|
| `docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md` | Technical audit, F-01…F-40, P0/P1/P2 plan | Current as of `66a0ce4`; **F-13/14/15/30 are already addressed** in `9089ba5` |
| `docs/VISIBILITY_AND_TRAFFIC_STRATEGY.md` | Channel diagnostics, listings, 30/60/90 | Current |
| `docs/CONTEXT_AND_ROADMAP.md` | **This document** — consolidation | Current as of `9089ba5` |
| `docs/PROJECT_CHRONOLOGY.md` | Chronology up to 28.09 | **Outdated** — stops at 28.09 |
| `PROJECT_STATUS.md` | The book (CURRENT STATE / OPEN ITEMS / HISTORY) | CURRENT STATE = 28.09 → **outdated** |
| `TASK.md` | A snapshot of the tasks | **Outdated** (30.09) |
| `docs/LISTING_CHANNELS_AUDIT.md`, `docs/TRAFFIC_AUDIT.md`, `docs/SCAN_LISTING_DRAFT.md` | Previous visibility work | Useful, but partially duplicated |
| `docs/MARKET_WRITEUP.md`, `docs/GUARD_METHODOLOGY.md`, `docs/QUICK_START.md`, `ARCHITECTURE.md` | Raw material for public pages | Ready to use |

### 9.2 Authoritative constants (for cross-checking)

`FREE_TIER_LIMIT` = `KRISTO_FREE_TIER_LIMIT` (default **1**) `main.py:134` · `X402_PAID_ENDPOINTS` **6** · `X402_FREE_ENDPOINTS` **27** · `STATS_CACHE_TTL_SECONDS` 60 `main.py:3951` · `BLOCKCHAIN_POLL_INTERVAL` 30 · `KRISTO_DASHBOARD_SCAN_INTERVAL` 60 · `WHALEFLOW_SCAN_INTERVAL` 60 · `AGENT_POLL_INTERVAL` 300 · `KEEPALIVE_INTERVAL_SECONDS` 600 · `SALES_CHUNK_BLOCKS` 5000 · `WHALEFLOW_CHUNK_BLOCKS` 100 · `WHALE_THRESHOLD_USDC` 5 000 000 · `C2_LAG_WAIT_SECONDS_DEFAULT` 2.5 · `FACILITATOR_TIMEOUT` 15 · `BASE_RPC_URL` default `https://mainnet.base.org` `config.py:57`.

### 9.3 One sentence

> The project has a working payment rail and proven payments, but three independent defects — **a free copy of the paid product**, **a signature that is not authoritative**, and **a product the buyer cannot find** — hold revenue at $0.052, while the most important fix (stopping the key leaks) sits unpublished in git.

---

*This document was generated on 2026-11-03 at HEAD `9089ba5`. The verified facts are valid for this revision; `origin/main` is `ae216f2`. In the next session, `git log -3` and `git status` are cross-checked first.*
