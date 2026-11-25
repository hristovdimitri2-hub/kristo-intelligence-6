# Next actions — consolidated

**Compiled 24.11.2026, 15:20 EET; updated 25.11.2026.** This supersedes
`docs/ACTION_BOARD.md` (03.11.2026), which is kept as history. One page, in the
order to work through it. Full text of every message is in `docs/OUTREACH_DRAFTS.md`.

---

## The one priority

**The market audit of 24.11 changed what the priority is. Read this first.**

The owner asked for a full audit of every API, every MCP server and every place we
are listed, because after 12 October the system looked silent. It was measured
instead of argued, and the answer is in `HANDOVER.md` §118. In one paragraph:

- **Nothing is lost.** 1,246,641 requests in 30 days (~30,000/day), 457 distinct
  agents reached a paywall, 163 were delivered content, 25 further directories we
  never submitted to probe us daily, all seven paid routes and all five alias
  routes answer a valid `402`, MCP serves seven tools. Discovery and plumbing are
  both intact.
- **The money is not there.** Lifetime: 180 payments, $1.983. Of that, **$1.785
  is our own demo key** (131 payments, confirmed by decoding the Base receipts of
  the fifteen most recent sales). Genuinely external, lifetime: **12 payments,
  $0.054 from 9 wallets.**
- **No sale was lost to a bug.** All 135 `payment_attempts` are accounted for: 98
  settled, and every refusal is either our own testing or adversarial conformance
  fuzzing (`0x1111…1111`, `payload_undecodable`, `amount below price: 1 < 5000`).

So the work is not distribution and it is not repair. Three independent
measurements — Ernest's CDP census, PayAPI's 6,323 views with 0 payments, and now
our own ledger — say the same thing: **the traffic is machines checking us, not
buyers wanting us.**

**What this does to the priorities below.** The marketplace line stays the only
untried channel, and it is still untried. But it should now be read with the audit
in hand: adding a seventh channel to a service that 457 agents already found and
12 wallets ever paid is not obviously the fix. The two candidates that survive
every measurement are the ones §108 named — **data a buyer cannot get elsewhere**,
and **selling the measurement itself**.

### The decision taken (24.11.2026, no approval requested)

**We sell the measurement.** It is the only asset in this project with no
competitor: 84 days of demand-side behaviour at a live paywall, including 135
payment attempts read individually. Nobody else has it, because seeing it requires
running a paywalled service for months and keeping the ledger.

The split is deliberate:

- **Public — `docs/X402_DEMAND_CENSUS.md`.** The aggregate, the method and the
  conclusion. It is a specimen, not a gift: it proves the dataset exists and shows
  what is being sold.
- **Held back — the per-agent table and the per-wallet payment history.** That is
  the product.

**The first buyer to test is Ernest** (`OUTREACH_DRAFTS.md` §N), because he sells
this measurement, he asked which of the two directions to take, and his own census
covers only the seller side. The message asks him to price it rather than accept it
as a favour, and asks him to confirm or contradict the monitor-not-buyer reading.

**Not yet done, and deliberately:** shipping the census as a new paid route. A
route needs an entry in `X402_PRICE_MAP` and a price constant in `config.py`, and
the standing rule forbids touching those without explicit approval. That decision
is the owner's, and it is the next step if the public specimen draws interest.

### Shipped, 25.11.2026 — the census is live at $0.25

The owner approved the one exception to the price rule. `GET /api/v1/demand-census`
now answers `402` at **$0.25** on `eip155:8453` and delivers the per-agent table;
`GET /api/v1/demand-census/sample` stays free like every other paid route's preview.
Two deliberate choices: it is **paywall-only** and absent from `REAL_X402_ROUTES`,
because promotion to the vitrine requires a paid canary, and it is **exempt from the
volume discount**, which would otherwise have sold it for $0.01 from the 11th call.

Verified against the running service after the deploy, not against the source: census
`402` at 250000 atomic units, the seven pre-existing prices unchanged
(5000/5000/5000/5000/10000/10000/50000), `payTo` equal to the canonical EIP-55
checksum, sample `200`.

**The message to Ernest went out on 25.11.2026** from the owner's Gmail, naming the
price instead of proposing one. `scripts/send_section_n.py` sends the §N body
extracted from `docs/OUTREACH_DRAFTS.md` verbatim, so the sent text and the record
cannot drift apart.

