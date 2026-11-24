# PROJECT CHRONOLOGY — full chronology of the project

**Source:** `PROJECT_STATUS.md` (our book — the first entry up to today) +
verifiable commits/PRs for the 27.09 additions, marked explicitly.
**Format:** date → session/entry (the title of the section in the book) →
**Task / Decision / Conclusion**. The order is chronological: oldest at the top.
**Archive rule:** the archive is more reliable than the chat history — on a
discrepancy, believe what is written here/in the book.

---

## 2026-08-27 — FREEZE
The book starts with a decision to pause.
- **Task:** the project stops because the revenue priority is freelance/CV.
- **Decision:** "Project waits in Git at zero cost"; the entire resume context is
  gathered in this file (`State at freeze` + `Resume checklist`).
- **Conclusion/state:** prices — a single source (stats/arb 0.005, rug 0.003,
  whale 0.01, sales 0.05); nohumans 3× VERIFIED; x402scan 11 resources; baseline
  27.08 = $1.33M/30d, 21k sellers. **Known holes:** the receiver key is not
  confirmed, E2E has not passed, `WALLET_PRIVATE_KEY` in Render is a burnt/published
  address — to be replaced on resume, it is never funded.

## 2026-08-29 — Growth sprint (resume)
- **Task:** return after the freeze — storefront, catalogues, x402 rail.
- **Decision:** storefront fixes LIVE (receiver, honest micro-prices, favicon);
  x402scan: 11 resources; mystery-agent audit 23/23; new `services/connectors.py`
  — a registry of 9 connectors + **STANDARD x402 EIP-3009 rail** (X-PAYMENT via
  the facilitator) + L402 bridge + `/api/connectors` + quickstart (108/108 tests);
  PayAPI resubmission IN REVIEW; outreach kit ready (BlockRun = priority 1).
- **Conclusion:** ⚠️ coordination rule: **two AI sessions do not push at the same
  time** into one repo — one session at a time.

## 2026-09-02 — MILESTONE: the first real sale
- **Task:** the first live settlement from an external wallet.
- **Decision:** PayAPI canary passed — **0.005 USDC** from an external tester
  (`0x7e6b…2b1c`, block 50783187). The root-cause chain was patched over 5
  canaries: CDP JWT claims, CDP body schema, v2 exact = signed-transaction
  payload; the server accepts BOTH forms (v2 + EIP-3009) — 124/124 tests.
- **Correction (29.09; source = production DB + block timestamp):** the event
  is **02.09 13:28:41 UTC** (block 50783187 — verified on-chain), not 01.09.
  Chet's canaries: **02.09 ×3 + 03.09 ×1**; the first $0.005 (stats), the rest
  $0.003 — **$0.014 total**.
- **Conclusion:** the x402 path works live; a known cosmetic bug (double-record
  of the dashboard counter).

## 2026-09-02 — Session: second verified route + reviewer fixes
- **Task:** a second verified route + review fixes.
- **Decision/Conclusion:** the second route is verified; the reviewers' feedback
  is integrated (recorded as a separate session, with no code changes from 03.09).

## 2026-09-03 — Verification + label semantics; 🏁 PHASE COMPLETE
- **Task:** final verification and clarification of label semantics.
- **Decision:** **verification only, NOT A SINGLE code change** — confirmation,
  not rewriting. The phase is declared: **product verified → GO-TO-MARKET**.

## 2026-09-05 — Standing notes (owner's instruction)
- **Task:** rules valid for the entire remaining history.
- **Decision:** recorded in `📌 STANDING NOTES` — they are kept and applied in
  every subsequent session; next to them — `🗺 Plans on events` (the plans are
  executed on the event, there is no improvisation).

## 2026-09-06 — First external payer + Chet accepts the title
- **Task:** LAUNCH signal and working relations with PayAPI.
- **Decision:** **0x4dB7 paid 0.003 USDC** for `/api/v1/signal` (06:41 UTC) —
  VERDICT C: LAUNCH SIGNAL; fingerprint = moderate multi-API operator, NOT a
  sampler/crawler. Chet accepted the headline change (tickers on the first line).
- **Conclusion:** the first genuine external client + an accepted edit from the
  operator; next comes a "number" email and monitoring for a return (operator
  deal trigger).

## 2026-09-07 — Session: listing channels (audit + 3 actions)
- **Task:** where we actually exist and where we do not in the catalogues.
- **Decision:** a full audit of the channels (the results — in
  `docs/LISTING_CHANNELS_AUDIT.md`), 3 concrete actions + a final check of the
  human tasks; the side projects are distinguished.

