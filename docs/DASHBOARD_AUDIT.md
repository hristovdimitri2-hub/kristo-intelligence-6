# DASHBOARD AUDIT — dashboards, sources, NEXUS (06.09, read-only)

Read-only audit: code reading + live HTTP checks. Zero code changes.
Safeguards respected: payTo/endpoint untouched, 154/154 PASS.

## 1. Table: dashboard → source → is it true

| Dashboard | URL/path | Data source | True? | Why |
|---|---|---|---|---|
| **Phone (Replit instance)** | Replit URL (on your side) | Own on-chain watcher — direct RPC scan of payTo | ✅ **TRUE** | Long-lived process without restarts: counters are not zeroed; reads the chain directly |
| **/dashboard** — widget "USDC volume / on-chain sales" (top) | `/api/dashboard-stats` | **RAM** daily stats + wallet watcher (on-chain scan of payTo) | ⚠️ with lag | the watcher shows the chain correctly, but the counters zero on deploy (correction of the old audit: NOT SQLite-backed) |
| **/dashboard** — "Real On-Chain Sales" section (bottom) | `/api/stats` + `/api/sales` (PAID endpoints) | **RAM** `_sales_history` | ❌ after deploy | `gunicorn` restarts on every deploy → RAM is zeroed → "$0.00 / 0 on-chain sales". Today we had 3 deploys |
| **/nexus** | `/nexus` (nexus_dashboard.html) | ① `/api/dashboard-stats` (30s) ② `/api/nexus/strategy` (admin — 401 for visitors) ③ **SIMULATED feed** (random generator of "discoveries") | ⚠️ mixed | Real numbers (①) + dead widget for visitors (②) + **fake data shown as live activity** (③) |
| **/sales/admin** — the "operational" dashboard ($79.02) | `/sales/admin` → `/api/admin/overview` | **CRM sqlite** (paid leads, `CRM_DATA_FILE`) + **Stripe snapshot** (if STRIPE_API_KEY is set) + RAM `onchain_revenue` | ⚠️ mixed | $79.02 = CRM/Stripe revenue (**not on-chain**); the onchain part is from RAM → zeroed |

### Hypotheses for today's discrepancy
- **(a) RAM counters, zeroed by the deploys — CONFIRMED.** `_sales_history` is an
  in-memory list in main.py (filled by the wallet watcher/settle path); every
  Render deploy restarts gunicorn → zero. Today: 3 deploys (Streamable HTTP,
  README, status).
- **(b) Two live instances — CONFIRMED architecturally.** The Replit instance
  (your phone) is a long-lived process with its own watcher on payTo → it shows
  the chain correctly. The Render instance was restarted 3× today → the RAM
  dashboards are zeroed. The Replit instance URL is not in the repo — it is on
  your side; their logic is identical (same code, different counter uptime).
- **(c) Different sources between the dashboards — CONFIRMED.** The table above:
  some widgets read SQLite/watcher (true), others — RAM (zeros), others —
  CRM/Stripe ($79.02), others — simulation.

## 2. Verdict on $79.02 and investor@crypto.io

- **$79.02 = the sum of CRM paid leads (+ Stripe snapshot, if the key is
  active)** in `/sales/admin` — it is NOT on-chain revenue. The on-chain revenue
  is $0.017 (5 transfers: 4 canaries + 1 external payer today).
- `investor@crypto.io` (17.08) is **a record in the CRM database** (sqlite, the
  file is on the Render disk), created through the VIP/Stripe flow in August.
  **I cannot determine live or test from the outside** — it depends on whether
  STRIPE_API_KEY in Render is `sk_live_…` or `sk_test_…`. **Check for you
  (1 min):** Stripe Dashboard → Payments → if the payment is in the Test mode
  list (or the key starts with `sk_test`) → test record; if it is in Live →
  real. Test data must NOT be confused with the on-chain revenue on the
  dashboard.

## 3. Verdict on NEXUS

**What it is:** a visual dashboard (`/nexus`, templates/nexus_dashboard.html)
with three sources: real polling of `/api/dashboard-stats` (30s), admin
`/api/nexus/strategy` (401 for visitors) and a **simulated feed** — a random
generator of "discoveries" (templates with random protocols/DEXes/amounts),
shown as live activity. This is advertised as the "NEXUS Discovery Engine".

**Is it connected to Kristo Intelligence?** Partially: it shows the numbers of
dashboard-stats (real), but the "Discovery Engine" itself is **`lib/agents/
market_evaluator.js`** — an independent Node module that scans CoinGecko
Trending / DeFiLlama / GitHub x402 repositories and sends Telegram suggestions.
**It is not started by main.py/Procfile** (it is launched manually with
`node …`) → **it does not run on Render at the moment**. It does not write to
the API's data (only `market_state.json` for the agent after manual approval).

**Is it an MCP tool?** NO — `tools/list` returns exactly 3 tools
(get_market_stats, get_onchain_sales, get_bot_status). NEXUS/the evaluator is
not there.

**Does it work at the moment?** The /nexus page opens (200), but: the strategy
widget is 401 for visitors (dead for them), the simulated feed "works" (it
shows made-up data), the evaluator does not run.

**Is it worth it as an MCP tool?** Not in its current form. The evaluator
proposes service ideas (not real data) and does not run in production. If you
ever revive it — first make it run, then think about MCP. Until then:
**do not offer it to anyone.**

## 4. Draft specification: ONE professional dashboard (no implementation)

**Principle: money and facts have ONE source — the chain.**

1. **Money (one source):** on-chain RPC scan of payTo — the code already exists
   (`competitor_recon.fetch_incoming_transfers` + `classify_transfers`).
   Write to **SQLite** (persistent), not RAM. Columns: tx, payer, amount, time,
   classification (canary / sampler / external-human).