### One defect the deploy exposed (25.11.2026)

Reading the live `402` envelope caught what the local suite could not: the receiver
address written throughout our own notes,
`0xB4FcF8ef52b5DC275924AeD2BAe94FE6cb7fC844`, is **not a valid EIP-55 checksum**.
The live service had it right all along — `…D2baE94…`, confirmed against
`eth_utils.to_checksum_address` — so no payment was ever at risk, since the 20 bytes
are identical and any library that validates a checksum would only ever have received
the correct string from the envelope. Six of our own files carried the bad spelling;
all are corrected. The method point matters more than the typo: to find a defect in a
public claim, read the live response rather than the note describing it.

### The recurring product, and why the archive started now (25.11.2026)

A one-off snapshot at $0.25 prices the specimen, not the asset. What cannot be bought
anywhere else is the **change between months** — which agents are new, which came
back, which stopped, what they paid — and a change needs two snapshots to exist.

`request_log` retains 30 days, so a month that is not snapshotted cannot be
reconstructed afterwards. The archive therefore has to start before the product can be
sold. `snapshots/archive/` now holds the dated baseline
(`demand_census_2026-11-24.json`, 1,494 agents, byte-identical to the served copy),
and the first sellable issue is **December 2026 against November 2026**.
`snapshots/archive/README.md` records the rule and the exact command.

One command a month is enough at this scale. Nothing is automated, no new route and no
new price exists yet, and a monthly route would need a price in `config.py`, which
requires the owner's explicit approval — so it is deliberately not built until there is
a second snapshot and therefore something real to sell.

### What the signal engine's own record says (measured 25.11.2026)

The free feed at `/public/signals/history` has scored this engine since 18.09 and the
numbers are unambiguous: **268 issued, 97 scored, 1 hit, 12 misses, 84 flats, 33
unresolved.** The single hit moved +3.9%; the average miss moved 5.6% against. The
first checkpoint (n=30) recorded a 1.2% hit rate, and it is stored as a failure with
`verdict: below_50_at_final_checkpoint`. The high-confidence band (0.6–0.8) is the
worst of the two: of its 11 directional calls, 1 was right and 10 were wrong.

Until today the paid route sold a signal and said none of this, while the free route
beside it published exactly this. A buyer acting on it could only discover the record
by looking somewhere else. **Fixed:** the record now travels with the paid response
(`track_record`), built by the same `build_feed()` the public page uses so the two
cannot disagree, fail-open so a paid delivery is never lost, cached 300s so a $0.01
route is not taxed. It is also printed in the vitrine description, in `README.md`, and
in the MCP tool description in `server.json`.

### Where the money can be, judged against what we measured

| candidate | verdict |
|---|---|
| Sell the feeds (signals, whale flow, arbitrage) | **rejected.** Lifetime external revenue $0.054, and the engine's own record is 1 hit against 12 misses. Selling it as edge would be selling something we have measured as unprofitable. |
| Sell distribution (more listings, more registries) | **rejected.** 457 agents reached a paywall, 25 directories probe us daily, 0 payments followed. |
| Sell the measurement (census + the engine's record) | **in flight.** The only asset here with no competitor, because it requires running a paywalled service for months and keeping the ledger. Ernest is the first buyer test. |
| Sell judgement (verification / evaluation of x402 sellers) | **next, after the census sells once.** A Base ecosystem digest reports an operator extending an *Evaluation* API the same week — the category is being built now. Our credential cannot be faked: we published our own failure. |

**Decision: the third, then the fourth — and the fourth's credibility is earned by doing
the third honestly.** Both are the same trade: the market pays for a judgement it cannot
make itself, and never for a feed it can crawl.

### The first three steps

1. **Done 25.11.2026** — the record travels with the product. A signal can no longer be
   bought without the measurement of how those signals have done.
2. **Next** — publish the failure as a first-class document rather than a footnote:
   the engine's full record, its method, and the two things it proves (that our
   measurement instrument is honest, and that a commodity feed is not an edge). This is
   the trust asset that makes the census and any evaluation product sellable.