## 2026-09-08 — Session: awesome-remote-mcp-servers — PR submitted
- **Task:** presence in the remote/MCP directory via a PR.
- **Decision/Conclusion:** the PR is submitted (recorded as a separate session).

## 2026-09-14 — The numbers became hard; the first unserved payer
Sections: „CORRECTION", „Stripe synchronization", „REVENUE BLOCKER", „The money
table is now in Postgres", „The incident the migration discovered", „Replay
locking is now in Postgres", „Fourth external payer".
- **Task:** the real numbers, deploy-resilient money data, a working Stripe.
- **Decision:** correction **$0.031 / 9 tx / 3 external** (and `0xA19F` IS a payer
  — the error was a paginated request); `onchain_sales` → Postgres (HistoryStore,
  one code/two dialects), **the seed became a bootstrap**; `payment_guards` →
  Postgres, **fail-closed**; the migration discovered an **HTTP 500** on the
  dashboard → patched (a finding from live hitting, not from tests); the 4th
  external ($0.003, `/api/v1/signal`) is **NOT served** — our node was lagging by
  1 block (recorded, NOT touched — fail-closed by decision).
- **Conclusion:** a deploy can no longer zero out the numbers; "we took money and
  did not deliver the product" is a priority-1 defect → it gives birth to the
  fix of 15.09.

## 2026-09-15 — Conversion fix: re-read the clock BEFORE you decline
Section: „Conversion fix: facilitator lag".
- **Task:** a paying agent is declined because the settlement block is 1 block
  AHEAD of our view — "our clock is old", not "the payment is invalid".
- **Decision:** `_confirmations_ok_with_lag_refresh()` — evaluation → one
  re-read of head (`head_refreshed_and_accepted`) → a ~2.5s wait + a retry
  (`waited_and_accepted`) → only then a decline (`node_lagging_rejected`).
  Fail-closed is preserved; a genuine depth deficit does not pass through the
  refresh.
- **Conclusion:** the philosophy was not relaxed, only the "race with the node"
  was legalised; 263 → **268 PASS**.

## 2026-09-16 — The new Stripe account + THE FIRST HUMAN PAYMENT
Sections: „THE NEW STRIPE ACCOUNT IS LIVE", „THE FIRST HUMAN PAYMENT".
- **Task:** the blocked account (14.09) → accepting real money.
- **Decision:** submission to **Managed Payments** (fallback chain of requests +
  `tax_code=txcd_10000000`); the trap rule (the key and `whsec_` change together)
  is closed automatically (`wire_stripe_webhook.py` + health/readiness scripts);
  **4 greens** on the final check. A real payment: **$29 Starter** —
  card → Stripe → webhook → CRM → dashboard, proven end to end (3 bugs, 2 fixed).
- **Conclusion:** the path for human money is closed end-to-end; the diagnostics
  of 14.09 showed the exact 400s in real time.

## 2026-09-17 — Infrastructure tidying + honest counting
Sections: „THREE DECISIONS ON RENDER", „RENDER HOURS", „THE $50.04 COST INCIDENT",
„0xE3BA: THE FINGERPRINT SAID MACHINE", „GLAMA SCORE", „THE TRUTH > THE NICE
NUMBER", „GLAMA CONNECTOR HTTP CHALLENGE", „WEEKLY MONITOR", „THE REFUND CYCLE
IS VISIBLE", „THE OFFICIAL MCP REGISTRY", „TELEGRAM BOT — second screen".
- **Task:** who is drawing from Render, who is spinning up a paid RPC, who is a
  real client, who is a refund — and where we exist publicly.
- **Decision:** the API stays on **Starter** (a cold start is more expensive than
  $7); the two travel-api services are suspended, `metal-leads-bot` is deleted;
  the whale scanner is **stopped by the owner** ($50.04 in 4 days on a paid RPC —
  the threshold afterwards became $5M); `0xE3BA` and the 4th "external" =
  **machines, not clients** (Truth > the nice number); Glama: the connector
  claimed, **score A 3.6**; the weekly monitor was **blind** → fixed; the first
  real **refund ($34.80)** became visible (subscription + CRM fields +
  dashboard); the Registry has us, but the entry is broken; the bot got
  attribution + `/whale`.
- **Conclusion:** the space is tidied (only our service is alive), the money is
  counted net, and the broken Registry entry opens the Glama wave.

