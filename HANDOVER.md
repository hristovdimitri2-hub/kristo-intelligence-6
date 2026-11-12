# Handover — 09.11.2026, end of session

Written to be read by a fresh session that has none of this conversation's
context. Everything below was measured, not inferred. If something here
contradicts what you observe, trust the observation and say so.

## What works, verified live

| | state |
|---|---|
| Payments (HTTP) | settling, ~1.5s end to end, through the CDP-first chain |
| Payments (MCP) | **an agent can now buy a tool in-session** — was impossible until 09.11 |
| CDP Bazaar | **7 routes listed** (six at $0.003–$0.005, plus `/api/v1/verify-seller` at $0.1), each with real `payers=1` |
| Test suite | **1231 green** (was 1218) |
| Board | `/health` 200, `/api/dashboard/data` 200, `degraded: []`, and each public sales row now says WHOSE it is |

## SCHEDULED RISK — 14 November, CDP maintenance. Read this before that date.

CDP's status feed carries, for 14 November:

    10:00 - 18:00 PST
    some users may experience degraded performance across multiple products

Up to four hours in which CDP — the facilitator our settlements **prefer** — may
not answer. Until 09.11 the fallback behind it did not work at all, so that window
meant *no payments*, full stop.

**Why it did not work** (measured by calling PayAI directly and reading the body,
`HTTP 400 {"errorReason":"invalid_payload","errorMessage":"accepted: Invalid input:
expected object, received undefined"}`): x402 v2 names the chosen option `accepted`
— ONE OBJECT — our 402 ships `accepts`, an ARRAY, and `settle_standard_payment`
forwarded the client's payload unchanged. CDP tolerates the array; PayAI does not.
So the chain was a real fallback only for clients that spell the field the spec
way, and everyone else — including an agent echoing our own 402 verbatim — had
exactly ONE usable facilitator.

**Fixed in `48e4dfc`:** `_with_accepted()` in `services/connectors.py` fills the
field in from the terms the SERVER itself offered, before the chain runs —
reconstruction, not falsification. A buyer that sent `accepted` keeps it byte for
byte; a payload with no terms is left alone rather than given an option nobody
signed; the caller's dict is not mutated. 7 tests in
`tests/test_facilitator_chain_is_a_real_fallback.py` (two of them pin exactly the
honesty conditions above). Suite 1,240 green at the time of writing.

**Still to do before 14 November: make one payment actually settle through PayAI
itself** — CDP's sibling in the chain — so the fallback is proven on the real rail
and not only in tests.

### 09.11 16:29–16:30 — the fallback fix was exercised; the board was read wrong

Two more payments landed, both labelled `own_key` ("нашият демо ключ — не е
клиент"). Neither was a customer; both were ours, and the fingerprints are in the
Render log:

  * **16:29:08 UTC** — tx `0x54d3b252…922f`, $0.003 on `GET /api/v1/signal`,
    client UA `Python-urllib/3.12` (our local Python — Render runs 3.14) and a
    payload that DID carry `accepted`: the standard-rail baseline.
  * **16:30:11 UTC** — tx `0x5d02aba9…c751d`, $0.003 on the same route, client UA
    `kristo-fallback` = `_forensics/test_fallback_real.py`, written 16:30:01 UTC.
    That is the pre-14-November test: the payload OMITS `accepted`, and the server
    answered at 16:30:09.915 with
    `x402 payload carried no accepted — filled it from the client's own terms
    (exact 3000) so the facilitator chain is not a single point of failure`.
    `48e4dfc` had never been exercised by a real settlement before this; now it
    has. **But the settle still went through CDP** (self-broadcast cannot run: the
    gas wallet `0x9c1eb9…50dd` holds 0 ETH), so the PayAI leg is still unproven on
    the live rail. The item above stays open.

**The board read "16 · $0.15 днес" as income**, while every one of that day's
sixteen payments was the demo key paying our own receiver. The owner asked "нашите
клиенти ли са?" — the honest answer is no: **0 customers and $0.00 of customer
revenue on 09.11**. Fixed here: `_daily_sales_series()` now carries `client_count`
/ `client_usdc` per day, `_between()` sums them for every range, and the page
prints "N от реални клиенти" on the "Днес", "Тази седмица" and on-chain "Днес"
cards — going YELLOW instead of green when nobody paid — plus "от реални клиенти:
$X" on the week cards and a dedicated column in the day table. The all-time class
tags are now prefixed "от началото:", because they add up to $0.32 directly under
a card showing one day's $0.15.

The lesson worth keeping: a Python assertion that the sentence exists in the
template had already passed while the sentence was being SWALLOWED at runtime —
`card()` took three parameters (`v, k, hero`) and the new text was passed as
`hero`, so it vanished and painted the card green. `tests/test_dashboard_card_render.py`
therefore runs the page's real script under node with a stub DOM and asserts what
the renderers actually produce.

### 09.11 19:10 — Base produces a block every 0.2 s; every window we walked assumed 2 s

Found by reading the r/x402 "Payability Report 13" thread and asking what in it applies
to us. Most of its numbers are market context (see the end of this section); one line in
it — that Base's cadence changed — turned out to be a live bug of ours.

**Measured, not quoted.** At head 55,269,652 (09.11 17:11 UTC) the timestamps of head,
head−1,000, head−10,000 and head−100,000 each give exactly **0.2000 s/block — 5 blocks
a second**, uniformly. Base was ~2 s/block when `BLOCK_TIME_SECONDS = 2.0` was written,
and the comment "Base mainnet ~2s blocks" was true then. It is not true now.

The consequence was arithmetic, not cosmetics: every window in the codebase reads
`N × 86400 / BLOCK_TIME_SECONDS`, so **each one covered a tenth of the time it promised,
silently** — the logs showed a window, not a warning.

| where | promised | actually walked (at 0.2 s) |
|---|---|---|
| `dashboard_store.retro_scan(days=30)` — first-run sales backfill | 30 days (default) · **10 days (the live env `KRISTO_DASHBOARD_RETRO_DAYS`)** | ~3 days · **~1 day** |
| `dashboard_store.whaleflow_backfill(hours=24)` — the paid whale feed | 24 hours | ~2.4 hours |
| `arb_radar` `data_age_blocks` in the PAID response | real age | 10× too small |
| `main.py` `NONCE_SEARCH_BLOCKS_DEFAULT = 5000` | "≈2.8 h" | ~17 minutes |
| `main.py` `BLOCKCHAIN_RESUME_LOOKBACK = 1800` | "~1 h" | ~6 minutes |
| `scripts/competitor_recon.py --days N` | N days | N/10 days |

**What was changed, and why each way.**

* `integrations/dashboard_store.py` — `BLOCK_TIME_SECONDS = 0.2` with the measurement
  written down, plus two helpers: `measure_block_time_seconds(w3)` (two real timestamps,
  one division; falls back to the constant when the RPC cannot answer — which is also
  the path the stubbed tests take) and `blocks_for_seconds()`. `retro_scan` and
  `whaleflow_backfill` now **measure** instead of assuming, so the next Base upgrade
  needs no code change. The whale backfill is now honest: 24 h = 432,000 blocks ≈ 432
  getLogs on a COLD boot (a warm start resumes from the watermark and pays nothing).
* A 30-day sales backfill at 5 blocks/s is ~13,000,000 blocks, and a recipient-filtered
  `eth_getLogs` is refused by the public RPC above ~1,000 blocks (`competitor_recon.py:28`)
  — >13,000 requests, an unaffordable boot that would look hung. So `retro_scan` now
  **clamps** to `SALES_RETRO_MAX_BLOCKS` (env `KRISTO_SALES_RETRO_MAX_BLOCKS`, default
  1,500,000 ≈ 3.5 days, i.e. the same wall-clock cost it already had) and **logs the
  window it really scanned**, naming the env var that raises it. A "30 days" that means
  3.5 must never read as 30. `tests/test_block_cadence.py` pins both the arithmetic and
  that warning sentence.
* `services/arb_radar.py` — `BASE_BLOCK_TIME_SECONDS = 0.2` (env `ARB_BLOCK_TIME_SECONDS`).
  This one is customer-facing: `data_age_blocks` is the number a paying buyer reads to
  judge staleness, and it flattered us by 10×.
* `main.py` — the two comments now state the real reach (17 min and 6 min). **The two
  defaults were deliberately NOT changed**: 17 minutes is still far more than the case
  the nonce search exists for (a retry arrives seconds later), and 6 minutes is still
  wider than a Render restart. Widening the nonce reach to catch LCD-style settlements
  broadcast long before we look is a real, separate decision — `KRISTO_NONCE_SEARCH_BLOCKS`
  is the knob, and each extra 5,000 blocks is another minute of chain walked per check.
  **Owner's call, not a silent edit.**
* `scripts/competitor_recon.py` — left at 2.0 **on purpose**, with a comment saying so:
  its windows are already bounded by the chunking floor and changing the divisor would
  silently re-scale every recon report we compare week to week. `--days N` there means
  ~N/10 days. Fix it knowingly, together with the reports, or not at all.

A defect found by the new tests, worth keeping: the two existing backfill tests
(`test_whaleflow.py`, `test_price_sweep.py`) hardcoded `block_number = 100_000`. Once the
divisor became honest, "24 hours" = 432,000 blocks and `max(1, 100_000 − 432_000)` is
block **1** — the window silently collapsed to nothing. Both were re-derived from
`blocks_for_seconds()` against a realistic head. The old tests were not wrong; they were
pinned to a number that had stopped being true.

**Verified on the live instance, not only in tests.** `e95b248` went live at 17:27:14 UTC
(`health: status=ok`, blockchain ready) and the production log carries the measurement and
the clamp together:

```
Whale flow scan loop started (backfill=24h, interval=60s).
WARNING | integrations.dashboard_store | Sales backfill: 10 days requested = 4320000
  blocks at 0.2000s/block, but the budget is 1500000 blocks — scanning 3.47 days
  instead. Raise KRISTO_SALES_RETRO_MAX_BLOCKS to cover more.
Whale flow backfill: 0 whale event(s) persisted.
```

Three things to read out of that: the production instance MEASURED 0.2000 s/block (the
mechanism works against the real RPC, not just a fake chain); the live
`KRISTO_DASHBOARD_RETRO_DAYS` is **10**, not the code's default 30, so that backfill was
washing 10 days into 1 and now covers 3.47; and the whale backfill finished in ~6 seconds
with **0** events, i.e. it resumed from a watermark already at the head and paid nothing
for the corrected window — the 432,000-block walk happens only on a genuinely cold start.
The suite is 1,249 green. (A new, unrelated non-fatal warning appeared in the same log —
`Track record issue failed (non-fatal): SSL error: decryption failed or bad record mac` —
not chased here, and not caused by this change.)

Two other things read out of the same r/x402 thread, for context rather than action:
Report 13 counts **34,137 resources / 3,250 hosts, 32,878 payable (96.31%)** — against
which our 7 paid routes are a rounding error, i.e. the catalogues are not the constraint,
the demand is. Its cleaned Base demand is **12,947.00 USDC over 2,529 wallets for the
week**, of which one seller took 7,273.94 (56%), and its Solana 3,188.74 USDC is mostly
3 × 1,000.00 "matched-price" transfers. Their own stated gap is that wallets paying >20
distinct `payTo` count as demand, so one-endpoint high-volume wallets inflate the
numbers — read the totals as an upper bound. `x402.nsgoods.org` (the report's author,
Nikolaos Dimitriadis) sells 12 x402 oracles including an **x402 Payability Check** at
$0.005/call; its free preview ignores the `resource` you pass and always checks its own
demo endpoint, so getting a third-party verdict on *our* 402 envelope costs $0.005 and
needed the owner's go-ahead — see the next subsection for what happened when we tried.

### 09.11 19:25–19:45 — the owner said yes to four things; every one was checked first

«Да, за всичко, но преди това проверки, за да не се обърка нещо.» So each item below is
the MEASUREMENT first, then the change — and where the measurement said "this would hurt",
the change was not made.

**1. Nonce-search reach — raised to 90,000 blocks (5 h), because measuring showed it is
free.** The production RPC is `api.developer.coinbase.com` (from `BASE_RPC_URL`) and it
refuses a range wider than 100,000 blocks: `-32602 query exceeds max block range 100000`.
Below that ceiling the width costs nothing at all — this exact query (USDC + 
`AuthorizationUsed` + payer topic) answered in **0.28 s at 5,000 blocks, 0.27 s at 20,000,
0.31 s at 50,000**. The old 5,000 was "2.8 hours" when the chain was 2 s/block; at the
measured 0.2 s it was 17 minutes, so the search was covering a tenth of what the code
claimed. `NONCE_SEARCH_BLOCKS_DEFAULT` is now 90,000 (5 h) with
`NONCE_SEARCH_BLOCKS_MAX` clamping it: an env var above the RPC's ceiling would not "search
further", it would fail on every payment. Two tests pin the reach and the clamp.

**2. `competitor_recon` — divisor fixed to 0.2 AND made affordable.** Fixing only the
divisor would have turned a `--days 30` recon into ~13,000 getLogs. Measured with exactly
this receiver filter: 1,000 blocks OK 0.25 s · 10,000 OK 0.34 s · **50,000 OK 0.36 s** ·
100,000 REFUSED. A receiver filter matches a handful of logs, so the limit is the range,
not the result count: `DEFAULT_CHUNK_BLOCKS` 1,000 → **50,000** turns a 30-day window into
~260 requests. Verified live, not just in theory — `--days 2` against the production RPC
scanned `54412507..55276507` (**the true 2 days**, 864,000 blocks at 5 blocks/s) and
reported the honest answer: 0 micro-payments, 16 `own_key` transactions excluded.
Reports produced BEFORE 09.11 were computed with the old divisor and cover a tenth of the
window they name; they are not re-run, they are superseded. `crawler_cadence` imports the
same constant, so it follows.

**3. Whale chunk raised in the live env, 50 → 1000 — fixing a risk the cadence fix
introduced.** The honest 24 h whale window is 432,000 blocks; at the live chunk of 50 that
is **8,640 getLogs on a genuinely cold start**. Measured with the network-wide USDC
Transfer shape: 50 blocks = 540 logs / 0.58 s · **1,000 blocks = 9,862 logs / 4.34 s** ·
5,000 REFUSED (`query exceeds max results 20000`). 1,000 sits at half that ceiling and cuts
the cold-start cost to 432 requests; `scan_whale_window` already halves its own chunk on
refusal, so a busy window costs a retry, never a gap. Applied through the single-key
endpoint (`PUT …/env-vars/WHALEFLOW_CHUNK_BLOCKS`), with the full 38-variable env backed up
first and re-read after: **38 before, 38 after, only that one value changed.** Do NOT use
the collection PUT for this — it replaces the whole set and would delete every variable not
in the payload.

**4. PayAI accepted our payload.** `scripts/phase2_verify.py` (verify only, no settle)
answered **HTTP 200 `{"isValid":true,"payer":"0xE50c5212…5763"}`** with the post-`48e4dfc`
payload — `accepted` present, `bazaar` extension echoed, exact 3000 atomic. That closes the
"does the other facilitator even accept the shape we send" half of the 14 November risk;
**a live `/settle` through PayAI is still unproven** and stays an open item.

**5. The $0.005 nsgoods check could not be paid — by them, not by us.** Two independent
attempts, each with a fresh authorization, each refused with **HTTP 402 and an empty `{}`
body** (distinct from their normal 402, which carries the full 3831-byte challenge):
the v2 shape (`PAYMENT-SIGNATURE`, `accepted` + extensions) and the v1 shape
(`X-PAYMENT`, what `x402-fetch` — the client THEIR OWN docs recommend — sends). Their
manifest is otherwise standard: `GET /payable?resource=<url>`, $0.005, `settles_on`
Base + Solana, `PAYMENT-REQUIRED` header plus `accepts[]`. **No money moved**: the payer's
USDC read 2.066515 before and after both attempts and there were **zero** USDC transfers
from the payer. So there is no third-party verdict, and the finding is itself the news —
the service that sells "is this endpoint payable" answered "unpayable" to a well-formed v2
client. Worth an email to `nikos@nsgoods.org`; not worth a third blind variant. Our own
payload is not the suspect: PayAI's facilitator returned `isValid: true` for the same
signing code minutes later.
The reproducible scripts live in
`C:\Users\AlienWare\.dsh\state\superagent\_forensics\` (`check_nonce_reach.py`,
`check_whale_chunk.py`, `check_recon_window.py`, `pay_nsgoods_payability.py`,
`diag_nsgoods_402.py`, `set_whale_chunk.py`) — deliberately outside the repo, like every
other probe in this project.

Committed as `0d61e01` (code + docs) and pushed; suite **1,252 green**. One honest note
about that suite: `tests/test_audit_fixes.py::test_a5_reverted_receipt_polls_then_overrides_to_delivery`
failed ONCE inside a full run (`3 failed, 1249 passed` — the other two were the stale
counts this commit fixes), then passed alone and in the next full run
(`1252 passed`). It is documented flaky in its own docstring (it patches `time.sleep`
process-wide, so another test's background loop can land in its list). Not caused by
these changes, and not hidden.

Also worth knowing for the next deploy: **an env-var change does not restart the service.**
`set_whale_chunk.py` verified `WHALEFLOW_CHUNK_BLOCKS = 1000` on the service while the
RUNNING instance was still on 50 — the new value only takes effect with the next deploy or
restart, which is why the code push above is also what carries it into production.

**And a caveat about that change, measured rather than assumed.** After the deploy the
live payload still said `effective_chunk_blocks: 50`, so "1000" was not taken on faith:
twelve consecutive 1,000-block windows were walked directly against the production RPC —
**12 accepted, 0 refused, 8,839 logs on average (44% of the RPC's 20,000 cap), ~2.2 s
each**. 1,000 is genuinely usable. The 50 is a TELEMETRY ARTEFACT, and it is worth knowing
before anyone trusts that number again: `_adaptive_get_logs` returns
`effective_span = MIN(span accepted during the walk)` and never grows the span back inside
a walk, so a single transient error (a 429, a timeout — not a size limit) ratchets the
reported span to its floor and leaves it there. So `effective_chunk_blocks` reports the
WORST span of a walk, never the configured one. Recommended follow-up (not done here — it
touches the shared chunking machine late in a session): publish the configured span next
to it, or let the span grow back after a few accepted windows.

### 09.11 20:20–20:30 — the PayAI leg is PROVEN, on the live rail, with real money

The 14 November risk was "if CDP is down, does a payment actually settle through PayAI?"
It is now answered twice, with $0.006 of the demo wallet and two real on-chain transfers.

**One: through our own chain code, against the live facilitators.** `_forensics/payai_settle_probe.py`
loads `services.connectors.settle_standard_payment` with `WALLET_PRIVATE_KEY`,
`CDP_API_KEY_*`, `FACILITATOR_CDP_API_KEY_*` and `X402_FACILITATOR_URL` REMOVED, so
self-broadcast cannot run and CDP cannot be the settler — if it settles, PayAI settled it,
and the chain it walks is exactly the [payai, cdp] default that runs when CDP is down.
Result:

```
self-broadcast  0.00s  FAILED — self_broadcast: no WALLET_PRIVATE_KEY configured
payai-settle    1.34s  ok
x402 settle TOTAL 1.34s (settled via payai)
tx 0x371010332488ce52ce86f3490b1d167b66ccc1bc1df8a457a31a48c35f7c3646
receipt status 0x1 · one ERC-20 Transfer payer → receiver, exactly 3000 atomic
balance: payer 2,066,515 → 2,063,515 · receiver 317,000 → 320,000
EXTENSION-RESPONSES: {"bazaar":{"status":"processing"}}
```

**Two: through the DEPLOYED service.** The only thing tests still owned was the live chain
*selection*, so the service was put in the same configuration for one paid call —
`_forensics/toggle_payai_first.py` removed the `FACILITATOR_CDP_API_KEY_*` pair (backed up
first; 38 → 36 variables), deployed `dep-dbp10jff3r`, and `scripts/demo_sponsored_pay.py
--send` paid $0.003. The production log:

```
18:27:41 standard x402 locally verified: payer=0xE50c5212…5763
18:27:43 x402 rail step find_settlement_by_nonce     1.570s
18:27:43 x402 settle phase self-broadcast  0.40s FAILED — gas wallet 0x9c1e…50dd has 0.00000000 ETH
18:27:44 x402 settle phase payai-settle    0.83s ok
18:27:44 standard x402 settled via payai: tx=0x64b9f77fe24f4dad7132786f82108406b7a2de2c351f4ebdf2221a70d8757dad
18:27:44 x402 settle TOTAL 1.23s (settled via payai)
18:27:45 Recorded real sale: USDC $0.003000 (tx=0x64b9f77f…)
```

Two extra things that log proves. The client got **HTTP 200** with
`PAYMENT-RESPONSE success=True network=eip155:8453`, so the buyer's side is intact. And the
NEW nonce search ran in production for the first time:
`find_settlement_by_nonce 1.570s` — the 90,000-block reach (5 h) cost 1.6 s inside a 5 s
deadline, i.e. the widened window does not menace the request path.

**Restored immediately, and verified.** The pair was put back (36 → 38 variables) and
`7608b8c` deployed; `/api/connectors` now reads
`self-broadcast (gas=True) → CDP → payai (cdp: JWT OK)` and the whale section reads
`effective=1000 configured=1000`. Two $0.003 payments both went to OUR OWN receiver, so the
board is honest about it: 18 tx / $0.159 / **0 real customers** on the day.

**Two public claims were lying and are fixed (`7608b8c`).** (a) `_eip3009_detail()` hardcoded
`→ CDP ({cdp}) → payai`; during the test above the live service ran PayAI FIRST and
`/api/connectors` still advertised CDP first — caught live, not in theory. The order is now
read from `_facilitator_chain()` itself. (b) The chunk telemetry: after the env raise the
public payload said `effective_chunk_blocks: 50`, which is TRUE and misleading —
`_adaptive_get_logs` reports the MINIMUM span accepted in a walk and never grows back, so one
transient 429 leaves the floor showing. Twelve consecutive 1,000-block windows were then
measured against the production RPC: **12 accepted, 0 refused, 8,839 logs on average
(44% of the 20,000 cap)**. `configured_chunk_blocks` is now published beside it and the page
prints the second only when the two differ.

Suite **1,254 green**. Tooling (outside the repo, as always):
`_forensics/payai_settle_probe.py`, `toggle_payai_first.py`, `check_whale_chunk_repeat.py`,
`wait_payai_first_deploy.py`, `final_state_payai.py`.

### 09.11 19:20–19:27 — paying for the seven MCP tools found a bug that took $0.10 for nothing

The owner's order was to pay for the remaining MCP tools so the tools enter the catalogue.
Six had never had a paid call (`get_whale_flow` settled post-fix at 15:11). All six were paid
in one run, `_forensics/pay_mcp_six.py`, after a dry pass that spends nothing and aborts on any
mismatch — the live challenge had to name the TOOL (`<host>/mcp#<tool>`), carry
`input.type=mcp` with a matching `toolName` and a valid `example`, and quote our own receiver,
token, CAIP-2 network and list price. All six passed, and all six settled on-chain
(`status=0x1`, nonce found as an `AuthorizationUsed` log for our payer, $0.123 total).

**One of them was then handed the payment challenge again.** `verify_seller_receiver` is the
only tool that takes input; its call settled $0.10
(tx `0x697923104b312862fc333fd6464e542a77a7253a635a2070125ccbff9d7413f0`) and answered with the
challenge. Cause, in `app/blueprints/discovery.py`: `_serve_paid_mcp_tool` forwarded the buyer's
header with `client.get(path)` — **no query string, so the tool's arguments were dropped**. The
route requires `receiver` and answered its honest `400 receiver_required`; the forward accepts
only a 200 with a `PAYMENT-RESPONSE` header, so the tool fell back to the challenge. The rail
settles BEFORE the route handler runs, so the money was gone and the nonce was spent — the buyer
could not even retry with the same signature. Six no-input tools settled and served in the same
run, which is exactly why six payments in a row hid it.

Fixed in `eb42e7d`: the arguments now travel as the route's query string, and the rules are the
tool's OWN `inputSchema` (required keys, types, `receiver` normalized to lowercase hex, unknown
keys refused). Validation runs **before the rail is touched**, so a call the route would reject
is rejected where no nonce is spent and the same signature stays usable. The unpaid path is
unchanged: an agent that has not been charged still gets the challenge and the schema.