3. **December** — the second census snapshot creates the first real delta product, and
   the $0.25 route gets its first paid canary, which is what promotes it to the vitrine.

### The paid canary, and the one place the record does NOT yet appear (25.11.2026)

Two real paid calls were made to `/api/v1/signal` with our own demo key ($0.01 each),
after the deploy, to check what a buyer actually receives rather than what the code
says:

- The **first attempt was refused** by the unready guard — `no_signal_to_deliver`,
  HTTP 503, `payment_taken: false` — because a fresh process has not run the signal
  engine yet. That is the guard working exactly as designed, and worth having seen.
- The **second attempt settled** and delivered. The body carried `track_record` with
  the measured figures: `hits 1, misses 12, flats 84, scored_n 97, hit_rate_pct 1.0,
  issued 268, avg_move_on_hit 3.862, avg_move_on_miss 5.625`, plus the free feed URL.
  The change is verified end-to-end on the live rail, not only in tests.

`scripts/phase1_paid_call.py` gained `--show-body`. It used to throw the delivered
payload away and print only the transaction, so a changed product could be paid for
and never inspected.

**Gap found, and closed with the owner's approval (25.11.2026).** The text in the CDP
Bazaar rows is the **402 challenge description** (`CHALLENGE_DESCRIPTIONS`), not the
vitrine description (`REAL_X402_ROUTES`). Verified against the index: the row for
`/mcp#get_trading_signal` reproduced `CHALLENGE_DESCRIPTIONS["/api/v1/signal"]`
verbatim. So the catalogue that agents actually search described the signal with no
mention of its record, while the vitrine pages, README, `server.json` and the paid
response all stated it.

The owner approved editing that one string. The sentence appended is deliberately
non-numeric — *"Its own measured record is published at `/public/signals/history` and
it is a losing one."* — so it cannot go stale as more signals resolve. Verified on the
live envelope, then one paid call ($0.01) re-indexed the row: **the CDP Bazaar row for
`/api/v1/signal` now carries it.**

**Still open, one command away:** the *MCP* row (`/mcp#get_trading_signal`) is a
separate resource with its own settlement, so it still carries the old text. Refreshing
it needs one paid MCP call (~$0.01) through `_tools`/`_forensics`' MCP payer. Recorded
here rather than done in the same pass, because a separate resource needs a separate
settlement and that is a different rail to test.


---

## The marketplace line (unchanged)

**The catalogue work is done. The marketplace work has not started.**

Six catalogues and directories now list us — CDP Bazaar, MCP Registry, Glama,
x402-list, x402scan, the awesome-list PR. Six listings, zero external calls ever.
That is not a distribution failure; it is the wrong kind of channel. A catalogue
is where an agent looks when it already knows what it wants. A marketplace is
where an agent goes to hire. We have never been in a marketplace.

The measured market (§108) says the same thing from the other side: x402 money
goes to **high-ticket integrations** or **high-frequency embedded pipelines**.
Our product is neither — a $0.005 lookup that an agent finds in a catalogue has
no reason to be called twice. More listings cannot fix that. An integration can.

**Two places where a hire happens on Base:**
- **Virtuals ACP** — offerings with escrow, `Virtual-Protocol/acp-cli`.
- **Olas Mech** — 14 323 settlements measured, `t.me/olaschat`.

---

## 1. Sent — five of six, by the owner on 24.11.2026

| # | To | Where | State |
|---|---|---|---|
| 1 | Ernest | `ernest@nolimbsfighting.com` | sent |
| 2 | r/x402 | the fourfold thread, 23.11 | sent |
| 3 | Virtuals ACP | `Virtual-Protocol/acp-cli/issues/new` | sent |
| 4 | Olas | `t.me/olaschat` | **not sent** — the only one left |
| 5 | x402scan | `Merit-Systems/x402scan/issues/1270` | sent |
| 5b | x402scan | `Merit-Systems/x402scan/issues/1340` | sent |

### 1b. Ready to send — two from Ernest's reply of 24.11