## 2026-09-18 — The public exit + hard thresholds
Sections: „PUBLIC TELEGRAM CHANNEL", „THRESHOLD $5M + RETENTION 30 DAYS", „THE
FOUR VIP DECISIONS", „VIP FLOW: BROKEN WALLET LINK", „THE SCANNER CAUGHT UP WITH
THE TOP + WATERMARK DURABLE", „DIAGNOSIS 1M WHALES", „PUBLIC TRACK RECORD FEED",
„THE TRACK RECORD CLOCK".
- **Task:** an exit to the audience + data survival + an honest feed.
- **Decision:** the channel **t.me/Kristointeligent** is public; the whale
  threshold **$5M / retention 30d** (a product decision: 53/day instead of
  227,000 noise); 4 VIP decisions (private chat, claim with confirmation,
  Postgres invitations, buttons in private); the watermarks became durable; the
  whaleflow table (**458 MB of 1 GB**) is a recorded risk before every re-run;
  the feed is **frozen BEFORE the first signal** (6 rules, guarded by a test).
- **Conclusion:** the public speaks only verified things; the database has a
  ceiling that must be audible.

## 2026-09-19 — PulseMCP: nothing is submitted (waiting)
Section: „PULSEMCP — PENDING SUBMISSION".
- **Task:** do they accept us automatically and is a manual submission worth it?
- **Decision:** `/submit` is **paused** (since 03.09); their channel is the
  Registry, and it already holds us correctly (v6.0.0, 0.003–0.005) ⇒ **nothing
  is sent**; the ready block waits in `docs/PULSEMCP_SUBMISSION_READY.md`.
- **Conclusion:** the next step is human and conditional — silence is an answer.

## 2026-09-20 — Ranking pulse (recorded on 21.09)
- **Result:** ABSENT for eth/kaito/ondo/degen; **#1 defi**, #2 for signals.
- **Conclusion:** PayAPI reads the old listing description — the words outside it
  are the words we do not exist by.

## 2026-09-21 — Hash anchor + end of the ranking
Sections: „HASH-ANCHOR ON THE STANDARD RAIL", „RANKING — FINAL EDIT".
- **Task:** a reorg with the SAME height passes by C2 (Miguel, Problem 2); what
  actually drives our ranking?
- **Decision:** `payment_guards` carries `block_number` + `block_hash` (zero
  additional RPC), `_detect_reorgs()` sees a hash change at a preserved height
  → `c2_reorg_detected`; **the threshold was NOT touched** (1 conf remains).
  The ranking: PayAPI has **no auto-recrawl** → the checkpoints are discarded,
  the protocol = we wait for Chet → one check → an entry; the "yes to both"
  letter is sent.
- **Conclusion:** payments are hash-anchored; "a clock is built only after a
  proven schedule".

## 2026-09-22 — AUDIT №4 + the Glama epic (day 1) + a sleeping STDIO bridge
Sections: „AUDIT №4 (F1/F3/F5)", „GLAMA API KEY", „The comment in PR #13219",
„GLAMA support ticket", „GLAMA: the listing is LIVE, the badge not yet",
„SLEEPING BRIDGE FOR STDIO".
- **Task:** the x402 path after the audits; entry into Glama; readiness for
  stdio-only hosting.
- **Decision:** F1 = **nonce-idempotent settle** (key = EIP-3009 nonce, never
  payer+amount), F3 = **425 settlement_in_flight** on a C2 decline, F5 = F5 hint
  ~24s, delivery-state columns + recovery (`_admit_undelivered_payment`); the PR
  bodies moved to **standard base64** (audit №5); Glama: a key + a weekly pulse,
  the listing alive (`claimed: true`), the REMIP/Remote option found (a connector
  instead of a Dockerfile), a ticket with Frank; the STDIO bridge is **recorded,
  not activated** (11 tests guard this).
- **Conclusion:** idempotency is locked to a **nonce, not an amount**; Glama
  gives us ownership, not just a listing.

## 2026-09-23 — Audit №5 + Glama CLAIM FINAL + (02:27) start of the reorg loop
Sections: „Audit №5 — fixing the receipt for the SDK clients"; „GLAMA CLAIM FINAL".
- **Task:** the SDK clients to read the receipt; finalising the Glama claim.
- **Decision:** `PAYMENT-RESPONSE`/`PAYMENT-REQUIRED` → STANDARD base64 (dual
  compat decoder); the Glama connector **claimed** via an HTTP challenge —
  Listing details/Health/Analytics unlocked (**TDQS 4.7, 3 tools, healthy**).
  The same night (02:27) — the first `c2_reorg_detected` on a placeholder hash
  (recorded later as a loop).