Proven live for the price of ONE payment, `_forensics/verify_mcp_forward_fix.py`: one signed
authorization was sent with no arguments — JSON-RPC `-32602`, *"…nothing was charged"*, nonce
unspent, balance unchanged — and then the **same signature** with a valid `receiver` was served
the real audit report and settled (tx `0x04bcd09f099b2819cb0a7c11811508dd7d7f40f5eb1eb076557351d5626b2eaf`,
`read: clean`, coverage complete). Seven new tests pin both halves.

### 09.11 19:45–19:56 — the seven tools ARE in a live MCP catalogue; CDP's MCP half is frozen

Two indexes, measured from outside (`_forensics/mcp_index_freshness.py`):

```
CDP   type=mcp  515 rows   newest lastUpdated 2026-11-08T23:36:43Z   FROZEN (>20 h)
CDP   type=http 32,761     newest lastUpdated 2026-11-09T19:46:48Z   a minute old
PayAI type=mcp  116 rows   alive
```

So our seven corrected CDP settlements cannot be indexed yet **whatever the app does** — their
MCP crawl has not run since 08.11 23:36, while their HTTP half updates every minute. Nothing in
the repo was changed for that.

PayAI's half is alive, and its `Bazaar Discovery` docs (fetched 09.11) say three things that
decided the next step: the catalog key is `(resource, toolName)` — the MCP **endpoint** plus the
tool name as two fields; listing is automatic from payments the facilitator processes that carry
the declaration; and **an MCP resource's first listing needs a settled payment** (a `/verify`
alone is deferred as `resource_needs_settlement`, and a probe answering `GET /mcp` with anything
but 402 is refused as `resource_not_x402` — measured: our `/verify` probe for `get_market_stats`
was rejected with exactly that reason, because our `GET /mcp` answers 200).

Also measured, and it is the fallback story getting stronger: PayAI's `/verify` returns
`{"isValid": true, "payer": 0xE50c…5763}` for the post-fix MCP payload — the 14 November rail
verifies our MCP identity too, not just the HTTP routes.

**A false negative first.** `listing-status` was queried with the URL *including* `#toolName`
and no `toolName` parameter, and the `resources` walk scanned rows written before the settle.
PayAI stores `resource` and `toolName` separately, so a row filed under `/mcp` could only ever
answer 404 to that query. Re-asked in the right shape, the 19:51 settle answered
`listed=True, lastWrite status=listed source=settle, probe alive 200`.

Six more settles through PayAI's leg of our own rail (CDP and the gas wallet removed, no deploy,
no env change) — `_forensics/payai_mcp_list_all.py`, $0.123 — and each tool was listed within
**seconds**: `get_market_stats`, `get_onchain_sales`, `get_bot_status`, `get_whale_flow`,
`get_arbitrage_opportunities`, `verify_seller_receiver`. All seven now answer
`type=mcp&payTo=0xd4cd…d08f` with `resource=https://kristo-intelligence-api.onrender.com/mcp`
and their own `toolName`.

One stale row remains and cannot be fixed from here: `(resource=…/api/v1/whaleflow,
toolName=get_whale_flow)`, written 14:06 from the pre-fix payload. PayAI refreshes **forward
only** and delisting a live entry is a manual request — so the corrected row is created
alongside it, not in place of it. Worth one Discord/issue note if it matters later.

Demo-wallet cost of the whole MCP-catalogue exercise, 2.060515 → 1.711515 USDC: **$0.123** for
the six CDP-rail payments (including the $0.10 the bug consumed), **$0.10** to prove the fix
live, **$0.003 + $0.123** for the seven PayAI listings. Tooling:
`pay_mcp_six.py`, `verify_mcp_forward_fix.py`, `mcp_index_freshness.py`,
`payai_mcp_verify_probe.py`, `payai_mcp_settle_row.py`, `payai_mcp_row_check.py`,
`payai_mcp_list_all.py`.

### 10.11 06:00 — CORRECTION: CDP's MCP half is NOT frozen. It indexes on settlement.

The heading above says "CDP's MCP half is frozen". **That was an inference, not a measurement, and
it is wrong.** Two pieces of evidence overturn it, both from a single CDP-settled MCP payment.

**1. CDP's indexer crawls us the instant a payment settles through CDP.** In the server log, in the
same second as the settlement:

```
05:57:19 2026-11-10 05:57:19,431 INFO  services.connectors | standard x402 settled via cdp:
         tx=0xdb7ccdcfeba1516a542bef65977e615472d0c157ce60b06fbcf685c9323f3dc1
05:57:19 10.195.116.51 POST /mcp 200  95  "CoinbaseBazaarDiscovery/1.0"
05:57:19 10.193.30.153 POST /mcp 200 436  "CoinbaseBazaarDiscovery/1.0"
05:57:19 10.193.30.153 GET  /mcp 200 325  "CoinbaseBazaarDiscovery/1.0"
05:57:20 10.194.107.244 POST /mcp 202  0  "CoinbaseBazaarDiscovery/1.0"
05:57:20 10.195.135.23 POST /mcp 200 6060 "CoinbaseBazaarDiscovery/1.0"
05:57:20 10.194.107.244 POST /mcp 200 5318 "CoinbaseBazaarDiscovery/1.0"
```

`CoinbaseBazaarDiscovery/1.0` is their crawler, and it reached our MCP endpoint six times. An
indexer that has not run since 08.11 23:36 cannot do that. **The reason our tools were absent is
that no MCP payment had ever been settled through the CDP facilitator** — our earlier MCP
settlements went through PayAI, and each index only lists what its own facilitator processed.