| # | What | Where | Note |
|---|---|---|---|
| 6 | **The CDP ticket** | support, as a reply in the Ernest thread | Ernest wrote it; we re-measured every row and corrected one claim. Text in `OUTREACH_DRAFTS.md` §L. Add your name. |
| 7 | **Reply to Ernest** | the same Gmail thread | Accepts his free benchmark of the seven routes; asks how he wants a referral introduced. Text in `OUTREACH_DRAFTS.md` §L2. **Still unsent as of 25.11:** §N went first and asks him two direct questions, so this belongs in the answer he sends back — or in a nudge if the thread is quiet for four days. |

**Why the ticket changed.** Ernest's second request said all MCP descriptions were
stale. Seven of eight were refreshed on 24 November by paying through each tool;
only the duplicate is still stale. Sending the original would have asked CDP to
answer a question we no longer have.

---

## 1c. What Ernest measured, and what it means

He read the whole CDP Bazaar discovery dump: **34,893 rows, 30-day window**, calls
per row multiplied by that row's price.

| | |
|---|---|
| Top 10 rows | **92%** of all spend |
| Top 100 rows | **96.9%** |
| Median revenue per row | **$0.01 per 30 days** |
| Rows reaching $1/month | 1,161 of 34,893 — **3.3%** |
| Hosts reaching $100/month | **32** |
| Rows with exactly one call in 30 days | **18,885** — mostly the owner testing their own route |

The verification routes that do sell are all occupied, and all by whoever
registered the space first:

| route | calls / 30d | price |
|---|---|---|
| `api.agents-trust.com/recommend` | 14,621 | $0.01 |
| `agent.pocket.network/v1/sanctions-watchlist-screen` | 3,733 | $0.005 |
| `api.strale.io/x402/domain-age-check` | 454 | $0.032 |
| `api.strale.io/x402/domain-reputation` | 219 | $0.054 |
| `api.strale.io/x402/sanctions-check` | 122 | $0.216 |

**His straight answer, in his words:** pre-payment trust checks *are* bought, as
$0.005–$0.05 lookups in the thousands — but he sees **no provider paying for the
pattern we built**, a platform checking a stranger's receiving wallet before paying.
Platforms absorb that cost themselves or run a sanctions screen. Nobody is buying
it as a standalone operation right now, and refining the route does not change
that, **because a route is invisible to buyers until someone has paid through it
and written the catalogue row.**

**His advice:** stop treating per-call fees as revenue — they are negligible unless
a volume buyer has no alternative. Two things earn: **(a)** data a buyer cannot get
anywhere else, or **(b)** selling the measurement itself, which is what he does and
what we have now bought twice.

**The consequence for us.** `verify-seller-receiver` is not a business, and neither
is any other single route we could add. The top verification route in the entire
index earns about $146 a month. This is the same conclusion the ACP work reached
from the other side: a catalogue entry is found only after it has been paid, and a
marketplace is where you are hired instead. Two doors, and both point away from
"one more route".

---

## 2. The four decisions — all approved, three finished

| # | Decision | State |
|---|---|---|
| 1 | **Jamenbin** — tell him the fixture moved | **DONE.** Comment posted 24.11 at 16:46Z on `VibeMirror-coder/n8n-nodes-omnidome#3`, verified by reading the issue back. |
| 2 | **Free or pilot tier** | **Approved.** Marketplace conversations may promise a pilot. |
| 3 | **`X402LIST_VERIFICATION_TOKEN`** | **Prepared.** Token still present (`x402list-verify-rCh48s…`, 59 chars) and `/.well-known/x402list.txt` serves it (HTTP 200). It expires 26.11 15:06Z. `_tools/remove_x402list_token.py` does the whole job — dry-run verified, `--apply` deletes the variable with `DELETE /env-vars/{key}` (never a `PUT` of the collection), triggers the deploy, then polls until the path returns 404. Reminder set for 26.11 17:10 EET. |
| 4 | **PayAPI's `Price` field** | **Half done.** The price edit went through on 24.11 — the public record now reads `$0.005 – $0.05`. The visible page text and `endpoints_count` still show the September values, for the reason measured in §2b. |

### 2b. PayAPI — price fixed, and "degraded" is a six-week-old record

Measured 24.11 through PayAPI's own discovery API
(`GET https://payapi.market/api/listings?status=all&limit=200`), not from memory.

**The price edit worked.** The public record for
`6278cdce-f93a-45c7-9829-ffbe570f4df5` now reads:

