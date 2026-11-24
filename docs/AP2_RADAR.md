# AP2 RADAR — what changed since last time

Checked: 2026-11-22 18:00 UTC · read-only, public artifacts, no identities.

## Changes in monitored repos

### google-agentic-commerce/AP2

- No new commits since the last check.


### google-agentic-commerce/a2a-x402

- No new commits since the last check.


### Merit-Systems/x402scan

- `20bba0ff30` 2026-08-24 — remove trpc routers
  - file: apps/scan/src/trpc/routers/public/facilitator-observability.ts
  - file: apps/scan/src/trpc/routers/public/index.ts
  - file: apps/scan/src/trpc/routers/public/observability.ts
  - file: pnpm-lock.yaml
- `37c10ade3a` 2026-08-24 — remove upsert from proxy
  - file: apps/proxy/.env.example
  - file: apps/proxy/package.json
  - file: apps/proxy/src/routes/proxy.ts
  - file: apps/proxy/src/server.ts
- `80b9f357b1` 2026-08-24 — remove db from the scan and admin
  - file: apps/scan/package.json
  - file: apps/scan/src/app/(app)/_contexts/sorting/resource-search/context.ts
  - file: apps/scan/src/app/(app)/admin/resource-search/_components/table/columns.tsx
  - file: apps/scan/src/app/(app)/admin/resource-search/_components/table/results-table.tsx
  - file: apps/scan/src/env.ts
  - file: apps/scan/src/services/resource-search/clickhouse-search.ts
- `b305581faa` 2026-08-24 — remove trigger job and delete clickaus db since it is no longer used
  - file: .changeset/config.json
  - file: .changeset/pre.json
  - file: .github/workflows/deploy-analytics.yml
  - file: knip.config.ts
  - file: package.json
  - file: packages/internal/databases/analytics/.gitignore
- `4b29346e90` 2026-08-24 — Merge pull request #1096 from Merit-Systems/aec/cleanup-db
  - file: .changeset/config.json
  - file: .changeset/pre.json
  - file: .github/workflows/deploy-analytics.yml
  - file: apps/proxy/.env.example
  - file: apps/proxy/package.json
  - file: apps/proxy/src/routes/proxy.ts
- `f6fc282bf5` 2026-08-25 — Merge remote-tracking branch 'origin/main' into feat/svm-channel-schemes-indexing
  - file: .changeset/config.json
  - file: .changeset/pre.json
  - file: .github/workflows/deploy-analytics.yml
  - file: .oxlintrc.json
  - file: apps/proxy/.env.example
  - file: apps/proxy/package.json
- `32249e1c59` 2026-08-25 — chore(svm): type payout extractor input structurally, run sync tests in CI
  - file: package.json
  - file: sync/transfers/scripts/probe-channels.ts
  - file: sync/transfers/test/channels-query.test.ts
  - file: sync/transfers/trigger/chains/solana/bitquery-channels/query.ts
- `ab37d7322d` 2026-08-25 — fix(svm): track a sync-state cursor for the channels sync
  - file: sync/transfers/trigger/chains/solana/bitquery-channels/config.ts
  - file: sync/transfers/trigger/sync.ts
- `e2526d65fe` 2026-08-25 — Merge pull request #1091 from lgalabru/feat/svm-channel-schemes-indexing
  - file: package.json
  - file: packages/internal/databases/transfers/prisma/migrations/20260821000000_transfer_event_scheme/migration.sql
  - file: packages/internal/databases/transfers/prisma/schema.prisma
  - file: pnpm-lock.yaml
  - file: sync/transfers/db/services.ts
  - file: sync/transfers/package.json
- `f1f3428e5c` 2026-09-01 — Remove unused example servers and evals
  - file: .changeset/config.json
  - file: evals/.gitignore
  - file: evals/README.md
  - file: evals/fixtures/express-openapi/package.json
  - file: evals/fixtures/express-openapi/server.js
  - file: evals/fixtures/next-wellknown/app/.well-known/x402/route.js