**2. CDP ACCEPTS our declaration.** The settle answered
`EXTENSION-RESPONSES: {"bazaar": {"status": "processing"}}` — accepted, not `rejected`, with no
`rejectedReason`. So the MCP-shaped declaration (`type: "mcp"`, `toolName`, `transport`,
`example`, `inputSchema`, `bazaar.schema`) is valid as far as CDP is concerned, and the docs'
`input.example` trap that closed [issue #4075](https://github.com/x402-foundation/x402/issues/4075)
is one we do not fall into.

The payment: one `get_whale_flow` call, **$0.003** (1.711515 → 1.708515 USDC), settled via the CDP
rail in 1.07 s, tool served 50 whales. Tooling: `_forensics/cdp_mcp_settle_decisive.py` (dry run by
default, `--send` to spend), `_forensics/watch_cdp_mcp_listing.py`.

**Still true, but NOT a cause: CDP's validation endpoint fails our MCP resource on its REQUIRED
checks — and it fails every listed MCP resource the same way.** `POST
https://api.cdp.coinbase.com/platform/v2/x402/validate` (free, no key) with `resource=…/mcp`
reports `returns_402` failed (we answer 200/400, never 402 with a `PAYMENT-REQUIRED` header) and
`bazaarExtension: null`.

SUPERSEDED, and the correction matters: I first read that as the cause. It is not. The same
validator, run against three resources that ARE listed in CDP's MCP catalog, fails identically:

```
https://mcp.xrpl-utilities.io/mcp     POST returns_402 passed=False actual=406  bazaarExtension=null
https://x402.magneta.finance/mcp      POST returns_402 passed=False actual=406  bazaarExtension=null
https://api.crawlwitness.com/mcp      POST returns_402 passed=False actual=400  bazaarExtension=null
```

`mcp.xrpl-utilities.io` is the project whose issue #4075 was closed as solved — it is IN the
catalog with 6+ tools. So `returns_402` is not a gate for MCP resources, `bazaarExtension: null` is
simply what this endpoint says about MCP, and the validator is HTTP-shaped. **Failing it proves
nothing about eligibility** and it must not be quoted as the reason we are absent.

**Where that leaves the question.** After 24 minutes (`_forensics/watch_cdp_mcp_listing.py`,
sweeping every 3 minutes) the catalog still held exactly **511 `type=mcp` rows and 0 quoting our
receiver**.

### 10.11 07:05 — THE CAUSE, and it is a spec MUST we were violating

The metadata-tone hypothesis was tested and excluded: the wording was rewritten to describe rather
than instruct (commit `c8c24c7`), the deploy went live, CDP settled a second MCP payment
(tx `0xf96b3a71…3a47`, $0.003) and their crawler came back — and 24 minutes later the catalog still
held 511 rows and none of ours.

What was left was the SPEC. `specs/transports-v2/mcp.md`, "Payment Required Signaling", uses MUST:

> When a tool requires payment, servers MUST return a tool result with **`isError: true`**
> containing the PaymentRequired data.
>
> Servers MUST provide the PaymentRequired in both formats:
> 1. **`structuredContent`** (REQUIRED): Direct PaymentRequired object
> 2. **`content[0].text`** (REQUIRED): JSON-encoded string of the same PaymentRequired object

**We satisfied neither.** Measured live, an unpaid `tools/call` returned result keys
`['content', 'structuredContent']` — no `isError` — with `content[0].text` a human sentence and the
challenge pushed into `content[1]`. To anything checking the documented signal, our unpaid call was
indistinguishable from a **successful** tool call, and Coinbase states the consequence in the same
breath: "if the tool returns success instead of a payment challenge, Bazaar cannot index the tool."

**The fix (`6f808a2`).** `content[0]` is now the JSON PaymentRequired, byte-identical to
`structuredContent`'s `accepts`; the human sentence moved to `content[1]`; the challenge result
carries `isError: true`. `x402` stays in `structuredContent` for clients already reading it.

`test_mcp_streamable_tools_call_returns_payment_instructions_not_execution` had pinned the OLD shape
(asserting "USDC" in `content[0].text`, i.e. the sentence first) — it was replaced with a stronger
assertion of the mandated shape rather than relaxed: `isError is True`, `content[0]` parses as the
PaymentRequired, its `accepts` equal `structuredContent`'s, and the sentence survives at
`content[1]`. Suite 1,277 passed.

Three hypotheses are now excluded BY MEASUREMENT, and the list matters as much as the finding:
"their MCP crawl is frozen" (false — it runs on settlement); "we must answer HTTP 402 on a bare
probe" (false — CDP's validator fails three ALREADY-LISTED MCP resources identically); "the metadata
reads as instructions" (reworded, re-crawled, still unlisted).

**PROVEN: the spec shape was the cause.** With `6f808a2` live, one more `get_whale_flow` paid
through CDP (tx `0xb417ecb8…c9eb`, $0.003, `bazaar: {"status": "processing"}`) and the entry was in
the catalog **within seconds**:

```
type=mcp total 511 -> 512
newest lastUpdated  2026-11-10T07:15:05.725Z   (settlement at 07:14:5x)
  [mcp] https://kristo-intelligence-api.onrender.com/mcp#get_whale_flow#get_whale_flow
        description  "Live whale flow: USDC transfers >= $5M on Base ..."
        accepts[0]   exact / eip155:8453 / 3000
        bazaar input type='mcp' toolName='get_whale_flow' example={}
        input keys   [description, example, inputSchema, toolName, transport, type]
        quality      {"lastCalledAt": "2026-11-10T07:15:05.725Z"}
```

`_forensics/watch_cdp_mcp_listing.py` caught it on its FIRST sweep, thirteen seconds after the
settlement — there was no 15-minute wait, and no re-crawl needed. For contrast, the same script sat
through a full 24-minute window twice (06:00 and 06:45) with `ours=0` while the declaration was
accepted and the crawler kept visiting. **The declaration was never the problem; the response to the
crawler was.**

The doubled fragment (`…/mcp#get_whale_flow#get_whale_flow`) is CDP appending `#toolName` to a
resource URL that already carries it; `mcp.xrpl-utilities.io` has byte-identical doubling on one of
its listed rows, so it is tolerated and is NOT worth "fixing" by dropping the fragment we need.

**Remaining: the other six tools.** Each needed its own settled CDP payment, exactly as this one did
— and all six were done on 10.11 with `_forensics/cdp_mcp_settle_six.py` (dry run by default,
`--send` to spend; the paid call's `arguments` are the tool's own declared `example`, which is
exactly what the crawler sends). Cost: four at $0.005 (`get_market_stats`, `get_onchain_sales`,
`get_bot_status`, `get_arbitrage_opportunities`), `get_trading_signal` at $0.003 and
`verify_seller_receiver` at $0.10 — **$0.123**.

**ALL SEVEN ARE LISTED IN THE CDP MCP CATALOG.** Verified from outside, sweeping every page of
`type=mcp`:

```
07:23:27  total=512  ours=1  ['get_whale_flow']
07:26:02  total=518  ours=7

toolName                         amount   type  example  lastUpdated
get_market_stats                   5000   mcp   {}       2026-11-10T07:17:16.070Z
get_onchain_sales                  5000   mcp   {}       2026-11-10T07:17:24.360Z
get_bot_status                     5000   mcp   {}       2026-11-10T07:17:29.201Z
get_arbitrage_opportunities        5000   mcp   {}       2026-11-10T07:17:33.484Z
get_trading_signal                 3000   mcp   {}       2026-11-10T07:17:37.392Z
verify_seller_receiver           100000   mcp   yes      2026-11-10T07:17:42.397Z
get_whale_flow                     3000   mcp   {}       2026-11-10T07:15:05.725Z
```

Indexing took about **three minutes** for the six (not the 15 the docs allow), and 13 seconds for
the first one. Total demo-wallet cost of the whole CDP MCP exercise: **$0.132** (three $0.003
diagnostic settlements + $0.123 to list the six), balance 1.702515 → **1.579515 USDC**.

A NOTE ON THE TIMEOUT THAT ENDED THAT RUN: `cdp_mcp_settle_six.py` died with a read timeout while
verifying the LAST settlement's nonce, i.e. AFTER all six payments had been made. The money is what
settles that question — exactly $0.123 had left the wallet, matching the six prices and nothing else
— so nothing was retried blindly, and the catalog then showed all six rows. Recovering a lost run by
measuring the wallet first is the pattern to keep: a read timeout is not a failed payment.






### 09.11 20:00–20:35 — „таблото да е активно винаги": рестартът вече не е грешка

The owner saw **„ГРЕШКА: HTTP 503 … Данните по-долу са НЕАКТУАЛНИ"** on the dashboard and asked
for it to be fixed immediately and to be permanently operational. Both halves were real, and
one of them was mine.

**Why it happened.** `/api/dashboard/data` returns `503 {"warming": true}` while the first board
build runs — by design, so a visitor never holds a worker for the length of a slow build. But
the board cache (`_DASHBOARD_LAST_GOOD`) is process memory, and auto-deploy is on, so **every
push** — including the docs-only handover commit `d49787a` — emptied it and produced that error
for the next visitor. The template turned it into a hard error and then waited out the whole 45 s
cycle before trying again.

**The fix (`9468c4f`) — the board survives a restart.** The last good **PUBLIC** payload is
written into `dashboard_meta` in the durable store and replayed on a cold start, so
"the process restarted" answers with the previous real figures plus their age instead of a 503.
Deliberately not a file: measured through the Render API, this service has **no persistent disk**
(`disk: null`), so `data/*.db` is wiped by every deploy — `dashboard_meta` is the table that
already survives for exactly this reason. Only the `(False, False)` grant is persisted, because
the admin and operator variants carry the CRM/Stripe section and must never reach shared storage;
the write is rate-limited to once a minute so a 30-second revalidation does not push 50 KB into
Postgres each time. A corrupt stored board degrades to the old cold behaviour, and a store that
refuses the write cannot fail a build.

**The page (`templates/dashboard.html`).** A 503 is now „ЗАГРЯВА" with a 2.5 s retry — checked on
the STATUS, because Render's own 503 while swapping instances carries no JSON. A dropped
connection is counted: the first three consecutive failures read „ПРЕЗАРЕЖДАНЕ" and keep the
figures on screen, and only past that does the badge say ГРЕШКА, which is the honest line between
"the board is being redeployed" and "the board is not answering". A genuine error also retries in
5 s now instead of staying red until the next 45 s tick.

**Proven live, by restarting the service** (`_forensics/verify_dashboard_always_on.py`): deploy
`9468c4f` live at 20:09:54, the board built and persisted itself, then `POST /services/{id}/restart`
— polling across the restart gave **6 × HTTP 200, 0 × 503**, one dropped connection
(transport error at 20:10:32, from the instance swap) and a 200 in 0.9 s six seconds later, with
the log saying:

```
20:10:03 WARNING | kristo.v6.main | dashboard board restored from the durable store
         (built 7s ago) — serving it instead of a cold 503
```

Tests: 12 new (44 in `test_dashboard_resilience.py`, suite **1,272**). The ones that carry the
weight: a restart serves the stored board through the real route with 200; a 10-minute-old stored
board is LABELLED stale rather than painted fresh; the admin and operator grants are never written
and never read back; a corrupt board still cold-starts; and structurally — the page's 503 branch
comes before the throw, the transient branch before the error badge, and neither contains „ГРЕШКА".
`tests/conftest.py` now points the store accessor at nothing for every test, because the suite
shares the developer's real database and a board written by one test would seed every later
test's cold path.

### 09.11 20:19–20:36 — the restart fix hid a second fault: SQLite was locking the board out

Deploy `8c6e300` went live at 20:18:46 and the board **still** failed, but differently — this time
in the service, and visibly so:

```
/api/dashboard/data    18 × HTTP 503, 1 × HTTP 500, ~50.4 s per request
last_error_type        {"(False, False)": "OperationalError"}
slowest_step           get_payapi_state  30,067 ms
cache_age_seconds      {}      refreshing: []
log                    dashboard: background refresh failed (variant
                       (False, False)): database is locked
```

**Two faults stacked, and the second one was created by the first fix.**

1. **The store itself.** `dashboard_store._connect()` opened SQLite with the default
   rollback-journal mode and `timeout=30`. In that mode **a writer blocks readers for the whole
   transaction**, and this one file is written by several threads at once (the boot-time retro
   scan and whale backfill, the scan watermarks, request-log retention). So a read — the log names
   `get_payapi_state` — sat on the full 30-second busy timeout and died with
   `OperationalError: database is locked`. Every rebuild failed, the board stayed empty, and every
   visitor got 503 „ЗАГРЯВА". Fix: `PRAGMA journal_mode=WAL`, best-effort (it fails on a read-only
   or in-memory file, and a store that cannot switch must still work). In WAL readers do not block
   on a writer and vice versa — exactly what this file's many-reads/occasional-long-writes
   workload needs.

2. **My own seed was unbounded, and that is what made requests take 50 s.** The seed introduced by
   `9468c4f` ran *inside* the cold path: the request waited the store's full 30-second timeout,
   then the 20-second cold wait — 50.4 s per request, 18 times in a row. A restart-survival fix had
   become a way to make a restart *slower* than the 503 it replaced.

**The fix (`_dashboard_seed_once`, main.py).** The seed now runs **once per process** on a
`dashboard-seed` daemon thread and a request waits at most `KRISTO_DASHBOARD_SEED_WAIT_SECONDS`
(default **2**; the request path is the one place the "no database work on the request path" rule
has an exception, so the exception is bounded). If the bound expires the thread keeps going, so the
NEXT request finds the board already there. Nothing in it can raise into a request.

**The test lesson, which cost more time than the fix.** `test_a_slow_store_cannot_hold_the_request`
passed alone and failed inside its file: the leak was not in the test but in the suite's shared
cache — a *gated refresh thread* released by the previous test published a board into
`_DASHBOARD_LAST_GOOD` after that test's teardown had cleared it. `_clean_cache` now settles **every**
live `dashboard-` thread (`dashboard-seed` **and** `dashboard-refresh`) before clearing, and the
test asserts the bound directly on `_dashboard_seed_once()` instead of inferring it from a
globally-empty cache. A test that depends on global emptiness in a threaded process is testing the
suite, not the code.

Tests: 2 new (35 in `test_dashboard_resilience.py`, suite **1,274**). The ones that carry the
weight here: a store that takes five seconds still returns from the request path in under three; the
seed is attempted **once per process**; and a corrupt stored board is skipped rather than raised.

### 10.11 05:12–05:21 — the board aged nine minutes in silence; the flag was a set, not a lease

The morning after `0f55a01`, the honest check (not a happy-path one) was: poll the board, then read
the log **hour by hour across the whole night** rather than trusting the first 500 lines, which
cover about a minute.

**What the fix bought, measured.** Across nine sampled hours (21:00 → 05:00) the log contained
**0 × `database is locked`, 0 × `background refresh failed`, 0 × `dashboard warmer`**. The only lock
line of the night was at **20:50:45** — one minute after the deploy, while the boot-time backfill
was still running. `last_build_timings_ms` is now `requests_summary` 2,311 ms, `get_payapi_state`
**0.6 ms** (it was 30,067 ms), `last_error_type: {}`, and the board answers in 0.3–0.9 s.
The deployment check gave **19 × 200 at 0.3–0.5 s** in place of the 50.4 s requests.

**What it left.** The first two probes of the morning served a **545-second-old** payload —
`stale=True` — and the very next request produced a fresh build in ~2 s. So the board was never an
error and never 503; it was *behind*, and only because a build had stalled: nine minutes with
`generated_at` frozen at 05:12:44, **not one error in the log**, and recovery on the first request.
That is the signature of one build hanging while holding `_DASHBOARD_REFRESHING`: the warmer ticked
every 30 s, saw "a refresh is already running", did nothing, and logged nothing. A bare **set** made
that state last exactly as long as the hang did — the precise opposite of «винаги активно».

**The fix — the flag is now a LEASE.** `_DASHBOARD_REFRESHING` maps a variant to *when* its refresh
started, and `_DASHBOARD_REFRESH_LEASE_SECONDS` (default **180**, env-overridable) is how long a
build may be "in flight" before a later caller calls it abandoned, logs a warning, and starts its
own. Generous on purpose: the slowest real step measures 2.3 s, so nothing healthy comes near three
minutes, and the one-build-per-variant guarantee still holds — both halves are pinned by tests.

**The page stops waiting a whole cycle.** The server has always sent a truthful `stale_reason`, and
the page ignored it, asserting instead that «живият прочит се провали» — not why a board that was
merely left unopened is stale. It now shows the server's reason, and while stale it re-asks after
**5 s** rather than waiting out the 45 s tick, bounded to six quick attempts (reset on the next fresh
paint) so a genuinely stuck board cannot turn into permanent 5-second polling. Net effect: the first
visitor after a quiet period sees LIVE in seconds instead of up to 45.

Tests: 3 new (38 in `test_dashboard_resilience.py`, suite **1,277**) — a six-minute-old in-flight
refresh is superseded and a young one is not, and structurally: the page's stale branch reads
`stale_reason`, re-asks in 5 s, and bounds that re-ask.

**Proven live, `c8d2be5`, 10.11 05:33** (`_forensics/verify_deploy_no_503.py`): the deploy went live
at 05:33:47 and the board returned **20 × HTTP 200, 0 × 503**, every one in **0.3–0.7 s**, with the
log naming the restart fix itself:

```
05:34:00 WARNING | kristo.v6.main | dashboard board restored from the durable store
         (built 5s ago) — serving it instead of a cold 503
```

For contrast, the same check on `0f55a01` at 20:49 saw one 503 at 50.4 s — the OLD instance still
draining a request during the swap, since the new process had a board 0.4 s after it went live.
`c8d2be5` produced none.

**And a real restart, verified to have actually rolled** (`_forensics/verify_restart_rolled.py`).
The first restart poll finished in 27 s — fast enough that it may have ended before Render replaced
the instance, so it proved less than it looked. The log settles it: the NEW process booted at
**05:35:45** (`Durable store ready (postgresql)`, `isolated store 'dashboard-scan'`) and answered
`/api/dashboard/data` **HTTP 200 in 0.95 s** at 05:35:50 — a board five seconds after boot, with
**8 × 200 and 0 × 503** across the swap.

### 10.11 05:39 — the monitor said `down`; the app was never down. The service had no health check.

The owner's monitor reported `ok → down` with
`Read timed out (read timeout=30)`. Every endpoint answered **200 in 0.3–0.4 s** at the same time,
so the alert was real but the diagnosis in it was not.

**What actually happened.** The docs-only commit `4f24119` — which exists only to record the
previous verification — triggered a deploy, because the service is `autoDeployTrigger: commit`.
The new instance went live at **05:37:36**; the OLD worker was stopped at **05:39:36**
(`Worker exiting (pid: 76)` / `Shutting down: Master`). A connection that landed on the dying
instance hung until the monitor's own 30-second read timeout, and the monitor called that "down".