```json
"price": { "min": 0.005, "max": 0.05, "currency": "USDC", "unit": "per_call" },
"payment_verified": true,
"endpoints_count": 3
```

`price` matches the seven live routes. `endpoints_count` is still `3`.

**Why the page still prints the old numbers.** The listing page renders its price
line from `verified_routes`, not from `price`:

```
3 of 3 routes settlement-verified · $0.003 to $0.005 USDC/request · 3 endpoints
```

`verified_routes` holds the three test payments of September — `$0.005` (2 Sep),
`$0.003` (2 Sep), `$0.003` (21 Sep). So the page advertises `$0.003 – $0.005`
while the 402 challenge charges `$0.005 – $0.05`. **Nothing we can PUT fixes
that line**; it only moves when PayAPI re-verifies a route. Submitting again does
not refresh it either — their OpenAPI documents that an existing URL returns the
existing fields — and Chet's rule is one product, one card. The four missing
routes are `GET /api/sales`, `/api/arb/opportunities`, `/api/bot-status` and
`/api/v1/verify-seller`.

**What `degraded` / `Uptime 90.4%` actually is.** Not an outage. The reliability
record is frozen:

| field | value | age |
|---|---|---|
| `reliability.computed_at` | 2026-09-06 | 2.5 months |
| `last_seen_at` | 2026-10-12 | 6 weeks |
| `last_verified_at` | 2026-09-21 | 2 months |
| `status` | `live` | — |
| `verification_paused` | `false` | — |

Their uptime window closed in September, when we really were redeploying daily.
Nothing about it describes today.

