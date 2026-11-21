# Handover — Kristo Intelligence

**Последна промяна: 15.11.2026.** Документът е писан да го чете нова сесия без
нито един от разговорите, които са го създали. Всяка секция е датирана и казва
дали е **измерване** или **извод**; където двете се разминават, вярвай на
измерването и го кажи.

> **Прочети това първо.** Документът е **хронологичен, не е текущо състояние.**
> Секциите 1–39 са записът от 09.11–13.11 и част от „отвореното" в тях е
> затворено след това. **§62 „Отворени задачи" е живият списък.** Където ранна
> секция казва нещо, което по-късна работа опровергава, по-късната печели.
>
> **За препратките.** Номерирани секции има само от **§27** нататък. Препратки
> към §1–§26 (срещат се в §12, §19, §20, §22, §29) идват от **по-ранна
> номерация**, която вече не съществува в този файл — третирай ги като „виж
> ранната част", не като линк. Изключение: „x402 v2 spec §9" е секция от
> **спецификацията**, не от този документ.
>
> **Ако си външен одитор:** чети `docs/INDEX.md` първо — карта на всичките 81
> документа, картата на кода и какво **не** е в репото (и защо липсата му е
> правилното състояние). После `docs/AUDIT_BRIEF.md` — задачите, правилата и
> формата на отчета. И **провери, че четеш живото копие**: три одита вече се
> провалиха, защото са чели остаряло.

## Текущо състояние (15.11.2026)

| | състояние |
|---|---|
| Платежен рейл | `self-broadcast → CDP → PayAI`; CDP таймаут 15 s (по подразбиране) |
| Платени маршрути | 8: `/api/v1/signal`, `/api/v1/whaleflow`, `/api/arb/opportunities`, `/api/bot-status`, `/api/sales`, `/api/stats`, `/api/v1/verify-seller`, `/api/v1/seller-check` |
| Цени | $0.005–$0.01; `verify-seller`/`seller-check` на **$0.05** (пилотът приключи на 16.11 — виж §68) |
| Тестове | **1435 събрани** (1434 минават, 1 пропуснат); CI зелен |
| CDP Bazaar | **19/19 реда с обаждания** |
| npm | `kristo-x402-client@1.1.2`, публикуван 15.11 |
| PayAPI | 11 маршрута в каталога, 3 settlement-verified; 1 агент подаден (`pending_checks`) |
| Доставка | **96.3%** от сетълментите стигат до реален платец (86/94 общо; 26/27 без нашите проби) |
| CDP поддръжка | Прозорецът на 14.11 е **отложен**; нова дата не е обявена към 15.11 |

---