**The root cause was configuration, and it is the same one behind the original complaint.** The
service had `healthCheckPath: ""` — NO health check. Render therefore routed traffic as soon as the
port opened, never verified that the new instance actually answered, and drained the old instance
about two minutes later. That is the same mechanism as the 503 the owner first reported, which was
triggered by the docs-only handover commit `d49787a`.

**The fix (owner-approved, infra, 10.11 05:42).** `healthCheckPath` is now **`/health`** on
`srv-d9maroe7bikc73adkaug`, applied through `PATCH /v1/services/{id}` → `serviceDetails.healthCheckPath`
and read back as `"/health"`. Render now sends traffic to an instance only once that path answers,
so a deploy is zero-downtime by construction rather than by luck. Nothing about the application
changed for this — `/health` is the endpoint the app's own keep-alive already pings, and it answers
in ~0.4 s.

**Not done, deliberately:** `autoDeployTrigger: commit` is unchanged, so a docs-only commit still
redeploys. Stopping that would need a build filter, and the current service API does not expose one
(`serviceDetails` has no `buildFilter` key). It is recorded here as the next lever if the monitor
still reports transient blips.

**Why `/health` and not `/ready`.** The codebase already assumed this config: `/health`'s docstring
says it is "liveness, and only liveness … what platform health checks (Render, Docker) and the
keep-alive loop act on", it makes **no RPC call** on purpose ("/health is what the platform restarts
us on"), and it answers 200 even with the database unreachable. `/ready` is the opposite by design —
503 when a dependency is unusable, precisely so that a dependency problem does NOT cause a restart.
Pointing Render's health check at `/ready` would turn every database hiccup into a restart loop.

**Verified across the next deploy** (`_forensics/monitor_sim_across_deploy.py`), by doing exactly
what the monitor does — `GET /health` with a **30-second read timeout** — every 5 s for four
minutes, deliberately spanning the ~2-minute drain that caused the alert. Deploy `44075f6` went live
at 05:43:55; the result was **44 × HTTP 200, 0 timeouts, worst latency 1.78 s, typical 0.3–0.4 s**.






## The owner's instruction, verbatim: «провери какво плаща с демо ключа»

Check what the demo key is really paying for. Why it is now a task with teeth —
`18e8af9` measured that **THIRTEEN OF THE DAY'S FOURTEEN payments were the owner's
own tests**, and the board could not say so: the public row carried no
`payer_class`, and the dashboard legend iterated a hardcoded class list, so when
`own_key` was added for the demo wallet the class silently VANISHED from the
totals. Fixed there: the public ledger now carries the class (a "Кой" column), the
legend is derived from `Object.keys(by_class)`, and the four fields that stay
private are `tx_hash`, `sender`, `route`, `block_number` — **a CATEGORY is not an
IDENTITY.**

Every payment whose payer is `0xE50c5212e8211639C49276dA190E248B83935763` is OURS
(that is the demo key's address; the receiver is `0xd4cdA9…08f`, the gas wallet
`0x9c1eb9…50dd`). Our own settlements on 09.11 came from it: `0x7bcde0d2…` (14:14
UTC) and `0x1f4647e0…` (15:11 UTC — a **deliberate test**, the one the previous
session could not explain; see below). If any catalogue's `payers` count or the
board's "external payers" treats that address as a customer again, the attribution
has regressed.

## THE OPEN LEAD — **CLOSED** 09.11 15:11 UTC, answered by measurement

**The question was:** does the CDP facilitator index from
`paymentPayload.resource` or from `paymentRequirements.resource`?

**The answer: `paymentPayload.resource`. `paymentRequirements.resource` is never
read.** Three confirmations, none of them inferred:

1. Coinbase's own facilitator-side extractor
   (`typescript/packages/extensions/src/bazaar/facilitator.ts`,
   `extractDiscoveryInfo`): `resourceUrl = paymentPayload.resource?.url`, then
   `new URL(resourceUrl).pathname` — **the fragment is stripped**, so
   `…/mcp#get_whale_flow` catalogues as `…/mcp` with `toolName` taken from
   `extensions.bazaar.info.input`. For v2 it touches `paymentRequirements` only
   for the v1 shape. One catalogue key = (`resource.url`, `input.toolName`).
2. CDP's docs: *"On the settlement call that triggers indexing, set both
   `paymentPayload.extensions.bazaar` and `paymentPayload.resource`."*
3. The live facilitator, asked directly. `verify` is FREE (no settlement) and
   reports the same bazaar verdict as `settle`. Four payload variants —
   `_forensics/cdp_verify_bazaar.py` — every one returned
   `EXTENSION-RESPONSES: {"bazaar":{"status":"processing"}}`. **Nothing was ever
   rejected**: not the schema, not the MCP `input`, and not the `#tool` fragment
   (12 of 30 already-catalogued MCP tools serve that same fragment —
   `_forensics/mcp_challenge_url_survey.py`).

**Why the catalog was empty anyway — deploy order, from Render's own records:**

| time (UTC) 09.11 | event |
|---|---|
| 14:14:20 | the only paid MCP call of that deployment's life |
| 14:14:39 | it settles through CDP, `tx=0x7bcde0d2…` |
| 14:14:40 | `CoinbaseBazaarDiscovery/1.0` probes **`POST /api/v1/whaleflow`** |
| 14:38:51 | `b356e2706` — the identity fix — goes live |
| 15:02:57 | `6ac8d45` (this handover) live |

At 14:14 the identity fix was **not yet deployed**, so the payload still named the
ROUTE; CDP catalogued the route and probed the route, and the route's entry went
`calls=1 → 2`. **The identity fix had never been exercised by a settlement.**

It has been now — 15:11 UTC, one $0.003 self-payment
(`_forensics/pay_mcp_now.py`; prices, `payTo` and the receiver untouched). The
payload carried `…/mcp#get_whale_flow` while the rail's requirements still carried
the route: `self-broadcast` FAILED (gas wallet holds 0 ETH) → `cdp-settle ok` →
`tx=0x1f4647e0…` → **`CoinbaseBazaarDiscovery/1.0` probed `POST /mcp`**
(initialize, tools/list, and `tools/call` → the challenge). The prober follows the
payload, exactly as the docs say.

**The catalogue entry has still not appeared, and the catalogue says why.**
Polled once a minute for 20 minutes after the settle: no `type=mcp` entry for our
receiver. Then, measured:

| half | entries | updated during 09.11 |
|---|---|---|
| `type=http` | 32,624 | **339 of the first 1,000**, newest 15:20:49 |
| `type=mcp` | 515 | **0 of 515**; newest `lastUpdated` **2026-11-08T23:36:43** |

The MCP half of the Bazaar has not moved all day while the HTTP half updates every
minute, and the newest MCP batch is one server's seven tools probed a second apart
at 23:36 yesterday — so MCP `lastUpdated` is a **crawl** stamp and MCP cataloguing
runs on its own, slower cycle. Our entry is queued, not rejected. **No code change
is justified by this**: every step we control is measured working.

`main.py:3693-3697` still puts the route into `requirements["resource"]`; that is
harmless (the v2 extractor never reads it) and stays as the honest description of
the endpoint the rail settled. `_merged_requirements()` deliberately does not merge
`resource` — correct, because the buyer's payload resource must not be overwritten
by the server's.

Remaining, and only one thing: **the other six tools each need their own paid
call** before they can be catalogued — one catalogue key per
(`resource.url`, `input.toolName`).

**How to re-check this** (read-only, from the session workspace):
`python _forensics/bazaar_our_state.py` and
`python _forensics/catalog_filters_ours.py`. The expected row is
`type=mcp  https://kristo-intelligence-api.onrender.com/mcp#get_whale_flow`.
If it is still absent, re-measure the table above first: **if the MCP half HAS
moved and we are still not in it, cadence is no longer the explanation and this
paragraph is wrong** — the next suspects are the metadata content policy (our
tool's answer opens with prose that tells an agent to send money and call another
URL) and a probe our tool fails.

### The second index: PayAI has us MIS-LISTED

Measured 09.11 16:20 UTC, `_forensics/payai_our_state.py`:

* PayAI's catalogue carries a `type=mcp` row for
  `https://kristo-intelligence-api.onrender.com/api/v1/whaleflow` whose
  `extensions.bazaar.info.input` is
  `{type: "mcp", toolName: "get_whale_flow", transport: "streamable-http", …}` —
  **a TOOL identity glued to a ROUTE url**, written by
  `lastWrite: {source: "settle", at: 14:06:46Z}`. The same pre-fix payload as
  CDP's route row: two independent facilitators made the same mistake because the
  same wrong resource travelled in the payment.
* `discovery/listing-status?resource=…/mcp` → **404 "No catalog row or recent
  write"**: PayAI has never seen the post-fix identity either.
* `…/api/v1/whaleflow` → `listed: true`, `hidden: false`,
  `lastProbe: {at: 15:58:15Z, status: "alive", httpStatus: 402}`, so PayAI
  crawls us and would list the MCP tool too if a verify or settle carried it.
* PayAI totals: 16,986 (16,870 `http` + 116 `mcp`).

**READY TO RUN, NOT RUN** (the owner's rule is that a public catalogue listing
waits for his explicit «Да»): PayAI documents that `/verify` also writes a
catalogue row and a verify costs nothing — `POST
https://facilitator.payai.network/verify` with the post-fix payload
(`resource = …/mcp#get_whale_flow`, `extensions.bazaar.info.input.type = "mcp"`,
`accepted` present; the same body `_forensics/cdp_verify_bazaar.py` already builds
for CDP). Expected: a correct (`…/mcp`, `get_whale_flow`) row, confirmable within
seconds via `listing-status`. The wrong `mcp` row for the route would remain and
may need hiding.

### The original lead, kept as measured history

This was the one live thread; everything else was already closed.

**The gap, measured:** the catalog carries `type=mcp` with **515 resources**. Ours:
**0**. Our six HTTP routes are in it; no MCP tool is.

**What was already fixed** (all deployed, all tested):

1. Our MCP tools advertised `extensions.bazaar.info.input.type = "http"` because
   `_x402_challenge_core` is shared with the HTTP path. An MCP tool declaring
   itself HTTP is not an MCP resource. Now retyped to `type: "mcp"` with
   `toolName`, `transport`, `example`, `inputSchema` —
   `_retype_bazaar_for_mcp()` in `app/blueprints/discovery.py`.
2. The MCP tool could not be BOUGHT at all: `tools/call` returned the challenge
   and never accepted a payment. Now it forwards the caller's own header to the
   HTTP route and serves the route's payload — but only when a **settlement
   actually happened** (`_serve_paid_mcp_tool`).
3. `resource.url` for an MCP challenge was the HTTP route, so CDP filed the
   settlement under the endpoint. Rewritten to `<scheme>://<host>/mcp#<tool>`.

**The settlement is real and goes through CDP.** Logged, 09.11 14:14 UTC:

```
x402 settle phase cdp-jwt       0.00s  ok
x402 settle phase cdp-settle    0.68s  ok
standard x402 settled via cdp: tx=0x7bcde0d2...
```

**And the catalog still shows 0 MCP, with `/api/v1/whaleflow` gaining a second
call instead.** So the settlement was filed under the route again, one hour after
the identity fix was deployed and after a further paid MCP call at ~16:45.

### The next thing to check, specifically

**Does the CDP facilitator index from `paymentPayload.resource` or from
`paymentRequirements.resource`?**

- If the former, fix (3) should have worked and something else is wrong.
- If the latter, the identity must be set on the **requirements** too — that is
  what `_merged_requirements()` sends, and it currently carries the HTTP path's
  terms.

Where to look: `services/connectors.py`, the `body = {"x402Version": 2,
"paymentPayload": payload, "paymentRequirements": payment_requirements}` in
`settle_standard_payment`, around lines 984 and 1034.

**Read the facilitator's actual reply before changing anything.** That is how the
`accepted` bug was found after hours of guessing, and it is the cheapest step:

```python
connectors._facilitator_post(
    "https://facilitator.payai.network", "settle", body)
```

`_forensics/repro_400.py` does exactly this and prints the body.

### 10.11 19:20–20:30 — read CDP's documentation; two of our own conclusions did not survive

The curation bar had been quoted in this project from memory. It is written down,
in `docs.cdp.coinbase.com/x402/seller/get-discovered`, and reading it changed two
priorities.

**1. The memory leak is NOT what blocks curation.** §12/§13 of
`docs/VISIBILITY_MEASURED.bg.md` said the only proven lever is CDP curation, which
needs ≥99% availability over 30 days, "which takes us straight to the memory
problem". That was an *estimate* (hourly kills × an assumed restart length) with no
measurement behind it. Measured instead, from the platform's own probes — Render
GETs `/health` and gunicorn logs each one:

| | measured |
|---|---|
| probe interval (quiet hour, 71 probes) | median **5.0 s**, p90 6.0 s, max 6.0 s |
| non-200 responses around the five OOM kills | **0** |
| windows with no missed probe at all | **3 of 5** |
| missed probe time, 70 minutes of wall clock | **~43 s** → ~8.6 s per incident |
| at 5 incidents/day | 43 s/day = 0.05% |
| **availability (probe proxy)** | **≈ 99.95%** (priority bar is >99.5%) |

The docs also say a curated endpoint that fails consecutive probes is
down-ranked and then dropped — 8-second restarts do not do that.
`_forensics/availability_from_probes.py` reproduces this. **A first version of
that script measured "seconds between consecutive log lines" and reported the
service dead 66% of the time. That is a different question** — an idle process
legitimately writes nothing for minutes. Do not reintroduce it.

**2. The icon we published is a format the Bazaar refuses, and a test locked it
in.** The docs, verbatim: "Supported formats are JPG, JPEG, PNG, WebP, and GIF.
SVG is not supported." We advertised `/static/icons/kristo.svg`, and
`test_bazaar_declaration.py` asserted the SVG by name. Now a PNG generated by
`scripts/make_brand_icon.py`, with the SVG kept as the web favicon. Both the 402
and the A2A card read one constant, `main.X402_ICON_PATH`.