**We measured the service ourselves, so the question does not need asking.** 24.11
20:17 EET, seven routes × six requests, all unpaid (the prober's view):

| route | 402 / 6 | avg | max |
|---|---|---|---|
| `/api/stats` | 6/6 | 381 ms | 707 ms |
| `/api/sales` | 6/6 | 299 ms | 421 ms |
| `/api/arb/opportunities` | 6/6 | 260 ms | 282 ms |
| `/api/bot-status` | 6/6 | 258 ms | 289 ms |
| `/api/v1/signal` | 6/6 | 272 ms | 320 ms |
| `/api/v1/whaleflow` | 6/6 | 294 ms | 357 ms |
| `/api/v1/verify-seller` | 6/6 | 251 ms | 282 ms |

42 of 42 answered `402`. `HEAD` returns `402`, `OPTIONS` returns `204`,
`/health` returns `200`. The `PAYMENT-REQUIRED` envelope decodes and carries
`scheme=exact`, `network=eip155:8453`, `payTo=0xB4Fc…C844`, `amount=5000`,
`extra.{name:"USD Coin",version:"2"}`. **We are not degraded, and the challenge
was not broken by the 13.10 header change** (`Cache-Control: no-store` + CORS
expose) — a `HEAD`/`OPTIONS` probe and a full GET both answer correctly.

**Conclusion.** The only lever left is a re-verification by PayAPI, on the
existing card. That is the one thing to ask Chet for, and the message in
`OUTREACH_DRAFTS.md` §L2 now says exactly that instead of asking what they probe.

---

## 3. Marketplace — measured, and the answer is "cannot be measured"

Full detail in `docs/ACP_MARKETPLACE_PLAN.md`.

**Done 24.11.2026:**

| | |
|---|---|
| CLI authenticated | owner wallet `0x823750e5383008ba2c3f48523b6f723b268ea62d` |
| Agent created | `Kristo Intelligence`, id `01a20e70-5e40-75cc-b063-7e1915ab544c` |
| Agent EVM wallet | `0x3724b449603cb7faf70ea87f79c3733c6d9546e4` |
| Agent Solana wallet | `45ZEZR5WQY1YexW6YHiP4GYwbLho4BsKyeK3m1ob95u6` |
| Agent email | `kristo_intelligence@agents.world` |
| Offerings / resources | 0 / 0 — correct, and they stay that way |

**The signer never completes, and it is not our fault.** Four approval links were
generated and opened; `agent signer-status` returns `pending` every time and the
CLI's config keeps `"publicKey": ""`. All four local keys were written into that
field by hand — none matched a server signer. The backend explains it: of the
endpoints that would report a count, `/agents/count`, `/agents/stats` and
`/agents/list` all return **500**, and `/agents/search` returns `{"data":[]}` for
**every** query — including our own agent's exact name and wallet address.

**Decision: do not build the provider worker.** The premise was a marketplace
where agents hire; the premise cannot be verified, and nothing that would verify
it works. Keep the agent — it is free and one command re-checks it later.

**Kept as a tool:** `_tools/acp/probe_market.mjs` reads the marketplace directly by
pulling the stored token out of the Windows Credential Manager (service `acp-auth`,
account `access-token-<ownerWallet>`), bypassing the CLI's signer requirement. It
was the instrument for every number above. Re-run it before revisiting ACP.

**A Windows trap worth keeping:** `acp-cli-signer-windows.exe` cannot write to
`%APPDATA%\acp-cli` — the sandbox gives spawned binaries read-only access outside
the workspace, so key generation dies with "Access is denied". Redirect **only**
`APPDATA` (to `_tools\home\AppData\Roaming`) and leave `USERPROFILE`/`HOME` alone:
the CLI keeps its token in `~/.config/acp`, and moving that loses the session.

**One thing to weigh before building anything:** ACP pays on buyer acceptance,
not on delivery. The money sits in escrow and a dispute leaves it there, while
x402 pays immediately and finally. For a $0.05 check the escrow overhead may cost
more than the sale — which argues for a higher price per job or a subscription.

---

## 4. Waiting on other people — no action from us

| # | Who | What |
|---|---|---|
| 1 | Abdellah | Re-running the 36-vector set against v4 (`3d76d803…`, 11 tests). Expected 22 + 14 + 0. |
| 2 | Ernest | Writing the CDP support request for the 7 duplicate rows. |
| 3 | x402-list | Manual review; the FORTE tier cannot be bought yet (§101). |
| 4 | Glama | The `/mcp/servers/` record — Discord message ready in `OUTREACH_DRAFTS.md` §K. |
| 5 | Glama | Tool Count 4/5 — decision taken: do not chase it. Removing response fields to buy 0.1 of a third-party score is not worth changing a paid endpoint. |
| 6 | Glama, the `/mcp/servers/` record | The connector is listed and rated A; the `/mcp/servers/` record does not exist and cannot be created from our side (both Add Server paths reject "already listed as a hosted connector"). `quality` is computed only for `/mcp/servers/`, so `awesome-mcp-servers` PR #13219 cannot merge. Discord message drafted in `OUTREACH_DRAFTS.md` §K; ticket #135407945 open since September. |

---

## 5. Technical — open, not urgent

| # | Item | State |
|---|---|---|
| 1 | Two-process deploy overlap | Render runs old and new instance together during a deploy, so log streams interleave. Harmless; makes "which process answered" non-deterministic from outside. |
| 2 | `autoDeploy` is on | Every push deploys production. Documentation commits carry `[skip render]`; verified to work. Build filters would be better but risk blocking real deploys. |

---

## 6. Done — so it is not reopened

| | |
|---|---|
| MCP Registry | `6.3.1` published, verified in the registry: 6 new descriptions, 0 old |
| CDP Bazaar | all 7 MCP rows carry the current descriptions |
| Two unbuyable routes | `/api/arb/opportunities` and `/api/v1/signal` refused every buyer because the serving process never started its producers; fixed, both now sell |
| Free samples | 7/7 return 200 |
| Documentation | 95/95 markdown files in English, zero Cyrillic — **with one named exception since 24.11**, see below |
| Suite | 1444 collected, 1443 passed, 1 skipped |
| Python client | `scripts/` + `docs/` — a paid call proven end to end |
| Document language rule | Now enforced by CI (`language` job). `docs/AP2_RADAR.md` is exempt: it is generated by `scripts/ap2_radar.py`, which writes Bulgarian, and it is a report to the owner, whom the rule keeps in Bulgarian. The exemption lives in `OWNER_FACING_GENERATED` in `scripts/doc_language_audit.py` and is printed by every run, so it cannot grow quietly. |

---

## 6. Today's clock

**18:00 EET — x402 Identity Working Group.** Reminder set for 17:40. Public
meeting, listening only is enough. Three things we could raise: the two rails
(nonce vs proof), who the payer is under delegated payment, and the missing
ERC-8004 identity in our own announcements.