**Всичко отдолу е историческият запис.** Заглавният ред по-долу („Everything
below was measured, not inferred") е от 09.11 и е твърде силен за документ с
толкова поправки — виж §55 и §53 за два случая, в които извод е бил сбъркан и
после поправен.

## What works, verified live — 09.11.2026 (historical, superseded)

> Това беше вярно на 09.11. Числата оттогава са остарели; виж таблицата
> „Текущо състояние" горе за актуалните.

| | state |
|---|---|
| Payments (HTTP) | settling, ~1.5s end to end, through the CDP-first chain |
| Payments (MCP) | **an agent can now buy a tool in-session** — was impossible until 09.11 |
| CDP Bazaar | **7 routes listed** (six at $0.003–$0.005, plus `/api/v1/verify-seller` at $0.1), each with real `payers=1` |
| Test suite | **1231 green** (was 1218) |
| Board | `/health` 200, `/api/dashboard/data` 200, `degraded: []`, and each public sales row now says WHOSE it is |

## SCHEDULED RISK — 14 November, CDP maintenance (HISTORICAL — resolved)

> **Изходът, записан на 15.11:** прозорецът беше **отложен** от Coinbase на 14.11
> в 09:13 PST („postponed due to market volatility"). Оригиналният осемчасов
> прозорец изчезна от `/upcoming.json`; към 15.11 няма обявен нов. Таймаутът
> беше върнат на 15 s още същата вечер, с рестарт. Пълният запис е в §52.
> **Отвореното по-долу („Still to do: make one payment settle through PayAI") е
> затворено** — PayAI е уреждал реални пари; виж §31 и §39.
>
> Числата по-долу (10:00–18:00 PST = 8 часа, „up to four hours") са от
> status feed-а на Coinbase и си противоречат взаимно — записано както е било.

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
`<forensics-dir>\` (`check_nonce_reach.py`,
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

> **Поправено 15.11.** Трите записа за този файл казват 44 (§тук), после 35 и
> после 38 — при „12 new", „2 new", „3 new". Броят не може да пада, значи поне
> едно от числата е сгрешено. Днес файлът съдържа **38** теста (преброени с
> `pytest --collect-only`).
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
`<render-service-id>`, applied through `PATCH /v1/services/{id}` → `serviceDetails.healthCheckPath`
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

## Never touch without the owner's explicit approval

> **Формулировката е поправена (15.11).** Преди пишеше „Never touch", което
> противоречи на практиката: цената на `verify-seller`, CORS хедърите и MPP
> предизвикателството **бяха променени** — с изричното одобрение на собственика
> (§42, §45, §28). Забранено е да се пипа **без негово „да"**, не изобщо.

Цените, които искаме, `payTo`, получателят (`X402_RECEIVER_ADDRESS`), комисионата,
402 envelope-ът, `secrets/`, `config.py`, `.env` — **само с изрично одобрение**.
`payTo` е платформен инвариант: проверява се от външни reliability scoring-и, а
Чет Паркър (PayAPI Market) го даде като условие.

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

**Четири** first places (редове 1–4 по-горе, всичките `1/5`), три различни цени,
шест пъти `settlement_required`.

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
  (83.0%) vs Solana **798,702** (16.9%). The two account for **4,727,302** of the
  **4,731,875** headline; the remaining **4,573 (0.1%)** sit on other chains or are
  unattributed. Ранната версия казваше „the two sum exactly to the headline" — не
  е вярно, разликата е 4 573, и процентите дават 99.9%, не 100%.
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
#1 earner is ONE unlisted address at $2.00M
```

> **Поправено 15.11.** Тук пишеше „$2.00M = 49.4% of all volume", а изводът
> отдолу — „Half the ecosystem's dollars are one address". Срещу записания
> знаменател (all time **$57.61M**) един адрес е **3.5%**, не 49.4%, и „половината
> долари" не се подкрепя от тези числа. 49.4% е било смятано срещу друг, по-тесен
> обхват, който не е записан — затова изводът се оттегля, докато обхватът не се
> запише.

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
2026-11:  73 attempts (month to date) — 53 settled, 16 rejected, 4 settle_failed
```

> **Поправено 15.11.** Редът казваше „60 (month to date)" и после даваше
> 53+16+4 = **73**. Частите не може да са повече от цялото, значи „60" беше
> грешното число (или броеше друг прозорец). Тук стои сборът на частите.

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
0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f  the active payTo (canonical EIP-55)
                    A900 vs A980    0DBE vs 8DBE
```

> **Поправено 15.11.** Тук стоеше `0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f`,
> което **не е валиден EIP-55 checksum** — същата грешка, която §55 описва.
> Обслужваната стойност винаги е била каноничната (`_checksum()` я нормализира);
> само написането в документи беше грешно. Адресът за копиране е
> `0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f`.

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

## 34. Lumière: C → A, 100/100, paid-tested (12.11.2026)

The funded test ran and passed:

```
id st_891b4f9b23f4   status done   outcome "delivered"
detail "ok via x402:0xec2aBD+sol:2WgRFR; values checked: \"checked_at\" is recent"
resultAt 2026-11-12T01:19:18Z   gradeBefore C   spent $0.01   refundTx null
```

The money moved and the delivery stamp is in our own ledger:

```
2026-11-12T01:19:24  /api/v1/verify-seller  $0.01  delivered_at stamped
payer 0xec2abd3eda89bed90124736e317e847d5fb6d034
```

Net cost to us: **$0** — we funded $0.01 and their tester paid the same $0.01
back to our payout wallet. That wallet has now paid us **four** times
(2026-10-17 ×2, 2026-11-11, 2026-11-12), which is why it is classed `canary` and
not `external`.

**The grade on their endpoint page:**

```
before:  C  74/100  "Caution: delivery not yet confirmed"
after:   A 100/100  "Proceed: paid-tested and reliable"
         7-day uptime 100% · median response 297 ms
         test payments: paid and delivered, values checked against known answers
         seller-funded tests: 1 funded · 1 delivered · 0 didn't
         payout-wallet incidents: 0
```

The stale CORS line that used to sit on that page — "Browser agents: Can't pay it
yet: CORS headers missing" — is **gone**. By 12.11 16:36 UTC the page reads
"Browser agents: Can pay it (CORS set up for x402)". It was their cache, not our
defect, and it cleared on its own. Verified live: `OPTIONS
/api/v1/verify-seller` → `204` with `Access-Control-Allow-Methods` and
`Access-Control-Allow-Headers`, and their own `GET /v1/failures?url=…` returns
`failures: []` for the last 7 days. Do not "fix" this again.

### The case is closed and nothing is queued

The maintainer closed issue #45 as completed. Nothing on our side is waiting,
and their public register says so outright:

```
GET /v1/seller-tests?url=…/api/v1/verify-seller
last7Days  {funded: 1, delivered: 1, notDelivered: 0, waiting: 0}
funded $0.01 eip155:8453   fundedAt 2026-11-12T00:04:50Z
fundTx 0xfb9bc3e5a58f6b3d4ab2fa390602512c8b8b81d5bd3a2aa11bf098be5b1489b5
attempts 1   outcome delivered   refundTx null   spent $0.01
```

`waiting: 0` is the part that matters. The "re-test queued" state in the bot's
earlier comment resolved into the funded test, and no second request is pending.
**Do not re-open or re-fund anything here.**

Their closing note credits the *listing* fix, not the payment:

> Tu corrección en el listado marcó la diferencia: con campos de respuesta reales
> publicados, la prueba pudo comparar la respuesta en lugar de devolver
> `nothing_to_compare`.

That is the transferable lesson: paying for a test buys nothing if the monitor
has no declared response fields to compare against. Any other delivery-grading
directory needs the same fix.

### What produced the A

Four things, in order of weight, and only one of them was paid for:

1. **The seller-funded test** — the only route that lifts the grade, because the
   grade is built on a real purchase. Free re-tests are suspended for weeks.
2. **The CORS fix** (commit `00ce229`) — they reported it, we fixed it, and their
   maintainer confirmed it on the live host.
3. **The response-field declaration** (commit `1fd1333`) — the scout's earlier
   receipt read `nothing_to_compare` because our Bazaar output example carried no
   field list, so a delivery check had nothing to check against.
4. **`/.well-known/paycheck.json`** — they verified the payout declaration, so a
   future rotation is a recognised event rather than an unconfirmed change.

Suite 1366.

## 35. The memory leak: very likely fixed by the connection-leak commit (12.11.2026)

Render had sent three "exceeded its memory limit" notices in twelve hours. The
metric showed the shape plainly — ~1.2 MB/min from ~150 MB to the 512 MB ceiling
in a few hours, i.e. about five kills a day.

### What the memory watch found

125 samples, one every five minutes, from 05:45 to 16:18 UTC:

```
rss_mb        144.8 (06:00)  ->  158.8 (16:15)     +0.023 MB/min
threads       15-16                                FLAT
gc_objects    136,230 - 137,070                    FLAT (+/-700, pure noise)
containers    sales_history 0 . daily_stats 1 . free_tier_ips 0 .
              paid_call_ips 0 . rate_limit_keys 0 . verify_block 0 .
              dashboard_cache 1 . isolated_stores 4 . rpc_clients 3   ALL FLAT
```

**No Python object is leaking, no thread is leaking, and no container is
growing.** RSS oscillates in a 144-150 MB band and occasionally drops.

### What the events show

```
2026-11-12T03:13:02Z  server_failed  oomKilled {"memoryLimit":"512Mi"}
2026-11-12T03:14:55Z  deploy_started dep-dbqiubu7bikc739m2u00   <- 7e9f7e1
```

**One OOM in the whole window, and the deploy that carried the three
connection-leak fixes landed two minutes later.** Nothing since: 13 hours without
a kill, against ~5/day before, and a rate 20-50x lower (0.023-0.073 MB/min vs
1.23 MB/min).

### The likely cause, and why the arithmetic fits

`7e9f7e1` closed three SQLite connection leaks. The one that matters is
`DashboardStore._connect()` used as `with self._connect() as conn:` — four sites,
and `sqlite3.Connection.__exit__` commits without closing. Those sites run on
every dashboard build, i.e. every ~30 s, and **each open SQLite connection holds
its own page cache** (default ~2 MB). Two leaked handles per build is ~2 MB/min;
measured was 1.2 MB/min. The order of magnitude is right, which is the most a
correlation like this can claim.

### Status: strong evidence, not proof

13 hours and 125 samples with a flat object census is good evidence and it is not
a proof. The honest test is the next 24 hours: if no OOM arrives, the fix is real.
**Do not upgrade the instance to 1 GB before then** — that would hide the result
without settling the cause.

**And one caveat on the 1.23 MB/min figure, because it is the number the whole
comparison rests on.** It was measured at 05:24–05:39 against a process deployed
at **05:22** — two minutes of warm-up before the first sample. Warm-up is
exactly when a service loads caches and runs its retro scans, so 1.23 MB/min may
be partly warm-up rather than steady-state leakage. The 05:44 deploy then
restarted it, and everything from 06:00 onward is flat. So the two rates are not
a clean before/after: they are two different processes, one watched for fifteen
minutes from two minutes after boot and one watched for ten hours. **The 24-hour
check is what separates "the fix worked" from "the earlier number was a warm-up
artefact", and both readings are consistent with the data we have.**

Suite 1368.

## 36. Self-audit against a published failure taxonomy — we pass (12.11.2026)

A CDP-verified post published an x402 health census for the week ending
2026-11-09: **40,608 resources on 4,313 hosts, 87.8% clean, 7.7% cautioned,
4.5% not payable.** It names four defects by size, and three of them are things a
seller can check on itself for free. So we checked ours, live, nothing paid.

**Result: we are in none of them.**

```
7/7 advertised URLs → 402               (not the "1,031 never answer 402" class)
7/7 resource.url == requested URL       (not the "788 answers with another URL" class)
7/7 resource.url scheme == https        (the trust-proxy trap below)
7/7 offer a plain "exact" scheme        (not the "1,502 Gateway-only" class)
```

Re-runnable: `_forensics/audit_402_taxonomy.py` reads our own
`/.well-known/x402.json` (`agents[].input.example_url` is the advertised URL),
probes each unpaid, decodes the `PAYMENT-REQUIRED` header and diffs
`resource.url` against what was asked for.

### Why the 788 class is the one that could have bitten us

The report's own fix for it is *"build resource.url from your public origin;
behind a TLS proxy set `trust proxy`, so it stays https."* We are behind
Render's TLS proxy, so a missing `ProxyFix`/`trust proxy` would have made every
one of our 402s advertise `http://…` — a silent, total mismatch that no local
test would ever catch (locally there is no proxy, so the scheme is right by
accident). It is right in production. **Do not remove the proxy handling.**

### The other two classes, checked while we were there

* `OPTIONS /api/v1/signal` → `204` with `Access-Control-Allow-Methods: GET, HEAD,
  POST, OPTIONS` and the full header allowlist. This is the behaviour Lumière's
  maintainer praised by name.
* `DELETE /api/v1/signal` → **`405`, `Allow: GET, HEAD, OPTIONS`, and no
  `accepts` in the body** — a wrong method is refused *before* money, which is
  also one of the things their closing note thanked us for.
* Two `WWW-Authenticate` lines, both ASCII: the x402 challenge (228 B) and the
  MPP `Payment` challenge (547 B, HMAC `id`, `method="evm"`,
  `intent="charge"`). The MPP rail matters more than the x402 one here: the same
  census puts MPP at **64.6% clean vs 88%** for x402, so a broken MPP header is
  a likely-fatal defect and ours is intact (`_header_safe` + final
  `encode("ascii")`, see §28).

### Known, deliberate, and not a defect

The 402 body carries the same `accepts` array under three keys — `accepts`,
`accepts[]` and `x402_accepts`. That is a reader-compatibility shim, and §31/§32
already record the open question of whether to collapse it. **It is not one of
the censused defects; do not "fix" it in a hurry** — dropping a key breaks
whichever provider read it.

### Free options this opened, none of them taken

Both are external actions and wait for the owner's explicit "да":

1. The post offers a **free full endpoint check** by DM — no cost, but it means
   posting our URL in that channel.
2. **Fizzl** (`wallet.fizzl.eu`) monitors one endpoint **free, hourly**, and
   alerts to Telegram/Discord/Slack/phone when it stops being payable. We
   currently learn about that only when a payment fails.

Also noted, not acted on: **Wever Pay** (Base mainnet, release 2.1.0) offers a
0.025 USDC buyer-signed Commerce Assurance purchase with a verifiable signed
receipt; their walkthrough at `weverpay.com/connect` deliberately stops before
any spending. The maintainer is explicitly asking what breaks.

## 37. Fizzl / x402 Doctor — independent check, badge, and two attacks we pass (12.11.2026)

**The "free full check" from the x402-health post is free AND self-service**
— no DM, no signup, no key. `GET https://x402-doctor.fizzl.eu/api/trust?url=<endpoint>`
returns a per-endpoint 30-day record. Our own endpoint:

```
verdict "go"  codes []  payable_ratio 1  days_checked 3  days_payable 3
streak 3  ms 141  protocol x402  price_usd 0.01  networks ["eip155:8453"]
payto 74ef609bc6  (hashed — they do not publish the address)
```

**Honest caveat:** `history` is `---------------------------ggg` — 27 dashes
then 3 `g`. The scan only has 3 days of our record; 27 days were never scanned
(they are not "not payable"). So "3/3" is true but thin, and the badge must not
be read as a long streak.

**Badge** — `https://x402-doctor.fizzl.eu/badge.svg?url=<endpoint>` — 200,
`image/svg+xml`, 894 bytes, `title` "x402: payable 3/3 days". It states the count
instead of a headline, and rises by itself as the scan accumulates days. Added to
README and the landing footer next to the Lumière badge, so the two independent
checks are both visible.

**Two of the five "x402 attacks" from their paper are directly checkable from
outside, and we pass both** (verified live, 7/7 advertised routes):

- **Free HEAD** — `@x402/core` ≤ 2.28.0 let a HEAD on a paid GET route through
  without payment. Every advertised route answers **402** to HEAD, so no handler
  runs for free. Fix upstream: `x402#3796`.
- **Cache hands the paid answer out for free** — their fix is
  `Cache-Control: no-store, private`. Every paid answer already carries
  **`Cache-Control: no-store`** — stronger. Re-runnable:
  `_forensics/check_head_real_routes.py`.

The other three are not verifiable from outside: settling before answering
(their middleware does it), someone else settling first (between server and
facilitator), and one payment/many answers (needs a paid call). The weekly
delivery check ($0.25) is the one that would test them.

**Wever Pay — read the offer, not paid.** The Commerce Assurance service is
`wever.deterministic-commerce-assurance.v1`, 0.025 USDC (25000 atomic) on
`eip155:8453`, asset `0x833589...` (same USDC), payTo
`0x138887D2947f996ADA0CF96d4034467371621216`, input `{artifact, forceOutcomeFailure?}`,
output `{assuranceStatus: PASS|FAIL, inputDigest, artifactDigest}`. Its own
`get_network_metrics` reports **x402 connections: 0**, purchases completed 2,
and availability **201 successful / 663 failed checks** — 23% healthy. That is
the reason to defer the 0.025 USDC spend: a service that is up 23% of the time
is not a reliable test of a buyer-signed receipt, and the maintainer's own
numbers already answer "what breaks". The release is also 2.2.0 on the server
against 2.1.0 in the post, so the published version is stale.

The monitor (1 endpoint free) is at `wallet.fizzl.eu/#/account` and requires
signing in with a wallet — no e-mail. That is a wallet-app action, so it waits
for the owner; it is not a web form.


## 38. Тихо изтичане на ключове към публичното табло — намерено и затворено (12.11.2026)

**Какво търсих.** Продължих проверката от §36 (таксономията на 402 грешките), но
този път питах обратното: *ние* какво излъчваме навън. Първо проверих всички
публични повърхности за изтекъл RPC доставчик — `/health`, `/ready`,
`/api/agent-manifest`, `/openapi.json`, `/llms.txt`, `/.well-known/x402.json`,
`/.well-known/paycheck.json`, плюс целия `/api/dashboard/data`. Резултат: **нула
течове**. Тоест въпросът "изтекъл ли е ключ сега" има отговор не.

**Но пътят съществуваше.** `redact_rpc()` (в `integrations/dashboard_store.py`)
съществува точно защото RPC доставчиците слагат ключа в самата URL — примерно
`https://base-mainnet.g.alchemy.com/v2/<КЛЮЧ>`. Имаше обаче **десет** места, където
логът беше редактиран, а **същото изключение беше записано нередактирано** в
състояние, което после излиза публично:

| ред | какво записва | къде отива |
|---|---|---|
| `main.py:1741` | `_organism_beat("data_store", "failed")` | секцията `organism` в публичното табло |
| `main.py:5972` | `reason` в `_safe_organism_summary` | публичното табло |
| `main.py:5996` | `reason` в `_safe_organism_journal` | публичното табло |
| `main.py:5848` | `reason` в organism chaos | публичното табло |
| `main.py:5889` | `reason` в organism rules | публичното табло |
| `main.py:8794` | `_organism_beat("delivery", "degraded")` | публичното табло |
| `main.py:8922` | `_organism_beat("data_store", "degraded")` | публичното табло |
| `main.py:6394` | `detail` при 503 | **публичен** отговор |
| `main.py:6299` | `error` при 500 | админ отговор |
| `nexus_core.py:177` | `error` за мъртъв източник | **публичната** `public_activity.html` |

При `main.py:8792/8794` и `:8920/8922` дефектът се вижда с просто око: логът на
реда отгоре минава през `redact_rpc(exc)`, а редът отдолу — не.

**Защо е латентен, а не активен.** Таблото не показва изтекъл ключ, защото
последните сканирания не са се провалили с RPC грешка. Дефектът е в
**съхранението, не в показването** — първият провал на сканиране с ключова URL в
изключението щеше да го запише завинаги в Postgres, а оттам в публичния payload.
Затова го поправих, преди да е гръмнал.

**Освен това разширих `redact_rpc`.** Досега маскираше само RPC ключове във вид
`/v2/<KEY>`, `apikey=`, `token=`. Но psycopg и redis връщат DSN с паролата в
текста — `postgresql://user:ПАРОЛА@host:5432/db` — и нередактирано изключение от
базата публикува паролата на самата база. Добавих втори шаблон, който маскира
паролата във всяка URL с форма `scheme://user:password@host`, като оставя
потребителя и хоста (за да остане грешката диагностицируема). Без фалшиви
положителни: гол URL без парола остава непокътнат.

**Порядък на операциите.** Навсякъде е `redact_rpc(exc)[:120]`, а не
`str(exc)[:120]` после редакция — ако първо отрежеш, можеш да разполовиш ключа и
да оставиш половината видим.

**Тестове.** Добавени три в `tests/test_dashboard_v2.py`:
`test_dsn_passwords_are_redacted_too`, `test_organism_failure_reason_is_redacted`
(хваща `reason` през monkeypatch на `organism.summary` / `organism_journal.entries`)
и разширеният `test_rpc_api_keys_are_redacted_before_logging`.

**Урокът.** Съществуващ scrubber не значи, че всички му пътища са покрити.
Проверката "има ли теч в момента" и проверката "има ли път за теч" са различни
въпроса — първата мина, втората не.


## 39. x402 List: 8 дни мълчание, една невярна цифра, която ние сме пратили (13.11.2026)

**Нишката.** На 5.11.2026 писахме до x402 List с два въпроса; получихме само
автоматичен отговор. Двата въпроса още стоят на страницата ни, затова ги
проверих сам, вместо да чакам.

**Въпрос 1 — `input_declared_uncomposable`.** Все още е така:

```
POST https://x402-list.com/api/v1/services/kristo-intelligence/verify-live
503 {"error":{"code":503,"message":"live delivery-verify temporarily
     unavailable: input_declared_uncomposable"}}
```

Връща се **преди** сетълмент, тоест не ни таксува — тази част работи както е
документирано.

Първоначалната ни хипотеза беше празният `queryParams` map. **Оказа се грешна** —
и без значение, защото вече сме го поправили. Живата декларация днес:

| маршрут | `queryParams` |
|---|---|
| `/api/v1/verify-seller` | `receiver`, `days` (и двете незадължителни) |
| `/api/v1/whaleflow` | `limit`, `hours` (и двете незадължителни) |
| останалите пет | празна карта |

И петте са `required: []`, `additionalProperties: false`. 503-то не се промени.

**Защо не можем просто да махнем `input`:** два други валидатора го изискват.
x402scan-овият agentcash одит вади входната схема от
`extensions.bazaar.schema.properties.input.properties.queryParams|body` —
липсва ли, маршрутът пада с `SCHEMA_INPUT_MISSING` (severity: error,
`tests/test_x402scan_compliance.py:313-320`). x402 Doctor-овият `bazaar-input`
проверка иска картата да присъства, дори празна. Тоест махането на `input`
печели техния composer и губи x402scan.

**Решаващото сравнение:** `forgemesh-utility-apis` —
`https://x402.forgemesh.io/color-convert` — носи verified tier и връща 402
**без никакъв `extensions` обект**. Значи техният composer приема „нищо
декларирано", но отхвърля декларация, която два други валидатора изискват.
Това е конфликт между изискванията на три каталога, а не наш дефект — и точно
затова трябва да питаме, не да гадаем.

**Въпрос 2 — `traction` е `null`.** Извадих 600 услуги и групирах
`assessment.traction`:

```
measured               432
null (never measured)  159
no-payto                 9
```

`pulsewatch-status` е `measured` с **обем 0, 0 транзакции, 0 купувачи** — тоест
оценката е автоматична и **няма минимален праг**. Нашето `null` ни праща в
групата „никога не измервани", не в „няма payTo". Значи нещо на наша страна
спира самото стартиране на измерването.

**Находката, която не търсех — наша собствена невярна цифра.** Писмото от 5.11
твърди „50 settled USDC sales … 28 of them came from 10 distinct external payer
addresses". Проверих регистъра днес (`/api/v1/settlement-classes`, класификация
по он-чейн поведение, не по самоотчет):

| клас | платци | сетълменти | USDC |
|---|---|---|---|
| `own_key` | 1 | 75 | 0.871 |
| `canary` | 3 | 15 | 0.061 |
| `sampler` | 4 | 17 | 0.057 |
| `external` | 7 | 9 | 0.031 |
| **общо** | **15** | **116** | **1.020** |

**Никой клас няма 28 сетълмента от 10 платци.** Изпратената цифра не е била
закръгляне, а неподкрепена. Защитимото число е: 116 общо, от които 41 са от
трети страни (14 различни платци), а **само 9 от 7 платци са търсене**. Балансът
на получателя е 1.020 USDC — точно сборът, нищо не е изтеглено.

**Писмото е изпратено.** Собственикът каза „прати" на 13.11.2026, 09:35 София.
Изпратено 09:40 до `info@x402-list.com` — единственият адрес, който x402 List
публикува (страницата им /contact), от `<contact-email>` през Gmail
SMTP. Текстът е `_forensics/x402list_followup_email.md` (извън репото), 5 544
байта. Съдържа и двата отговора, които намерих сам, и корекцията на нашата
невярна цифра. Чакаме отговор в рамките на 5 работни дни.

**Урокът.** Каталог, който измерва вместо нас, хвана разлика, която нашият
собствен регистър показваше през цялото време. Първото полезно нещо, което
направих с тази нишка, не беше да отговоря на въпросите им, а да проверя дали
твърденията ни към тях са верни.

## 40. Rail 2 не е „legacy" — това е пътят за smart портфейли (13.11.2026)

**Поводът.** В канала на x402 Foundation продавач в продукция (Roberto Martins,
Base/CDP + Solana/PayAI + Algorand) описа точно нашия случай: „our manual rail
(plain USDC transfer + tx-hash claim) exists precisely because smart wallets and
passkey signers reject EIP-3009 signatures. For us it is not an edge case — it is
the conversion path for Coinbase Smart Wallet, Binance Web3, passkey wallets and
plain exchange withdrawals, which would otherwise be lost sales."

**Проверката.** Рейлът **вече съществува** — `main.py:5401`, „Rail 2", с
`X-Payment-Proof`, `_decode_payment_proof` (main.py:4034), `_verify_payment_onchain`
(main.py:4059), 12 потвърждения, C1 повторно използване на hash и H2 обвързване
към endpoint. Тествах го с реален, неконсумиран tx: `GET /api/v1/whaleflow` с
`X-Payment-Proof` → **200, 16 263 байта**. Не липсва функция.

**Дефектът е етикетът.** Публичната повърхност наричаше рейла „legacy" и
„MANUAL fallback" — тоест „остаряло, използвай само ако няма друг начин". За
портфейл, който не може да подпише EIP-3009, това е **единственият** път, а не
резерва. Агент, който чете 402, вижда „MANUAL fallback" и се отказва.

**Промяната** (само етикет и позициониране, без логика и без промяна на
12-те потвърждения):

| място | преди | сега |
|---|---|---|
| `/llms.txt` | „Rail 2 — legacy self-describing proof (fallback)" | „Rail 2 — smart wallets and exchange withdrawals" + кой точно е клиентът |
| 402 body `x402_retry_instructions` | „MANUAL fallback: …" | „SMART WALLETS AND EXCHANGE WITHDRAWALS (…): …" + „normal path, not a last resort" |
| 402 body `payment_proof` | без `for` | `for` — изброява Coinbase Smart Wallet, Binance Web3, passkey, exchange |
| `/api/v1/quickstart` | „alternative (legacy, slower)" | „alternative (smart wallets and exchange withdrawals)" |
| `/api/agent-manifest` | `legacy_proof.amount_usdc`, „Legacy alternative" | `proof.amount_usdc`, „Smart-wallet alternative" |
| `/ai-plugin.json` | `legacy_headers` | `alternative_headers` |
| `README.md` | „Rail 2 — manual fallback" | „Rail 2 — smart wallets and exchange withdrawals" |
| `templates/dashboard.html` | „legacy (X-Payment-Proof)" | „smart wallets (X-Payment-Proof)" |
| `packages/x402-client/README.md` | „Legacy", „Legacy rail" | „Smart wallets and exchange withdrawals", „Smart-wallet rail" |
| `examples/demo_agent/README.md` | „legacy релсата" | „smart-wallet релсата" |
| `docs/DISTRIBUTION_STATUS.md` | „legacy" | „smart wallets и exchange withdrawals" |

**Проверено:** 1374 теста минават, 1 skipped (пълният набор, 452 s); 141
таргетирани теста за рейла, SEO, конекторите и виралното разпространение —
всички минават. `git diff` показва 3 кодови файла + 5 документа.

**Не е променено:** 12-те потвърждения (~24 s) остават. Това е реален разход, а
не етикет; намаляването им до 3 е отделно решение със собствен риск (reorg).
Позиционирането е честно, защото казва „~24s" навсякъде.

> ⚠️ **Грешно, поправено в §53.** Base прави блок на **0.2 s**, не на 2 s. Значи
> 12 блока са **~2.4 s**, не ~24 s. Числото 12 се оказа правилното, а
> обосновката — не. Не цитирай ~24 s оттук.

**Отворено:** 12-те потвърждения — стойността е 12, но не е обоснована. 2–3
блока на Base е 1–2 s, а една reorg проверка стига. Отделно решение.

> ⚠️ **Грешно, поправено в §53.** „2–3 блока е 1–2 s" приема 2 s блокове. При
> 0.2 s те са 0.4–0.6 s. Стойността остана 12; виж §53.

## 41. Платежният път: мъртва проверка на домейна, непроверен сетълмент, nonce без заключване (13.11.2026)

Собственикът каза „да за всичко" и остави решенията на мен. Ето какво намерих
в платежния път и какво направих — всяко с тест.

### 1. Проверката на EIP-712 домейна беше МЪРТВА (най-сериозното)

`precheck_payment_payload` сравнява `requirements["extra_name"]` и
`["extra_version"]`, за да върже подписа към НАШИЯ токен („USD Coin", версия 2).
Но `main.py` никога не слагаше тези два ключа: домейнът пътува като
`accepts[0].extra` — **обект** — а проверката търсеше два **плоски** ключа. Значи
сравнението мълчеше и клиент можеше да подпише върху произволен домейн.

Втори дефект в същата проверка: четеше `payload["extra"]` (горно ниво), а
`_local_recover_signer` строи домейна от `accepted["extra"]` — тоест
валидираше **различен обект** от този, върху който е направен подписът.

Поправено: `main.py` вече слага `extra_name`/`extra_version` от същия `extra`,
който 402 рекламира; и двете функции четат `accepted.extra` с `payload.extra`
като резерва. Проверено на живо:

```
добър домейн   -> []
фалшив домейн  -> ["extra.name mismatch: 'Fake Token' != 'USD Coin'"]
грешна версия  -> ["extra.version mismatch: '9' != '2'"]
```

### 2. Сетълментът се проверяваше само по `receipt.status`

`status=1` доказва, че транзакцията е минала — **не** че е преместила НАШИЯ USDC
към НАШИЯ получател. Фасилитатор, уредил токен по избор на клиента, също дава
`status=1`. Сега и двата рейла четат един и същ Transfer лог през новата
`_receipt_usdc_transfer` (едно място, за да не се разминават).

**Fail-open е запазен нарочно:** проверката работи само когато receipt-ът Е
четим и `status=1`. При нечетим receipt доставката остава — RPC смущение не
бива да струва платено обаждане. Когато обаче receipt-ът е четим и в него
няма наш Transfer за поне цената → отказ с `c2_no_matching_transfer`.

### 3. Приходите се записваха по цената, не по подписаната сума

`amount >= price` е правилото (преплащане се приема). Значи сетълмент от
0.05 USDC на рут за 0.005 се записваше като 0.005 — подценен приход на всяко
преплащане. Сега `claim_payment_tx` и `_record_real_sale` получават реално
преместената сума (`settled_amount`), а преплащането се логва.

### 4. Nonce без заключване

`_self_broadcast_settlement` четеше `get_transaction_count(addr)` без
`"pending"` и без lock. Две едновременни уреждания виждат едно и също число:
второто пада с „nonce too low" или заменя първото в mempool-а и изгаря газ за
сетълмент, който никой не записва. Сега четенето и излъчването са в една
критична секция под `_SELF_BROADCAST_LOCK`, а броячът се чете с `"pending"`.

`blockchain/wallet.py:pay_request_fee` има същия модел, но **няма нито един
викащ** (проверено с grep) — поправих nonce-а и оставих бележка, че при
повторно включване трябва да дели СЪЩИЯ lock: един газ портфейл = една nonce
последователност.

### 5. Публичният `/api/connectors` подписваше JWT на всяка заявка

`_eip3009_detail()` вика `_cdp_jwt`, което прави истински ES256 подпис — на
безплатен, неаутентикиран endpoint. Сега резултатът се кешира 60 s, а ключът на
кеша е **конфигурацията** (веригата на фасилитаторите, наличието на key_id,
флагът за газ), не само флагът — смяна на конфигурацията дава свеж ред, а не
остарял. Причината за провал на JWT се показва само на оператор
(`reveal_detail`, същият сигнал, който пази адреса на портфейла).

### 6. 12 → 3 потвърждения

Стойността 12 никога не е била обоснована: 12 блока на Base е ~24 s, а 2 s блок
не е 2 s reorg прозорец. 3 блока е ~6 s, а `_confirmations_ok_with_lag_refresh`
препрочита върха преди отказ. Променено навсякъде: код, текстове на 402,
`llms.txt`, quickstart, README, dashboard, landing, npm README, примерния JS,
`GUARD_METHODOLOGY.md`, `OUTREACH_WAVE1.md` и тестовете, които твърдяха „12".

> ⚠️ **Грешно, поправено в §53.** Целият този пас беше обърнат на следващия ден:
> Base прави блок на **0.2 s**, значи 12 блока са ~2.4 s, а 3 блока ~0.6 s.
> Стойностите са върнати на **12** (proof rail) и **5** (standard rail). Числата
> „~24 s" и „~6 s" тук са неверни — не ги цитирай.

**Проверено:** пълният набор минава; новите тестове са
`test_a_settlement_that_moved_no_usdc_to_us_is_refused`,
`test_a_settlement_under_the_quoted_price_is_refused`,
`test_the_precheck_pins_the_token_domain_the_route_declares`,
`test_the_public_health_line_is_cached_and_hides_failure_detail`,
`test_an_adopted_already_settled_tx_must_be_a_hash`.

### 7. `_adopt_already_settled` приемаше и стойност, която не е хеш

Когато фасилитатор върне 400 с текст „already" и поле `transaction`, ние
приемахме това като успешен сетълмент. Тялото обаче е **твърдение**, не
доказателство. Две неща ограничават щетата: стойността вече трябва да
**изглежда** като хеш (0x + 64 hex), и викащият чете receipt-а и проверява
USDC Transfer към нашия получател за поне цената (точка 2 по-горе). Произволен
или измислен хеш пада там, вместо да отвори безплатно обаждане.

**Остава открито:** `/validation` още държи `SUITE_TESTS_PASSED` и
`UPTIME_DAYS_GREEN` като ръчни константи (датирани са с `SUITE_LAST_RUN` и
`UPTIME_MEASURED_TO`, така че не лъжат за времето); `requests_summary` (3.1 s)
още не е пипан; `main.py` остава монолит от ~9.6k реда; `requirements.txt`
смесва dev и prod зависимости; няма CI pipeline със сканиране за тайни.

## 42. Stripe: mock плащане в продукция и тих fallback към Pro (13.11.2026)

### 1. `KRISTO_ALLOW_MOCK_PAYMENTS` работеше и в продукция

Mock checkout е сесия, която отключва платен продукт **без да са се движили
пари**. Флагът сам по себе си е капан: един env var, написан в продукционния
dashboard, дава безплатен достъп до всички човешки продукти.

Сега `_mock_payments_allowed()` отказва, когато процесът е продукционен.
Продукцията се разпознава по маркерите на платформата (`RENDER`,
`RENDER_SERVICE_ID`), не по наша конфигурация — така липсващ или сбъркан
`APP_ENV` не може тихо да изключи проверката. Локално и в тестовете флагът
продължава да работи, защото потокът зависи от него.

### 2. Непознат `plan_key` таксуваше цената на Pro

`_plan_amount` падаше на `PLAN_PRICES["pro"]` за всеки непознат ключ. Печатна
грешка в името на плана даваше фактура за $79, без никъде да пише, че нещо е
сбъркано. Сега непознат план **хвърля**, а `create_checkout_session` го връща
като `checkout_error` / `unknown_plan` — отказ, не 500 и не грешна фактура.
Пътят на агентския каталог не е засегнат: той подава `amount_usd` изрично.

### 3. `int(resolved_amount * 100)` режеше вместо да закръгля

За 29/79/149 е безопасно, но 0.29 или 1.15 биха дали с цент по-малко. Сега
`int(round(...))`.

### 4. Проверено: сумата при агентския checkout идва от сървъра

Одитът не беше сигурен откъде идва `amount_usd` при
`create_catalog_checkout_session`. Проверено: `main.py` подава
`agent["price_stripe"]` от `catalog_store.get_product(agent_id)` — тоест от
сървърния каталог, не от тялото на заявката. Дупка за манипулиране на цената
няма.

**Тестове:** `test_mock_payments_cannot_unlock_a_product_in_production`,
`test_an_unknown_plan_is_refused_not_charged_as_pro`.

## 43. Зависимостите: pytest беше production пакет, cryptography не беше вързан (13.11.2026)

`requirements.txt` е файлът, който деплоят инсталира (Dockerfile,
`DEPLOYMENT.md`, `DEPLOYMENT_CHECKLIST.md`). В него имаше две грешки:

**1. `pytest` беше production зависимост.** Всеки продукционен образ носеше
test runner, който никога не се пуска. Преместен в нов `requirements-dev.txt`,
който започва с `-r requirements.txt`, за да не изгуби dev инсталацията
runtime зависимостите.

**2. `cryptography>=42.0.0` — невързан и подгрешно заглавие.** Той е **runtime**
зависимост: `services/connectors.py` подписва CDP JWT с него (ES256 /
secp256r1). Стоеше като `>=` под заглавие „Testing", тоест две грешки наведнъж:
деплоят инсталираше каквото pip реши в онзи ден, а заглавието казваше на
читателя, че е dev пакет. Сега е `cryptography==48.0.0` (колкото е в lock-а),
в собствена секция „Crypto / signing".

**Тестове:** `test_the_deploy_does_not_install_a_test_runner`,
`test_the_dev_dependencies_are_in_the_lock_too`,
`test_the_crypto_dependency_is_pinned_and_is_not_called_test_only`.

## 44. CI pipeline: нямаше никакъв (13.11.2026)

До сега единствената проверка преди промяна да стигне продукция беше ръчно
пускане на набора на една машина. Добавени `.github/workflows/ci.yml` и
`.github/dependabot.yml`.

**Job `tests`:** Python 3.12, инсталира `requirements-dev.txt` (тоест runtime
набора + pytest — файлът за деплой вече не носи test runner, така че pipeline,
който инсталира само него, би умрял с `pytest: command not found`), пуска
`pytest -q`.

**Job `secrets`:** gitleaks върху **работното дърво** (`--no-git`), не върху
историята. Това е съзнателно: портата е „не КОМИТВАЙ тайна", а не „одитирай
всеки комит". Историята знае, че съдържа стар материал, а пренаписването ѝ е
разрушително решение, което собственикът още не е взел — job, който пада от
първия ден и не може да се поправи без force-push, е шум, не сигнал. Когато
историята се изчисти, `--no-git` се маха и проверката става пълна.

**Dependabot:** седмично за pip (групирано в един PR), месечно за GitHub
Actions и за npm пакета `packages/x402-client`. `cryptography` подписва CDP JWT,
а `web3` движи парите — CVE в тях не е домакинска работа.

**Тест:** `test_the_pipeline_installs_the_dev_file_and_says_what_it_scans` пази
и двете: че pipeline-ът инсталира dev файла и че сканирането казва обхвата си.

## 45. Rate limit за скъпия път на платения рейл (13.11.2026)

`_RATE_LIMIT_DEFAULTS` имаше девет скоупа — admin login, checkout, leads,
webhooks, двата публични фийда — и **нито един за платения рейл**. Заявка с
представен credential струва локално EIP-712 възстановяване и може да стигне до
фасилитатор и до газ-плащащ broadcast; нищо не я ограничаваше, тоест клиент
можеше да подава подписани-но-неизползваеми payload-и толкова бързо, колкото
отваря сокети.

Добавен е скоуп `x402_settlement` (120 заявки / 5 min на IP), който се брои
**само когато има представен credential** — не при обикновен 402. Това е
съзнателно: 402-ката е безплатна по определение и ограничаването ѝ би наказало
всеки discovery crawler, а смисълът на предизвикателството е, че е свободно да
попиташ. Лимитът е щедър, защото истинският купувач ретрайва няколко пъти, не
стотици.

**Тест:** `test_the_settlement_path_is_bounded_but_a_plain_challenge_is_free`
пази и двете посоки — че обикновената 402 не харчи бюджета, и че втората
заявка с credential получава 429.

## 46. CI-то падна на първия си пуск — и това беше полезно (13.11.2026)

Първите четири CI пуска (по PR-ите на Dependabot) паднаха. `Test suite` мина
**успешно** на всеки — тоест pipeline-ът за тестове работи. Падна
`Secret scan (working tree)`. Логовете на job-а искат админ права, затова свалих
gitleaks локално и сканирах експорт на проследяваните файлове (точно това,
което CI вижда).

**19 находки. Нито една не е тайна.** Всичките са публични по определение:

| какво | колко | защо не е тайна |
|---|---|---|
| Base USDC контракт + нашият получател | 9 | публични он-чейн идентификатори, отпечатани във всеки 402 |
| keccak теми (`Transfer`, `AuthorizationUsed`) | 3 | протоколни константи |
| IndexNow ключ | 2 | **трябва** да се сервира на `/<key>.txt`, иначе проверката не работи |
| `agenteconomy` домейн-контролен токен | 1 | **трябва** да се сервира на `/.well-known/…`, иначе claim-ът изтича |
| Подписан публичен атестат на Lazaretto | 1 | доказателство, публикувано на `lazaretto.dev/report/…`, не дава достъп |
| placeholder hostname + фалшиви ключове в тестовете на редактора | 3 | буквално измислени стойности |

**Поправката не е да изключа сканирането.** Добавен е `.gitleaks.toml`, който
`extend`-ва правилата по подразбиране (`useDefault = true`), не предефинира нито
едно правило и изброява **стойности**, всяка с коментар защо не е тайна.

Едно уточнение, което си струва да се помни: шаблоните за адресите са с `(?i)`,
защото **същият** адрес се пише с контролна сума в 402 и с малки букви в
сравненията — първата версия на allowlist-а хвана 17 от 19 и пропусна точно
двете места, където адресът е долен регистър.

**Защо НЕ allowlist-вам „всеки `0x…` 64 hex":** частен ключ и хеш на транзакция
изглеждат еднакво. Широко правило за hex би скрило истински теч. Затова
allowlist-ът именува конкретни адреси и теми.

**Проверено локално:** със конфигурацията gitleaks дава `no leaks found`, exit 0
(преди: 19 находки, exit 1).

**Проверено в CI:** на `da882de` **и двата job-а минават** — `Test suite` ✓ и
`Secret scan (working tree)` ✓. Предишните четири пуска падаха само на второто.

**Тест:** `test_the_secret_scan_config_explains_every_exemption` пази
конфигурацията да не се превърне в сляпо изключение — изисква `useDefault`,
забранява `[[rules]]` и иска всеки allowlist да има описание.

## 47. Радарът замлъкна за нас; CDP вече ни листва изцяло (13.11.2026)

Собственикът препрати новия доклад на **чуждия** радар
(`Nikolife2016/pulsefeed-x402` #3, 13.11), който ние наблюдаваме
(`scripts/ap2_radar.py:106`, `docs/WATCH_LIST.md` ред 5). Ето какво излиза от
него, проверено срещу източниците.

### 1. Радарът вече няма нищо за нас

Докладът от 13.11 съдържа **2** нишки, нито една не назовава нашия endpoint —
и ние не сме дори в отсечените като разсейка. През октомври ни споменаваше по
4 пъти на доклад. Съвпада с §10.11: студеният GitHub outreach е наситен и вече
филтриран канал. Собствената му бележка го потвърждава: аргументите по ключови
думи са тествани на 123 нишки, сработили са 88 пъти, приложими — **4**.

### 2. Заявката ни към x402scan стои 5 седмици без отговор

`Merit-Systems/x402scan#1270` — отворена от 08.10, последен коментар 14.10.
Единственият отговорил е `lowkeybuilds`, който продава „Listing Fix" за $29;
собственото ни измерване потвърди диагнозата му, но не купуваме. **Не е само
при нас:** по-нова заявка (#1343, 12.11) също е без нито един коментар. Опашката
не мърда за никого.

**14.11 — учтиво побутване, публикувано** (собственикът го одобри изрично):
`#1270` получи follow-up, който казва, че забележката от 14.10 е затворена —
19/19 реда вече имат обаждания, а „2 от 6" е било вярно за тогава, защото
Bazaar-ът още е наваксвал. Няма нова молба и няма повторна презентация; ако
заявката е просто в опашката, не се иска нищо. Коментарът е от
`hristovdimitri2-hub` 14.11 07:21 UTC, заявката остава `open`.

### 3. Добра новина: CDP вече ни листва изцяло

През октомври CDP показваше **2 от 6** наши route-а за нашия payTo
(`what_cdp_merchant_knows.py`). Сега:

```
pagination.total = 19
rows with any call = 19/19      (всеки ред е имал обаждане за 30 дни)
SUM: calls30d=53  payers30d=21  (сумирано по редове)
rows with payers30d >= 2: 2
```

Тоест дефектът, заради който беше заявката, е отстранен от страна на CDP.

### 4. $0.01 на seller-audit маршрутите е НАШ пилот, не бъг

`KRISTO_VERIFY_SELLER_PRICE=0.01` е зададен в продукцията (проверено през Render
API). Това е **изрично одобреният от собственика 30-дневен пилот от 11.11.2026**
за двата маршрута (`/api/v1/verify-seller` и `/api/v1/seller-check`), с насрочено
връщане на 11.12.2026 08:00 UTC (`schedule-39d6abaf`). Проверено: напомнянето е
налично и пътят в него е валиден — `Desktop\projects\kristo-intelligence-6` е
**junction** към `Desktop\проекти\kristo-intelligence-6`, една и съща папка.

**Взаимодействие с поправката от §41:** при базова цена $0.01 отстъпката
`min(0.01, 0.01)` не правеше нищо, тоест пилотът тече чист. Поправката (изключване
на verify-seller от обемната отстъпка) става важна **след** пилота: при $0.10
отстъпката щеше да свали маршрута на $0.01 след 10 обаждания.

### 5. Честното число за търсенето (не числата на радара)

`/api/v1/settlement-classes`, all-time, 13.11 19:42 UTC:

| клас | сетълменти | платци | USDC |
|---|---|---|---|
| `own_key` (ние на себе си) | 75 | 1 | 0.871 |
| `canary` (трети страни ни проверяват) | 15 | 3 | 0.061 |
| `sampler` (малки проби) | 17 | 4 | 0.057 |
| **`external` (търсене)** | **9** | **7** | **0.031** |

`clean_number`: 116 сетълмента / $1.02 общо, от които **41 сетълмента от 14
трети страни** = $0.149. Числата на радара (53 обаждания / 21 платец) са от CDP и
**включват нашите собствени канари** — не ги чети като търсене.

## 48. Dependabot внесе web3 8.0.0 в групов PR и счупи тестовете (13.11.2026)

Собственикът показа CI страницата. Пусът на `92bd0d8` падна на `Secret scan` —
това е онова падане, което вече е поправено (`.gitleaks.toml`, зелено на
`da882de`). Но от прозорците на Actions излязоха две неща, които си струваше да
се пипнат.

### 1. Предупреждения, които можеха да се махнат

* `actions/checkout@v4` и `actions/setup-python@v5` сочат **Node.js 20**, който е
  отхвърлен — всяки пуск носеше предупреждение, което никой не може да оправи.
  Вдигнати на **v7** (и двете имат `v7` таг; проверено през API).
* `ubuntu-latest` ще мигрира към **Ubuntu 26** през октомври 2026. Това е смяна
  на средата, която никой не е комитнал — затова runner-ът е **закован** на
  `ubuntu-24.04`. Промяна на runner-а трябва да е комит, който някой е направил
  нарочно, не нещо, което се случва под зелено.

### 2. Най-важното: груповият PR на Dependabot внесе ГЛАВНА версия на web3

Dependabot отвори 4 PR-а. Резултатите от CI им:

| PR | какво внася | `Test suite` |
|---|---|---|
| #4 | `actions/checkout` 4 → 7 | ✅ success |
| #5 | `actions/setup-python` 5 → 7 | ✅ success |
| #7 | `pytest` 9.1.1 → 9.2.0 | ✅ success |
| **#6** | **група от 6 runtime пакета** | ❌ **FAILURE** |

PR #6 внасяше наведнъж **`web3` 7.16.0 → 8.0.0** (главна версия),
`gunicorn` 26 → 27, `stripe` 15 → 16 и още три. Тестовете падат. **Преди днес
този CI не съществуваше и никой нямаше да разбере** — шест-пакетен bump изглежда
рутинен и не се чете внимателно, а `web3` движи парите.

Затова `dependabot.yml` вече **игнорира главни версии** за `web3`,
`cryptography`, `stripe`, `gunicorn`, `Flask` и `psycopg`. Те идват като отделни
PR-и с отделен преглед или не идват. Понеже `ci.yml` вече ползва `@v7`, PR-ове
#4 и #5 стават излишни (Dependabot сам ще ги затвори).

**Тест:** `test_the_pipeline_does_not_run_on_a_moving_runner_or_a_dead_node`
забранява `ubuntu-latest` и мъртвите Node 20 действия в **активната**
конфигурация (коментарите се изключват — бележката, която обяснява защо
runner-ът е закован, споменава `ubuntu-latest` по име).

## 49. Малките ъпдейти на зависимостите: локът беше причината PR-овете да падат (13.11.2026)

След като `ignore` спря главните версии, Dependabot отвори отново два PR-а —
#8 (група от 5 runtime пакета) и #7 (`pytest`). **И двата падаха**, но вече не
заради web3: заради `requirements.lock`.

`test_every_exact_pin_agrees_between_the_two_files` сравнява `requirements.txt`
и лока. Dependabot пипа само първия, затова всяка негова промяна оставя лока
назад и тестът — правилно — пада. Тоест guard-ът от §43 свърши точно работата,
за която е писан, върху първите си истински PR-ове.

**Направено на ръка, защото Dependabot не може да обнови лока:**

| пакет | от | на |
|---|---|---|
| `gunicorn` | 26.1.0 | 26.2.0 |
| `stripe` | 15.5.1 | 15.6.2 |
| `psycopg[binary]` | 3.3.4 | 3.3.8 |
| `python-dotenv` | 1.2.3 | 1.2.4 |
| `pytest` (dev) | 9.1.1 | 9.2.0 |

`requirements.txt`, `requirements-dev.txt` и `requirements.lock` са обновени
**заедно** — иначе PR-ът остава червен.

**Проверено, не предположено:** новите версии са инсталирани в venv-а и целият
набор е пуснат: **1388 passed, 1 skipped**. Проверено и в PyPI, че нито една от
новите версии не внася нова зависимост отвън лока (gunicorn и python-dotenv
нямат базови зависимости; stripe иска `typing_extensions` и `requests`, psycopg
иска `typing-extensions` и `psycopg-binary` — всички вече в лока).

**Защо това е безопасно, а web3 8.0.0 не беше:** това са patch/minor версии на
пакети, чиито интерфейси не сме пипали, а `web3` беше главна версия на
библиотеката, която подписва и излъчва транзакции. Затова `web3` остава
игнориран за главни версии.

## 50. Спецът даде име на два наши дефекта: `settlement_pending` и двойния подпис (13.11.2026)

Собственикът препрати канала `github-discussions` на x402 Foundation. Две неща
в него ни засягат пряко, и **спецификацията вече им е дала име** — тоест вече не
са „наше мнение", а нарушение.

### 1. `settlement_pending` — ние губехме платили клиенти

x402 v2 spec §9 добавя **`settlement_pending`**: „транзакцията е излъчена, но
потвърждението не можа да се установи" (RPC грешка или таймаут при чакане на
receipt). Кодът е **non-terminal** — транзакцията може още да се потвърди — и
отговорът **ЗАДЪЛЖИТЕЛНО** носи хеша, за да може получателят да се съгласува
със веригата.

**Ние четяхме `success: false` като „плащането се провали".** Тоест сетълмент,
който вече е бил излъчен, се отказваше и платещият клиент губеше обаждането си.
Честотата не е теоретична: Lena Hierzi (Celo) измери на продукционен
фасилитатор **19 settle 500-ки в ~11.7k сетълмента, от които 9 реално бяха
минали**.

Поправено с `_adopt_settlement_pending` в `services/connectors.py`: хешът се
осиновява и `main.py` го проверява на веригата (Transfer към нашия получател за
поне цената) преди доставка. Съответствието е **по кода, не по текста** — spec
§9 изрично го изисква, защото фасилитатор може да преформулира `errorMessage` във
всеки release. Проверено и в двата пътя (CDP и веригата на фасилитаторите), а не
само при CDP: кодът е на ниво спецификация.

Добавен е и `_tx_hash_or_none` — една проверка на формата за всяко място, което
осиновява хеш, посочен от фасилитатор.

**Тестове:** `test_settlement_pending_is_adopted_not_treated_as_a_failure`,
`test_settlement_pending_matching_is_on_the_code_not_the_message`.

### 2. Нашият npm клиент подписваше наново при всеки retry → двойно плащане

Niraj Vora (issue #3438) описа точно този дефект от страната на купувача. В
`packages/x402-client/src/index.js` `pay()` се викаше **във всеки 402 кръг**, а
всяко викане прави **нова** EIP-3009 авторизация с **нов nonce**. Сървър, който
отговори 402, след като първият кредит вече е бил излъчен, получаваше **втора,
независима авторизация** — купувачът плаща два пъти.

**Срещу НАШИЯ сървър това не беше достижимо** (ние връщаме 401 или 425, никога
402, след като има представен кредит) — но пакетът е публикуван в npm за всеки
x402 сървър.

Сега: **най-много един подпис на заявка.** При повторен 402 за същите условия
клиентът връща `{ error: "payment_outcome_unknown" }` вместо да подпише отново.
Възстановяването иска поглед към nonce-а на веригата, което този пакет
съзнателно не прави (нула зависимости, без RPC).

Версията е вдигната на **1.1.2** (публикуването в npm е външно действие и чака
„да"). Оправена е и остарялата бележка „~24 секунди" — сървърът вече иска 3
потвърждения (~6 s), а чакането е от страната на сървъра.

> ⚠️ **Грешно, поправено в §53 и завършено в §60.** „~24 s" и „~6 s" приемат 2 s
> блокове; Base прави 0.2 s. Числата са **12** и **5** потвърждения (~2.5 s и
> ~1.0 s). npm 1.1.2 е публикуван на 15.11.

**Тест:** `a repeated 402 never buys the same purchase twice` (15/15 в пакета).

### 3. Отбелязано, но НЕ пипано: `extra.paymentFlow`

Spec §6.1 дефинира `authorization` (по подразбиране), `upfront` и `escrow` и
изисква `accepts[].extra.paymentFlow` да присъства, когато потокът не е
`authorization`. Нашата Rail 2 (обикновен трансфер + tx хеш) е точно
„client-prepaid метод" с `upfront` поток.

**Не сме го добавили в `accepts[]` съзнателно:** транспортът ѝ е наш хедър
(`X-Payment-Proof`), не стандартният `PAYMENT-SIGNATURE`. Ако обявим запис в
`accepts[]`, който стандартен клиент не може да плати, ще подведем именно
клиентите, за които спецификацията съществува. Това е решение за собственика,
не мълчалива промяна.

## 51. CDP статусът не ни е струвал нищо — но четенето на нашите таблици намери бъг (13.11.2026)

Собственикът препрати CDP status feed-а. Инцидентите в него (9–13.11) са точно
условията, при които фасилитаторът връща `settlement_pending` — кодът от §50.
Затова проверих продукционните таблици, вместо да предполагам.

`_forensics/did_cdp_incidents_cost_us.py` (read-only). Последни 14 дни:

```
payment_attempts:  settled 56 | rejected 16 | settle_failed 4
```

**Отговорът: CDP не ни е струвал нищо.** „Degraded Performance — Coinbase
Payments" изрично казваше „Payments using funds on Base are not affected", а
нашите провали са струпани на **09.11** — преди инцидентите от 10–11.11.
Причината им е наша, не тяхна:

| колко | какво |
|---|---|
| 9 | `payload_undecodable` — клиентът праща payload, който не декодираме |
| 3 | `payai_unreachable(status=400)` — PayAI отказва (поправено с `_with_accepted`, §10.11) |
| 2 | `local_eip712_recovery_failed: Missing value for field 'verifyingContract'` |
| 2 | 20s deadline (verify / settle) |

### Поправено: домейнът се строеше от КЛИЕНТА, не от нас

`_local_recover_signer` взимаше `verifyingContract` от клиентския `accepted`.
Клиент, който върне **частичен** `accepted` (само `scheme` и `network` — нещо
съвсем нормално), оставяше `verifyingContract` = `None` и eth_account хвърляше

```
ValueError: Missing value for field `verifyingContract` of type `address`
```

Това излизаше като `local_eip712_recovery_failed` и изглеждаше като **наш** бъг.
Два загубени опита на 09.11.

Сега домейнът е **наш** (asset, network, token домейн — ние сме ги издали в 402),
а клиентските стойности са само резерва. Същият принцип като
`_merged_requirements`. Това е и **по-правилната проверка**: подпис върху друг
домейн се възстановява до друг адрес и пада на сравнението с `from` — точно
отказът, който искаме. А когато никъде няма asset, отказът вече е чисто
изречение, не суровото съобщение на eth_account.

**Тест:** `test_recovery_uses_our_domain_when_the_client_echoes_a_partial_accepted`
— покрива пълния `accepted`, частичния, липсата на asset навсякъде и (важното)
че възстановяване срещу **друг** `verifyingContract` не връща платеца.

### Отбелязано

`payload_undecodable` (9) е от страна на клиента и не е наша задача, но
съобщението е твърде общо, за да е диагностицируемо — кандидат за подобрение.

## 52. Прозорецът на Coinbase е ПОТВЪРДЕН, а резервната ни релса НЯМА ГАЗ (14.11.2026)

### Прозорецът

`status.coinbase.com/api/v2/scheduled-maintenances.json` (status.cdp.coinbase.com
не се резолвва) потвърждава:

```
name:             Scheduled System Maintenance — November 14
status:           scheduled
scheduled_for:    2026-11-14T10:00:00-08:00
scheduled_until:  2026-11-14T18:00:00-08:00
body:             "...some users may experience degraded performance across
                   multiple products. Your funds are safe."
```

Тоест **20:00 – 04:00 София**. Напомнянията (`schedule-445ae14c` в 19:45,
`schedule-4231b6c2` в 04:05) пасват точно. Забележка: обявеното време е „до 4
часа", но прозорецът е 8 часа — напомнянията покриват целия.

### Откритието: `self-broadcast` не може да работи

Веригата на сетълмента е `verify=local → self-broadcast → CDP → payai`.
`self-broadcast` плаща газа с `WALLET_PRIVATE_KEY`. Проверено:

```
WALLET_PRIVATE_KEY → 0x9c1eb97e121a6836200C539a1BF0ecdC37F750dd
ETH on Base        → 0.00000000
nonce              → 0
```

**Няма газ и никога не е изпращал транзакция.** Значи първата резервна релса
срещу фасилитаторска авария не съществува.

Комбинирано с прозореца: **осем часа, в които разчитаме само на PayAI** — при
че CDP е деградиран, а собствената ни релса е с празен портфейл.

### Поправено: `/api/connectors` твърдеше `gas=True`

`_eip3009_detail` печаташе `gas={bool(os.getenv("WALLET_PRIVATE_KEY"))}` — тоест
само че **ключът съществува**. Единственият читател, на когото този ред е
важен, е оператор по време на точно такава авария, и `gas=True` му казваше
обратното на истината.

Сега `_gas_wallet_status()` връща `absent | key-set | funded | empty | unknown`:

* **Публичният** ред (безплатен, неаутентикиран) казва `key-set, funds unprobed`
  и **не твърди нищо за наличност** — иначе би струвал RPC на всяка анонимна
  заявка.
* **Операторският** изглед проверява реално и казва `funded` или
  `EMPTY — self-broadcast cannot pay`. Пробата е кеширана (600 s при funded,
  60 s иначе), а провалът се отчита като `unknown`, не се гадае.

**Тест:** `test_the_gas_line_reports_funds_not_just_a_key` покрива липсата на
ключ, непроверения публичен ред (и че той наистина не пипа веригата), празния,
заредения, проваления и изписването на тревожния случай.

### За решението на собственика

Да се зареди газ портфейлът е **парично действие** и ключът му е публикуван
(изгорен), тоест всеки може да изтегли каквото сложим. Не съм пипал нищо.
Вариантите:

1. **Нищо** — приемаме PayAI-only за осем часа; напомнянията вече намаляват
   таймаута към CDP на 5 s, така че падането към PayAI е бързо.
2. **Малко газ** (~0.0005 ETH ≈ $1.5) — включва `self-broadcast`, но с публичен
   ключ, тоест подаряваме тези пари на всеки, който го прочете.
3. **Нов газ портфейл с нов ключ** — правилното решение, извън обхвата на
   текущата задача (иска нов `WALLET_PRIVATE_KEY` в Render).

### Решението (собственикът го потвърди, 14.11)

**Вариант 1 — нищо не се пипа за довечера.** Обосновката е, че
`settlement_pending` от §50 покрива точно най-вероятния изход от такъв прозорец
(„CDP излъчи, но не потвърди"), така че вече не губим платили клиенти в него, а
напомнянията свалят таймаута към CDP на 5 s, за да е бързо падането към PayAI.
Проверено преди прозореца: `X402_FACILITATOR_TIMEOUT` **не е зададен** → 15 s по
подразбиране, значи `--set 5` в 19:45 и `--unset` в 04:05 правят точно каквото
трябва.

**Вариант 3 остава истинската поправка** и не бива да се губи: газ портфейлът
(`0x9c1eb97e…750dd`, от `WALLET_PRIVATE_KEY`) има **0 ETH и nonce 0**, тоест
`self-broadcast` не може да плати газ и първата резервна релса срещу
фасилитаторска авария не съществува. Вариант 1 е приемлив за един осемчасов
прозорец, не като постоянно състояние. Има отделно напомняне за това.

### ОТЛОЖЕНО в 21:0x София (14.11) — прозорецът няма да се състои

Собственикът препрати CDP Discord feed-а. Последното съобщение в него:

> Scheduled System Maintenance — November 14
> **Scheduled** — Our scheduled system maintenance has been postponed due to
> market volatility. We will announce a new date and time soon.

Потвърдено от живото API
(`status.coinbase.com/api/v2/scheduled-maintenances/upcoming.json`):

```
count: 1
  Scheduled System Maintenance — November 14
  scheduled_for: 2026-11-14T18:00:00-08:00 -> 2026-11-14T19:00:00-08:00
  status: scheduled   created_at: 2026-11-14T09:13:00-08:00
  единствено обновление [scheduled]: "...has been postponed..."
```

Две неща се промениха спрямо сутринта:
1. **Оригиналният осемчасов прозорец (10:00–18:00 PST) го няма в API-то.**
   Останалият запис е едночасов (18:00–19:00 PST = 04:00–05:00 София) и той е
   отложен.
2. Записът е **създаден** в 09:13 PST с тяло, което казва „отложено" — тоест това
   е съобщението за отлагането, не стар запис.

**Затова върнах таймаута на 15 s още същата вечер:**

```
DELETE X402_FACILITATOR_TIMEOUT -> HTTP 204
after: 40 variables, X402_FACILITATOR_TIMEOUT set: False
```

последвано от рестарт (иначе 5 s остават в стария процес) и проверка:
`/health` 200 ok, рейлът `→ CDP → payai (cdp: JWT OK)`.

Напомнянето за 04:05 е превърнато от „върни 15 s" в **„провери за нова дата"** —
то вече гледа `/upcoming.json` и иска нови напомняния, ако Coinbase обяви нов
прозорец.

**Поправен и бъг в собствения ни скрипт:** `render_timeout_window.py --unset`
отпечатваше `keys lost by this call: ['X402_FACILITATOR_TIMEOUT']` и излизаше с
код 1 — тоест обявяваше за провал единствения правилен изход. Сега при `--unset`
управляваният ключ се изключва от проверката за изгубени ключове.

### Изпълнено в 20:22 София (14.11) — и едно откритие

```
PUT X402_FACILITATOR_TIMEOUT=5 -> HTTP 200
after: 41 variables, X402_FACILITATOR_TIMEOUT set: True
keys lost by this call: none
```

**ОТКРИТИЕ: Render НЕ рестартира сам при per-key PUT на env var.**
`X402_FACILITATOR_TIMEOUT` се чете при import
(`services/connectors.py:74`, `FACILITATOR_TIMEOUT = float(os.getenv(..., "15"))`),
така че без рестарт старият процес продължава да ползва **15 s** и промяната е
само на хартия. Проверено: ключът беше сложен, а `server_restarted` се появи
едва когато задействах изрично `POST /v1/services/<id>/restart`. Това е важно за
`--unset` на 15.11 в 04:05 — напомнянето вече включва рестарта като стъпка 2.

След рестарта (`server_restarted` в 18:24:23 UTC, след PUT-а в 18:22):

```
/health -> 200 status=ok service=up db=ready
x402-eip3009 -> verify=local canonical;
  settle=self-broadcast (gas=key-set, funds unprobed) → CDP → payai (cdp: JWT OK)
```

Второто е и потвърждението на тази секция на живо: публичният ред вече казва
`key-set, funds unprobed` вместо подвеждащото `gas=True`.

`settlement_pending` от §50 вече покрива случая „CDP излъчи, но не потвърди",
който е най-вероятният изход от този прозорец.

## 53. Сгреших с потвържденията: Base прави блокове на 0.2 s, не на 2 s (14.11.2026)

### Какво направих погрешно

В §41 намалих потвържденията от 12 на 3 с обосновката „12 блока на Base е ~24 s,
а 2 s блок не е 2 s reorg прозорец". **Първата половина беше невярна.** Base
произвежда блок на всеки ~0.2 s, значи 12 блока е ~2.4 s, не ~24 s.

Тоест:
* 12 никога не е било скъпо, както изглеждаше — просто числото е било избрано
  при старата каденция;
* новите 3 бяха **~0.6 s**, не ~6 s, както написах навсякъде;
* публикувах грешно число в ~15 файла и го подпечатах с тестове.

### Как се разбра

Не от нашия код — от **чужд седмичен доклад**: x402 Payability Report 13 казва
„Base now produces blocks roughly every 0.2 seconds instead of 2. A 7-day window
is 1,260,025 blocks this week. If your tools convert days to block counts at 2
seconds, they already cover about a tenth of the time you think."

Проверих сам, вместо да вярвам: 25 последователни блока около 57 215 802 →
**средна разлика 0.21 s**.

### Поправено

| | преди | сега |
|---|---|---|
| proof rail | 3 блока (0.6 s) | **12 блока (~2.4 s)** |
| standard rail | 1 блок (0.2 s) | **5 блока (~1.0 s)** |

Добавен е `BASE_BLOCK_SECONDS = 0.2` с измерването и датата, за да не се губи
основата на числата. Текстът навсякъде е с реалните стойности:
**„12 confirmations, about 2.5 seconds"** вместо „3 confirmations, about 6
seconds". Историческите записи в този файл и в `docs/PROJECT_CHRONOLOGY.md` **не
са пипани** — те пазят какво е било вярвано тогава, което е доказателството как
е станала грешката.

**Защо 5 за standard rail:** 1 блок беше избран, когато блокът беше 2 s; сега
това е 200 ms прозорец, което не е guard. Клиент, който дойде рано, получава
**425 и препраща СЪЩИЯ кредит** — значи цената на по-дълбокото изчакване е
кратко чакане, не загубена продажба.

### Тестове

`tests/test_confirmation_depth.py` — 4 теста, които правят аритметиката
**явна**: каденцията трябва да е под секунда, proof rail-ът да иска 1.5–5 s,
standard rail-ът да има поне 0.5 s, и двата да останат под обещаната скорост.
Следващата смяна на каденцията чупи тест тук, вместо да я намери чужд доклад.

### Урокът

**Брой блокове не е време.** Guard, изразен в блокове, мълчаливо променя
значението си, когато веригата смени каденцията — и нищо в кода не го казваше.
Числото трябва да е изразено във време или поне основата му да е записана до
него.

## 54. Одит на самия документ: какво беше сгрешено и как е поправено (15.11.2026)

Независим одит на `HANDOVER.md` намери конкретни грешки в числа, противоречия и
структурни проблеми. Проверих всяка находка срещу файла и поправих тези, които
издържат проверка. **Някои находки се отнасяха за изостанало GitLab копие, не за
това хранилище** — това също е записано, за да не се търси проблем, който го няма.

### Поправено

| находка | какво беше | поправка |
|---|---|---|
| Заглавие и статус | „09.11.2026, end of session"; таблица с 1231 теста и 7 маршрута | Заменено с датиран блок „Текущо състояние (15.11.2026)" + указание, че документът е хронологичен |
| „Everything below was measured, not inferred" | твърде силно за документ с поправки | Отбелязано като от 09.11 и смекчено, с препратка към §53 и §55 |
| „SCHEDULED RISK — 14 November" | стоеше като отворен; прозорецът мина | Отбелязан като **historical, resolved**, с изхода и препратка към §52 |
| „Still to do: settle through PayAI" | противоречи на доказателството, че PayAI урежда | Отбелязано като затворено (§31, §39) |
| „Never touch" | забраняваше цени/envelope изобщо, а те са променяни с одобрение | Преименувано на „Never touch **without the owner's explicit approval**" |
| Невалиден EIP-55 в §33 | таблицата даваше невалидното написание като „the active payTo" | Показан каноничният адрес + бележка |
| Грешни „~24 s" / „~6 s" в §40, §41, §50 | приемат 2 s блокове | Добавени предупреждения на трите места, сочещи към §53 |
| Липсващ §54 | след §53 идваше §55 | Тази секция запълва номера |

### Проверено и оставено като е

* **Аритметиката на блоковото време** (0.2 s): 10 дни = 4 320 000 блока, 1 500 000
  ≈ 3.47 дни, 90 000 = 5 ч, 24 ч = 432 000 блока — излиза.
* **Сумите за публикуване** ($0.042, $0.242, $0.062, $0.368, $0.098) и класовете
  в §31/§39 (113 за $0.997; 116 за $1.020) — излизат.
* **Аритметиката в §40–§57**: 86/94 = 91.5%, 5+2+1 = 8, 22+29+10+9+3+1 = 74,
  $0.001+$0.02 = $0.021 — излизат.

### Няма `HANDOVER.md.` в това хранилище

Одиторът е чел `HANDOVER.md.` (с точка) в **GitLab копие** и е заключил, че този
файл изостава. Проверено на 15.11: в това GitHub хранилище има **само**
`HANDOVER.md` и той съдържа §40–§61. `git pull` не връща втори файл. Ако някой
види `HANDOVER.md.`, това е ръчно копие през уеб интерфейса, не е версия.

### Осемте числови находки — поправени на 15.11

Първо бяха оставени настрана, защото поправката им променя анализ, не правопис.
Собственикът каза „да", затова са поправени **на мястото им**, всяка с бележка
какво е било и защо е сгрешено:

* **§31** не се сумираше („60" срещу 53+16+4=**73**) → сборът на частите, с бележка.
* **§38** казваше „осем места", таблицата има **10** реда → поправено на „десет".
  (Повреденият пример `postgresql[REDACTED]host` беше артефакт на одиторската
  редакция — в файла стои `postgresql://user:ПАРОЛА@host:5432/db` и е коректен.)
* **§29**: 3 928 600 + 798 702 = **4 727 302**, не 4 731 875. Твърдението „the two
  sum exactly to the headline" е оттеглено; остатъкът 4 573 (0.1%) е изписан.
* **x402-trust**: „$2.00M = 49.4% of all volume" смесваше обхвати — спрямо
  записания знаменател $57.61M един адрес е **3.5%**, и изводът „half the dollars
  are one address" е оттеглен, докато обхватът не се запише.
* **§57**: лентата $0.01–0.02 има ~687 портфейла, от които **659 са един endpoint**
  (~96%) → „~8× повече" е артефакт на един случай, изписан като такъв.
* **agent402**: „Three first places" → **четири** реда с `1/5`.
* **Броят тестове** в `test_dashboard_resilience.py` скачаше 44 → 35 → 38 при
  „12/2/3 new". Броят не може да пада; днес файлът има **38** теста (преброени).
* **Препратките** към §1–§26 не сочат нищо, защото номерирани секции има само от
  §27. Добавена е бележка в началото; конкретната грешна препратка в §58
  (`§9/§35`) е поправена на `§31 и §39`.
* Кръстосани препратки към §9, §12, §19, §20, §22, които не съществуват като
  номерирани секции.

## 55. Нашият собствен delivery ratio: 96.3% срещу реални платци, и един реален платец, който плати и не получи нищо (14.11.2026)

> **КОРЕКЦИЯ (14.11, по-късно същия ден).** Първоначалното число по-долу беше
> **91.5%** и то **подценяваше** резултата. `delivered_at` е добавен на
> **22.09.2026 20:29** (`ff36cc4`), така че редовете, уредени преди това, имат
> NULL, защото функционалността не е съществувала — не защото купувачът не е
> получил нищо. Честното разделяне (`_forensics/honest_delivery_ratio.py`):
>
> | | редове | доставени | ratio |
> |---|---|---|---|
> | преди печата (22.09) | 2 | — | **неизвестно, не провал** |
> | след печата, всички | 92 | 86 | **93.5%** |
> | след печата, без нашия демо портфейл | 27 | 26 | **96.3%** |
>
> Тоест срещу **реални платци** сме **96.3%**, над 94%-а на nohumans, а не под
> него. Независимо потвърждение: PayAPI Market верифицира `/api/v1/whaleflow` с
> транзакция `0x5d6c407a…` — **един от редовете, които броях като недоставени** —
> а тяхната дефиниция изисква „got real product back". Значи печатът е липсвал,
> а отговорът е излязъл.
>
> Шестте недоставени след печата: **1 външен** (случаят с 405 по-долу, поправен
> на 11.11) и **5 наши собствени демо проби**.

### 1. Числото, което не знаехме

nohumans.directory публикува „94% от уредените x402 обаждания са доставени" —
за **други** продавачи. Ние никога не бяхме смятали нашето. Измерих го от
продукционната база (`_forensics/our_deliver_ratio_guards.py`):

```
payment_guards: 94 реда, 86 с delivered_at  ->  91.5%   (подценено, виж корекцията)
settled-not-delivered: 8
```

`payment_attempts` **няма** `delivered_at`, така че разделянето идва само от
`payment_guards` — durable claim ledger-ът, който се пише при уреждане и се
щампова от `after_request`, когато отговорът наистина излезе.

От осемте недоставени:
* **5 са нашият собствен демо портфейл** (`0xe50c5212…`) — не са клиенти;
* 2 са отпреди печата (септември) — **неизвестно**, не провал;
* **1 е истински външен платец.**

### 2. Истинският платец: плати $0.003 и получи 405

`0x0bbd2fec…`, 21.10.2026, `/api/v1/signal`, клас `external`, никога не е
ретрайнал. Проследих го до секундата в `request_log`:

```
17:51:39.608  POST /api/v1/signal -> 402   JarvisClaw-Federation/1.0
17:51:44.064  payment_guards: consumed (уредено)          <- парите взети
17:51:44.071  POST /api/v1/signal -> 405   JarvisClaw-Federation/1.0  <- нищо
```

Клиентът е подал **POST** към GET-маршрут. `before_request` се изпълнява и
когато URL-ът не съвпада по метод, тоест paywall-ът уреди плащането и **след
това** диспечерът отговори 405. Точно това, за което предупреждава r/x402:
„валидирай преди сетълмент; лошо тяло връща 400 преди replay проверката, така че
лоша заявка никога не изгаря подпис".

**Този дефект вече е поправен** (`main.py:5352-5396`: guard преди да се погледне
какъвто и да е credential, с `Allow` и `payment_taken: false`). Проверих го
**на живо**:

```
POST /api/v1/signal -> 405  Allow=GET, HEAD, OPTIONS
  {"error":"method_not_allowed", ... "payment_taken": false}
```

и е покрит от `test_a_wrong_method_never_reaches_the_settlement_rail`, който
доказва, че settlement релсата не се достига. Тоест находката не е нов дефект —
тя е **потвърждението с реални пари** защо поправката съществува.

### 3. `n_paid_undelivered` е метриката, която ни липсваше

Директориите я броят срещу нас; ние не я показвахме. 8 реда, от които 3 не са
наши проби, а **1 е реален клиент**. Малка сума ($0.003) и голям клас: платил и
неполучил е загубен клиент, не загубена продажба.

### 4. EIP-55: документите публикуваха невалиден checksum

Живият 402 рекламира `0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f`, но
`config.py` и **12 живи документа** носеха
`0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f`, който **не е валиден EIP-55
checksum**. Обслужваната стойност винаги е била правилна (`_checksum()` я
нормализира), но който копира адреса от документ, получава написание, което
checksum-валидиращ клиент чете като **адрес-двойник**. Нормализирани 21 срещания
в живите документи (`_forensics/normalise_payto_casing.py`). Историческите
записи (този файл, `docs/archive/`, `docs/TEST_REPORT_2026-08-17.md`,
snapshot-ите от `scripts/phase3*`) са **нарочно непокътнати** — те пазят какво е
било вярвано.

### 5. Осем нови теста: собствен одит срещу капаните на купувача

`tests/test_seller_trap_audit.py` проверява нашите собствени маршрути срещу
капаните, които r/x402 изброява за продавачи (overcharge, скрита цена, ротиращ
payTo, адрес-двойник, изтекла оферта, CORS, липсващ resource, preflight). Не
плаща нищо — това е евтината половина на „имаме 19/19 обаждания, но никога не
проверихме доставката".

### 6. Броят на тестовете

`SUITE_TESTS_PASSED` стоеше на 1397, а пакетът беше 1405 — guard-ът
(`test_visibility_seo.py`) падаше на два теста. Обновен на **1405** заедно с
`README.md` (двете места) и `SUITE_LAST_RUN = "2026-11-14"`. Пълен набор:
**1404 passed, 1 skipped**.

### 7. Speckit scaffolding в работното дърво

`kristo-intelligence/` (31 файла: `.clinerules`, `.specify`) е tooling на Cline,
не наш код, и стоеше неотследен — `git add -A` щеше да го метне в комит.
Добавен в `.gitignore` заедно с `.specify/` и `.clinerules/`.

## 56. `?limit=` на whaleflow беше непокрит, а `payment_rail` беше червен по грешна причина (14.11.2026)

### 1. `?limit=` — реализиран, но никога тестван

Параметърът съществува и се клampва в handler-а (1..200, non-numeric пада на
default), но **нищо не го покриваше**. Има значение заради пари: default-ът от
50 реда е ~16.9 KB / ~4.2k токена, което струва на **купувача** 4× нашето $0.003
на mid модел и 20× на frontier. Купувач, който не може да поиска по-малко, плаща
токени, които не е искал.

`tests/test_whaleflow_limit.py` — 5 теста: стойността на купувача се използва;
клamp 1..200 (заявката може да **свали** отговора, никога да го вдигне);
`?limit=0` и `?limit=-5` пак отговарят (клampнати до 1), не дават 400;
`?limit=abc` пада на default вместо да провали **платено** обаждане; `?hours=`
се клampва по същия начин до 1..168.

### 2. `payment_rail` беше трайно червен

Блокът биеше **само при сетълмент** (или при провал на сетълмент), тоест щом
няма плащане в два от пет-минутните му интервала, таблото го четеше като
остарял и показваше **червен рейл, който работи**. `services/organism.py` дори
твърдеше в коментар, че „този блок също бие от keep-alive пътя" — което никога
не беше реализирано.

Това е точно класът фалшива тревога, за който същият коментар предупреждава:
панел, по който никой не може да действа, учи читателя да го игнорира — и тогава
истинският провал става невидим.

`main.py _payment_rail_readiness()` отговаря на въпроса, който **името на блока**
задава — има ли конфигуриран път за сетълмент — и е отговорим на всеки цикъл,
за разлика от „някой плати ли". Keep-alive цикълът вече го бие на всяка
итерация, независимо от self-ping-а. Сетълментът продължава да го бие с
по-силния `ok`/`degraded` от пътя на заявката; това само спира мълчанието да се
чете като смърт. Коментарът в `organism.py` вече описва какво наистина се случва.

`tests/test_organism.py` +4: блокът е червен, когато нищо никога не е биело
(състоянието, което това премахва); readiness beat го изчиства; пробата дава `ok`
с верига и `degraded` без; пробата никога не хвърля.

## 57. Купихме си външна присъда: „caution", и пазарът ни казва, че сме под пазара (14.11.2026)

Собственикът препрати обява на `df-data-agent.app` — x402 пазарна
интелигентност, която класира услуги по **платещи портфейли, не по брой
обаждания** (същата методология като нашия `settlement-classes`). Купихме две
неща от тях, общо **$0.021**, с `_forensics/pay_dfdata_check.py` и
`pay_dfdata_price.py` (и двата с твърди откази преди да пратят пари: наш
получател, не-USDC актив, друга сума, липсващ EIP-712 домейн, недостатъчен
баланс).

### 1. `/x402/check` върху нашия endpoint — $0.001

```
verdict: "caution"
caution: "only 2 paying wallet(s) in 30 days — thin evidence it works"
         "almost all of this service's volume comes from 1–2 wallets
          (often the seller testing or self-paying)"
good:    "price is in line with market (0.6× median of 837 comparable APIs)"
avoid:   (нищо)
service: 19 endpoints, calls_30d 53, paying_wallets_max 2,
         concentrated: true, sweep_suspected: false
```

**Трета страна, независимо, стигна до същия извод като нашия собствен
класификатор** (§31 и §39: 75 `own_key` срещу 9 `external`). Това не е ново знание,
но е първото потвърждение отвън — и `concentrated: true` е точно това, което
купувач с `nohumans-guard` вижда, преди да плати.

Транзакция: `0xbe3bb733db043af4316d8679a8c9e44e773e7bb480945f67c73c722e6c4b70fd`.

### 2. `/x402/price-advisor` за нашата категория — $0.02

```
comparable_endpoints: 74 · selling_endpoints: 48 · confidence: high
suggested_price_usd: 0.005   range [0.0019, 0.013]
basis: "APIs with 3+ paying wallets active in the last 14 days"

selling (48):  min 0.001 · p25 0.0019 · median 0.005 · p75 0.013 · max 0.1
all (74):      min 0.001 · p25 0.0023 · median 0.008 · p75 0.02  · max 0.2

your_price: 0.003 → cheaper_than 67%, percentile 33,
            "within the normal range of comparable APIs that sell"
```

**Лентите са най-интересното** (`selling` / `всички`, средно платещи портфейли):

| лента | endpoint-и | продават | средно портфейли |
|---|---|---|---|
| под $0.005 | 22 | 17 (77%) | 5.9 |
| $0.005–0.01 | 29 | 18 (62%) | 8.9 |
| **$0.01–0.02** | 10 | 7 (70%) | **68.7** |
| $0.02–0.05 | 9 | 3 (33%) | 2.6 |
| $0.05–0.10 | 3 | 3 (100%) | 4 |
| над $0.10 | 1 | 0 (0%) | 2 |

Лентата **$0.01–0.02 изглежда с ~8× повече платещи портфейли** от съседните — но
това е артефакт на един случай. Средното от 68.7 върху 10 endpoint-а е ~687 общо,
а `console.ax1.vc` сам има **659**, тоест ~96% от лентата е един endpoint; другите
девет са ~3 портфейла средно, колкото съседните ленти. Топ-печелившият в
категорията е `console.ax1.vc` на **$0.02** с **659 платещи
портфейла и 328 388 обаждания** → **~$6 568 оценен приход за 30 дни**.

### Какво значи това (решение за собственика)

**Цената не е ограничението — разпространението е.** $0.003 е под
препоръчаните $0.005 и на 33-тия перцентил, но търсенето ни е 2 портфейла.
Вдигането на цената няма да донесе купувачи; то ще вземе повече от малкото,
които вече идват. Лентата $0.01–0.02 обаче показва, че пазарът плаща повече,
когато услугата е намерена — тоест проблемът е видимост, не цена.

**Не съм пипал цени.** Това е решение на собственика, а и `X402_PRICE_MAP` е в
списъка „никога без изрично решение".

### Инструментите остават

И двата скрипта са в `_forensics` и могат да се пуснат пак: `check` върху който
и да е endpoint ($0.001) и `price-advisor` за която и да е категория ($0.02).
Полезни са и срещу конкуренти — `check` дава присъда за всеки чужд endpoint.

## 58. PayAPI: вече ни листват и settlement-verified, и това поправи едно наше число (14.11.2026)

Собственикът препрати обява на PayAPI Market за нов **пазар на „работи"**
(`/agent-marketplace`, 26 агента, 19 от тях първопартийни). Проверих дали ние
присъстваме — и се оказа, че **присъстваме, и то добре**.

### Нашият запис

```
slug:                kristo-intelligence-defi-signals-api
name:                Kristo Intelligence — DeFi Signals API
category:            Finance
provider:            Dimitri Hristov
endpoints_count:     11
price:               0.003 – 0.005 USDC
payment_verified:    true      verification_paused: false
verified_route_count: 3
```

Трите верифицирани маршрута, всеки с линк към Basescan:
`/api/stats` ($0.005, 02.09), `/api/v1/signal` ($0.003, 02.09),
`/api/v1/whaleflow` ($0.003, 21.09).

Техният каталог: **1 693 settlement-verified API-та, 2 889 листвани, 30 664
endpoint-а**, от 1 683 независими доставчика. Листването е безплатно и PayAPI
взема **0%**.

### Находката, която поправи наше число

Транзакцията, с която PayAPI верифицира `/api/v1/whaleflow` —
`0x5d6c407a2518fb9e4271c9fa88147bbc08a9f8658525dd02b1444e2e43485e1c` — е
**един от редовете, които в §55 броях като недоставени**. А тяхната дефиниция на
„settlement-verified" изисква „we paid a real x402 call, got real product back".

Тоест `delivered_at IS NULL` **не значи** „купувачът не получи нищо": печатът е
липсвал, а отговорът е излязъл. Причината е, че `delivered_at` е добавен на
**22.09.2026 20:29** (`ff36cc4`), а онзи ред е от 21.09 — преди функционалността
да съществува. Виж корекцията в §55: срещу реални платци сме **96.3%**, не 91.5%.

### Как се листва (ако решим)

`POST https://payapi.market/api/agent/submit-listing` — минимумът е
`contact_email` и един платен URL (`url`, `paid_route_url` или `urls`, до 20).
Всяка route се проверява за HTTP 402, а цена/`payTo`/мрежа/описание се
попълват от предизвикателството. Безплатно.

**Не съм публикувал нищо.** Листването на нов запис е външно действие и чака
изрично „да" — а и не е спешно: вече сме в каталога с три верифицирани маршрута.
Ако решим да ползваме пазара на работи, `/api/v1/verify-seller` е най-подходящ
(той е задача — одит на продавач — а не просто данни), но това е отделно
решение.

## 59. Довършване на висящите задачи: едно свършено, три блокирани от теб (14.11.2026)

Собственикът каза „довърши всички задачи, които ти изпратих". Ето какво излезе —
и три от петте не могат да се довършат от агент, което е честният отговор.

### Свършено: отговорът до Ernest (одит за $5)

`_forensics/reply_to_ernest.py` — изпратен през нашия Gmail SMTP, двойна врата
(dry-run по подразбиране). Приех одита и поисках конкретно:

* `/api/v1/verify-seller` и `/api/v1/signal` като основните два маршрута;
* останалите пет за пълнота;
* **каталожната половина** — дали всеки маршрут изобщо присъства в Coinbase CDP
  Bazaar, PayAI discovery и 402index, и какво блокира индексирането.

Той е реален продавач, не студена оферта: `x402-probe.lucciocarmino.workers.dev`
отговаря на `/health` с жива x402 конфигурация, носи v1 манифест на
`/.well-known/x402` и заявява ownership proof `0xEe523a5145cfaEa8cCEc34Fb364a2A92Fad62A3a`.
Одитът е насочен точно в слабото ни място — `df-data-agent` ни даде `caution`
заради тънко търсене, а каталожна дупка би го обяснила.

### Блокирано 1: PayAPI Agent marketplace — иска твоя имейл

Листването на агент **не е API**. Потокът е уеб: `/agent-marketplace/list` →
въвеждаш имейл → PayAPI праща **линк за вход** → отваряш го → добавяш агента в
таблото. Проверих и трите страници и целия OpenAPI: `/api/` референции в
страницата няма, fetch() няма, а в спецификацията няма нито auth endpoint, нито
agent-submit. Единственият submission endpoint (`POST /api/agent/submit-listing`)
приема схемата на **API каталога** (`urls`, `price`, `payTo`, категории
Data/Verification/Intelligence/Tools/Finance) — не агентските полета.

Агентът не може да прочете пощата (само SMTP за пращане), значи **не може да
отвори линка**. Затова: `docs/PAYAPI_AGENT_LISTING.md` съдържа готовия листинг
(всичките 20 полета, които PayAPI рендира, с точните input/output схеми от
`/sample`) — остава само да го поставиш.

### Блокирано 2: npm publish на 1.1.2 — токенът е изтекъл

`kristo-x402-client` е публикуван до **1.1.1**; локално сме на **1.1.2**. Dry-run-ът
е чист (5 файла, 10.9 kB). Реалният `npm publish` пада:

```
npm error 404 Not Found - PUT https://registry.npmjs.org/kristo-x402-client
```

`npm whoami` също дава **E401 Unauthorized** — `_authToken` в `~/.npmrc` е
невалиден. npm маскира 401 като 404 при publish, за да не издава дали пакетът
съществува. Трябва нов токен.

### Блокирано 3: Token Kiosk и x402-trust `rotate-request`

И двете ги имаше само в разговора — в нито един файл на диска. Търсих
`kiosk` в целия repo и в `_forensics`: единственото попадение е чуждо
(`chatmcp/mcpso#5566`, „Agent Kiosk" на @ralf9090, от radar дайджеста).
`rotate-request` не се среща никъде. Не измислям имейл до непознат получател по
спомен — трябва ми черновата или получателят.

### Урокът

Три от петте задачи бяха блокирани не от липса на достъп до мрежата, а от
**самоличност и поща**: линк за вход, npm токен, чернова в разговор. Агент с
пълен мрежов достъп пак не може да влезе в чужд акаунт. Това си струва да се
записва като отделен клас блокер, за да не се брои за провал.





























## 60. npm 1.1.2 е публикуван — 15.11.2026

Токенът, който собственикът даде, е **staged publishing** токен: качва без 2FA, но
одобрението иска втори фактор. Регистърът отговори `401` с `WWW-Authenticate: OTP`
и линк за security key. Собственикът одобри сам от своя терминал:

```
npm stage approve bfe72f30-4659-4726-bdb6-fe27a2f161ee
  -> approved and published successfully
```

Проверено след това:

```
versions:  1.0.0, 1.1.0, 1.1.1, 1.1.2
dist-tags: latest = 1.1.2
tarball:   10 921 bytes, sha1 43719bbdcb8eab290f561f2dce2e36eee9f3ba57  (съвпада със staged shasum)
```

Чиста инсталация в празна директория мина (`added 1 package, 0 vulnerabilities`) и
`require()` зареди 8 експорта. Shasum-ът на стeйджа и на публикувания tarball
съвпада — нищо не е подменено по пътя.

**Урокът за класа блокери:** токенът не беше проблемът. Проблемът е, че *одобрението*
на стeйдж е отделно оторизирано действие от *качването*. Токен, който качва, не
одобрява. Това е разликата между „имам достъп" и „имам право да финализирам".


## 61. PayAPI агентът е подаден — без браузър, през собствения им API (15.11.2026)

Задача 2 от трите. Собственикът беше стигнал до страницата и беше поискал линк за
вход, но линкът живее 15 минути и изтече, докато се разберем. Вместо да го карам
да цъка пак, прочетох как dashboard-ът работи и го направих по API.

### Как се влиза (намерено в `assets/index-*.js`)

```
POST /api/provider-login {"email": "..."}   -> праща линк
линкът носи  #login=<token>
POST /api/provider-login {"token": "..."}   -> {"token": <сесия>, "email": "..."}
```

Токенът е във **fragment**, тоест сървърът никога не го вижда — но endpoint-ът,
който го обменя, е публичен. Тоест: поисках нов линк сам, прочетох го по **IMAP**
(същата Gmail app password, която ползваме за SMTP, работи и за IMAP), и го
обмених за сесия. Без браузър, без собственика.

### Как се подава агент

`POST /agent/services/submit` с `Authorization: Bearer <сесия>`. Схемата я извадих
от собствения им валидатор (функция `KN` в bundle-а): `name`, `task`, `task_slug`,
`description`, `category`, `tags`, `paid_route_url`, `paid_route_method`,
`networks`, `pay_to_base`, `input_schema`, `output_schema`, `example_input`,
`sample_url`, `typical/max_latency_seconds`, `underlying_model`,
`a2a_agent_card_url`, `erc8004_agent_id`, `invite_code`.

**Цената НЕ е в payload-а** — пазарът я чете от нашия собствен 402. Задачата
(`task_slug`) е `token-and-wallet-risk` от техните 27, категория `Verification`.

### Резултатът

```
HTTP 201
id:      a611774e-09d7-4745-a08e-5863fb35a33c
slug:    kristo-seller-audit-verify-an-x402-seller-before-you-pay
status:  pending_checks
price:   0.01 USDC   <- прочетена от нашия 402, потвърждава, че пилотът е активен
plan:    free, 1/1
```

Остава `pending_checks` — не се показва публично, докато не мине проверка.
`verification_state: none` се попълва от тях.

**Урокът:** „само през браузър" беше вярно за *човека*, не за протокола. Щом
клиентът е JS, логиката му е четим код — и щом endpoint-ът е публичен, входът е
възпроизводим. Три от петте блокера в §59 бяха от този клас; този падна, защото
проверих какво точно прави страницата, вместо да приема, че не мога.

## 62. Отворени задачи — живият списък (15.11.2026)

Това е единственият списък с отвореното. Всичко в секции 1–61 е запис; ако там
пише „отворено", но го няма тук, значи е затворено.

### Чака собственика

| # | задача | какво трябва |
|---|---|---|
| 1 | **Ключът на `payTo`** | Осем негативни проверки. Дай **пълния** адрес на Account 1 от MetaMask (двата кандидата се различават по последните 4 знака: `…d08f` активният с 1.02 USDC срещу `…d88f` старият с 0). Без него одитът не може да продължи |
| 2 | **Token Kiosk имейл** | Черновата или получателят. Няма я никъде в хранилището (проверена цялата git история) |
| 3 | **Пренаписване на git историята** | Байтовете на стари тайни стоят в стари комити. `git filter-repo` + force-push е твое решение, не мое. **Подготвено и проверено на 15.11** (пробен запис: 0 остатъка); чака адрес за проекта и „да" за force-push |
| 4 | ~~**Дали да оставим $0.01**~~ | ✅ **затворено, надживяно от §68** — пилотът приключи съзнателно: `KRISTO_VERIFY_SELLER_PRICE` на Render е **$0.05**, кодът по подразбиране също, и напомнянето за връщане на $0.10 на 11.12 е **изтрито**. Няма какво да се връща. Проверено 18.11 |
| 5 | **Нов газ портфейл** | ✅ **готово 16.11** — нов портфейл `0x5f6d3F20282A8958C6607D7E17dC8C83B1F0Ee74`, ключът е на Render като единичен env ключ, услугата е рестартирана, адресът има **0.00243575 ETH на Base** и кодът връща `funded`. Резервната релса вече съществува. Виж §63 |

### Чака външни хора

| # | задача | състояние |
|---|---|---|
| 6 | **PayAPI агент** | `pending_checks` от 15.11. Не се показва публично, докато не мине тяхната проверка |
| 7 | **CDP поддръжка** | Проверено 15.11 16:50: `scheduled_maintenances: []` — няма обявен прозорец |
| 8 | **x402 List** | Чака се отговор. Осем дни мълчание към 13.11 (§39) |
| 9 | ~~**Мъртвото Vercel копие**~~ | ✅ **решено 18.11** по issue [Merit-Systems/x402scan#1340](https://github.com/Merit-Systems/x402scan/issues/1340). Записът „не е наше и не можем да го махнем" беше **грешен** — маха се с точно докладване, което Ърнест направи. Проверено независимо на 18.11: пълен обход на CDP (34 620 HTTP + 550 MCP реда) връща **нула** реда с `kristo-intelligence.vercel.app`, а всичките **26** реда, сочещи към нашите портфейли, са на живия хост |
| 10 | ~~**Ernest — x402 одит ($5)**~~ | ✅ **платено и приключено** — 5.0001 USDC на 16.11 (§68, tx `0x084de743…`, блок 58317883), после още **15.0001 USDC** на 18.11 за fix-sheet-а (tx `0xf5a433e9…`, блок 58958146). Отчетът е получен; безплатната 14-дневна повторна проверка също е направена от него на 18.11 |

### Вътрешни, без външна зависимост

| # | задача | бележка |
|---|---|---|
| 11 | **`requests_summary` = 3.1 s** | Най-бавната стъпка при построяване на таблото. Не е започната |
| 12 | **`main.py` монолит** | ~9 660 реда |
| 13 | **24-часова проверка на паметта** | Частично проверено 15.11: инстанцията е вдигната ~05:23 UTC; след ~8 мин загряване паметта е **плоска** (~201 MB, ±1 MB за 23 мин). Пълните 24 ч още не са изтекли |
| 14 | **Останалите 4 маршрута в x402dash** | Частично покритие |
| 15 | **„$1 Delivery Report"** | Не е започнат |
| 16 | **Осемте находки от одита** | ✅ поправени на 15.11 — виж §54 |

### Известни дефекти в процеса (не в кода)

* **Деплоят на `12227c2` се провали** (15.11 07:13 → 07:28). Билдът мина, деплоят не,
  причината не се дава от API-то. Продукцията остана на `2ab0f73` и е здрава.
  Промяната е само в тестов файл, тоест runtime-ът не е засегнат, но репото е
  напред от продукцията. Всеки следващ деплой ще я включи.

### Знай това, преди да пипаш

* `X402_FACILITATOR_TIMEOUT` се чете **при import** (`services/connectors.py:74`), а
  Render **не рестартира сам** при промяна на един env ключ. Всяка промяна иска
  `POST /v1/services/<id>/restart`. Проверено на 14.11 (§52).
* Само **единични** env ключове. Никога `PUT` върху колекцията `/env-vars` — на
  07.11 празен payload изтри конфигурацията.
* `payTo`, цените и 402 envelope-ът се пипат **само с изрично „да"** (§ „Never touch
  without the owner's explicit approval").
* Около 40 скрипта в `_forensics/` са **извън хранилището**
  (`<forensics-dir>\`), тоест нова сесия не
  може да ги пусне, докато не ги намери там.
* Хранилището може да е **публично**: съдържа личен Gmail, локални пътища и Render
  ID-та. Провери, преди да добавяш още.


## 63. Нов газ портфейл — зареден и потвърден (16.11.2026)

`self-broadcast` нямаше газ (0 ETH, nonce 0), тоест първата резервна релса не
съществуваше. Собственикът каза „оправяй всичко както трябва да е", затова
направих следното сам, без да го занимавам с ключове и акаунти.

**Какво е направено:**

1. Генериран е **нов, отделен портфейл само за газ**:
   `0x5f6d3F20282A8958C6607D7E17dC8C83B1F0Ee74` (валиден EIP-55, 0 ETH, nonce 0).
   Ключът е в `secrets/gas_wallet_key.txt` — gitignore-нат, стойността не се
   отпечатва никъде.
2. Ключът е сложен на Render като **единичен** env ключ `WALLET_PRIVATE_KEY`
   (`PUT /v1/services/<id>/env-vars/WALLET_PRIVATE_KEY`, HTTP 200). Никога не се
   пипа колекцията — на 07.11 празен payload изтри конфигурацията.
3. Услугата е **рестартирана** (`server_restarted`, 16.11 06:37:30 UTC), защото
   env се чете при import и Render не рестартира сам.
4. Проверено: Render съхранява ключа и той дава **точно** новия адрес.
   `/health` → 200, `status: ok`, `fee_receiver` непроменен.

**Защо нов, а не старият:** старият ключ (`0x9c1eb97e…750dd`) е записан като
изгорен/публикуван още на 27.08 FREEZE. Опитах да го проверя независимо —
извадих всеки 64-hex низ от историята и сравни адресите: **0 попадения**. Тоест
не можах нито да потвърдя, нито да опровергая, защото оригиналното репо изчезна.
Нов портфейл струва 2 минути; залагането на стария струва целия газ.

**Какво чака собственика:** ~€5 ETH **на Base** към новия адрес.
Път: Revolut → Coinbase → купуване → Withdraw → мрежа **Base**.

**Съпътстващо:** деплоят на `12227c2` се беше провалил на 15.11 07:13
(build ok, deploy failed, без причина от API-то). Оказа се преходен — следващият
деплой (`8bc2743`, 15.11 16:51) мина и сега продукцията върви на последния комит.

**Отворено, отделно:** активният `fee_receiver` е `0xd4cdA900…d08f`, а
собственикът държи `0xd4cdA980…d88f` (Account 1). Три акаунта в MetaMask, нито
един не е получателят. §33 цитираше комит `d848a72` („key rotation done") като
доказателство за ротация на портфейлен ключ — но този комит е за **Render API
ключове**. Ротация на портфейл никога не е документирана. Приходът в получателя
е $1.02 и расте; ключът му не е намерен.

### Зареждането е потвърдено на веригата (16.11, 14:33 София)

Докладът на собственика твърдеше, че преводът е минал. Проверено **на веригата**,
не по доклада:

```
0x5f6d3F20282A8958C6607D7E17dC8C83B1F0Ee74
Base ETH    0.00243575     <- точно колкото твърди докладът
Base USDC   5.346988       <- също колкото твърди
nonce       0
може газ    ДА
```

И проверено, че **сървърът** го вижда като зареден, не само веригата — пуснах
същия код локално с новия ключ:

```
публичен ред (probe=False) : key-set    <- умишлено не пипа веригата
операторски  (probe=True)  : funded
```

**Резервната релса вече съществува.** Веригата е
`verify=local → self-broadcast → CDP → payai` и първата резерва най-после може да
плати газ. Дотогава при фасилитаторска авария оставаше само PayAI.

**Бележка:** заедно с етера собственикът е пратил и 5.35 USDC в същия портфейл.
Не е нужно — газ портфейлът не държи приход, той само плаща такси. Не вреди, но
означава, че в портфейл, чийто ключ стои на Render, има и $5. При бъдещо
зареждане е достатъчен само етерът.


## 64. CORS обещаваше POST на маршрути, които приемат само GET (16.11.2026)

Повод: тред в r/x402 — някой е пратил празен POST до 137 обявени платени x402
маршрута и само ~31% са върнали истинска 402-ка; останалите 404 или 405. Изводът
в треда: глаголът се избира от клиента, не от продавача, значи купувач, който
пробва POST, вижда счупен endpoint и си тръгва без да плати.

### Нашето състояние беше добро — проверих го, преди да пипна

| тредът иска | ние |
|---|---|
| 405, не 404 (404 изглежда мъртво) | ✅ 405 |
| 405-ицата да казва кой глагол работи | ✅ `Allow: GET, HEAD, OPTIONS` |
| глаголът да е обявен в 402-ката | ✅ `extensions.bazaar.info.input.method = GET` |
| никога да не таксуваме за не-отговор | ✅ `payment_taken: false` |

405-ицата казва и че подписът може да се ползва пак: „Nothing was settled, so any
payment authorization you sent has not been used and your balance is unchanged —
repeat the request with GET and the same credential."

### Какво беше сгрешено

`Access-Control-Allow-Methods` казваше `GET, HEAD, POST, OPTIONS` на маршрути,
които приемат само GET. Браузърен агент, който вярва на preflight-а, праща POST и
получава 405. Хедърът обещаваше глагол, който после отказваме — същият клас
дефект, само по-дребен.

Проверих преди промяната: **всичките осем платени маршрута** връщат
`allowed: GET, HEAD, OPTIONS` от собствените си 405 тела, тоест нито един не
приема POST. POST съществува другаде в приложението (`/mcp/message`,
`/api/checkout`, Stripe webhook-ът), но не на платен маршрут — а този хедър е само
за платените.

### Поправката

`_X402_CORS_ALLOW_METHODS` е `"GET, HEAD, OPTIONS"` (main.py:5123), с обосновката
записана до константата. Нов тест
`test_cors_never_promises_a_verb_the_paywall_refuses` заключва правилото: **405
тялото е източникът на истина**, и 402-ката, и preflight-ът могат да обявяват само
подмножество от него. Този тест щеше да хване първоначалното надобещание.

Проверено на живо след деплоя: preflight 204 → `GET, HEAD, OPTIONS`; 402 →
същото; POST → 405 с `Allow: GET, HEAD, OPTIONS`.

**Не е пипан платежният път.** Само CORS хедърът и тест.

Набор: 1414 минават, 1 пропуснат, **1415 събрани** — рекламираното число в
`discovery.py`, README и handover-а е обновено на 1415.


## 65. Получателят е сменен — приходът вече е достъпен (16.11.2026)

Довършено е това, което стоеше открито от §32: **всеки сетълмент в историята на
проекта беше отивал на адрес, чийто ключ никой не държи.** Търсенето е изчерпано
(машината, git историята, пощата, MetaMask-ът, `secrets/` — всяко чрез извличане
на адрес от всеки 64-hex кандидат, нула попадения). Значи пари можеха да влизат
там и никога да не излязат. $0.01, които PayAPI платиха за верификацията на агента,
е най-ясният пример — още седи там.

### Новият получател

```
0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844
```

Ключът е в `secrets/receiver_key.txt` (gitignore-нат, не се отпечатва). **Сървърът
не се нуждае от него** — получаването не иска подпис. Затова ключът не е на Render,
за разлика от газовия.

### Какво е променено

* `config.py` — `BOUND_BASE_FEE_RECEIVER` сочи новия портфейл, с причината записана
  до него. Старата константа не бива да се връща: fallback, който сочи портфейл без
  ключ, мълчаливо връща неизползваем получател.
* Render env `BASE_FEE_RECEIVER` — новият адрес, **единичен ключ** (никога
  колекцията). Държеше стария в неканоничен регистър; `get_base_fee_receiver()` го
  нормализира.
* Документи, които описват какво **работим днес**: `.env.example`, `README.bg.md`,
  `docs/DISTRIBUTION_STATUS.md`, `docs/OUTREACH_KIT.md`, `docs/GRANT_APPLICATION.md`,
  `REGISTRATION_CHECKLIST.md`, `DEPLOYMENT.md`, `DEPLOYMENT_CHECKLIST.md`.
* Три теста спряха да държат адреса твърдо и го четат от конфигурацията:
  `test_402_response_headers`, `test_x402scan_compliance`, `test_audit_fixes`.
  Втвърденият адрес ги караше да проверяват стар портфейл — и двойката в
  `test_audit_fixes` падна **правилно**: подпис, който именува грешен получател, се
  отказва. Това е релсата да си върши работата.

Нарочно оставени със стария адрес, защото той е тяхната тема: `HANDOVER.md`
(ловът), `TASK_FOR_KILO_find_the_payto_key.md` (задачата беше да се намери ключът)
и `docs/PAYAPI_AGENT_LISTING.md` (адрес за одит, не наш).

### Проверено на живо след деплоя

```
/health fee_receiver   0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844
402 header payTo       0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844
x-payment-address      0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844
8 от 8 платени маршрута OK
/.well-known/x402  new=2 old=0
/openapi.json      new=2 old=0
/llms.txt          new=1 old=0
```

### Какво остава

1. **PayAPI и x402scan са регистрирани срещу стария `payTo`.** Трябва да се
   уведомят и верифицират наново, иначе виждат разминаване между обявено и
   действително.
2. **Собственикът трябва да внесе ключа в MetaMask**, за да може да тегли прихода
   (файлът е `secrets/receiver_key.txt`).
3. Старите $1.02 в `0xd4cdA900…d08f` остават недостъпни. Това е цената.

Набор: 1414 минават, 1 пропуснат, 1415 събрани.


## 66. Недостигът на дълбочина вече чака, вместо да откаже платилия (16.11.2026)

Открито при **собственото ни тестово плащане** към новия получател, веднага след
ротацията от §65. Пуснах `scripts/phase1_paid_call.py` срещу `/api/v1/signal` и
получих `{"ok":false,"error":"settlement_in_flight"}` — два пъти подред. Парите
обаче се движеха: получателят отиде от 0 на 0.003, после на 0.006.

**Тоест две плащания бяха взети без продукт.** Нашият собствен клиент не опитва
пак при 425, значи парите отидоха и нищо не се върна. Точно това, което
x402 общността нарича по-лошия отказ: агентът на купувача вижда само че парите
ги няма.

### Причината беше един клон

`_confirmations_ok_with_lag_refresh` вече чакаше, когато блокът на сетълмента е
**пред** нашата глава — защото това значи изостанал часовник. Когато блокът е
**на или зад** главата, но не е достатъчно дълбок, отказваше **веднага**, с
довода, че не е проблем с часовника.

Доводът е верен за причината и грешен за цената: на Base блокът е ~0.2 s, значи
5 потвърждения идват за около секунда. Платилият получаваше 425 за изчакване,
което вече почти беше свършило.

### Поправката

Клонът за недостиг на дълбочина вече **чака веднъж и препрочита**, точно както
прави клонът за изостанал часовник. Fail-closed е запазен: ако дълбочината още
я няма, отказът става със **същото** събитие `c2_insufficient_confirmations` —
просто след като веригата е имала своята секунда. Когато дълбочината дойде, се
записва `waited_and_accepted`, което е съществуващото събитие за точно това.

Чакането е `KRISTO_C2_LAG_WAIT_SECONDS`, по подразбиране **2.5 s** — около
дванайсет Base блока, повече от петте, които стандартната релса иска.

Тестът, който заключваше старото поведение (`no refresh/wait for a depth
shortfall`), е **пренаписан, не изтрит** — сега покрива и двата изхода.

### Доказателството, на живо

След деплоя същият клиент, същата команда:

```
{"ok":true,"path":"/api/v1/signal","usd":0.003,
 "tx":"0x2faf3a6a03b26aefeb7536a3292471311e84b00fcf61f3c11a6437296f907806"}
```

Верига: статус успешен, `0.003 USDC -> 0xb4fcf8ef…fc844` (новият получател).
Регистър: последна продажба $0.003 „току-що", днес 5 сетълмента / $0.022.

**Първият опит вече успява.** Преди поправката всеки свеж опит получаваше 425.

Набор: 1414 минават, 1 пропуснат, 1415 събрани.


## 67. `required` в bazaar декларацията: 59 → 85 при външен оценител (16.11.2026)

Открито случайно, докато четяхме r/x402. Външна услуга — `settled.tools` —
индексира x402 маршрути, купува от тях с истински USDC на Base и дава оценка на
качеството. Попитахме я директно за нашия маршрут (`/v1/free/check?url=…`) и
видяхме къде сме.

### Състоянието преди

```
quality.total   59      ← прагът им за „плати" е 60
  liveness      40
  schema        15
  latency        4
  activity       0      ← получателят не беше в книгата им
  delivery       0      ← „the listing gives nothing to compare it with"
onchain      pending
payability   payable
```

И при търсене по собствената ни категория **не се появявахме в топ 20** — нито
при „crypto signals", нито при „defi signals", нито при „trading signals".
Лидерите бяха с оценка 79–94.

Две причини, и двете наши:
1. **`delivery: 0`** — декларацията в 402-ката носеше `properties` (9 ключа), но
   **не и `required`**. Техният четец взема `.required` и `.properties` от обекта
   `example` и сравнява доставеното с обявеното; без `required` няма с какво да
   сравни, значи доставката не се брои.
2. **`activity: 0`** — книгата им още пазеше стария получател. Това е цената на
   ротацията от §65, и е временна: преизчисляват четири пъти в деня.

### Поправката

`_BAZAAR_EXAMPLE_REQUIRED` + `_bazaar_example_required()` в `main.py`. Публикуваме
`required` **само** за маршрути, за които сме го измерили: свеж и кеширан 200 на
`/api/v1/verify-seller` върнаха еднакви 14 ключа, значи 9-те, които примерът вече
назовава, са винаги там. Псевдонимът `/api/v1/seller-check` се разрешава към
каноничния и обявява същия договор.

Маршрут без измерен набор **не публикува клаузата изобщо**, вместо празен списък:
„не е обявено" е честно, „обявено празно" е твърдение. Тестът, който забраняваше
`required` изцяло, е пренаписан — сега иска всяко обявено `required` поле да е
подмножество на `properties` и да присъства в реално доставеното тяло.

### Резултатът, измерен на живо след деплоя

```
                преди    сега
quality.total     59      85
  liveness        40      40
  schema          15      15
  latency          4       7
  activity         0       8
  delivery         0      15
onchain        pending    ok
payability     payable    delivered
```

Класиране по собствената ни категория:

```
                    преди        сега
"crypto signals"    не в топ 20  #14 от 20
"defi signals"      не в топ 20  #4  от 20
"trading signals"   не в топ 20  #17 от 20
```

**От невидими до класирани, с един `required` и едно преизчисляване на тяхната
книга.** Урокът: обявата не е документация, а вход на алгоритъм, и алгоритъмът
чете точно определени полета. Липсващо поле не е „по-малко шум" — то е нула
точки.

Набор: 1414 минават, 1 пропуснат.


## 68. Цените са вдигнати по данни, и одиторът е платен (16.11.2026)

### Плащането

Ърнест поиска **5.0001 USDC** на `0xEe523a51…2a3a`, ако одитът е бил полезен, и
изрично каза, че не дължим нищо, ако не е. Одитът намери дефект, който таксуваше
купувачи за празен отговор — единственото нещо, което този продукт не бива да
прави. Затова е платен.

```
от    0x5f6d3F20282A8958C6607D7E17dC8C83B1F0Ee74   (газовото портфейлно)
до    0xEe523a5145cfaEa8cCEc34Fb364a2A92Fad62A3a   (Ърнест)
сума  5.0001 USDC
tx    0x084de743f3d422f6b620444157b15cf4d2885b4f987480e95442e64dace9f94e
блок  58317883 · статус успешен · газ 45 059
```

**Проверка преди подписване:** получателят е **същият адрес, от който Ърнест ни
плати** (`0xee52…2a3a` фигурира в собствения ни регистър като платец за двете
одитирани обаждания). Скриптът отказва да изпрати, ако адресът не съвпадне.
След превода: Ърнест 8.704620 USDC, газовото портфейлно 0.346888.

### Цените

Ърнест измери пазара, вместо да разсъждава: в **34 890 x402 маршрута** в Bazaar
за 30 дни лентата под $0.005 дава средно ~$0.03 бруто на маршрут, а лентата
$0.02–$0.06 — ~$2.25. В категорията данни на веригата същата лента дава ~$10.97
на маршрут, срещу $0.02 под $0.005. **Обемът не расте, когато цената пада** —
евтините ленти са просто където живеят неактивните маршрути.

| маршрут | беше | сега | защо |
|---|---|---|---|
| `/api/v1/verify-seller` (+ `seller-check`) | $0.01 (пилот) | **$0.05** | върхът на препоръчания диапазон $0.03–0.05; половината от каталожните $0.10; 10× най-евтиния ни маршрут |
| `/api/v1/signal` | $0.003 | **$0.01** | под препоръчания минимум не е цена, а липса на цена |
| `/api/v1/whaleflow` | $0.003 | **$0.01** | същото |

Останалите четири (`stats`, `sales`, `bot-status`, `arb`) остават на $0.005 —
Ърнест не ги посочи и ние нямаме измерване за тях.

**Пилотът приключи съзнателно**, не изтече: `KRISTO_VERIFY_SELLER_PRICE` на
Render е $0.05 (не $0.01), кодът по подразбиране също е $0.05, и напомнянето за
връщане на $0.10 на 11.12 е **изтрито** — няма какво да се връща.

Повишаването на `signal`/`whaleflow` беше **условно**: Ърнест го поиска „само
след като се поправи 2б, така че платено обаждане никога да не връща празно".
Това е поправено по-рано същия ден (§ предходния).

### Какво се счупи от смяната, и как е поправено

* **Банлистата на „фантомните" цени** забраняваше `$0.05` и `$0.01` — цени,
  които вече сервираме. Правилото има прецедент: `$0.10` беше махнат оттам на
  07.11, когато стана реална цена. Махнати са и трите числови шаблона; остават
  само обещанията за безплатен достъп, които производството не изпълнява.
  По-силният guard е производният — той съди числото по това дали е реална цена
  на маршрут, а не по ръчно поддържан списък.
* **`server.json`** (манифестът за MCP регистъра) държеше твърди цени и те се
  проверяват срещу `X402_PRICE_MAP`. Обновени: `min_usd` 0.003→**0.005** (това е
  минимумът по ВСИЧКИ маршрути, не по променените), `max_usd` 0.1→**0.05**,
  `signal`/`whaleflow`→0.01, `verify-seller`→0.05.
* **Два теста** в `test_signal_route.py` твърдяха $0.003 като литерал. Сега четат
  константата — същият урок, който банлистата вече беше записала.
* **Живите твърдения** в `README.md`, `HANDOVER.md` (заглавната таблица) и
  `docs/AUDIT_BRIEF.md` са обновени. Хронологичните секции и датираните отчети
  **не са** — те цитират цените на своето време и пренаписването им би разрушило
  записа, не би го поправило.

### Остава от одита

1. **PayAI каталогът** — 13 наши реда, **всичките със стария `payTo`**. Виж
   следващата секция; писмото до тях е готово.
2. **Псевдонимите** — Ърнест твърди, че делят класирането в Bazaar (19 реда за
   един хост). Продуктова промяна; не е пипана.
3. **Различни URL за MCP инструментите** в PayAI — външна интеграция.


## 69. Каталогът на PayAI: два реални дефекта, четири маршрута върнати (16.11.2026)

### Какво каза Ърнест и какво се оказа

Той написа, че PayAI показва ресурс само след плащане, преминало през техния
фасилитатор, и че редовете ни са остарели. **И двете е вярно, а второто беше
по-лошо, отколкото той можеше да види отвън.**

Проверено на живо: каталогът връщаше **нула реда** и за оттегления, и за новия
`payTo`. Тринайсетте стари реда ги нямаше. Тоест не бяхме „вписани със стар
адрес" — **не бяхме вписани изобщо**.

### Пътят работи, и е доказан

Сетълмент през фасилитатора на PayAI **създава ред**. Локална сонда уреди
`/api/v1/signal` и редът се появи за 45 секунди — с **новия** `payTo` и новата
цена $0.01. Оттегленият адрес остана на нула.

### Дефект 1: `resource` като низ не се индексира

Сондата пращаше `paymentRequirements["resource"]` като **обекта** на 402-ката.
Сървърът пращаше `resource.get("url")` — **низ**. Товарът и в двата случая носеше
обекта, значи единствената разлика бяха изискванията.

Осем клиентски сетълмента (stats, bot-status, sales, verify-seller, по два пъти)
не създадоха **нито един** ред.

**Поправка:** сървърът строи и двете форми, а `connectors._requirements_for()`
избира според фасилитатора — низ за CDP (спекът го иска така и CDP урежда така
от месеци), обект за този, който води каталог.

### Дефект 2: два наши ключа убиват индексирането

След поправка 1 редът пак не се появяваше. Изолирано на живо, в две стъпки:

1. Същият маршрут, уреден локално само с `accepts[0] + resource(обект)`,
   индексира `/api/stats` за 45 секунди. Значи променливата е в изискванията.
2. Сървърът праща същото плюс `description`, `mimeType`, `extra_name`,
   `extra_version`. Първите две са законни полета в схемата на PayAI; последните
   две са **наши**, добавени само за `precheck_payment_payload`. Изпращането на
   първите две и **скриването** на последните две индексира `/api/bot-status` за
   45 секунди.

**Поправка:** `_requirements_for()` ги маха на изход, вместо да ги премахва от
източника — локалната проверка продължава да ги чете.

**Цената беше тиха по конструкция:** фасилитаторът пак уреждаше, клиентът пак
виждаше tx hash, а ние просто никога не се появявахме в каталога, който агентите
търсят.

### Резултат

Вписани и потвърдени в каталога на PayAI с новия `payTo`:

```
/api/v1/signal      $0.01    20:30:57Z
/api/v1/whaleflow   $0.01    19:39:04Z
/api/stats          $0.005   20:04:57Z
/api/bot-status     $0.005   20:06:12Z
```

Оттегленият `payTo` — нула реда. Общо похарчено за всички опити: **~$0.30**,
всичко от нашето демо портфейлно към нашия собствен получател.

### Какво остава ОТКРИТО, и то честно

**`/api/sales` и `/api/v1/verify-seller` още не се листват.** Уредени са общо
шест пъти през истинския сървър, след като и двете поправки бяха живи, и не се
появиха. Прихванах точното тяло, което сървърът праща, и то **изглежда
правилно** — чисти изисквания, `resource` като обект, товар с `resource` и
`accepted`. Значи разликата между пътя на сондата (който листва) и пътя на
сървъра (който не) **не е в тялото**, или не е само в него.

Следващата стъпка, когато се върнем към това: временен лог на изходящото тяло в
живия сървър, за да се сравни байт по байт с това на сондата. Дотогава това е
отворено, не е поправено, и не бива да се представя за поправено.

`/api/arb/opportunities` също не е вписан — но там причината е **нашият
собствен guard**: отказва сетълмент с `no_opportunities_to_deliver`, докато
скенерът не е пускан, и не взема пари. Това е разменa, не дефект.


### 69а. Поправка на §69: и шестте маршрута са вписани (16.11.2026, по-късно)

§69 записа `/api/sales` и `/api/v1/verify-seller` като **открити**. Вече не са.
И двете се появиха в каталога, след като ги уредих по пътя на сондата, а не през
живия сървър:

```
/api/v1/signal        $0.01    19:30:57Z
/api/v1/whaleflow     $0.01    19:39:04Z
/api/stats            $0.005   20:04:57Z
/api/bot-status       $0.005   20:06:12Z
/api/sales            $0.005   20:32:12Z
/api/v1/verify-seller $0.05    20:42:37Z

оттегленият payTo      → 0 реда
```

**Всичките шест уреждаеми маршрута са вписани.** Седмият,
`/api/arb/opportunities`, е спрян от собствения ни guard — отказва с
`no_opportunities_to_deliver`, докато скенерът не е пускан, и не взема пари.

### Какво остава истински открито

**Сетълментите през живия сървър не опресняват реда.** Това е измерено, не
предположено: `/api/sales` е уреден шест пъти през сървъра и нито веднъж не се
появи; същият маршрут, уреден веднъж по пътя на сондата, се появи за 45 секунди.
Същото за `verify-seller`.

Диагностиката, която добавих за това (`X402_LOG_OUTBOUND=1`, един WARNING ред на
сетълмент с ключовете и формите, без подпис), **не хвана редовете**: за прозореца,
в който сетълментът е минал, Render върна 300 реда — 191 access, 108 INFO и
**точно 1 WARNING** — а транзакцията е на веригата с успешен статус. Тоест
сетълментът се случва, а фазите му не стигат до лог потока, който чета.

Затова следващата стъпка не е още един деплой, а **друг начин да се види
изходящото тяло** — например да се запише в базата или в отговора на самата
заявка, вместо в лога. Дотогава: редовете съществуват и са верни, но ще
остареят при следваща промяна на цена или адрес, защото нищо в нормалната
работа на сървъра не ги обновява.

**Диагностичният флаг остава вдигнат** (`X402_LOG_OUTBOUND=1` на Render), за да
е готов за следващата сесия. Кодът го чете само ако е точно `1`; по подразбиране
е изключен и тестът пази това.

## 70. `validate` показва обявата, преди да платим за нея (19.11.2026)

§69 остави открит въпрос: не виждаме изходящото тяло, затова не знаем какво
каталогът получава. Има по-прост отговор, отколкото заслужавахме.

**`POST https://api.cdp.coinbase.com/platform/v2/x402/validate` не иска API ключ
и връща повече от „валидно".** Връща `bazaarExtension` — обекта, който CDP
възнамерява да публикува за маршрута: `input.method`, `input.queryParams` и
`output.example`. Тоест **обявата, показана ни преди някой да е платил.**

Досега можехме да научим какво мисли каталогът за един маршрут само като
платим и после чакаме ред да се появи. На 16.11 това струваше реално време:
`/api/stats` беше уреден осем пъти в два кръга и не се появи, а причината
(`extra_name`/`extra_version` в изискванията) излезе с три изолирани сетълмента.
Едно `validate` обаждане щеше да покаже разликата с една заявка, безплатно.

### Инструментът

`scripts/validate_preview.py` — минава през платените маршрути, взема 402-та им
и пита CDP какво ще индексира. Сравнява нашата декларация с индексираното и
маркира `DIFF`, ако се разминават.

    python scripts/validate_preview.py            # 7-те платени маршрута
    python scripts/validate_preview.py --json     # машинно четимо
    python scripts/validate_preview.py /api/stats # един маршрут

Изходният код е 1 при отказ, за да може да върви в CI.

**Първото пускане, 19.11, срещу живия сървър: 7/7 минават, нула разминавания.**
`/api/v1/whaleflow` обявява `hours, limit`; `/api/v1/verify-seller` — `days,
receiver`. Останалите пет са без query параметри. Всички носят `output.example`.

### Второто нещо, което измерихме

**Непознат extension блок не е мястото, където CDP отказва.** Същите изисквания,
пуснати с добавено `extensions.moi-authority`, връщат 200. Това е различен клас
от дефекта на 16.11: тогава проблемът беше **непознат ключ в обекта на
изискванията**, който спря индексирането изцяло. `extensions` е безопасна
територия; `accepts[0]` не е.

### Какво това не е

`validate` не е `settle`. Той проверява, че изискванията са оформени правилно и
казва какво ще индексира — не доказва, че плащането ще мине. Използва се за
хващане на грешки в декларацията, не за прогноза за сетълмент. Откритият въпрос
от §69 (защо сетълментите през сървъра не опресняват реда) остава открит; това
само показва какво трябва да излезе, не какво излиза.

## 71. Готов запис за Evidence нишката в `#tsc-public` (19.11.2026)

Собственикът каза „да“. Записът е `docs/TSC_EVIDENCE_ENTRY.md` — едно съобщение,
на английски, за нишката на Martin Sansone в публичния канал на x402 TSC.
Собственикът даде и самата обява: нишката е обява за среща от 19.08.2026 („Evidence“,
26 август, 10:00–11:00 CST), а темата е картата на съществуващите 13+ предложения и
въпросът **нов extension или поправка в Signed Offers and Receipts #2811**. Затова
записът отваря с този въпрос и затваря с отговор по него: `settlement_pending` вече
е в v2 спецификацията, тоест липсва guidance и конформанс корпус, не още един
extension. Оформен е за директно поставяне в Slack: `*удебелено*`, голи URL адреси,
без markdown връзки и без заглавия — иначе текстът излиза суров. Мястото е в
**REPLIES** на обявата, не като ново съобщение в канала.

Носи три неща, по едно от двата края на веригата:

1. **Доставка.** `settlement_pending` е non-terminal: транзакцията е излъчена, но
   потвърждението не е установено. Ние четяхме `success: false` като отказ и
   губехме платили клиенти. Заедно с измереното от оператор на фасилитатор
   (~19 отказа в ~11.7k сетълмента, 9 реално минали) и трите препоръки: осиновяване
   на хеша, собствена проверка на веригата, сравнение **по код**, не по текст.
2. **Оферта.** `validate` връща `bazaarExtension` — обявата, показана преди
   плащане; CDP сам залепва `#toolName`; непознат ключ в `accepts[0]`
   (`extra_name`/`extra_version`) дава осем сетълмента без нито един ред.

   Отделно е отбелязано, че за **MCP** ресурси `validate` казва
   `returns_402` failed и `bazaarExtension: null` — същото и за вече листвани MCP
   ресурси. Ендпойнтът е HTTP-оформен и провалът му не значи нищо за MCP.
3. **Честните числа** (171 / $1.883; 122 / $1.685 собствени; 12 външни / $0.054).

Линковете сочат към публичното репо. Проверено на 19.11: репото е `public`,
клонът по подразбиране е `main`, трите цитирани файла вече са в него — тоест
връзките работят, без да е нужен нов push.

**Записът НЕ е публикуван.** Поставянето в канала е действие на собственика;
§7 изрично забранява push без изрично „да“. Комитнат е локално.

### Публикуван — 19.11.2026, 18:24

Пуснат е от `mitaka7210` като отговор в нишката на Martin Sansone. Slack е
рендирал `*удебеленото*` правилно; номерираният списък и тиретата са загубили
маркерите си — това е нормално за Slack, не дефект на записа.

Наблюдения от дъмпа на канала, които ни засягат:

1. Записът застана до работата на Pablo и Joe K по `agentoracle.co`: двама
   независими имплементатори затвориха „асиметрията“ с пълно преизчисляване на
   §4.3 върху истински подписан receipt. Нашият запис цитира точно този принцип
   („relying party recomputes rather than trusts“) — тонът попада в нормата.
2. **Страницата с екосистемата на фондацията е пенсионирана**, а PR-овете към нея
   се затварят без merge (PR #356 на Roberto Martins стои от 27.09). Roberto
   предлага регистър, индексиран по **измерено здраве**, не по PR-ревю; naxytra
   пита същото за живите продавачи. Това е нов, използваем извод по нашата тема
   от §66–67 и не е записан никъде другаде.
3. Roberto Martins публикува `/.well-known/honest-revenue.json` и казва направо, че
   „most listing volume out there is self-dealing“ — същото разделяне, което
   направихме в `docs/HONEST_REVENUE.md`.
4. Отворено в канала: `#4198` (прозорец на дублираното плащане), `tsc#17`
   (governance за WG/SIG), изоставената Java имплементация (Thomas Kammerlocher
   предлага да я вдигне до v2), 2.29.0 на Philippe d'Argent.

## 72. Регистърът по измерено здраве вече съществува — и ние сме в него (19.11.2026)

Собственикът каза „да“. Пълният отчет е `docs/REGISTRY_STATUS.md`; тук е същината.

**Въпросът** (от дъмпа на `#tsc-public`): страницата с екосистемата е пенсионирана,
PR-овете се затварят без merge, Roberto Martins предлага регистър, индексиран по
измерено здраве, а не по PR-ревю. Пита се къде днес може да се листва жив продавач.

**Отговорът: на осем места, и нито едно не иска PR.** Проверено на живо на 19.11:

| индекс | какво казва за нас |
|---|---|
| Official MCP Registry | 4 версии, `active`; последната е **6.2.0 от 04.11** |
| x402register.com | оценка **A, 90.7**, ранг 2668, наличност 100 %, медиана 576 ms |
| x402lint.dev | оценка **B, 89** — 17 pass, 4 warn, **2 fail**; сканирано 04.11 |
| x402-list.com | `payment_ready`, compliance **A 14/14**, но **endpoint_count 6** |
| Roundhouse | 10 реда; `concentrated: true`, `top_payer_share_30d 0.9581` |
| x402-trust.com | **A** на шест маршрута (80.9–82.2), claim 4/4 |
| Glama | часов import от официалния регистър, без ревю |
| Lumière / Akari / 402 Index / x402dash / PayAPI / Agentic.Market | регистрация или първи сетълмент |

### Трите извода

1. **Всеки индекс носи октомврийските ни числа, защото октомврийските са последните
   публикувани.** Официалният регистър държи 6.2.0 с **6 инструмента** и
   `$0.003–0.005`; същата версия в репото има **7 инструмента** и `$0.005–$0.050`
   (регенерирана 16.11, никога не е публикувана повторно; `build_registry_server_json.py
   --check` казва OK). Версиите там са неизменяеми — трябва **нова** версия.
   `x402-list` е същото на второ ниво: `endpoint_count 6`, `price_max 0.01` и текст
   `$0.003-0.005` — нашето собствено октомврийско подаване, върнато обратно.
   `Roundhouse` държи осем MCP реда под **пенсионирания** `0xd4cd…d08f`, един от тях
   с удвоения фрагмент.
2. **Трета страна вече публикува концентрацията ни.** Roundhouse дава
   `top_payer_share_30d 0.9581` и `concentrated: true` за whale-flow, а
   „потвърденият обем“ $1.719 е почти изцяло нашият собствен ключ. Това е проблемът
   със самоизмамата, машинно четим, на чужд индекс. Нашият отговор вече съществува:
   `/api/v1/settlement-classes`.
3. **Три наши файла подценяваха каталога — поправено днес.** `/.well-known/x402.json`
   казваше „the 6 live x402 endpoints“ над списък от **седем**; `/validation` —
   „six routes across two tiers“ до заглавие „7 live x402 routes“; `llms.txt` —
   „the same six paid routes“. И трите вече се **смятат** от таблицата с маршрути.

### Какво НЕ бива да се строи

Проучването провери дали някой индекс чете самопубликуван scorecard или файл за
честни приходи. **Никой не чете:** `/scorecard.json`, `/health`, `/receipts`,
`/.well-known/honest-revenue.json`. Идеята „да публикуваме scorecard, за да ни
индексират“ е мъртва в зародиш. Четените артефакти са тези, които вече сервираме.

`/.well-known/honest-revenue.json` остава разумен само като **човешка** конвенция —
тя е на Roberto, каналът я цени, и никой не я чете машинно. Това е причина да се
вдигне в работна група, не да се имплементира днес.

### Какво следва, по ред

1. **Да се публикува `server.json` като 6.3.0.** Иска свеж `mcp-publisher login
   github` (токенът в `~/.config/mcp-publisher` е изтекъл — има само
   `token.json.expired-backup`), после `publish`. Това е единственото действие,
   което оправя Glama и API Tracker наведнъж, и е блокирано на браузъра на
   собственика. Бинарният файл `_tools\mcp-publisher.exe` вече го няма — трябва да
   се изтегли отново (~20 MB).
2. Да се опресни подаването към `x402-list` — копието им е октомврийският ни текст.
3. Да се купи пре-сканиране на x402lint за $0.05, за да се видят 2-та fail и 4-те
   warn (безплатният кеш е по-стар от 24 ч и връща `no_fresh_report`).
4. Да се занесе отрицателният резултат в `#wg-domain-discovery`: никой индекс не чете
   самопубликуван файл за честни приходи, а ние вече имаме работещ пример.

**Какво това не променя:** вече сме индексирани и оценени. Нищо тук не е аргумент
да се плаща за позиция.

### Допълнение след третото проучване: x402-trust ни е свалил на B

Проверено на живо (не от нашата страница): **всичките седем платени маршрута вече
са оценка B** (76.8–78.7), `/mcp` е 65.4, `/api/v1/verify-seller` 69.4, а
**`/api/stats` носи `error` флаг и препоръка `avoid`**. Нито един платен маршрут не
е A. Техните измерени стойности за нас: uptime **97.6 %** (средното за A среза е
99.8 %), латентност **950 ms** с флаг „slow“, стабилна цена, 125 проби/30 дни.

Публикуваният им модел (от `trust/leaderboard` JSON) е
`0.45·technical-reliability + 0.30·spec-compliance + 0.25·economic-reputation`,
а technical-reliability е `0.45·uptime + 0.40·observed-age + 0.15·latency`. Четирите
компонента, които **ние** описваме на `/validation` („technical fit, transparency,
ecosystem presence, operational confidence“), не съществуват на техния сайт — тоест
цитираме чужда методика грешно на собствената си trust страница.

Две наши неща са сгрешени заради това:
1. `/validation` още публикува копие от **04.11 с оценка A** на шест маршрута.
   Страницата казва, че линковете са меродавни, но хората четат копието — и то вече
   ни ласкае.
2. Описанието на тяхната методика (горе) е невярно.

Освен това x402-trust още държи **четири реда `kristo-intelligence.vercel.app`,
оценка F, `delisted: false`** — пенсионираният хост е изчезнал от CDP (§66), но не
и оттук, и това е единствената F до името ни.

**Новият ред на действие:** първо $0.005 за техния report за `/api/stats` (най-евтиният
въпрос, който сме задавали — реален индекс казва „avoid“ за най-пробвания ни маршрут),
после поправка на `/validation`, после повторното публикуване като 6.3.0.

Отделно: `x402-list.com/best` и **Agent402** са още два индекса, в които вероятно ни
няма.

### Какво свършихме по този ред (19.11, вечерта)

**1. `/validation` — махнахме преписаните чужди оценки.** Страницата публикуваше
копие от 04.11 с оценка **A** на шест маршрута, докато живите оценки бяха **B**, и
описваше методиката на x402-trust с четири компонента, които не съществуват на
техния сайт. Сега: живата значка, линк към живите оценки, публикуваният модел
(`0.45·technical reliability + 0.30·spec compliance + 0.25·economic reputation`,
а technical reliability = `0.45·uptime + 0.40·observed age + 0.15·latency`) и
изречение, че не преписваме чужди движещи се измервания. Тестът, който
**изискваше** грешния четирикомпонентен модел, е пренаписан — той го правеше
постоянен. Махнати са и двете колони „probe status / last probe“ от таблицата с
цените, защото идваха от същия препис.

**2. `server.json` → 6.3.0.** Версията в официалния MCP регистър беше 6.2.0 от
04.11 с **6 инструмента** и `$0.003–0.005`; локалният файл от 16.11 има 7
инструмента и `$0.005–$0.050`. Версиите там са неизменяеми, значи трябва нова.
Вдигнахме `SERVICE_VERSION` и `build_registry_server_json.VERSION` на 6.3.0
(петте повърхности, които тестваме, се съгласяват), регенерирахме файла,
`mcp-publisher validate` казва **valid**, `publisher-provided` е **3907 байта** —
под лимита от 4096. Инструментът `mcp-publisher.exe` 1.8.9 е изтеглен наново в
`_tools`, sha256 съвпада с release-а. **Публикуването не е направено** — иска
`mcp-publisher login github` (device flow, собственикът).

**3. x402lint пре-сканиране — купено, $0.05.** `POST /v1/scan` през новия общ
инструмент `_forensics/pay_external_x402.py`. Резултат: **B, 84**, 17 pass /
3 warn / **3 fail**. Пълният подписан отговор е
`docs/x402lint_scan_2026-11-19.json`, tx `0x26c25f94…`. Трите FAIL-а са наши:

| проверка | какво иска |
|---|---|
| `P8 desc-length-cap` | 1 описание > 500 знака (`openapi` GET /api/v1/verify-seller = 603); CDP го реже |
| `S2 openapi-x402-scheme` | липсва `components.securitySchemes.x402` в OpenAPI |
| `S4 paid-ops-security-402` | 7 платени операции без `security` (sec=0), макар да имат `402` |

WARN-ове: `P5 head-no-settle` (HEAD с невалиден X-PAYMENT връща 401/503/400 вместо
402 или 405 — 503-ките заслужават поглед), `S6 well-known-x402` (x402lint търси
`endpoints[]`/`accepts[]`, ние даваме `resources[]` — може да се носи и двете),
`D5 x402-org-ecosystem` (не сме в `coinbase/x402` partners-data; PR = действие на
собственика). Двете SKIP-ове са тяхна нестабилност („directory unreachable“,
същото, което даваше и 500-ките).

**Забележка за инструмента:** тялото на POST заявка през PowerShell губи кавичките
си — затова `pay_external_x402.py` има `--body-file`. Тяхната точка връща 500
периодично и 402 в другия случай; скриптът вече прави до 8 опита.

**4 и 5 не са свършени:** `x402-list` има owner-update поток на
`/services/kristo-intelligence/update` с еднократно domain-доказателство (описан в
`/llms-full.txt`) — не е изпълнен; Agent402 ни обхожда от месеци (151 318 заявки в
нашите логове), но `POST /api/index/register` не е подаден.

### Купихме report-а — и причината за „avoid“ е нашата собствена смяна на получателя

`_forensics/pay_x402trust_stats.py` (пробен режим по подразбиране, `--send` за
плащане) плати $0.005 на 19.11. Резултатът:

    score 78.3  grade B  recommendation avoid  confidence 0.95
    subscores  technical-reliability 91.2 · spec-compliance 98.3 · economic-reputation 31.2
    breakdown  uptime 0.976 · compliance 0.976 · latency 0.674 · age 0.929
               · activity 0.417 · stability 1.000
    flags      provider-verified (info)
               payto-changed-recently (ERROR)
               shared-payto-wallet (warn)

> „payTo changed 2 day(s) ago (0xd4cdA900… → 0xB4FcF8ef…) — possible endpoint
> hijack; verify before paying.“

Тоест `avoid`-ът е **нашата собствена, умишлена смяна на получателя**, прочетена
като възможен отвличащ взлом. Флагът `shared-payto-wallet` пък казва, че портфейлът е
„споделен с 12 други endpoint-а“ — тези дванадесет са **нашите собствени** маршрути
зад един получател.

**Това не е дефект на продукта.** Това е наблюдавана промяна без обявено намерение и
изтича сама. Публикуваме я в `/.well-known/paycheck.json` — файл, който Lumière чете,
а x402-trust не.

Истински са само две подоценки: **latency 0.674** (969 ms средно от една европейска
точка, включително разстоянието до региона на Render — структурно) и **activity
0.417** (обем на ниво портфейл: $0.85 и 4 платеца за 30 дни, повечето нашият ключ —
това е истинският проблем с търсенето).

**Стандартът, който това разкрива:** законната смяна на ключ е неразличима от
отвличане за всеки индекс, който не чете обявление за смяна. Ние сервираме файла на
една конвенция; никой не го чете. Това е вторият аргумент за `#wg-domain-discovery`,
до факта, че никой индекс не чете и самопубликуван файл за честни приходи.

**По въпроса за x402-list и Agent402:** в x402-list **вече сме** (`payment_ready`,
compliance A 14/14); не сме `verified`, а този статус не се купува и не се подава —
появява се, когато ТЕ платят на наш маршрут и той достави. Agent402 — да, струва си
един безплатен `POST /api/index/register`; това е единственият намерен индекс с
`supports_x402` като филтър от първи клас. Нито едно от двете не е спешно.

## 73. Трите FAIL-а са затворени, Agent402 е регистриран, грантът е написан (20.11.2026)

### Трите FAIL-а — проверени в генерирания spec, не в обещанието

`8fe1ef3` (в кода) + `218f13a` (довършване в дървото). Проверката е през живия
маршрут `GET /openapi.json`, не чрез четене на файл:

    openapi 3.0.3
    securitySchemes keys: ['x402']
    paid ops: 7   without security: []   longest description: 346 chars

Тоест: `components.securitySchemes.x402` присъства; и седемте платени операции носят
`security`; нито едно описание не надхвърля 500 знака (най-дългото е 346, беше 603).
Описанието на `/api/v1/verify-seller` е съкратено, без да губи смисъла — загубеното
изречение за `partial` остава в `llms.txt` и в 402-та, където няма лимит.

**Броят на тестовете също беше счупен, и то тихо:** `/validation` и README твърдяха
1444, а пълният набор събира 1446. Двата теста, които пазят точно това
(`test_validation_page_states_the_real_suite_size`,
`test_readme_test_count_agrees_with_the_suite_and_with_validation`), паднаха в пълния
прогон и минаха сами — класическа разлика между „пълния набор“ и „този файл“.
Поправено на 1446 в трите места. Пълен набор след поправката: **1445 passed, 1
skipped** (1446 събрани).

### Agent402 — регистриран, и се оказа, че вече ни е индексирал

`POST /api/index/register` с `{"origin": "https://kristo-intelligence-api.onrender.com"}`
върна `200`:

    listed: true   toolCount: 29   paidToolCount: 26   routable: true   health: 1
    paywall: ok, 402 на /api/v1/signal
    reverify: 15 route(s) re-checked against their live 402 now

Не е ново листване — crawler-ът ни е обхождал и преди; това е препрочитане на
документите и ново проверяване на 15 маршрута. Безплатно, без акаунт, без ревю.

### x402-list — заявката е създадена, но описанието излезе смачкано

Потокът е `POST /api/v1/services/{slug}/request-update` → еднократен token →
публикуване на `/.well-known/x402list.txt` → `POST .../verify-ownership` → ръчно ревю.
Заявката мина: `201`, `request_id 5f198270-614d-42db-b4ef-913b8ee6`, token с валидност до
**2026-11-23T07:48:16Z**.

**Проблемът е мой, не техен.** Подадох описанието през PowerShell here-string с
двойни кавички, а `$5M` и `$0.005` се разшириха като (празни) променливи. В заявката
„USDC transfers >= $5M“ стана „USDC transfers >= )“. Втори опит с коригиран текст
(491 знака, записан във файл, без кавички) върна `429`: „One update request per
service per email is open at a time… until 2026-11-23T07:48:16.348Z“.

**Решението:** оставете заявката да изтече. На 23.11 се пуска наново чистата версия
(`_forensics/x402list_update.py`, записва отговора в
`_forensics/x402list_update_result.json`, така че token-ът се чете от файл, не се
преписва на ръка). Дотогава `endpoint_count` остава 6 — мониторът пак проверява
живата 402-та, така че това е метаданни, не изчезнал маршрут.

**Проверено за самия поток:** `GET /api/v1/services/kristo-intelligence` връща
`endpoint_count: 6`, `min_price_usd 0.005`, `price_max_usd 0.01` и описание, което
още казва `$0.003-0.005`. Седмият маршрут, който липсва, е `/api/v1/verify-seller`.

### Грантът на Sentient Foundation — документът е готов за поставяне

`docs/GRANT_SENTIENT_APPLICATION.md`. Формата е Typeform
`https://form.typeform.com/to/IRj7WaKH` („Sentient Foundation Open Source AGI Grant“),
програмата — $42M, два пътя (grant без equity и investment), rolling review без
кохорти. Документът отговаря поле по поле на реалните въпроси от формата, които
извадих от HTML-а ѝ, и оставя `[YOU]` само там, където фактът е само твой.

**Тезисът, който избрах:** проектът е втората половина на програмата — „infrastructure
that lets it be trusted“, не продукт за крайни хора. Двете измервания (нетерминален
`settlement_pending`; обявата, която се публикува, не е обявата, която е подписана) са
точно това. Искането е **$30 000 за 6 месеца** с три междинни резултата, плюс резервен
вариант $3 000 само за първия. Честните числа са вътре: 171 сетълмента, $1.883, от
които 122 и $1.685 са нашият собствен ключ; външни — 12 плащания, $0.054.

**Две неща, които документът казва без заобикалки:** сигналът няма измерен edge
(1.2% на историческите данни) и 89.5% от доларите са нашият собствен ключ
(Roundhouse независимо публикува `top_payer_share_30d 0.9581` за whale-flow). Ако
това не се каже в заявката, то ще се каже от ревюто.

## 74. Червеният CI на 8fe1ef3 не беше нашият код — беше CoinGecko (20.11.2026)

Run #84, „Test suite — Process completed with exit code 1“, 2m 28s, без нито един
тестов надпис в анотацията. Първото подозрение беше точното: трите FAIL-а, които
комитът уж затваря. Проверено и отхвърлено.

### Какво НЕ беше

В отделен worktree на `8fe1ef3`:

- `tests/test_x402lint_contract.py` → **9 passed** (включително
  `test_no_advertised_description_exceeds_the_500_character_cap`);
- `tests/test_visibility_seo.py` → **33 passed** (пазачът на броя тестове).

Тоест нито един от трите lint-а, нито броячът на тестове е паднал. Целият набор
на `8fe1ef3` обаче дава **1 failed, 1442 passed, 1 skipped** — и падналият е един:

```
tests/test_audit_fixes.py::test_a5_reverted_receipt_polls_then_overrides_to_delivery
assert [2, 2, 2, 2, ...5569804019209] == [2, 2, 2, 2]
Left contains one more item: 0.2615569804019209
```

### Причината

Тестът брои всички `time.sleep` в нишката на заявката и иска точно `[2, 2, 2, 2]`
— четирите 2-секундни poll-а на receipt-а. Но `/api/stats` в същата заявка стига и
до `services/market_data.py`, който при retryable отговор на CoinGecko спи
**bounded jittered backoff** в СЪЩАТА нишка: база 0.25 s + до 25 % → 0.25–0.31 s.
`0.2615569804019209` е точно `0.25 + uniform(0, 0.0625)`.

Локално CoinGecko отговаря (или кешът е топъл) и петият запис не се появява. В CI
— няма мрежа към CoinGecko или има 429 — появява се. Затова същият комит дава
червено на `8fe1ef3`, а `567eb6c` и `241d977` (които съдържат същите lint промени)
са зелени. **Пайплайнът съобщаваше наличността на външен API, не нашия код.**

### Поправката

1. `tests/conftest.py` — нова autouse фикстура `_no_market_data_retry_sleep`
   нулира `_COINGECKO_BACKOFF_BASE_SECONDS`, така че изчисленият delay е 0 и retry-ът
   не спи. Retry-ът и fallback-ът към stale данни остават; изчезва само паузата.
   Тестовете, които са ЗА backoff-а (`test_market_data_resilience.py`), си задават
   собствени стойности.
2. `tests/test_audit_fixes.py` — assertion-ът вече брои само 2-секундните poll-ове:
   `[s for s in sleeps if s == 2] == [2, 2, 2, 2]`. Твърдението е за receipt poll-а,
   не за всеки sleep по пътя на заявката.

### Което остава честно да се каже

`/api/stats` под pytest все още прави **реални** HTTP заявки към CoinGecko. Нулирахме
само паузата при retry, не самата заявка. Тоест наборът все още зависи от външен API
за времето си — по-бавно е и може да падне по причина, която не е наша. Това е
истинска крехкост и не е поправена тук; следващият, който я пипне, трябва да реши
дали да стъбне market data в conftest, или да я остави с ясна граница.

## 75. Грантът е подаден (20.11.2026, 18:06)

Собственикът попълни формата и натисна Submit. Потвърждението дойде на
`hristovdimitri2@gmail.com` от Typeform Notifications в 18:06 — това е единственият
запис за подаването. Страницата „благодарим“ не показва номер; единственият
идентификатор е в дъното на имейла: `wmgl5fscw4opng2m5l6twgwmgl5fewx0`.

**Какво е подадено:** grant track, искане **25k** (опциите са 10k/25k/50k/>50k —
25k е най-близкото до шестмесечния обхват), прикачен документ
`docs/GRANT_ONE_PAGER.pdf` (2 страници, 107 748 байта, генериран от HTML-а с headless
Chrome; комит `e52b194`).

**Клонът „Grant“ се оказа 7 екрана.** Логиката на самата форма скача на „благодарим“
веднага след прикачването — няма въпроси за екип, за traction, за приходи, за рунд, за
видео и няма чекбокс за условия. Затова цялото доказателство за екипа и числата
пътува в PDF-а, не във формата. Формата не пита и за платежна сметка — само имейл.

**Четирите отговора, които носеха тежестта:** проблемът и защо сега (нетерминален
`settlement_pending` + обявата, която се публикува, не е подписаната); кого помага;
какво е отворено и какво би се загубило; какво отключва грантът (пет резултата по
месеци, conformance наборът пръв).

**Какво следва:** имейл, ако проектът е предселектиран. Срок не е даден — прегледът е
rolling, без кохорти. Ако поискат и четирите подкрепи извън парите (distribution,
compute credits, engineering, community), искането вече е написано в
`docs/GRANT_SENTIENT_APPLICATION.md`, раздел 7.

**Честната оценка, записана за да не се преписва по-късно:** не сме идеалният
кандидат. Програмата иска две неща — продукти за хората, които пазарът е подминал, и
инфраструктурата, която ги прави проверими. Ние сме второто. Заявката го казва
направо и не се преструва на друго; искането е залог за conformance работата, не за
приходите на endpoint-а. Дали ще мине — решава панелът.

## 76. PayAPI Market: картата е вързана към стария портфейл (20.11.2026)

Chet Parker (PayAPI Market) отговори на писмото от 16.11 за смяната на получателя.
Отговорът му, дословно по същество:

> „The live listing for Kristo Seller Audit was verified against the old payTo
> 0xd4cdA900…d08f. … A change of receiver does not auto-update the badge. To re-verify
> on the new address … please update the form row at https://payapi.market/list with the
> new wallet and the same paid route, then we can run one new canary. **Do not create a
> second card from email. One product, one card.**“

**Проверено на живо, за да се знае какво точно е остаряло** (картата
`/agent-marketplace/kristo-seller-audit-verify-an-x402-seller-before-you-pay`):

| какво показва картата | какво казва живият ни 402 |
|---|---|
| примерен вход с `receiver=0xd4cdA900…d08f` (стария) | — |
| цена **0.01** USDC | `amount: 50000` = **0.05** USDC |
| портфейл от стария canary | `payTo: 0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844` |

Тоест картата лъже за цената с 5×. Ако canary-то плати обявеното 0.01, нашият 402
иска 0.05 и проверката на сумата връща 401 — canary-то ще падне по причина, която
изглежда като наш дефект. Затова при обновяването **цената също трябва да стане 0.05**,
а примерният вход да не сочи мъртвия портфейл.

**Действието е на собственика** (иска вход с имейл): същият имейл
`hristovdimitri2@gmail.com`, същият маршрут
`https://kristo-intelligence-api.onrender.com/api/v1/verify-seller`, новият портфейл
`0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844`. Формата чете портфейла от 402-та сама,
така че повторното подаване на същия маршрут трябва да оправи и трите неща.

**Едно уточнение за парите:** canary плащането на PayAPI ($0.01) стои в стария
портфейл заедно с останалите $1.033. Ключът му никога не е намерен (§32, §33, §65) —
парите са невъзстановими и не си струва да се гонят.

### Какво има в dashboard-а (видяно 20.11)

Собственикът влезе в provider dashboard-а. Три неща, които не се знаеха:

1. **Портфейлът е на ниво ПРОВАЙДЪР, не на карта.** Полето „Wallet address“ стои над
   списъка и в момента сочи стария `0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f`. Това
   е редът, който Chet иска да се обнови — едно поле, не три карти.
2. **Живата API карта е остаряла много по-зле от агентската.** Публичната ѝ страница
   (`/api/kristo-intelligence-defi-signals-api`) казва: „Pay-per-call **from $0.003**“,
   „**$0.003 to $0.005** USDC/request“, „3 endpoints / 4 tools“, 3 верифицирани
   маршрута (`/api/stats`, `/api/v1/signal`, `/api/v1/whaleflow`), последна проверка
   **21.09**. Реалното днес: **7 маршрута**, **$0.005–$0.050**, 7 MCP инструмента.
   Тоест картата обявява цена под реалната — същият дефект, който затваряхме в
   `config.py`.
3. **6893 показвания за 7 дни** (agent search 6314 · agent get 578 · marketplace grid 1).
   Това е най-голямото число за видимост, което проектът е измервал, и то е от
   agent-facing търсене, не от хора. Показвания, не обаждания и не плащания — но
   доказва, че агентският трафик до нас съществува. Заедно с $0.054 външни приходи
   това е още едно доказателство, че тясното място не е откриваемостта.

Две карти стоят `rejected` („AI Gateway“, „AI Agents“) — дубликати, не са живи.

**Правилото „един продукт, една карта“ остава:** обновява се съществуващото, не се
създава ново.

### Dashboard-ът е само за четене — затова питаме Chet (20.11)

Собственикът опита да смени портфейла и да оправи цената. Не може: полето
„Wallet address“ на ниво провайдър **няма Edit**, а картата в таба „Agents“ също няма
контрола за редакция. Това е логично — `/list` казва „We read the 402 and fill the
wallet“, тоест PayAPI сам попълва портфейла и цената от нашата 402-та, а таблото само
показва какво е прочело при последната проверка.

Тоест „обнови form row-а“ от писмото на Chet не е поле, което се пипа, а повторно
прочитане. Път за повторно прочитане от наша страна не намерихме (формите са
JS-рендирани и не показват update поток за вече листван маршрут), затова му пишем с
конкретните стойности и питаме кой е контролът — той отговаря в рамките на часове и
сам предложи да съдейства.

**Състоянието на агентската карта, както го показва таблото:** „Live · Paid and
delivered“, последна проверка „Paid canary passed“ — 0.01 USDC canary → стария payTo,
tx `0x2541c190…6f42`, блок 58140667, status 1, 08:41:49 Europe/London, с бележка „HTTP
200 genuine on-chain audit, coverage complete, canary wallet is the sole external
payer. 425 settlement_in_flight first; same-tx X-Payment-Proof fetch, no second
payment.“ Тоест badge-ът е истински и е вързан за стария адрес. „Checks are not running
yet“ — периодичните проверки още не вървят.

### Подадено наново през `/list` — чака платената им проверка (20.11)

Направихме точно каквото Chet поиска: същият имейл, същият маршрут, през формата
`https://payapi.market/list`. Формата прочете нашата 402-та и показа собствения си
ред:

    https://kristo-intelligence-api.onrender.com/api/v1/verify-seller
    HTTP 402, $0.05 USDC, payTo 0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844

Тоест **цената и портфейлът се оправят сами**, щом маршрутът мине през формата —
таблото не се редактира, защото PayAPI чете от 402-та. Отговорът на Submit:

> „Submitted. Your listing stays pending and goes live once our paid check passes (we
> pay one call, cap $0.10). … We review your listing within 24 hours. We will pay this
> exact URL once, up to $0.10. The badge is for the JSON that comes back after pay, not
> for the 402.“

**Какво да се гледа, когато дойде имейлът:** ако кажат „live“, тогава за същия маршрут
ще има **две** обяви — старата агентска карта (цена $0.01, стар портфейл) и новата.
Формата предупреждава, че връща „a second listing that is the same product or a
sub-path of one already live“, така че е възможно и отказ. И в двата случая следващият
ход е един и същ: казваме на Chet какво е станало и искаме старата карта да се
обнови или махне, вместо да стоят две.

**Цената на canary-то не ни струва нищо:** $0.05 е под техния таван от $0.10, те
плащат. Примерният вход, който изпратиха, беше с адрес-пълнеж; нашият маршрут връща
валиден отчет и за адрес без активност (`ok: read != "failed"`,
`services/seller_audit.py`), така че проверката минава и така.

## 77. CI падна втори път и не можахме да прочетем защо (20.11.2026)

Run-ът на `179e738` (шестте комита от днес) даде `Test suite — exit code 1`, пак без
нито един тестов надпис. Разследването:

- **Локално наборът минава** на същия комит: 1445 passed, 1 skipped, 9m42s.
- **Логът на CI не се чете без admin права.** `GET /actions/jobs/{id}/logs` връща
  `403 Must have admin rights to Repository`. Тоест от публичния API, с който
  работим, причината за провала е невидима — вижда се само „exit code 1“.
- **Разликата между зеления и червения run е само документация.** `b2c819a` (с
  поправката на CoinGecko flake-а) мина за 118 s; `179e738` (само docs + PDF) падна
  за 122 s. Продължителността е почти еднаква, значи наборът е извървян докрай и
  един тест е паднал — не е срив при колекцията.
- **Не е PDF-ът и не са документите:** никой тест не чете `docs/`, нито търси из
  репото; проверено с търсене за `rglob`, `os.walk`, `REPO_ROOT` и `docs/` в
  `tests/`. `test_secret_hygiene.py` чете пет конкретни файла, `test_row_access_sweep.py`
  — списък с Python файлове.

**Поправено е другото, което пречеше:** `.github/workflows/ci.yml` вече tee-ва
изхода на pytest във файл, обръща всеки `FAILED`/`ERROR` ред в GitHub анотация
(`::error::`) и качва лога като артефакт. Анотациите се четат от публичния API без
admin права — тоест следващият провал ще каже името на теста, вместо да го оставя за
гадаене. `set -o pipefail` е задължителен там, иначе `tee` връща 0 и паднал набор
изглежда зелен.

**Какво остава открито:** кой тест е паднал на `179e738`. Двете хипотези са (а)
интермитентен flake в CI средата, който локално не се проявява, или (б) нещо, което
зависи от средата на runner-а (мрежа към CoinGecko, часова зона, липса на `.env`).
Следващият червен run ще го назове.

**Заключено: беше flake.** Следващият push (`3f5c14b`) мина зелен, а кодът между
двата run-а е само документация — `179e738` съдържа docs + PDF, нищо изпълнимо.
Зеленият ред е `b2c819a` (успех) → `179e738` (провал) → `3f5c14b` (успех), като
първият и третият имат същия тестов код. Тоест pipeline-ът е интермитентно нестабилен
и нито едно от двете червени не е било наш дефект. Поправката на CI-я остава полезна
точно затова: следващият път няма да гадаем.

**Новите стъпки се провериха на зеления run:** „Annotate failed tests“ = skipped (както
е замислено, върви само при провал), „Upload the suite output“ = success.

## 78. PayAPI блокира обявата: регистрираният портфейл е старият (20.11.2026, 18:28)

Отговорът дойде по имейл и е най-полезното нещо от цялата нишка — тяхната
автоматична проверка сама е открила несъответствието:

> „The challenge pays to 0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844, which does not
> match the registered wallet (0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f). Funds would
> be sent to a different address.“

Тоест обявата **не е минала към ревю**, защото регистрираният на ниво провайдър
портфейл още е старият, а новият 402 плаща на новия. Chet казва и изхода: „If you
believe this is an error, reply and a member of staff will review it.“

**Това затваря кръга по въпроса защо „обнови form row-а“ не проработи:** полето
„Wallet address“ е само за четене, PayAPI го сравнява с 402-та, а ние не можем да го
променим от таблото. Единственият път е човек от тяхна страна.

**Капанът, който не бива да се задейства:** да върнем получателя на стария адрес, за
да съвпадне с регистрирания. Ключът на `0xd4cd…d08f` никога не е намерен (§32, §33,
§65) — парите там са невъзстановими. Проверката е права и се оправя от тях, не чрез
връщане назад.

**Изпратено:** отговор до Chet с искането да обнови портфейла на провайдъра на
`0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844`, с изричното предупреждение да не се
предлага връщане към стария адрес, и с бележката, че същата причина държи остарели
още две обяви (API картата с „from $0.003“ и агентската карта с $0.01).

## 79. `server.json` 6.3.0 е публикуван в официалния MCP регистър (20.11.2026)

Публикуван в **17:38:42Z** (19:38 Sofia). Проверено от самия регистър, не от нашия
файл:

    name    : io.github.hristovdimitri2-hub/kristo-intelligence
    version : 6.3.0   status: active   isLatest: true
    tools   : 7
      get_market_stats /api/stats 0.005 · get_onchain_sales /api/sales 0.005
      get_bot_status /api/bot-status 0.005 · get_trading_signal /api/v1/signal 0.01
      get_whale_flow /api/v1/whaleflow 0.01 · get_arbitrage_opportunities
      /api/arb/opportunities 0.005 · verify_seller_receiver /api/v1/verify-seller 0.05
    pricing : min 0.005, max 0.05, USDC, Base
    remotes : /mcp, /mcp/sse

Досега регистърът държеше **6.2.0 от 04.11 с шест инструмента и `$0.003–0.005`** —
тоест всеки, който ни е търсил там, е виждал стар продукт на стара цена. Версиите
са неизменяеми, затова се наложи нова версия, а не редакция. Glama поема записа на
часовия си цикъл, API Tracker — също.

### Капанът на Windows, който изяде два device кода

`mcp-publisher login github` **автентикира успешно** и после пада с:

    Error: failed to save token: open C:\Users\AlienWare\.config\mcp-publisher\token.json:
    Access is denied

При това PowerShell **може** да пише в същата папка, а самият binary **може** да пише
файлове (проверено с `mcp-publisher init` — създаде `server.json` в работната папка).
Тоест блокиран е точно този път, не инструментът.

**Решението:** пренасочване на home директорията само за процеса —

    $env:USERPROFILE='...\_tools\home'; $env:HOME=$env:USERPROFILE
    mcp-publisher login github      # и после publish, със същия redirect

Токенът отива в `_tools\home\.config\mcp-publisher\token.json`, извън репото (не се
комитва). Третият код мина. Първите два бяха изгубени заради това — не заради GitHub.

**Ако някой някога пак публикува:** първо този redirect, после login. Иначе се губи
код напразно.

## 80. Абдела провери едно наше число и то не издържа (20.11.2026)

В `#tsc-public`, под записа ни за Evidence нишката, Abdellah (github.com/holistis)
отговори, че е проверил едно число. Проверих го и аз, със същия метод (шест
неавтентикирани GET-а по 100 реда към discovery endpoint-а, броене на `#` във всеки
resource):

| | редове | един фрагмент | два фрагмента |
|---|---:|---:|---:|
| каквото пишехме | 541 | **534** | 7 |
| измерено днес, 20.11 | **542** | **190** | **352** |

Числото не се възпроизвежда. **Поправено е в три файла:** `docs/INDEXING_WRITEUP.md`
(публикуваният текст, Finding 4), коментар в `app/blueprints/discovery.py` и коментар
в `tests/test_mcp_streamable.py`. Навсякъде пише и кой го е хванал.

**Какво добавя същият преглед, защото променя смисъла на съотношението:**

- **279 от 352-та реда с два фрагмента са на един хост** (`tanod.dev`, последно
  обновени 4–5 ноември). Без него: 73 от 263 реда са удвоени. Тоест „повечето редове
  са удвоени“ всъщност е „един голям продавач декларира фрагмента“.
- **Нашият хост вече носи и двете форми едновременно** — седем удвоени реда
  (сетълнати на 10.11, декларирали фрагмента) и седем единични (сетълнати на 17.11,
  декларирали голия URL). Същите седем инструмента, каталогизирани два пъти под две
  самоличности. Това е по-силното доказателство от всяко съотношение: коя самоличност
  получава един инструмент зависи от това какво е декларирал продавачът в момента на
  сетълмента.

**Офертата му:** нашите `settlement_pending` случаи да станат known-answer вектори, с
кредит към нас, и ще каже тук преди да публикува каквото и да е. Тестовете са
`test_settlement_pending_is_adopted_not_treated_as_a_failure` и
`test_settlement_pending_matching_is_on_the_code_not_the_message` в
`tests/test_connectors.py`, а имплементацията, която приковават, е
`_adopt_settlement_pending` в `services/connectors.py`.

**Едно предупреждение, което трябва да пътува с векторите:** при нас „осинови хеша“ не
се отделя от „провери веригата сам“ — кодът проверява трансфера към нашия `payTo`
преди доставка. Вектор, който твърди само че хешът е осиновен, ще мине и срещу
имплементация, която после доставя без проверка.

**Отговорът е изпратен** в `#tsc-public` на 20.11.2026: числото е признато за грешно,
казано е какво е измерено днес, добавен е изводът, който не бяхме видели (нашият хост
носи и двете форми едновременно), и е приета офертата за векторите с кредит към нас.
Чакаме неговото потвърждение преди да публикува нещо.

**Защо това е добре за записа, а не лошо:** поправката е публична, направена от нас, в
същата нишка, в която твърдяхме „evidence should be checkable“. Числото, което не
издържа, е нашето — а не сме го защитили, а сме го сменили. Ако някой някога провери
дали записът ни за Evidence нишката е надежден, това е доказателството.

## 81. Отговорихме в двете нишки, които радарът посочи (21.11.2026, 09:11)

Докладът на радара от 20.11 19:53 даде две приложими нишки. Отговорихме и в двете, от
`hristovdimitri2-hub`, като коментар — не като нов issue:

| нишка | какво казахме | какво искахме |
|---|---|---|
| `Merit-Systems/help-us#18` | измерения обем на `api.agentsearchhq.com` от CDP каталога | да ни индексират в AgentCash search |
| `VibeMirror-coder/n8n-nodes-omnidome#3` | същото за `humanmirror.fr` + две възпроизводими поправки | място в commons-а |

**Числата са премерени наново на 21.11, не цитирани от радара.** Целият каталог е
**39 134** реда (526 от тях `type=mcp`); четенето е с пагинация по 1000 и сумиране на
`quality.l30DaysTotalCalls` / `l30DaysUniquePayers` по хост:

| хост | редове | обаждания 30д | платци (сума по редове) |
|---|---:|---:|---:|
| `api.agentsearchhq.com` | 6 | **372** | 22 |
| `kristo-intelligence-api.onrender.com` | 26 | 99 | 34 |
| `api-production-24833.up.railway.app` | 18 | 65 | 12 |
| `api.aarn.space` | 2 | 46 | 12 |
| `brain.usebrainchain.com` | 2 | 19 | 5 |
| `humanmirror.fr` | 3 | 12 | 9 |
| `cryptopulseapi.com` | 2 | 6 | 5 |

**Радарът цитира свои записи, не живо четене** — за същите хостове дава 340/32/35/13/3
обаждания, докато живото четене дава 372/65/46/12/6. Разликата е в датата на четене
(радарът пази числото от момента, в който е видял нишката). Затова в публичен коментар
се цитира само живото четене, с дата.

**„Платци“ е сума по редове, не уникални хора** — една и съща адресна книга може да
плати по два маршрута и се брои два пъти. Затова „11 платци на extract“ е долна граница,
не тотал. Това е записано и в самия коментар, за да не се цитира като уникални.

**Едно задължение, което поехме:** коментарът в #3 казва „I'm in“ — тоест регистрация в
`humanmirror.fr/api/omnidome/registrar/` (POST с име на агент и capabilities, връща
`agent_id` + `api_key`, без портфейл). Ключът се пази локално и не се показва в нишката.
Регистрацията е доброволна и още не е направена.

**Страничен ефект:** коментарът в #3 реферира `#18`, затова GitHub създаде „mentioned
this“ запис в #18. Двете нишки вече са свързани и всяко бъдещо движение се вижда и в
двете.

**Очакване, честно:** `help-us` има 12 отворени заявки, повечето с нула коментара —
отговор там е малко вероятен. `omnidome#3` е собствената покана на оператора, значи
отговор е вероятен.

## 82. r/x402 не е канал за продажби — измерено на чужд пост (21.11.2026)

Собственикът препрати пост в `r/x402` от `u/Mental-Past-2104` за **AutoTuneMPC**
(MPC solver + Optuna tuning, $0.02 / $1.50 / $2.00, „indexed on Coinbase Bazaar“).
Проверих твърдението „indexed“ в каталога, защото то е проверимо:

| | |
|---|---|
| редове в CDP каталога | **3** (`/v1/solve`, `/v1/autotune`, `/v1/templates/autotune`) |
| обаждания за 30 дни | **5** |
| платци (сума по редове) | 3, по 1 на ред — вероятно **един** човек, който е и продавачът |

Тоест пост с 4 гласа, обявен като индексиран, дава **5 обаждания за месец**. Нашият
хост в същия каталог има 99. Каналът не носи обем — носи само публика. `r/x402` има
263 седмични посетители и 84 седмични приноса; това е общността на стандарта, не
пазарът.

**Едното число от поста, което си струва да се запише:** продавачът казва, че повечето
x402 клиенти имат **таван по подразбиране $1.00 на обаждане**, и че двата му скъпи
маршрута ($1.50 и $2.00) изискват вдигане на тавана до ~$2.50. Твърдението е негово,
непроверено — но е правдоподобно и обяснява защо цени над $1 са трудни за продажба:
клиентът отказва преди да е видял офертата. Нашите $0.005–$0.05 са 20–200 пъти под
тавана, тоест той не ни е ограничението. Ограничението си остава търсенето.

**Два модела, които не копираме сега:** безплатен `/v1/validate` (хваща лош вход преди
плащане) и $29 предплатен ключ за хора. Първото е разумно, но ние нямаме измерени
провалени платени обаждания, за да го оправдаем; второто е човешки заобиколен път към
x402 и при $0.054 външни приходи е преждевременно.