**3. No paid route said WHEN to call it.** That is an explicit curation
requirement and a ranking input ("Bare endpoint names and placeholder text score
zero on metadata quality"). Measured across the Bazaar: **9.3% of 33,392 rows**
carry a "when to use" line — we were in the other 90.7%, 17 of our 19 rows. All
twelve paid paths now carry one, in 176–389 characters. The 500-character ceiling
is a *payment* rule, not a ranking rule: over it the facilitator rejects verify
AND settle. Guards: `tests/test_listing_says_when_to_use.py`, checked against the
defect (10/10 old descriptions rejected, both pre-existing ones accepted).

**4. The facilitator's own verdict on our metadata, read live for the first
time.** The discovery docs say `EXTENSION-RESPONSES` carries the bazaar status —
`success` / `processing` / `rejected` (+ `rejectedReason`). One $0.003 paid call to
`/api/v1/whaleflow` after deploying the new metadata
(tx `0xa2864c7269e000bdf29884cc0a29d55783942875040e6db4b3d3df128ad94083`):

    EXTENSION-RESPONSES: {"bazaar": {"status": "processing"}}

So the declaration is **accepted**, not silently refused. Also all 12 paid routes
re-validated after the change: `valid=True`, `outcome=accepted`, `notes=0`.

**Metadata is submitted with the SETTLEMENT, not read from a crawl** ("On the
settlement call that triggers indexing, set both
`paymentPayload.extensions.bazaar` and `paymentPayload.resource`"), and indexing
takes up to 15 minutes. So a metadata edit is inert until a paid call carries it.
`_forensics/did_the_catalogue_take_it.py` waits out that window and re-reads the
rows.

**What is still true and still the wall.** Curation remains **editorial**: "Meeting
these qualifies an endpoint for review — listing remains editorial, based on
service quality, category coverage, and ecosystem fit." There is no application
form. We now meet all five documented requirements (live mainnet payments ✅,
availability ≈99.95% ✅, health probe ✅, validate 12/12 ✅, agent-ready metadata ✅)
and 14 distinct external addresses have paid us $0.126 on chain. **No new external
payer has arrived from any of this work.** Suite 1313.

### 10.11 20:00–21:30 — CDP DOES see our money. The rail was never the blocker.

Round 2 left one question open: external payments exist on chain, yet CDP reports
`payers=1` on every row of ours. My first answer, written here an hour earlier, was
that PayAI settles instead of CDP and CDP therefore never sees us. **That answer was
wrong, and it is left in the git history on purpose.**

It rested on one log line from the newest external payment (tx `0x2ca6e79f…`,
$0.003, 04.11 02:46 UTC):

    02:46:14 | services.connectors | standard x402 settled via payai: tx=0x2ca6e79f…

**One line is not a measurement.** All ten settlements we have in our logs since
09.11 read `settled via cdp` (09.11: 14:14:39, 15:11:36, 16:29:08, 16:30:11 …;
10.11: 08:12:53.696, 08:12:57.063, 08:13:00.699, 08:13:04.177). Zero read
`settled via payai`. The 04.11 line is the only payai settlement in our history and
predates the verification change.

**What the app actually does** (paid call, 10.11 08:12:52–53 UTC,
`_forensics/render_2026-11-10_0800_0900_rails.txt`):

    x402 rail step challenge_core             0.000s
    x402 verify step precheck_payment_payload 0.000s
    x402 verify step _local_recover_signer    0.041s
    standard x402 locally verified: payer=0xE50c5212… (canonical EIP-712, no facilitator needed for verification)
    x402 rail step extract_nonce              0.000s
    x402 rail step find_settlement_by_nonce   0.316s
    x402 settle phase self-broadcast          0.34s  FAILED — gas wallet 0x9c1eb97e… has 0.00000000 ETH
    CDP JWT built successfully (kid=organizations/3dc43ce6-0…, PEM=True)
    x402 settle phase cdp-jwt                 0.11s  ok
    x402 settle phase cdp-settle              0.64s  ok
    standard x402 settled via cdp: tx=0xafc230574538924888e313c2e26f3e39a4676d17037868f5d5bf073fe55ed8ad
    standard x402 payment settled: payer=0xE50c5212… amount=$0.0030

Three facts, none of which were known before:

1. **Verification is local.** `_local_recover_signer` and "canonical EIP-712, no
   facilitator needed for verification". The `[payai, cdp]` chain is about
   *fact-checking a payload*, and it is no longer even called. It does not describe
   settlement.
2. **Self-broadcast has been broken for a long time.** Gas wallet
   `0x9c1eb97e121a6836200C539a1BF0ecdC37F750dd` holds **0.00000000 ETH** (confirmed
   on Base, not just from the log), so our own broadcast always fails and the flow
   falls through.
3. **CDP settles our payments**, successfully, in about a second.

**Corrected reading of `payers=1`.** CDP sees our money; the only payer it has ever
seen is us. Read from CDP's own free merchant endpoint
(`GET /platform/v2/x402/discovery/merchant?payTo=0xd4cdA900…`, `_forensics/what_cdp_merchant_knows.py`):
19 rows, `l30DaysTotalCalls` 1–5 each, **`l30DaysUniquePayers = 1` on every single
row**, sum 34 calls / 19 "payers" — and that sum is 19×1, not 19 distinct people.
Rows with ≥2 payers: **zero**. Every `lastCalledAt` coincides to the second with our
own canaries, paid from `0xE50c5212e8211639C49276dA190E248B83935763` = the demo key.

So `payers=1` is not a verdict on the rail. It is the exact record of the fact that
**no external payer has ever settled through CDP** — which is a statement about
demand, not about plumbing. The two sound alike and lead to opposite decisions.

**What this retracts.** The pending owner decision to activate the dual-rail CDP
switch is **withdrawn as unnecessary**: the CDP rail is already active and settling,
and `FACILITATOR_CDP_API_KEY_*` must already be present in the environment, because
the JWT is built with a real `kid=organizations/3dc43ce6-0…/apiKeys/ad07bd0b…` and
`PEM=True`. Nothing needed flipping; nothing was flipped.

**What it opens.** Settlement now depends on exactly one outside service, because
the fallback path is disabled by an empty gas wallet. If CDP is unavailable in the
14 November window there is no second working path. Funding that address with a
little ETH restores an independent path — but it spends money and needs the owner.

**And the real conclusion stands unchanged:** the only lever with a large measured
effect (§12: `curated` rows, 30.8% with ≥20 payers vs 0.76% market-wide) is given
editorially. What CDP currently sees is the demo key, so from the platform's point
of view we look like a seller buying from itself.

### 10.11 21:00 — the radar that found us, and the free number it quotes

A forwarded GitHub notification (`Nikolife2016/pulsefeed-x402` issue #3, "radar: N
веток ждут ответа") is a bot that scans GitHub threads naming x402 endpoints and
quotes CDP's per-host stats. It mentioned us four times between 03.09 and 09.10,
always from our own outreach: `kristo-intelligence-api.onrender.com: N листинг(ов)
в Bazaar, оплаченных вызовов за 30 дней M, уникальных плательщиков K` — it walked
1 listing/3 calls/1 payer → 2 listings/4 calls/2 payers (+1 listing, +1 payer,
consistent with 1+1, not with two distinct humans).

**Its numbers come from the endpoint above**, which is free and authoritative; the
radar is not a new data source, it is a nicer wrapper. `_forensics/what_cdp_merchant_knows.py`
reads it directly.

Two things it does tell us:

* **Cold GitHub outreach is a saturated, now-filtered channel.** The radar cut us as
  a bulk mailer in its 10-13 round (`⛔ Отсечено как рассылки: … @hristovdimitri2-hub
  ×1`), and its own note says keyword arguments were tested on 123 threads, fired 88
  times, and only 4 were kept. Our September integration suggestion to
  `AnthonWinther/Trading_bot#1` is still open with no reply.
* **Neighbour benchmarks, measured by a third party:** `agent402.tools` 539
  listings / 4,899 calls / 29 payers; `api.clawfetch.ai` 8 / 478 / 14;
  `api.craigmbrown.com` 31 / 155 / 7; most hosts 1–8 payers. Our own 19 rows sit in
  the same band. This is the same ceiling §9 states, from a source that is not us.

Also confirmed the same round: the free CDP `/validate` call does **not** credit a
row (`_forensics/does_validate_inflate_cdp_counts.py`: two rows read 1 call / 1 payer,
two validations sent, unchanged after ~15 minutes). So CDP's counters are real
settlements — our own canaries — and not probe noise. And our x402scan listing
request (`Merit-Systems/x402scan#1270`) has been open since 08.10 with no maintainer
reply; the only answers are from `lowkeybuilds`, who was right on both counts but is
selling a $29 "Listing Fix". The diagnosis matched our own measurement; do not buy.

### 10.11 — two independent measurers, and a correction to the 99.95% above

Registered on **x402dash** (`POST https://api.x402dash.com/v1/register`), where
1,895 providers existed and none was ours (`/v1/providers?q=kristo` → 0). First
four endpoints accepted, HTTP 201, `verified: true`; the rest wait on the
documented 5/hour/IP limit — `_forensics/register_on_x402dash.py N` continues it.

**x402-list.com has indexed us since 2026-10-29** and publishes independent
numbers: compliance **A, 14/14 checks, none failed**; `payment_ready: true`;
`verified: false` (their FORTE tier is *they* pay a real x402 call — 13 of 1,271
services have it); `reliability_uptime_30d: **98.6%**`.

Day by day: **11-09 and 11-10 are 100%**; the entire deficit is **11-07 (92.13%)
and 11-08 (89.39%)** — the SQLite/dashboard incident days, before the fixes. Their
probe runs every ~16 minutes (67-90/day), so 8-second OOM restarts are essentially
never caught; those two days were ~2 hours of real outage each.

**Correction to the section above:** "availability ≈ 99.95%, the memory leak is not
what blocks curation" was a one-day, 70-minute sample. A third party measures
**98.6% over 30 days**. The honest statement is narrower and more useful: we are at
100% today and yesterday, and we sit below 99% because of two specific days that
predate the fixes. The memory question is not closed — it is "currently healthy,
historically below the bar", and the 30-day number only climbs if 07-08.11 age out
without a new incident.

## Hard-won facts — do not relearn these

- **`accepted` (singular, ONE OBJECT) must travel in the payment payload.** A
  spec-strict facilitator refuses without it:
  `"accepted: Invalid input: expected object, received undefined"`. This is why
  PayAI never settled for us and everything went through CDP. `echo_extensions`
  in `scripts/demo_sponsored_pay.py` now adds it. **Build payloads with that
  helper, never by hand** — hand-building is how `_forensics/pay_mcp_tool.py`
  missed the field for two rounds.
- **A 200 is not proof of payment.** The MCP forward arrives from `127.0.0.1` and
  the free tier grants on IP, so `PAYMENT-SIGNATURE: FAKE` returned real data
  until the settlement check was added.
- **Import `eth_account` and `web3` at boot.** Deferred, the first buyer's payment
  compiles 417 modules — ~20s on a 0.1-CPU instance, which is what made
  `_local_recover_signer` look like it hung.
- **The catalog fluctuates.** Measured 34,156 → 33,058 → 31,000-ish, and
  `nev3r` in the x402 WG tracks the same thing (28,221 ↔ 101,965). A scan that
  finds fewer of our resources than yesterday is probably this, not a regression.
- **Bound every step of the payment rail.** `X402_STEP_DEADLINE_SECONDS` (verify,
  20s), `X402_NONCE_SEARCH_SECONDS` (5s), `X402_SETTLE_DEADLINE_SECONDS` (50s —
  it MUST exceed the facilitator chain's own 15s × 2 budget, or the wrapper is the
  failure). Total 75s, under gunicorn's 120s, asserted by a test.
- **gunicorn `--timeout 120`.** A request that has not answered by then gets its
  worker KILLED, taking every other in-flight request with it. That is what the
  repeated `Background threads started` lines were.
- **Deploy via per-key `PUT /env-vars/{KEY}`.** `PUT /env-vars` REPLACES THE WHOLE
  SET and once destroyed all 33 production variables.

## Never touch

Prices we charge, `payTo`, the receiver (`X402_RECEIVER_ADDRESS`), the commission,
any 402 envelope, `secrets/`, `config.py`, `.env`. `payTo` is a platform invariant:
third-party reliability scoring checks it, and Чет Паркър (PayAPI Market) gave it
as a condition.

## The owner's own words worth keeping

- He could not tell where the money came from on the board. It was because
  `DEMO_PRIVATE_KEY` classified as `external` → "истински клиент", so nine
  self-payments read as nine customers. Fixed: class `own_key` →
  "нашият демо ключ — не е клиент". **A board that cannot separate a customer
  from a test cannot be steered by.**
- He is in the x402 `#wg-domain-discovery` Slack, where the standard is being
  written. `takeshi` (vet402.com) asked whether discovery should carry
  **delivery after settlement** — which our board already models, since it records
  `settled` before the delivery checks because a 425 is a buyer who paid.
  `nev3r` tracks the catalog fluctuation. Both are places our measurements are
  directly relevant. **Nothing external is posted without his explicit "Да".**

### 10.11 21:00 — the first machine buyer that pays without a human picking us

The closest thing to an answer to "how do the first external payers arrive", because
it describes a channel where **a machine pays, not a person**: the Smart Order
Router of `agent402.tools`.

**We are already in their index, and that is not the news.**
`GET https://agent402.tools/api/index?seller=kristo-intelligence-api.onrender.com`:

    routable = true       health = 1  (last five crawls: [1,1,1,1,1])
    toolCount = 22        of which 19 paid
    networks = [eip155:8453]   payTo = 0xd4cdA900…
    discoveryPath = /.well-known/x402    lastVerifiedAt = 2026-11-10T18:45:52Z
    routerDispatchEligible = false
    routerDispatchReason   = settlement_required — "below the settlement floor"

No registration is needed: they read `/.well-known/x402`, find 22 routes and re-probe
health every 30 minutes. Their only paid seller entrance, `POST
/api/index/register`, answers `400 bad-request` for us precisely because we are
already indexed. (I sent that POST before checking, which was wrong: the standing
rule is that nothing external is posted without the owner's explicit "Да". It
returned 400 and created nothing, so nothing was published.)

**What `settlement_required` means, in their own words:**

> on Base the router pays sellers with on-chain settlement history above the floor
> from enough distinct payers; a seller below it is tried only under the small
> unproven ceiling **when its verdict carries unprovenTier**.

Our $0.003 and $0.005 rows carry:

    routerDispatchEligible = false (settlement_required)
    executeViaCallableNow  = true
    executeViaLane         = "unproven"
    unprovenTier           = true   unprovenMaxUsd = 0.05

Our **$0.10** rows (`/api/v1/verify-seller`, `/api/v1/seller-check`) carry:

    executeViaCallableNow = false   (no unprovenTier — above the ceiling)

**So the price excludes us mechanically from the only channel with machine buyers.**
The unproven ceiling is **$0.05 per call and $0.25 per day**, and only after every
proven seller for the task has been passed over.

How far "proven" is, from their own board (7-day window, 3,800 crawled sellers,
33,391 Bazaar rows): rank 50 is `www.blockchainiq.co` with **93 calls / $21.23 / 18
buyers in a week**; rank 1 is 630,596 calls and $12,382.42 from 1,689 buyers. We are
not in the top 50 — 34 calls over **30 days**, nearly all of them ours. A seller that
*is* eligible, `x402.ottoai.services`, reads `{"eligible": true, "reason":
"eligible"}`.

**Why I did not manufacture a payment.** `POST /api/route/execute` is a documented
path where **their router itself buys the result from an outside seller** and resells
it. I could have called it with a task matching one of our routes and had their wallet
pay our payTo $0.003 — a first external payer within the hour. **I did not, and the
reason is not technical.** That is self-funding through a middleman, and both
platforms screen for exactly it: AgentCheck advertises "who has real repeat buyers and
**who funds their own customers**", and agent402 has a whole rule,
`settlement_self_funded` — "a payment made with USDC that the wallet it pays had sent
the payer earlier is the seller's own money coming home and does not count". A payment
we arranged ourselves is not an external payer; it would corrupt the only number the
goal measures.

**What follows.** The channel is real and machine-run, and entering its paid half
needs two things, both already on the table: **the price** ($0.10 sits above the
unproven ceiling; $0.003–0.005 sit inside it) and **real distinct payers** (the
settlement floor is the same wall the goal measures). Their docs add a third, free
one: the router shortlists by how well a description matches the task — "an accurate
description is how you win it" — which is the metadata lever already in progress.

New probes: `who_would_pay_us_without_choosing_us.py`,
`what_the_market_charges_for_safe_to_pay.py`,
`what_an_agent_sees_when_it_searches.py`, `which_of_our_rows_are_incomplete.py`,
`has_any_new_external_payer_appeared.py`.

### 10.11, later — CORRECTION: the price is NOT the gate, and our own money buys nothing

The paragraph above ends "**So the price excludes us mechanically from the only
channel with machine buyers**", and lists the price as the first of two levers.
**That is wrong. Retracted, in writing, the same day.**

The router honours `top: 25` (it ignores `limit: 25`) and then returns 25 candidates
instead of 5 — enough to see not just who wins but the flag each row carries. With
`top: 50`, our own rows:

| task | our rank | price | `routerDispatchEligible` |
|---|---|---|---|
| live DeFi trading signal for ETH | **1/5** | $0.003 | **false** |
| arbitrage spreads between Base DEX venues | **1/5** | $0.005 | **false** |
| audit incoming USDC payments of any Base address | **1/5** | $0.10 | false |
| is this x402 seller really being paid… | **1/5** | $0.10 | false |
| on-chain USDC sales and revenue history | 3/5 | $0.005 | **false** |
| verify a seller before paying it on Base | 5/5 | $0.10 | false |

Three first places, three price points, six times `settlement_required`.

Three independent measurements say price decides nothing:

1. our **$0.003** row ranks **#1** and is still `false` — a $0.05 ceiling would
   have let it through;
2. across 200 rows from 8 tasks, **ten price points carry both verdicts** — $0.001,
   $0.002, $0.003, $0.005, $0.01, $0.02, $0.03, $0.05, $0.10, $0.15 each have
   `eligible: true` *and* `eligible: false` rows;
3. **five `eligible: true` rows have exactly ONE payer** — `insider` on FilingsPulse
   is $0.10 with 1 payer and 14 calls, the same price as our excluded
   `verify-seller`; and `eligible: false` rows run up to **304 payers**. So the count
   is not the gate either.

**Our own payments buy nothing.** Traced on Base over the last 800,000 blocks:

    payer -> receiver    47 payments, 0.7590 USDC, blocks 55,082,300 .. 55,712,490
    receiver -> payer     0
    anyone -> payer       0     (the demo wallet received no USDC in this window)
    anyone -> receiver   47     every one of them from the demo key 0xE50c5212…

So the literal reading of `settlement_self_funded` ("the receiver had sent the payer
the money") does **not** explain the refusal — no such transfer exists. The
conclusion is worse than the explanation: **47 self-payments, zero open gate.**
Whatever the condition is, it does not count our own money and cannot be bought with
it.

**What follows.** The retraction above removes a planned fix: a $0.005 pilot would
not make `verify-seller` routable, because our $0.003 row is already #1 and still
excluded. The router is a real machine channel and **already ranks us first for 4 of
10 real tasks**, but will not execute to us, and the gate is a quality of settlement
history that **cannot be self-manufactured**. Therefore the first external payer
cannot come from the router. It has to come from a surface that does **not**
pre-check our history and instead selects by name and description: CDP catalogue
search, `x402scan`, AgentCheck. There we already rank #1 for our own name and are
absent for the words buyers type — that lever is the one that stays.

The price question does not disappear, it changes role: it does not open the machine
channel, it decides whether a buyer picks us in the catalogue, where 163 competitors
for "is it safe to pay" have a median of $0.010 and we ask $0.10.

New probes: `why_the_whale_alias_never_surfaces.py`,
`what_opens_the_settlement_floor.py`, `is_our_payer_our_own_money.py`,
`who_funded_the_demo_wallet.py`; data in `agent402_route_top50.json` and
`who_funded_the_demo_wallet.json`.

### 10.11 21:35 — CDP search reads `tags` and the description, NOT the URL. Every route now says its own job.

The one sentence this project kept repeating — "CDP ranks on the words in a
resource URL" — is wrong, and the proof is impossible to explain any other way:

    query "verify seller"   ->  /api/v1/verify-seller is ABSENT from all 9 rows
                                (the query is a literal substring of that path)
    same query, rank 2/17   ->  /api/v1/seller-check — SAME handler, SAME price,
                                same service; the only difference is its tags and
                                its description

Every row that wins a query contains the buyer's words verbatim in `tags` or in
the description: `dex-arbitrage` for "dex arbitrage", `seller check` for "seller
check", `is this token safe` for "token safety". The URL is decoration.

**What was broken.** `X402_RESOURCE_TAGS` had entries only for the five aliases, so
all seven canonical paid routes fell back to `X402_DEFAULT_RESOURCE_TAGS` and
published the same five words — `crypto, whale-tracking, x402, arbitrage, signals`.
None of the five is the job any of the seven does, and the dearest route
(`/api/v1/verify-seller`, $0.10) was findable by another route's words. Across 20
buyer-intent queries we appeared for **11 of 20 — every one through an alias, never
through a canonical route**.

**The fix** (commit `865bae5`, deployed and verified on the live 402s — all 12
routes publish the committed tags): each canonical route owns its five tags and its
description now OPENS with the words the job is asked for in, keeping the honest
scope after the em dash.

    /api/v1/verify-seller  verify-seller, seller-audit, x402-seller,
                           payment-evidence, due-diligence
    /api/v1/whaleflow      whale-flow, whale-transfers, large-transfers,
                           smart-money, base
    /api/v1/signal         defi-signals, trading-signals, market-signal,
                           crypto-signals, base
    /api/bot-status        telegram-bot-status, sales-bot, heartbeat, uptime,
                           service-status
    /api/arb/opportunities dex-arbitrage, price-spread, cross-venue, defi, base
    /api/sales             usdc-revenue, onchain-sales, settlement-history,
                           payment-history, base
    /api/stats             service-stats, usage-stats, market-snapshot,
                           fear-and-greed, base

The two honest limits survive as **tests, not intentions**: `/api/stats` may not
claim "market stats" (no market cap, no volume) and `/api/bot-status` must still
say whose bot it reports. The decision to leave those two without an *alias* is
unchanged — this changes what they publish, not what they pose as.

**Not yet visible in CDP.** Its catalogue rows still carry the old generic tags
(read at 21:47), which is "not yet", not "no": CDP re-read our 10.11 descriptions
on its own schedule, so it does re-read. The claim to measure next round is whether
`/api/v1/verify-seller` enters the results for "verify seller" and whether canonical
rows win places that only aliases won before.

**And the goal's own number, unchanged:** 19 CDP rows, 34 calls, every row
`l30DaysUniquePayers = 1`; over the last 120,000 Base blocks the receiver took 2
payments, both from the demo key. **No external payer.**

### 10.11 21:50 — the third field: `serviceName` was one name for twelve routes. And CDP reads a 402 only at settlement.

§19's fix covered `tags` and the description. The third field CDP matches was still
hard-coded: `"serviceName": "Kristo Intelligence"` on every route, and a company
name matches nothing a buyer types. In CDP's index every winning row is named after
its job — "Check an x402 seller's trust", "x402 seller dossier", "Token Safety
Check" — and one seller legitimately carries several such names (agent402 has four
across four endpoints), so a per-route name is the normal shape.

`X402_RESOURCE_SERVICE_NAMES` (commit `785fb7e`, deployed and verified — **12 of 12
live 402s publish their committed name**): `Kristo x402 seller audit`, `Kristo whale
transfers`, `Kristo crypto signals`, `Kristo DEX arbitrage`, `Kristo USDC revenue`,
`Kristo market snapshot`, `Kristo telegram bot status`, `Kristo whale alerts`,
`Kristo trading signals`, `Kristo DEX arbitrage spread`, `Kristo seller check`,
`Kristo onchain sales`. The three descriptions that come from `REAL_X402_ROUTES`
(and therefore `/.well-known/x402.json`) now open with the buyer's words too.

**The operational fact that matters more than the edit.** CDP snapshots the live 402
**at settlement** and keeps that copy until the row settles again. Proof from its own
rows: `verify-seller`'s `lastCalledAt` is 09.11 07:10 and its stored description is
the 09.11 text; `whaleflow` settled at 10.11 17:47 and stores the text that was live
at 17:47 — both changes to that text came later.

So: crawling surfaces (agent402 every 30 min, `/.well-known/x402`) pick the new words
up for free on their own; **CDP — the only catalogue where a buyer chooses and pays —
picks them up only on the next settlement of each row.** Refreshing is therefore not
"keeping rows alive", it is the only way this fix reaches the place where the choice
is made. Ten cheap rows total **$0.042**; the two $0.10 rows add **$0.20**. If those
two drop to $0.01 for the pilot, the same refresh costs **$0.062** and matches the
$0.010 median of the 163 competitors in the "is it safe to pay" category.

### 10.11 22:20 — PayAI is a second live catalogue and ranks us first; the free validator refreshes nothing

PayAI runs its own Bazaar with a search:
`GET https://facilitator.payai.network/discovery/search?query=…&limit=…`. It had
never been measured, and it is friendlier than CDP:

    "verify seller"        rank 1 of 5        "arbitrage"          rank 1 of 50
    "trading signal"       rank 1 of 18       "whale flow"         rank 3 of 24
    "telegram bot status"  rank 1 of 2        "whale alerts"       absent
    "onchain sales"        rank 1 of 3

Seven of eight buyer queries find us; five of them put us first.

**But its metadata is stale too, and two rows are broken.** `/api/sales` and
`/api/stats` still carry the PLACEHOLDER "`Kristo Intelligence - paid API data
(/api/sales)`" — text the code stopped producing on **05.11**. So in a live
buyer-facing catalogue two of our rows still describe nothing.

**And the free path to publish is closed.** The only keyless entrance to CDP
(`POST https://api.cdp.coinbase.com/platform/v2/x402/validate`,
`{"resource": …, "method": "GET"}`) answers `valid=true` for our routes but does not
touch the stored copy. Experiment: three test rows validated once each plus two
CONTROL rows left untouched, compared after 12 minutes — **no row changed, on either
side**. Publishing the new words has a price:

    ten cheap HTTP rows            $0.042
    all twelve HTTP rows           $0.242   ($0.20 of it the two seller-audit rows)
    all nineteen rows (with MCP)   $0.368
    same, if the three $0.10 rows become $0.01  $0.062 / $0.098

The tool already exists — `scripts/phase1_paid_call.py --path <route>` makes exactly
one paid call, so the refresh is one call per row. **Nothing is spent without the
owner's explicit "Да".**

### 10.11 22:40 — what is actually paid for today, and a false alarm cleared

**The false alarm first.** The local sqlite store carried a repeating pattern today:
pairs of `/api/v1/whaleflow` and `/api/v1/signal` payments REJECTED every 10–30
minutes between 15:15 and 19:50, with our own two refusal strings —

    "authorization expired: validBefore=0 <= now=1794340148"   (connectors.py:262)
    "verify exceeded the 0s deadline — the rail refused"       (main.py:4037)

It looked exactly like an external client being turned away every half hour, which
would have made the blocker OURS rather than discovery. It is not: every user agent in
that table is `Werkzeug/3.1.8` (the Flask test client), `X402_STEP_DEADLINE_SECONDS`
is **unset on Render** (so the live deadline is the 20 s default, not 0), and an hour
of Render logs — 1000 lines, 19:55–20:10 — contains **zero** rejections, zero
`validBefore`, zero `settled via` and zero rail steps. The rows are local test noise.
Render also runs on Postgres (`DATABASE_URL` is set), so the local sqlite is an
artifact, not a copy of production.

**Then the measurement that settles the price decision.** 12,000 CDP rows sampled
(12 pages × 1000, `type=http`), split by `quality.lastCalledAt`:

    12,000 rows, paid within 48h: 2,325 (19.4%)
      median price of the paid ones: $0.0085   (p25 $0.0028, p75 $0.0200)
      median payers: 3     72.8% have >=2 payers  (66.1% of all rows do)

    share paid within 48h by price band
      $0.001-0.005   4,141 rows   17.2%
      $0.005-0.01    1,823 rows   25.7%   <- the densest
      $0.01-0.02     2,146 rows   22.0%
      $0.02-0.05     1,541 rows   21.0%
      $0.05-0.099      968 rows   18.4%
      ~$0.10           470 rows   14.3%   <- ours
      >$0.10           847 rows   11.1%

    in our own category (tags with security/audit/safety/trust/risk):
      170 rows paid recently -- 46 at $0.01, only 10 at $0.10

So $0.10 IS paid, at about half the rate of the $0.005–0.01 band, and in the
"is it safe to pay" family the buyers cluster at $0.01 by 46 rows to 10. The pilot is
not a preference; it is where the paid rows in our category actually are. Also
recorded: our twelve rows have one payer each while the median recently-paid row has
three.

Caveat kept: the sample is a 12,000-row slice of ~33,000 taken on consecutive pages,
not a random sample, so the numbers describe that slice. The direction is consistent
in every band.

### 10.11 23:05 — who looks at us and does not pay, and the 402 is not the blocker

Three hours of Render access logs (1,187 parsed request lines) name every user agent
that touches a PAID route. Roughly twenty automated agents crawl us hourly and **not
one pays** — they are directories, liveness monitors and rankers:

    Agent402/1.0            CarbonMonitor/0.1 healthcheck
    x402station/0.1         AgentRankProbe/0.1 (spark.tail6ec125.ts.net)
    alalanet-prober/1.0     SentinelOracle/0.1 (glimind.com)
    mcp-health-probe/0.1    agents-trust-probe/1
    lumiere-paycheck-prober nohumans.directory-probe/1.0
    mcpbeat/0.1             mcptry.com indexer
    CreoraPublicReader/1.0  JarvisClaw-HealthCheck/1.0
    Mekler-Conformance/1.0  InterfaceDeltaBot/1.0 (interfacedelta.com)
    x402-list-monitor/1.0   protogrid-probe/0.1
    copilot-cli/1.0.103-unstable

One tell worth keeping: `nohumans.directory-probe` fetched the free `/sample` routes
first (200) and the paid ones after (402) — some of these agents check what they would
get before deciding.

**The "our 402 is unreadable" hypothesis is dead.** The live `PAYMENT-REQUIRED` header
base64-decodes to a valid v2 object, and header and body agree on every payment field
(scheme exact, network eip155:8453, atomic amount, payTo, asset, maxTimeoutSeconds,
extra = USD Coin v2 domain) on /api/v1/signal, /api/v1/verify-seller and
/api/v1/whaleflow. **So the pending "clean up the three copies of accepts and the
manual X-Payment-Proof flow" question is cosmetic, not a blocker** — a standard client
can pay us today.

The two measurements together say the constraint is not discovery. Twenty agents see
us every hour and none buys, we rank first for the words we sell, and the 402 conforms.
What is left is the price (§22: 46 paid rows at $0.01 against 10 at $0.10 in our own
category) and asking someone to try — both outside the code.

### 10.11 23:30 — final state of the objective, and one correction

The goal's own number, at the end: **no external payer.** 19 CDP rows, 34 calls in 30
days, every row `l30DaysUniquePayers = 1`, **zero rows with 2 or more**; on chain over
the last 120,000 Base blocks the receiver took 2 payments, both from the demo key
0xe50c5212… (last at block 55,712,490). Nothing in this session changed that.

What is live and what is frozen:

    live 402s (12 routes)      new tags, serviceName and descriptions -- PUBLISHED
    /.well-known/x402, x402.json   the new descriptions
    PayAI Bazaar               rank 1/5 "verify seller", 1/3 "onchain sales",
                               3/24 "whale flow" -- but with the OLD text
    CDP catalogue and search   FROZEN at each row's last settlement, so we are still
                               absent for "verify seller", "x402 seller audit",
                               "token safety"
    agent402                   has NOT re-read the metadata, two hours after deploy

**Correction to §20.** That section said agent402 "re-crawls every 30 minutes" and
would therefore take the new words for free. It does not: two hours after the deploy
its index is byte-identical (32,798 bytes, `Kristo Intelligence` ×5, `Live whale flow`
×3). Its 30-minute cycle is liveness, not metadata.

What remains, all three outside the code:

  1. publish into CDP — one paid call per row: $0.042 for the ten cheap rows, $0.242
     for all twelve HTTP rows, $0.368 for all nineteen. Tool already exists:
     `scripts/phase1_paid_call.py --path <route>`.
  2. the price — §22: 46 paid rows at $0.01 against 10 at $0.10 in our own category;
     a $0.01 pilot on the two seller-audit rows makes step 1 cost $0.062.
  3. ask someone to try — the only channel with a short time constant, and an external
     send, so it needs the owner's explicit "Да".

Nothing was spent and nothing was sent this session.

### 11.11 — the owner said yes to the pilot. Executed, and CDP finds us now.

**The price** is a deployment setting, not a code change: `KRISTO_VERIFY_SELLER_PRICE=0.01`
set as a SINGLE env key on Render (38 → 39 variables, nothing else touched; the
collection `PUT /env-vars` that replaces everything was never used). `config.py` is
untouched because the constant already reads `os.getenv`, so the live 402s AND the
manifests built from the same constant publish $0.01, while the repository keeps its
default and the "verify-seller is the dearest route" test stays true. **Note for next
time: an env change does NOT trigger a deploy on this service — an explicit
`POST /services/<id>/deploys` was needed.** Reverts 11.12.2026 (reminder armed).

**The publish: 12 paid calls, $0.062** — signal/whaleflow/whale-alerts/trading-signals
at $0.003, arb-opportunities/arbitrage-opportunities/sales/onchain-sales/stats/
bot-status at $0.005, verify-seller and seller-check at $0.010. Eleven returned
`{"ok":true}` with a tx hash; the twelfth (`/api/v1/verify-seller`) **paid and did not
deliver** — the route needs a `receiver` query parameter and the helper did not send
one, so it answered `receiver_required` and $0.01 bought nothing. Re-run correctly with
`?receiver=…` on the alias `seller-check`. On chain: 12 transfers, exactly $0.062.

**The result.** The catalogue view lagged ~20 minutes, then all twelve rows carried the
new `serviceName`. The search, which is the actual measure:

    query                     before              after
    verify seller             ABSENT of 9         rank 3/11
    x402 seller audit         ABSENT of 17        rank 4/17
    defi signals              ABSENT              rank 1/6
    market stats              ABSENT              rank 2/4
    whale flow                rank 9/12           rank 3/13
    whale transfers           --                  rank 3/9
    seller check              --                  rank 1/15
    telegram bot status       --                  rank 1/13
    onchain sales/usdc rev    --                  rank 1/3 and 1/6
    dex arbitrage             --                  rank 1/14
    trading signal            --                  rank 4/12

**12 of 14 queries find us, five of them first.** We are still absent only for "is this
seller safe to pay" and "token safety", both honestly: we do not give a safety verdict
and we do not check tokens.

**A defect this found:** paying `/api/v1/verify-seller` WITHOUT `?receiver=` takes the
money and answers `receiver_required` — the buyer loses the call. The parameter is
declared in the bazaar extension, so a careful agent sends it, but the refusal is on our
side and fixable (return something useful without the parameter, or put a working
default address in the 402's resource). **Not touched without a decision.**

### 11.11 — the board audit the owner asked for: the 02:47 payment, traced

The owner saw `2026-11-11 02:47:06 · $0.003 · пазарна проверка, робот — не е клиент` and
asked where it came from. Traced through the chain, the service's own logs and the
board's API:

    block 55,874,253   tx 0xdc6dea0e…c2cd74b   0.0030 USDC
    payer  0xA19F621581DBc851a21D6179868111709a52aCCC
    02:46:58  x402 payment required: endpoint=/api/v1/signal, price=$0.003
    02:47:04  standard x402 locally verified: payer=0xA19F…aCCC
    02:47:06  standard x402 settled via cdp (settle TOTAL 1.36s)
    02:47:06  Recorded real sale: USDC $0.003000

So it is a real x402 payment for **/api/v1/signal**, settled through CDP, with a locally
verified signature. Not an artefact and not ours.

**Is the "robot" label right? Re-fingerprinted today rather than trusted.** The address
was promoted from the watchlist to `market_crawler_a19f` on 17.09 on a 30-day
fingerprint (125 transfers / 98 distinct receivers), and the file itself says judgements
are revisable. Last 1,000,000 blocks (2.3 days): **508 outgoing transfers to 269 distinct
receivers** (~220/day), our receiver among them. The label holds — it crawls the whole
market, so its payment means "we are in the crawl set", not "someone chose us". Its
SECOND payment to us (the first was 09.09).

**The board's numbers check out**, read from its own API rather than a screenshot:
`{"date": "2026-11-11", "requests": 11671, "sales_count": 13, "sales_volume_usd": 0.065}`
= 12 refresh payments ($0.062) + 1 crawler payment ($0.003). The demo key stays a
separate class (`own_key`), the crawler is `sampler`, and "real customer" stays empty.

**The honest note.** By the goal's LITERAL wording ("measured with a different payer …
on chain") this payment satisfies it: the payer is not the demo key and is a real
external agent. By its MEANING ("one that chooses us") it does not: the same address
pays 269 different receivers in two days. Both readings are on the table and the choice
is the owner's — not mine to make for him.

Also: CDP's `quality` block has not yet recorded today's settlements (still
`l30DaysUniquePayers = 1`, `lastCalledAt = 09.11`) even though the row's metadata did
refresh — metadata and quality update on different schedules. And a new catalogue turned
up in the logs: `x402rank-probe/1.0 (+https://x402rank.com/methodology)`.

### 11.11 — the owner said yes to three things; all three done

**1. The verify-seller defect is fixed** (commit `e3590b5`, deployed and proven with
money). The rule now: **a request we cannot serve is never settled.**
`_x402_unservable_payload(endpoint)` reads the SAME declaration the 402 publishes
(`X402_INPUT_QUERY_PARAMS` and its `required` list), and `_x402_paywall` calls it only
when a payment credential is PRESENT — so an unpaid GET of the bare path still returns
the canonical 402, because that challenge is what the catalogues read to index the route.
Refusing the bare path outright would take the route out of discovery to fix a billing
edge.

Verified live:

    bare path, no credential          402  (catalogues keep working)
    fake credential, no receiver      400  missing_required_parameter
    same via the seller-check alias   400  missing_required_parameter
    fake credential, WITH receiver    401  (reaches verification, as it should)
    argument-free route               401  (the guard never applies)

And the money proof: a real signed payment without `receiver` answered
`missing_required_parameter` and the demo wallet's balance was **unchanged**
(1.378515 → 1.378515, **$0.00**). The same call cost $0.01 and delivered nothing before
the fix. Six new tests in `tests/test_declared_input_matches_handler.py` pin the ORDER,
not just the status: the settle function is monkeypatched and must never be called. Two
of them stub the view function — letting /api/v1/verify-seller run made the file hang ten
minutes doing live chain reads.

**2. x402dash registration, in batches.** It reported 4 of our 12 routes; the old script
always submitted `PATHS[:N]`, so it could never reach the rest — the new
`_forensics/register_x402dash_batch.py <offset> <limit>` takes an offset and treats 409
"already registered" as progress rather than a stop. Result so far: **4 → 7**
(whaleflow, signal, stats registered; whale-alerts was already there), then the 5/hour
limit answered. The remaining four (`/api/sales`, `/api/bot-status`,
`/api/arb/opportunities`, `/api/v1/verify-seller`) have a reminder armed ~65 minutes out.

**3. TASK.md refreshed and committed.** It was a 30.09 snapshot claiming 6 paid routes,
423 tests and a werkzeug production server. It is now a short entry point naming
HANDOVER.md and docs/VISIBILITY_MEASURED.bg.md as the sources of truth, with today's
verified numbers, the open decisions and the rules that are not broken. Two audit
documents reference it, so refreshing beat deleting.

Suite 1322.

## 27. x402scan.com: are we paid or free? (measured 11.11.2026)

The owner's question: if x402scan shows us as free, we are "free" in a catalogue
with thousands of paid rows, and that is a real reason nobody pays us.

**Answer: we are shown as paid.** Measured against the app's own public tRPC
queries (`_forensics/what_x402scan_shows_about_us.py`, read-only, no payment):

* Our server `https://kristo-intelligence-api.onrender.com` id
  `0c176841-4de1-4087-906d-e5d41f414ace`, 15 rows.
* **7 rows carry a price** (`< $0.01` for $0.003/$0.005 — their `formatCurrency`
  collapses sub-cent) and a stored 402 response whose `accepts` point at our
  `payTo`. All 7 answer 402 on the live host; all 8 free rows answer 200.
* The other 8 rows are our own docs (`/openapi.json`, `/llms.txt`, `/health`,
  `/dashboard`, `/.well-known/x402`, `/.well-known/x402.json`,
  `/api/mcp/manifest`, `/api/v1/agents`) and carry the **Public** badge, not
  "Free". They are genuinely free.
* The "Activity" section on our server page shows **84 transactions, $0.904,
  8 unique buyers over 30 days**; all-time 97 / $0.923 / 14, last
  `2026-11-11T06:04:32Z`.

The catalogue is 221,987 rows, 198,120 with `accepts` (198,076 live). The "689
paid" figure in the radar is x402scan's own sales count, not the catalogue size.

Three real defects surfaced, and one of them was fixed on the spot:

1. **`/api/v1/verify-seller` was missing from x402scan.** Their own discovery
   reads our `openapi.json` (15 endpoints, `authMode=paid`, `price=0.010 USD`)
   and reported 14 registered / 1 unregistered — the pilot route. Our rows were
   frozen at 2026-11-04T17:37; their facilitator sync is paused
   (`FACILITATOR_SYNC_PAUSED = true`), so it never refreshes. **Fixed**: I ran
   the public mutation `public.resources.registerFromOrigin` (the same call the
   page's "Refresh" button makes) with `origin=https://kristo-intelligence-api.onrender.com`.
   It answered `success:true, registered:7, publicCount:8, failed:0, skipped:0,
   deprecated:0, total:15`; the row `/api/v1/verify-seller` now carries
   `amt=10000`, `price=0.010 USD`, and the origin's `updatedAt` moved to
   2026-11-11T18:11:18Z. Nothing was deprecated.
2. **A dead second copy of us**: x402scan keeps a separate server
   `https://kristo-intelligence.vercel.app` (id `73148ccf-…`), 16 rows, 12 of
   them paid ($0.05–$0.10, `success=true`, last crawl 05.08.2026), pointing at a
   host returning `404 DEPLOYMENT_NOT_FOUND`, with **0 transactions**. Any agent
   that lands there sees a broken shop. There is no public way for us to remove
   it.
3. **MPP conformance warning.** The registration answered `warningDetails` for
   all 7 paid rows: `MPP_NO_PAYMENT_CHALLENGES`, severity `error`, "WWW-Authenticate
   header contains no Payment challenges". Our 402 sends
   `WWW-Authenticate: x402 realm="kristo-intelligence", …` — the legacy x402
   scheme, not the MPP `Payment` challenge. An x402 client is unaffected; an
   MPP-native client (mppx, Tempo) would not see a payable offer. This is a real
   gap, not a blocker, and the badge stays "Paid" because it is derived from
   `accepts[0].amount`, not from the warnings.

Also note: our prices render as `< $0.01`, so the catalogue never shows the real
$0.003/$0.005.

Suite 1322.

## 28. Four defects found from OUTSIDE, all in the transport layer (11.11.2026)

The owner approved fixing four things that external raters had already found.
Every one of them was invisible to a server-side client and fatal to a class of
buyer, which is why a catalogue of 85 paid calls contained none of the affected
kind. Fixed together, with 15 new tests
(`tests/test_paywall_transport_fixes.py`).

**1. CORS preflight — no browser agent could ever pay us.**
Lumière PayCheck graded `/api/v1/verify-seller` and reported, verbatim:
*"Browser agents — Can't pay it yet: CORS headers missing (server-side agents are
fine)"* and *"The CORS preflight (OPTIONS) is refused with HTTP 402."* Reproduced
locally: `OPTIONS` returned the canonical `402` carrying
`Access-Control-Allow-Origin: *` but **no** `Access-Control-Allow-Methods` and
**no** `Access-Control-Allow-Headers`. A browser sends the preflight first and
aborts on that answer, so the paid retry never happened. Both reference
implementations in this niche answer it correctly — measured the same hour:
`tradingagentstack.com` → `204` + `Allow-Headers: content-type, payment-signature,
x-payment`; `x402pulse.dev` → `204` + `Allow: GET, HEAD, OPTIONS, POST`.
**Fixed**: `before_request` answers `OPTIONS` with `204` before the paywall can
challenge it, listing the payment headers we accept. A preflight also no longer
consumes a free-tier call.

**2. A method the route does not answer was settled before it was refused.**
Flask runs `before_request` even after URL matching has already failed, so a
`POST` to a GET-only paid route reached the paywall, was challenged, was
**settled**, and only then died with a `405` from the dispatcher. Not theoretical:
on 21.10.2026 `JarvisClaw-Federation/1.0` POSTed `/api/v1/signal`, paid $0.003 and
got the 405 — the row is still in `payment_guards` with `delivered_at IS NULL`,
which is exactly the `n_paid_undelivered` a payer agent counts against a seller.
**Fixed**: `routing_exception instanceof MethodNotAllowed` is refused with a
`405` + `Allow` before any credential is read, and the test asserts the
settlement rail is never reached.

**3. `MPP_NO_PAYMENT_CHALLENGES`** (x402scan, severity `error`, all 7 paid rows).
MPP is the Machine Payments Protocol, contributed by **Tempo × Stripe** (SDK
`mppx`, IETF spec at `paymentauth.org`), and it activated HTTP 402 with a
`WWW-Authenticate: Payment …` challenge. **Fixed** by adding a second `Payment`
challenge in the same response (MPP documents multiple challenges explicitly),
carrying the real terms as base64url JCS `{amount, currency, recipient}` and an
HMAC-bound `id`. It advertises `header="PAYMENT-SIGNATURE"` on purpose: that is
the field our existing rail verifies, so the advertised path is honourable. A
native MPP `{challenge,payload,source}` Credential is **refused with a 401 that
settles nothing**. The legacy `x402` token is byte-identical, and a test pins it.

**Measured caveat, do not lose this:** *neither* `tradingagentstack.com` *nor*
`x402pulse.dev` emits an MPP challenge — checked live. So this made us **ahead of
the field**, not level with it, and it was never the reason anyone failed to buy.

**4. The local SQLite said `file is not a database` — 1,335 times.**
`/api/dashboard/data` returned `500` on 10.11 (976 times) and 11.11 (320), and
the board served `stale=true` with the log line
`dashboard: background refresh failed (variant (False, False)): file is not a
database`. `KRISTO_DASHBOARD_DB=data/dashboard_state_v2.db` sits on the
container's **ephemeral** disk, so there is nothing to restore. The operator's
documented remedy was to point the variable at a fresh name — a human plus a
deploy at exactly the moment the board is telling visitors the service is broken.
**Fixed**: `DashboardStore._ensure_db` now catches `sqlite3.DatabaseError`,
**quarantines** the file (renamed to `*.corrupt-<UTC>`, never deleted, sidecars
removed) and creates a fresh one, once. Safe because that file holds only
`payapi_state` and the scan `meta` watermarks; the money table, the replay lock
and every history live on PostgreSQL via `HistoryStore`. One subtlety worth
keeping: `sqlite3.Connection.__exit__` commits but does **not close**, so the
handle had to be closed explicitly — on Windows an open handle makes the
quarantine rename fail with `WinError 32`, i.e. the healing would have worked
everywhere except the operator's own machine.

Suite 1342.

## 29. The direction, chosen from the data (11.11.2026)

The owner's answer to "where should Kristo go?" was **"не зная още — избери ти от
данните"**. This is that choice, with the evidence it rests on.

### What the measurements actually say

* **The market is small and the money is at the top.** x402scan, 30 days to
  11.11.2026: **4,731,875 payments, $1,753,871, 30,248 buyers, 13,979 sellers** —
  an average ticket of **$0.37**. Chainalysis (03.06.2026) puts **95% of settled
  VOLUME in payments above $1**, with the $0.10–$1 band at 4%.
* **Roughly half the boom was fake.** Artemis: ~50% of peak transactions were
  "gamified" (wallet-to-wallet between one operator); an earlier reading put 48%
  of the count and 81% of the dollar volume as non-organic. The daily count fell
  from 731,000 (Dec 2025) to ~57,000 (Feb 2026) — **−92%** — and then matured.
  Our 11 external payers being bots is therefore the NORM, not our failure.
* **Chain: we are on the right one.** x402scan, same window: Base **3,928,600**
  (83.0%) vs Solana **798,702** (16.9%) — the two sum exactly to the headline.
  Headlines claiming "Solana 65–90%" use other scopes; Sato Hub documents why the
  numbers are not comparable.
* **The largest real 402 traffic is not agent→agent.** Cloudflare: **over 1
  billion HTTP 402 responses a day** to AI crawlers, "well above payments between
  agents", plus a Monetization Gateway (01.07.2026) and default crawler blocking
  from 15.09.2026.
* **Our own record.** 11 distinct external payers, 27 payments, **$0.089
  lifetime**, all bots (`probe402-settle-leg`, `JarvisClaw-Federation`, CDP's own
  crawler). 13 routes at $0.003–$0.10. The highest-priced route,
  `/api/v1/verify-seller` at $0.10, has **zero external buyers** — and
  `tradingagentstack.com` sells the same product at **$0.01**.

### The one asset nobody else has

We are ourselves an x402 seller, and we keep a **delivery ledger**:
`payment_guards.delivered_at`, 90 settled / 82 delivered, written by the
`after_request` hook. That lets us measure **settled-but-not-delivered per
seller** from the seller side — the exact axis the raters cannot see:

* Lumière PayCheck grades `/api/v1/verify-seller` **C** purely because "delivery
  not yet confirmed";
* TradingAgentStack's product is a check *before* you pay, and its own docs admit
  delivery is what it cannot confirm;
* vet402 carries `n_paid_undelivered` but only ever measures its OWN probes.

Add `request_log.user_agent` plus the existing `classify_payer`
(`integrations/dashboard_store.py`, categories canary/sampler/external) and we
can publish the **agent / script / noise** classification that PayAI named as an
open problem on 05.11.2026 — the industry is explicitly asking for it.

### The move

**One paid product at $1.00 — a Delivery Report — and one free public page.**

The paid route answers what a payer agent needs *after* it has been burned: does
this seller actually deliver what it settles? Filled from data we already hold —
settlement vs delivery per seller, facilitator settlements into the payTo, payer
concentration and the repeat-payer curve, the agent/script/noise label, the
seller's own catalogue declaration vs what it serves, and the published ratings
from agenteconomy / Lumière / vet402 with their dates.

The free page is the distribution engine: one page per seller scored on
**delivery**, updated daily. It costs us nothing — the data is already collected —
and every listed seller is a reason for someone to visit. The $1 report is the
deep version.

**Keep all 13 micro routes exactly as they are.** They cost nothing, they keep us
in every catalogue, and they are the funnel.

### Rejected, with the number that rejects it

* **Solana** — 16.9% of indexed payments. Our bottleneck is delivery quality and
  visibility, not chain coverage.
* **PayAI as facilitator** — $0.00179 per Base settlement against a $0.003 sale
  is **60% of the transaction**. CDP gives us 1,000 free settlements a month and
  we do ~90 in two months, i.e. $0 today.
* **A token** — x402 has no token. $PING is **−98.5%** from its ATH ($0.0786 →
  $0.00116, $80M+ → $1.16M cap); the whole x402 token sector is two orders of
  magnitude down. Buying $PING was as much exposure to the protocol as buying a
  token named "HTTPS" is to the encrypted web.
* **More routes at $0.003** — we already have 13 and the dollars are above $1.

### The test of this decision

Not "did we get paid" but **"does the $1 band convert where $0.003 never did"**.
Implementation is small: one route, one `_BAZAAR_OUTPUT_EXAMPLES` entry, one
`X402_INPUT_QUERY_PARAMS` entry — all three already exist as mechanisms.

Suite 1346.

## 30. Two more measurement layers, and both rate us well (12.11.2026)

Found while checking a paste about three.ws. There are now **three** independent
indices that score us, and the two new ones are the serious ones.

### Settled (settled.tools) — the one that BUYS

Its scout pays from `0xA1d1C0cf717402ff3651aA4873CcF96410B01978`, and that
address is in our `payment_guards`:

```
purchases 3 · delivered 3 · not_delivered 0 · paid $0.009
2026-10-14 14:19  /api/v1/whaleflow  $0.003  tx 0x31207b30…b8123
2026-10-14 23:18  /api/v1/signal     $0.003  tx 0xe0789c99…9746d
2026-10-30 11:20  /api/v1/whaleflow  $0.003  tx 0x7f8bcea7…4102c
"bought from this wallet 3 times since 2026-10-14, and all 3 delivered."
```

Public pages `/e/7070` (signal) and `/e/10270` (whaleflow); seller badge
`/badge/seller/0xd4cd…d08f.svg` reads "bought 3× · all delivered".

Quality (0–100): whaleflow **85**, signal **79**, verify-seller **73**, with
`delivery 15/15` on both bought routes and recommendation **pay**. What drags
the score:

* `latency 1/10` on signal, from `avg_latency_ms 2123`. **NOT a code defect** —
  measured live on 12.11 the 402 answers in **330–840 ms**; the average is a
  30-day window polluted by 4 failed probes out of 29 (one is the 09.11
  outage) and it decays as fresh probes accumulate. Do not "fix" this.
* `activity 8/20` everywhere — 8 distinct payers in 30 days. Not fakeable.
* verify-seller: `delivery 0` and flag `price_changed` (band $0.01–$0.1),
  because `KRISTO_VERIFY_SELLER_PRICE=0.01` moved the price off the $0.1 base.
* `delivery_receipt.checks.verdict = nothing_to_compare` — "the listing has no
  sample response to compare against". The receipt is from **14.10**, i.e.
  BEFORE the L2 `properties` fix of 11.11. A re-test should now read
  `as_advertised`.

Also listed on **PayAPI Market** as `kristo-intelligence-defi-signals-api`
(provider "Dimitri Hristov", Finance, `settlement_verified: true`, reliability
69.7 "established").

### x402-trust (x402-trust.com) — we are a VERIFIED provider

```
providerVerified: TRUE      host score 78.68 · grade B · 21 endpoints · 808 probes/30d
https://x402-trust.com/provider/kristo-intelligence-api.onrender.com
```

Paid rows: **1×A** (`/api/v1/signal` 80.4), **11×B** (65.0–79.3), zero C/F.
The eight docs rows are `?` (no payment flow to grade). The A/B split is
canonical routes 78.9–80.4 vs aliases 65.0–66.8.

`/.well-known/x402-trust.txt` carries the P-256 public half; the **private half
lives outside the repo** and is what signs `update-profile` and `remove`.

**The dead Vercel copy is here too — 18 rows, 14 of them grade F (28.7), 4 `?`.**
And unlike x402scan, where delisting is admin-only, x402-trust has
**self-service removal**: `POST /verify/<host>/action {"action":"remove"}` signed
with the provider key, which "deletes the provider's data and blocklists the host
against all automated discovery, permanently". Fallback without the key is a
`x402-trust-remove` line in `/.well-known/x402-trust.txt` — impossible on a 404
host. Lost key → `POST /verify/<host>/rotate-request` mails a rotation link to
the contact address on file.

Our provider profile is empty (`orgName`, `supportUrl`, `docsUrl`, `address`,
`description` all null) — we hold a verified badge and publish nothing.

### Ecosystem numbers worth keeping (x402-trust, 12.11)

```
listed 395,796 · active 236,960 · delisted 158,836 · reachable 36%
402-spec-compliant 95% of reachable · payTo wallets ever paid 27% · earning 6,196
all time $57.61M / 258,512,256 settlements / 226,927 payers
Base $46.89M (81.4%) · Solana $10.73M (18.6%) · +148% MoM (Oct vs Sep 2026)
#1 earner is ONE unlisted address at $2.00M = 49.4% of all volume
```

Half the ecosystem's dollars are one address; the directory is "mostly phantom".
Discovery sources, and where we are: x402scan 206,225 ✅ · bazaar 54,695 ✅ ·
**thirdweb 53,401 ❌** · payai 17,737 ✅ · threews 4,923 ❌ (samples only 500 per
facilitator) · ultravioletadao 4,589 ❌ · dexter 3,164 ❌ · mcpregistry 332 ✅.

### Added 12.11

`GET /.well-known/paycheck.json` → `{"payTo": ["0xd4cd…d08f"]}`, read from
`X402_RECEIVER_ADDRESS` so the declaration can never disagree with the 402 quote.
Lumière PayCheck cross-checks it against wallet rotations; without it a rotation
is `avoid` for 24 h then `caution`. Free, added to `X402_FREE_ENDPOINTS`.

Suite 1350.

## 31. The three PayAI follow-ups, and only one of them was code (12.11.2026)

### 1. Does the CDP facilitator charge us? No. Measured.

CDP gives **1,000 free onchain transactions a month**, then $0.001 each;
verification is free. Our own settlements, counted from `payment_guards` and
`payment_attempts`:

```
2026-09:   4 settlements
2026-10:  26
2026-11:  60 (month to date)   — of which 53 settled, 16 rejected, 4 settle_failed
```

That is **0.4–6% of the free tier**, and the rejected attempts cost nothing
because verification is free. **Our facilitator cost is $0** and there is no
hidden line item. Do not move to PayAI for Base: at $0.00179 a settlement it
would be **60% of a $0.003 sale**.

### 2. Asking PayAI to crawl faster — no-op, it is their schedule.

### 3. Solana as a second `accepts[]` network — BLOCKED, and it is not a config change.

There is **no Solana wallet and no Solana configuration anywhere**: zero
mentions of Solana in the codebase (bar one test fixture about a token pair) and
none of the 40 Render env vars names one. Advertising a Solana accept would mean
quoting a `payTo` we do not control, and our whole settlement rail
(`_try_consume_standard_payment`) verifies Base EIP-3009 through the CDP
facilitator — it cannot verify an SPL transfer at all. **An accept we cannot
verify is worse than no accept**, so this needs a real prerequisite first:
create a Solana wallet, decide the custody story, and add a Solana verification
path. It is a project, not an envelope edit.

### 4. The classifier — published, and it does not flatter us

`GET /api/v1/settlement-classes`, **free** (added to `X402_FREE_ENDPOINTS`: a
statement nobody can read without paying is not a statement).

PayAI's ask, 05.11.2026: *"x402 data mixes real agent spend with cron jobs, bots
and wash activity. Nobody can say how much of it is genuinely agentic. Build the
open classifier: label every settlement as agent, script or noise, then publish
the clean number."*

The number, from `onchain_sales` in production (113 rows, $0.997):

```
own_key   n=74  $0.8680  1 payer    ← us, exercising the rail
sampler   n=17  $0.0570  4 payers   ← crawl infrastructure, a heartbeat
external  n=16  $0.0520  9 payers   ← the only class that is demand
canary    n=6   $0.0200  1 payer    ← a third party verifying us

THIRD PARTY: 39 settlements, $0.129, 14 distinct paying addresses.
             $0.868 of $0.997 — 87% — is our own money.
```

`payer_class` is already persisted per sale and is derived from **on-chain
behaviour** (fan-out fingerprinting, self-payment) plus our own key's identity —
see `scripts/competitor_recon.KNOWN_PAYERS` / `PAYER_CLASSES`. A payer cannot
relabel itself by changing its User-Agent, which is the whole reason the number
is worth anything.

The route states what it is NOT: our ledger, not the ecosystem's; 113 settlements
is not a market. Settled (4,787 paid test purchases) and x402-trust (395,796
endpoints) measure far more than we can, and the honest use of ours is as a
worked example of the method.

Suite 1358.

## 32. WE DO NOT HOLD THE payTo WALLET'S PRIVATE KEY (12.11.2026)

Read this before promising any action that needs the receiver to sign. It was
found while trying to claim the Settled page, on the owner's explicit
"да, извади ключа за подписа".

**The three wallets, each confirmed on chain:**

```
payTo (receiver)     0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f   EOA — KEY NOT HELD
WALLET_PRIVATE_KEY   0x9c1eb97e121a6836200C539a1BF0ecdC37F750dd   EOA — the GAS wallet
secrets/demo_private_key.txt
                     0xE50c5212e8211639C49276dA190E248B83935763   EOA — the test payer
```

`WALLET_PRIVATE_KEY` on Render is **not** the receiver. It is the gas /
self-broadcast key (`services/connectors.py:456` — "a dust of Base ETH for
gas"). Deriving the address from it was the first thing that failed, and it is
the reason never to assume that env var is the money key again.

**Exhaustive search, not a guess.** `_forensics/hunt_payto_key.py` walks the
repo (minus venv/.git/node_modules), `secrets/`, the DSH state directory and the
Desktop, finds every 64-hex string and derives an address from each:

```
files scanned      7,715
64-hex candidates  8,398
MATCHES            0
```

**The payTo key is not on this machine.**

### What this blocks

* **Settled's claim** — their only path is a signature by the payTo wallet
  (EIP-191, or ERC-1271 for contract wallets). The payTo is an **EOA with no
  code**, so ERC-1271 does not apply either. We cannot claim there.
* Any future service that asks the payTo to sign: x402-trust's `remove` and
  `update-profile` (those need their own P-256 provider key, also lost),
  wallet-gated listings, and every "prove you own the payout address" flow.

### What it does NOT block

* **Receiving.** The receiver works with no key at all, which is why 91
  settlements landed in it.
* **agenteconomy.** They offer a domain-control path for exactly this case, and
  it worked: `claimed: true, method: domain_control, verified_at
  2026-11-11T23:02:49Z`, with the owner badge, the card and rating e-mails.

### The risk nobody has confirmed yet

**If no human holds that key, the revenue in it can never be moved.** 0.926 USDC
is small today and it grows with every sale, and a payout address whose key is
gone eventually has to be rotated — which is a far worse problem once buyers and
catalogues point at it. The most likely answer is that the owner holds it in a
browser wallet, in which case the two remaining claims are 30 seconds each.
**Ask, and get the answer on the record.**

Suite 1361.

## 33. The key hunt, the verifiers we mistook for customers, and Lumière (12.11.2026)

### The payTo key: not on this machine, and here is the proof

The owner asked for the key explicitly ("да, извади ключа за подписа") and then
said he was certain it was written down somewhere — possibly emailed to himself,
possibly sent to himself on Viber. Four independent sweeps, each deriving an
address from every 64-hex candidate and comparing to the payTo:

```
working tree        7,715 files · 8,398 candidates      → 0
git history         4,221 objects · 3,487 candidates     → 0
Gmail (Todos/All)   400 self-sent messages scanned       → 0
secrets/, Documents\Backups, DSH state, Desktop          → demo key only
Render WALLET_PRIVATE_KEY                                → the GAS wallet
```

`_forensics/hunt_payto_key.py`, `scan_git_history_for_key.py` and
`scan_self_sent_mail.py` are the tools; none prints key material.

**Two leads worth keeping.**

1. **MetaMask is installed in Chrome**
   (`nkbihfbeogaeaoehlefnkodbefgpgknn`), and its vault lives in
   `Chrome\User Data\Default\Local Extension Settings\…`. If the payTo wallet was
   created there — and nothing on disk suggests it was created anywhere else —
   the key is inside that vault and only the owner's password opens it. **The
   owner should open MetaMask and look for an account ending in `08f`.** That is
   a 60-second check and it is the most likely answer.
2. **There are two nearly identical addresses in history**, and they explain why
   the owner remembers having a key:

```
0xd4cdA980839C8FED4374EE37EA8DBE8c4ECfd88f  "OLD WRONG ADDRESS", burned key, published
0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f  the active payTo
                    A900 vs A980    0DBE vs 8DBE
```

   Commits: `f6c40da` (dashboard was advertising the burned operator wallet),
   `8dc22e9` ("purge burned wallet refs"), `dcebafd` (labels the old one "OLD
   WRONG ADDRESS"), `d848a72` ("key rotation done"). A key existed and a rotation
   happened; the key for the *active* address is the one nobody can find.

`TASK_FOR_KILO_find_the_payto_key.md` is the task written for the Kilo agent —
the one that built the app — and it is the template to reuse: state the goal,
give the derive-and-compare test, list what is already excluded so the work is
not repeated, and demand one of three concrete answers instead of "I could not
find it".

### Two measurement services were reading as real customers

The same mistake `own_key` was created to fix, one layer out. Both were falling
through to `external`, whose Bulgarian label is **"истински клиент"**:

```
settled_scout            0xa1d1c0cf717402ff3651aa4873ccf96410b01978   3 payments
lumiere_paycheck_tester  0xec2abd3eda89bed90124736e317e847d5fb6d034   5 payments
```

Both addresses are published by their owners — `settled.tools/llms.txt` names
the scout's payer, and `lumierepaycheck.org/v1/seller-test` names its tester as
the payTo of its own 402, which is where we read it. They pay us **on purpose**
to find out whether we deliver; the payment is the instrument, not the demand.

Now `canary`, and `reclassify_known_payers()` at boot corrected the stored rows
by itself. The honest number changed:

```
before:  external  16 settlements  $0.052  9 payers   ← "9 customers"
after:   external   9 settlements  $0.031  7 payers   ← 7 customers
         canary    14 settlements  $0.051  3 payers
```

### Lumière: the maintainer replied, and the tester was already paying us

Their maintainer (Book0fEli) answered issue #45 personally and verified our fixes
live: `OPTIONS → 204` ✅, `/.well-known/paycheck.json` declaring `0xd4cd…d08f` ✅,
100% uptime, 74/100.

**The finding:** the `payTo` of their seller-test route is
`0xec2aBD3EDA89BeD90124736e317e847D5fb6d034` — **the same wallet that paid us
$0.01 at 2026-11-11T23:06:38Z**, which we settled and stamped as delivered. Their
side recorded it `payment_failed` and they say so plainly: their fault, neutral,
does not affect the endpoint.

Free re-tests are **suspended for weeks**. The path they offer instead is a
**seller-funded test**: pay $0.01 at their endpoint's price, their tester pays the
same $0.01 on to our payout wallet within about three hours, and a delivered test
lifts the grade above C. **Funded and queued:**

```
id st_891b4f9b23f4   status queued   $0.01
fundedAt 2026-11-12T00:04:50Z   runAfter 2026-11-12T01:16:50Z   gradeBefore C
```

`scripts/lumiere_funded_test.py` is the POST-capable paid call that did it —
`scripts/phase1_paid_call.py` is GET-only and this route is POST, so it is the
same handshake with a body. A reminder is armed to read the result.

Suite 1362.