- `3700a520dc` 2026-09-01 — Merge pull request #1130 from Merit-Systems/json/remove-example-servers-and-evals
  - file: .changeset/config.json
  - file: evals/.gitignore
  - file: evals/README.md
  - file: evals/fixtures/express-openapi/package.json
  - file: evals/fixtures/express-openapi/server.js
  - file: evals/fixtures/next-wellknown/app/.well-known/x402/route.js
- `dbe073f50d` 2026-09-16 — better warnings ← KEYWORDS: discovery
  - file: apps/scan/src/app/(app)/(home)/resources/register/_components/form.tsx
  - file: apps/scan/src/app/(app)/_components/discovery/discovery-actions.tsx
  - file: apps/scan/src/app/(app)/_components/discovery/discovery-panel.tsx
  - file: apps/scan/src/lib/discovery/favicon-blocked.test.ts
  - file: apps/scan/src/lib/discovery/favicon-blocked.ts
  - file: apps/scan/src/lib/discovery/server-host-mismatch.test.ts
- `131a5d3ca9` 2026-09-16 — rm cal link
  - file: apps/scan/src/app/(app)/(home)/resources/register/_components/form.tsx
- `c0c178675c` 2026-10-14 — rm cal link from register support links
  - file: apps/scan/src/app/(app)/(home)/resources/register/page.tsx
- `5732bb83c8` 2026-10-14 — fix build: use <a> for mailto link (typedRoutes rejects string href)
  - file: apps/scan/src/app/(app)/(home)/resources/register/_components/form.tsx


### developerfred/x402-conformance-probe

- `e6904c30d5` 2026-11-02 — feat: x402 conformance probe with 20 endpoints, fixtures, report, test endpoint, and paid retry
  - file: .gitignore
  - file: REPORTED.md
  - file: discover.ts
  - file: endpoints-discovered.json
  - file: fixtures/averray-verify-verify-runs.json
  - file: fixtures/browserbase-x402-endpoint.json
- `25883ed0b0` 2026-11-02 — feat: add REPORTED.md with issue links for all defects
  - file: REPORTED.md
- `9918c61ab1` 2026-11-02 — feat: expand to 30 endpoints, add response time/body size columns, CI workflow, Vercel deploy
  - file: .github/workflows/conformance.yml
  - file: .gitignore
  - file: fixtures/averray-verify-verify-runs.json
  - file: fixtures/browserbase-x402-endpoint.json
  - file: fixtures/coinmarketcap-dex-search.json
  - file: fixtures/exa-search-api.json
- `e0fb7d3161` 2026-11-02 — feat: add landing page and vercel config so production site has full documentation
  - file: index.html
- `8344b30a8b` 2026-11-02 — feat: track vercel.json in repo (remove from gitignore)
  - file: .gitignore
  - file: vercel.json
- `8d9bf500bc` 2026-11-02 — feat: melhorar diagramação do REPORTED.md e templates de issue no GitHub
  - file: .github/ISSUE_TEMPLATE/config.yml
  - file: .github/ISSUE_TEMPLATE/x402-conformance-defect.md
  - file: REPORTED.md
  - file: discover-all.ts
  - file: endpoints-discovered.json
  - file: generate-config.ts


### alchemyplatform/alchemy-x402

- `1cf2ff51ae` 2026-03-10 — Merge branch 'main' into chris/architecture-required
  - file: .changeset/config.json
  - file: .changeset/switch-changelog-github.md
  - file: .github/workflows/publish.yml
  - file: CHANGELOG.md
  - file: MAINTAINERS.md
  - file: package.json
- `99aa16e2b4` 2026-03-10 — Merge pull request #24 from alchemyplatform/chris/architecture-required
  - file: README.md