- **Conclusion:** the Glama thread is **closed** (management via connector
  admin); the hidden defect (placeholder hash) is being born right now.

## 2026-09-24 — CHET RE-WAREHOUSE letter
- **Task:** a reaction to the re-warehouse snapshot.
- **Decision/Conclusion:** the letter is ready (auto-campaign or re-check) — **we
  await a reaction**; nothing was sent without a signal.

## 2026-09-25 — Closing the loop: reorg loop + F1 gate
Sections: „OPEN ROOTS AND DEBTS", „c2_reorg_detected LOOP — DIAGNOSIS +
FIX", „F1 GATE".
- **Task:** `c2_reorg_detected` spinning 1273 times on one and the same tx; how
  alive is the x402 path really (F1 gate)?
- **Decision:** the diagnosis is **CONFIRMED** — the detector was comparing a
  placeholder (`000…0`) against a real hash; fix `3266a9f` (all-zeros = "no
  anchor"), 1273 records deleted, **412/412**; the gate: A1 = the path has
  **never been walked** live, A2 = no-pay E2E **all green**, the full proof
  **awaits WALLET**; 4 open roots recorded (the placeholder-hash root
  clarified).
- **Conclusion:** the noise is dead, the signal alive; the only waiter is the
  wallet.

## 2026-09-27 — Token hygiene, PRs and ghosts
Sections: „GitHub PAT 'thd-ice'", „PR #1308 — the phantoms cleaned up", „The last
living ghost — Vercel stopped", „PR DISCIPLINE"; + AP2 radar events (log).
- **Task:** checking an old PAT; phantom prices in live PR bodies; a surviving
  v5 Vercel deployment; a lesson for future reviews.
- **Decision:** the PAT is **used nowhere → deleted from GitHub** (rule:
  excess tokens are deleted, not left to expire); #1308 body → real prices
  ($0.003–0.005, "No free tier", no VIP/discount) — **lesson: a PR body only via
  `--body-file`** (PowerShell eats the `$`s); the Vercel ghost is **stopped by
  the owner** (404 on both `/mcp` and the root) ⇒ the execution of 17.09 is
  complete — zero live v5 surfaces; **PR discipline** is recorded (first the
  scope: goal/author/size/thread, then the lines).
- **Conclusion:** "better a dead link than a live lie — on any hosting"; the PR
  descriptions live outside the sweep tests.

## 2026-09-28 (UTC) — Live additions from the session (verifiable commits)
Not in the book (they were written after it); source = git/PR/API:
- **PR #13219 (awesome-mcp-servers):** the conflict resolved by the procedure of
  22.09 (a new branch from upstream/main, the line re-inserted, force-push) →
  `mergeable: clean`, `has-glama` alive; the body **rewritten** as #1308 (real
  prices, `--body-file`, grep check); the **Note** about travel-api/#11557/
  #1081 removed from both PRs (13219 + 1308).
- **Sentinel:** #13219 added to `WATCHED_PRS`; **Variant B** — the boot message
  removed (quiet start, +test); **PR watcher hardening**: durable baseline
  `pr_watch_state` (like payment_guards), a missing baseline = an entry without a
  message, open→merged/closed alerts even after a restart, a conflict alert
  **only for open** + `unknown` does not overwrite the baseline, a `"?"` fetch
  error preserves the line; payment alerts → `TELEGRAM_VIP_CHAT_ID` (the private
  chat), the rest in the channel — **420+ tests**.
- **Security:** `TELEGRAM_WEBHOOK_SECRET` **rotated** (env PUT + setWebhook with
  the same URL, getWebhookInfo clean, e2e `/vip` → 200 `vip_offer`); rule: **env
  variables are enumerated by NAME only**. **The date is 28.09 (confirmed by
  logs on 30.09):** rejection 401 at 08:18:48 → e2e 200 at 08:25:52 UTC, a
  re-check 19:03:42; on 27.09 the webhook events are only boot registrations
  (0 e2e/rejection) — `PROJECT_STATUS` had recorded "27.09" and is corrected.
- **Tools:** `scripts/_pr_watch_select.py` (a read-only SELECT through a Render
  job — today's routes: `/v1/services/{sid}/jobs/{id}` + `/v1/logs?ownerId&resource`).
- **This archive:** `docs/PROJECT_CHRONOLOGY.md` — the entire history in one place.

---

**Footer:** source = `PROJECT_STATUS.md` (the book) + verifiable commits/PR/API
results. If the chat history and this file diverge — this file is believed.
Sessions continue to be appended to the book; this archive is updated from it.

<!-- CONT -->