2. **Payers:** from the same scan — `external_unique_payers` = the launch
   metric; the known sampler/crawler = the heartbeat section (already
   implemented in `listing_monitor.receiver_scan`).
3. **Requests:** from a **persistent log** (sqlite: timestamp, endpoint, UA,
   channel, payment?) — not RAM. The columns are already logged
   (`_live_request_log` has user_agent/referer/funnel) — only the persisting is
   missing.
4. **Band/ranks:** from `listing_monitor.fetch_state()` (PayAPI agent/get + the
   8 terms) — already written.
5. **Auto-refresh:** 30–60s (fetch of JSON, not a full reload).
6. **Remove/redirect:** the simulated NEXUS feed, the RAM-based widgets in
   /dashboard, the duplicate dashboards → one canonical dashboard, the remaining
   URLs redirect to it.
7. **Funds:** separate the "CRM/Stripe revenue" section with the label
   "off-chain, mode: live/test" — never mix them with the on-chain numbers.

**Safeguards for a future implementation:** payTo/endpoint untouched; the RAM
`_sales_history` stays for the payment layer (402 settle), but the dashboard
reads from the persistent store; the 154/154 tests must keep passing.

## 5. IMPLEMENTATION (06.09, after approval) — ONE canonical dashboard

**Built according to the specification from section 4. Zero changes to
payTo/paid endpoints. 164/164 tests PASS (154 old + 10 new).**

### What was built
- **`integrations/dashboard_store.py`** — persistent SQLite store
  (`data/dashboard_state.db`): `onchain_sales` (dedup by tx, classification
  canary/sampler/external), `request_log` (UA/funnel), `payapi_state`,
  `meta` (block watermark). One HTTP provider: public RPC, read-only
  eth_getLogs — the same logic as `competitor_recon`.
- **`main.py`**: `_record_real_sale` → also writes to the store (the payment
  path is never broken by this — try/except); `_capture_live_request` → writes
  every request to the store; a new background thread `dashboard-scan` (retro 30
  days at startup → incremental scan every 60s from the watermark → PayAPI
  refresh every 15 min); free endpoint **`GET /api/dashboard/data`**;
  `/dashboard` → the new dashboard; `/nexus` → 302 redirect to `/dashboard`.
- **`templates/dashboard.html`** — new dashboard, 4 sections, auto-refresh 45s:
  (a) On-Chain Sales [truth], (b) API Requests [log], (c) Listing & Ranking
  [PayAPI, "unscored/baseline" until the first scan lights up], (d) CRM/Stripe
  [OFF-CHAIN, hidden with a toggle, masked emails, NEVER in the total].
- **Removed:** the old RAM widgets, the simulated NEXUS feed, the dead
  nexus_dashboard.html. The Discovery module (`lib/agents/market_evaluator.js`)
  stays in the code — without a claim to "live" status.
- **`scripts/validate_retro_scan.py`** — a one-time check: real scan →
  comparison with the expected (5 transfers / $0.017 / external 0x4dB7).

### Result of the live validation after the deploy (06.09)
- **Deploy #1:** `/api/dashboard/data` → **$0.017 / 5 transfers / 1 external**,
  the history contains
  `2026-09-06 06:41:03 · $0.003 · EXTERNAL (0xb881f9dcdd…)`.
  The retro scan ran on Render (watermark block 50960727).
- **Deploy #2 (= the "restart does not zero" test):** AFTER a full gunicorn
  restart the numbers are the SAME (5 / $0.017), the watermark has advanced
  (50961026) — the persistent store works exactly like crm_sales.db.
  **PASS ✅**
- `/nexus` → 302 to `/dashboard`; `/api/dashboard-stats` → 200 (invariant).

### IMPORTANT discovery about section (d) CRM/Stripe
On the Render instance the CRM database (`data/crm_sales.db`) has **0 paid
records** and the Stripe snapshot returns **an empty list of payments** — that
is why section (d) shows $0.00. This is the honest state of Render.
**$79.02 / investor@crypto.io are NOT visible from Render** — they live in the
CRM database of the other instance (Replit/the phone), which is a separate
machine with a separate SQLite file; there is NO synchronization between the two
databases in the code.
=> Possible actions (your decision): (a) Replit remains the source for off-chain
sales and you watch the amounts there; (b) a one-time export/import of the paid
records to Render; (c) Stripe becomes the only off-chain source — then check in
the Stripe Dashboard whether the Render key is live/test and why the list is
empty (test records on another instance?).

### Why a restart no longer zeros the numbers
The data is in `data/dashboard_state.db` (persistent disk, like crm_sales.db).
The watchdog does not even rely on memory: the scan continues from the recorded
watermark block, and the dedup by tx hash makes a repeated write impossible.

### What to check as the owner (2 min, after deploy)
1. Open **`/dashboard`** → the On-Chain Sales section must show
   **$0.017 / 5 payments / 1 external**, and in the history — the line
   `2026-09-06 06:41:03 · $0.003 · EXTERNAL` with a link to BaseScan.
2. Open **Basescan** → the recipient address → compare: the latest transfers
   must be exactly these 5. A discrepancy = bug priority 0.
3. **The "restart does not zero" test**: write down the numbers → do a deploy
   (or wait for the next one) → open `/dashboard` again → the numbers must be
   the SAME or larger. If they are zeroed — bug priority 0.
4. **`/nexus`** → it must redirect you to `/dashboard`.
5. The CRM/Stripe section is hidden → "Show off-chain amounts" → you see
   $79.02 with the label OFF-CHAIN; it is NOT added to $0.017 anywhere on the
   dashboard.
6. (Optional) `python scripts/validate_retro_scan.py` locally → PASS.