- `fdd3b3934d` 2026-03-11 — gp/revert changes - i give up for now (#36)
  - file: .github/workflows/publish.yml
  - file: package.json
- `2960f9edef` 2026-03-11 — chore: add changeset for v0.6.3 (#37)
  - file: .changeset/update-readme-solana-support.md
  - file: .claude/skills/changeset/SKILL.md
  - file: MAINTAINERS.md
- `a6337cf358` 2026-03-11 — chore: release v0.6.3
  - file: .changeset/update-readme-solana-support.md
  - file: CHANGELOG.md
  - file: package.json
- `a4b4575e38` 2026-03-11 — chore: add husky pre-commit hook with lint-staged (#38)
  - file: .husky/pre-commit
  - file: package.json
  - file: pnpm-lock.yaml
- `d6527e270e` 2026-03-11 — fix(ci): restore GitHub release creation in publish workflow (#39)
  - file: .changeset/fix-github-release.md
  - file: .github/workflows/publish.yml
- `24e04a21eb` 2026-03-11 — chore: release v0.6.4
  - file: .changeset/fix-github-release.md
  - file: CHANGELOG.md
  - file: package.json
- `fef4a164ec` 2026-03-11 — fix(ci): upgrade GitHub Actions to Node.js 24-compatible versions (#40)
  - file: .github/workflows/ci.yml
  - file: .github/workflows/publish.yml
- `b88e5d2c09` 2026-03-11 — gp/test OIDC again (#41)
  - file: .changeset/puny-doodles-thank.md
  - file: .github/workflows/publish.yml
- `9f40ecd33e` 2026-03-11 — chore: release v0.6.4
  - file: .changeset/puny-doodles-thank.md
- `97584c3122` 2026-03-11 — fix: add missing version bump and validate changeset files in CI (#42)
  - file: .changeset/fix-missed-version-bump.md
  - file: .github/workflows/ci.yml
- `34163bc903` 2026-03-11 — chore: release v0.6.5
  - file: .changeset/fix-missed-version-bump.md
  - file: CHANGELOG.md
  - file: package.json
- `3c691c6580` 2026-03-11 — fix: add repository URL to package.json for npm provenance verification (#43)
  - file: .changeset/fix-repository-url.md
  - file: package.json
- `b5253ae81d` 2026-03-11 — chore: release v0.6.6
  - file: .changeset/fix-repository-url.md
  - file: CHANGELOG.md
  - file: package.json


### tanaka-77/mart402-agent-kit

- `d8884449d5` 2026-07-22 — Initial commit
  - file: LICENSE
  - file: README.md
- `d58c305a44` 2026-07-22 — Create pay_and_parse.py
  - file: examples/python/pay_and_parse.py
- `eaa122b2e8` 2026-07-22 — Create extract.ts
  - file: examples/typescript/extract.ts
- `4809a6f695` 2026-07-22 — Create config.json
  - file: examples/mcp/config.json
- `bf9ea7c93d` 2026-07-22 — Create selftest.yml
  - file: .github/workflows/selftest.yml
- `d5800b9f65` 2026-07-22 — Update README.md
  - file: README.md


### node4dev/x402-agent-toolkit

- `26ff86cf8d` 2026-04-19 — Initial commit
- `753973ea1d` 2026-04-22 — feat: full rewrite for x402 v2 (v0.1.1)
  - file: README.md
  - file: package-lock.json
  - file: package.json
  - file: src/config.ts
  - file: src/index.ts
  - file: src/tools/sendToken.ts
- `e5a1d938d3` 2026-04-22 — docs: trim README for public repo
  - file: README.md
- `5403073e76` 2026-04-22 — feat: accept PRIVATE_KEY with or without 0x prefix
  - file: src/wallet.ts
- `31ce483671` 2026-04-25 — updated with additional tool
  - file: README.md
  - file: package.json
  - file: src/index.ts
  - file: src/tools/x402Quote.ts
  - file: src/tools/x402Request.ts
- `a15366a2bb` 2026-04-25 — Merge pull request #1 from node4dev/feat/x402-quote-tool
  - file: README.md
  - file: package.json
  - file: src/index.ts
  - file: src/tools/x402Quote.ts
  - file: src/tools/x402Request.ts


### haoruilee/awesome-agent-native-services

- (API error: HTTP 403)


### Drudley/indexagentica

- (API error: HTTP 403)


### Nikolife2016/pulsefeed-x402

- (API error: HTTP 403)


## The conversation (issues and PRs updated since last time)

### google-agentic-commerce/AP2

- (API error: HTTP 403)

### google-agentic-commerce/a2a-x402

- (API error: HTTP 403)

### Merit-Systems/x402scan

- (API error: HTTP 403)

### developerfred/x402-conformance-probe

- (API error: HTTP 403)

### alchemyplatform/alchemy-x402

- (API error: HTTP 403)

### tanaka-77/mart402-agent-kit

- (API error: HTTP 403)

### node4dev/x402-agent-toolkit

- (API error: HTTP 403)

### haoruilee/awesome-agent-native-services

- (API error: HTTP 403)

### Drudley/indexagentica

- (API error: HTTP 403)

### Nikolife2016/pulsefeed-x402

- (API error: HTTP 403)

## New public WG repos (search on every check)

- Nothing new publicly on the WG patterns.

## Census series (growth across the months)

- No census published yet in monitored repos.

## EVENTS (log · publication date + source)

### 2026-08-19 — Stripe acquires OpenRouter — a marketplace for pay-per-use AI APIs

- **Published:** 2026-08-19 · **recorded in the radar:** 2026-09-14
- **What:** Stripe announces that it is buying OpenRouter (a single entry point to
  hundreds of models priced per token). Verified on 14.09 in TWO independent public
  sources; both give 19.08.2026 (the publication date, not the date it was noticed).
- **SIGNAL:** micro-paid APIs are becoming a strategic raw material, and the
  settlement of micro-amounts — an infrastructure layer that a giant buys instead of
  building. It supports the project's thesis: agentic/micro-payments are the gateway
  to new markets.
- **Source:** stripe.com/newsroom — "Stripe agrees to acquire OpenRouter to help
  businesses optimise token routing and usage"; openrouter.ai/blog — "OpenRouter is
  Joining Stripe"

### 2026-09-18 — Solvador — confidential settlement on x402 (Slack #general)

- **Published:** 2026-09-18 · **recorded in the radar:** 2026-09-18
- **What:** The owner reports Solvador — a project for **confidential settlement**.
  The date comes from the daily digest of #general, submitted by the owner; I have not
  verified it against a public source (the channel is private and is not scanned).
- **SIGNAL:** The trust layer (niche #2) gets one more builder. It enters the
  **competitive map for #2** — we watch, without reacting.
- **Source:** x402 Slack #general (private) — daily digest from the owner

### 2026-09-18 — "402 Wall" (Sergei) — a trust/visibility project (Slack #general)

- **Published:** 2026-09-18 · **recorded in the radar:** 2026-09-18
- **What:** A project by Sergei focused on trust/visibility ("402 Wall"), shared in
  #general. Again from the owner's digest, not verified publicly.
- **SIGNAL:** A second independent builder in the trust/visibility layer — the same
  niche as ours, a different angle. We watch.
- **Source:** x402 Slack #general (private) — daily digest from the owner

### 2026-09-18 — Dr J — code402 + live MCP endpoint + x402-conformance (free offline verifier)

- **Published:** 2026-09-18 · **recorded in the radar:** 2026-09-18
- **What:** Dr J shows code402, a working MCP endpoint and **x402-conformance** — a
  FREE **offline verifier of receipts** (receipts).
- **SIGNAL:** A potential **PARTNER for cross-check**: an independent receipt verifier
  is exactly what makes our 4 audits verifiable from the outside. The cross-check
  proposal **has already been made in our reply** in #general.
- **Source:** x402 Slack #general (private) — our reply to Dr J, submitted by the owner

### 2026-09-18 — Brickken dev challenge — noted for later

- **Published:** 2026-09-18 · **recorded in the radar:** 2026-09-18
- **What:** A dev challenge announced by Brickken (digest of #general, from the owner).
- **SIGNAL:** Noted, WITHOUT commitment: a possible **RWA segment** — for a later
  stage, not a priority now.
- **Source:** x402 Slack #general (private) — daily digest from the owner

### 2026-09-18–2026-09-23 — x402 Slack #general (18–23.09): Miguel accepted the methodology · new x402 sellers · discovery/metadata positioning

- **Published:** 2026-09-18–2026-09-23 · **recorded in the radar:** 2026-09-27
- **What:** (1) Miguel publicly accepted the methodology + an invitation for a
  cross-check on their next payment (23.09); (2) new x402 sellers: PipeForge Inspector
  (Algorand+Bazaar), Berneta Price Watcher ($0.02/call, Base+Bazaar+x402scan), Aleks
  OpenChatNet ($1/24h, agent chat rooms) — the market is filling up, prices around
  5-300× ours; (3) discovery/metadata positioning is an active topic — an audience for
  Outreach wave 1.
- **SIGNAL:** Conclusion: the door is exactly this room, the timing is after
  merge+gate.
- **Source:** x402 Slack #general (private) — digest from the owner, period 18–23.09

### 2026-09-27 — External signal: the "Intelligence Contract" concept in AI automation circles

- **Published:** 2026-09-27 · **recorded in the radar:** 2026-09-27
- **What:** The "Intelligence Contract" concept (informational vs autonomous;
  tolerance calibration; explicit decision rights) is circulating in AI automation
  circles. OUR CORRESPONDENCE: the 425 code, the fail-closed calibration, the F4 retry
  right, guard-methodology = scattered pieces of exactly this document.
- **SIGNAL:** A niche for wave 3: "Intelligence Contract for x402 payments" —
  methodology v2. It is not being built now; it is recorded and waits for the first
  operator deals as proof that we sell from experience, not from theory.
- **Source:** External signal submitted by the owner (AI automation circles) — not a
  public artifact with a URL, not verified publicly

## THERMOMETERS (manually maintained — now in the template so they are not lost on overwrite)

1. Real daily x402 volume: **~$28k/day** (external data, 13.09) — note: **for
   revision** (the source and the measurement method have not been verified).
2. Flag — first public failure/scandal in agent payments: **not observed** (13.09).
3. Flag — a regulatory document on agent payments: **not observed** (13.09).
4. Trust layer (niche #2): **3+ independent builders** — Solvador (confidential
   settlement), "402 Wall" (Sergei), Dr J (code402 + x402-conformance) — 18.09, x402
   Slack #general. **Conclusion: the phase is confirmed.** Our advantage remains
   unchanged: **the published method + the 4 audits + a working cash path**.

## INDEXING — do we appear in the public x402 indexes?

| Date | Index | Total entries | Our entries |
|---|---|---|---|
| 2026-09-15 | Coinbase bazaar discovery (canonical) | 16035 | 0 |
| 2026-09-15 | x402scan | n/a | origin page exists, 0 resources shown |

- **Coinbase bazaar discovery (canonical) (2026-09-15):** Searched by host across the
  whole index — zero of our resources. Our 402 carries extensions.bazaar, and the last
  settlement came through an external facilitator (relayer 0x64cc42b1…). The mechanism
  by which the index is populated from settlements is NOT publicly documented — it is
  not invented, only observed.
- **x402scan (2026-09-15):** /server/<host> returns 200 (we are known as an origin),
  but the resources load client-side and are not visible in the payload. Registration
  requires a SIWX signature; the reading APIs are paid. Action for the owner:
  /resources/register with a wallet.

Method (fixed, so that it is comparable): Coinbase bazaar —
`GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources`, search for
our host in `items[].resource`. Registration in x402scan — from a browser with a
wallet (SIWX signature), one `register-origin` registers all our resources.

---
The Slack channels (wg-tax, wg-domain-discovery) are PRIVATE and are NOT
scanned — the owner reads them by eye, monthly.
