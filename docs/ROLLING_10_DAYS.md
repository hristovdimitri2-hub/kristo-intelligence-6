# The rolling ten days

**Purpose.** The owner starts unrelated tasks, one after another. This file exists
so the answer to "where are we" never depends on anyone's memory: it always holds
the last ten days, what is still hanging in the air, and what happens next.

**Rule for whoever edits it:** the window moves. When a day is added, the oldest
day leaves. Curated prose is expected here; the factual base is reproducible with
`python scripts/rolling_10_days.py`, which prints the commits grouped by day.

**Window: 16.11.2026 – 26.11.2026** (174 commits).

---

## What shipped, oldest first

### 16 Nov — the payment path itself

Rotated the fee receiver, because the old one had no key anybody could find. Fixed
CORS advertising POST on routes that answer only GET. Created and funded a
dedicated gas wallet (0.00243575 ETH on Base, verified on chain). Fixed two PayAI
catalogue defects with real money behind them: the facilitator was being sent two
of our own keys that silently unlisted every settlement, and the `resource` had to
be sent in the shape the index keys by. Raised three underpriced routes. Added
`depth-shortfall waits a second before refusing`. Wrote `docs/INDEX.md`: a map of
all 81 documents, with the stale-copy check as its first task.

### 17 Nov — what indexing actually requires

Recorded that nothing in the declarations reliably gets an endpoint indexed.
Declared the bare `/mcp` endpoint (the catalogue appends the tool name itself).
Stopped reading an API 404 as "this listing does not exist" — a different thing
entirely. Gave the GitLab runner `node`, so nine tests stopped silently skipping.

### 18 Nov — measuring the buyers, not the supply

Measured the signal engine's own edge: **1.2% is not a threshold artefact**.
Measured buyers rather than listings: **eight wallets holding $131 spent five
cents.** Moved the shop window to lead with the seller check instead of the
signal. Corrected the Glama record's date.

### 19 Nov — paid audits read, kill criterion adopted

Bought the x402lint scan and took the typed grades out of `/validation`; bumped to
6.3.0. Read x402-trust's paid report: the "avoid" on `/api/stats` was our own key
rotation, not a defect. Stated plainly that **89.5% of recorded revenue is our own
money**. Adopted a **kill criterion**. Drafted the Evidence-thread entry for the
x402 TSC channel, and previewed the Bazaar listing before paying for it.

### 20 Nov — registry published, our own figure corrected

Published `server.json` 6.3.0 to the official MCP Registry. **Corrected our own
published MCP fragment count** after Abdellah re-counted it — a public correction
of a number we had put our name to. Assembled the grant submission pack. Diagnosed
PayAPI: the card is bound to the retired wallet and misprices us at 0.01.

### 21 Nov — what a forum post actually yields

Ran the first OmniDome boost. Registered the agent there as promised in the
thread. **Measured what an r/x402 post yields: five calls a month, one payer.**
Replied in both radar threads with measured volumes and two reproductions.

### 22 Nov — fixtures for third parties

Published OmniDome fixture 1 as a runnable artifact: `settlement_pending`
acceptance plus chain-before-delivery. Held `settlement_pending` with no readable
receipt as 425 rather than fail-open — then reverted, and decided to wait for
Abdellah's vector format. PayAPI still advertised the retired wallet.

### 23 Nov — registry verified, discovery evidence posted

Published 6.3.1 to the MCP Registry and verified it against the registry API.
Glama's TDQS breakdown showed two tools overlapping on wallet state; disambiguated
them. Fixture 1 revision history, fixture 2 on catalogue identity and the silently
voided `accepts` key. **Posted the payTo-rotation evidence to the domain-discovery
working group.** Google began showing the site: all eleven sitemap URLs 200.
Removed `requirements.lock`, a hand-maintained lock the deploy never installed.

### 24 Nov — the market audit, and the decision that followed

**The audit (§118):** 1,246,641 requests in 30 days, **457 distinct agents reached
a paywall**, 163 delivered, 25 directories probing us daily, all routes answering
valid `402`. Lifetime: 180 payments / $1.983 — of which **$1.785 is our own demo
key. Genuinely external: 12 payments, $0.054, 9 wallets.** Every one of the 135
recorded attempts is accounted for.

**The decision:** sell the measurement, not the feeds. The demand census was
published as the free specimen. All 95 markdown files were translated into English
and the English-only rule got a CI gate with one named exemption. One consolidated
board replaced the 03.11 one, with five messages ready and their destinations
verified. §113–115: the Glama badge, CoinMarketCap selling the same market data at
$0.01, and **the missing channel is a marketplace, not a seventh catalogue**. A
zero-dependency Python client (14 tests).

### 25 Nov — the measurement became products, and the honesty reached the surfaces

- **Census route live at $0.25** (`/api/v1/demand-census`), free sample, paywall-only.
- Canonical EIP-55 checksum fixed across six files; no money was ever at risk.
- **The signal's own measured record now travels with the signal** (`track_record`),
  built by the same code as the public page, fail-open, cached — plus six tests.
- The record was added to the 402 challenge, the vitrine, `README`, and the MCP
  tool list; the archive baseline started, because a month not snapshotted is gone.
- **The MCP surface was fixed at its source**: the honest sentence had been written
  into a *generated* file whose source was never edited, so `/mcp` still sold the
  signal without its record. Two guards added; suite 1479 → 1481.
- **The MCP Bazaar row was refreshed** with a real $0.01 call (tx `0xbb454d92…`)
  after the log explained that two "failures" were the unready guard refusing
  before settlement, not a payment defect.
- Messages sent: §N to Ernest, §O to Script Master Labs (HIVE402). Ernest replied
  by pricing our own demand-side measurement back to us ($25 one-off / $15 a
  month); §R declined it and named the boundary — repeat rate, paying-wallet share
  and revenue per agent are not observable from outside a service — while keeping
  the useful half: **the buyer of a demand-side ledger is the seller.** His free
  benchmark then arrived; §S checked it — the route table and prices are exact,
  but the call counts are our own test traffic (**131 of 180 lifetime payments are
  our own key**), which is the same blindness every index has, his included. §T
  then measured the per-path split against production: **his counts are not
  reproducible under any window, but his conclusion is right** — `verify-seller` is
  the one route with calls that are not ours (4 of 19, `$0.04` of `$0.95`), so the
  §L2 decision to drop it is reversed. §U corrected the introduction we do not have
  (**5 CRM leads, zero customer checkouts**) and asked him to name his share: the
  product shape — *the buyer of demand-side measurement is the seller* — is now
  confirmed three times in one week. He then reported that `/mcp` fails the 402
  preflight; §V measured it with **Coinbase's own validator**: the tool result was
  already conformant, his proposed fix would have broken the documented MCP
  transport, and the real defect was that **GET /mcp served a free document on a
  payable URL**. Fixed and re-validated: **25 of 25 checks pass** (was 1 fail and
  24 skipped), `POST` untouched, the document still free at `/mcp.json`, suite
  **1481 → 1486**. He offered the fix as a `$15` change-sheet; the fix took less
  time than the emails.
- **And then the correction that matters more than any of it:** every reply to
  Ernest between 24.11 19:52Z and 25.11 was **undelivered**. The address in this
  repo rejects mail (`554 5.7.1 … does not exist`); he writes from
  `ernest-earnordie@agentmail.to`. Seven bounces, five of them whole replies —
  including the one that reversed our verify-seller decision. Found by reading the
  mailbox back over IMAP, not by assuming. `send_draft.py` now refuses a dead
  recipient; §W is the consolidated resend and no new bounce came back.
- **Our own reader of his vector set, which he offered a column for, found a
  defect in our own artifact** (§130): three vectors where our logic refused a
  payment that had landed, because the fixture treated *"authorization already
  used"* as terminal while production recovers it by nonce. His adapter had been
  hiding it by synthesising a pending response. Fixed to **v5** (`ccdfea67…`,
  11 → 13 tests), and our reader — run from the gist's own bytes — now returns
  **22 / 14 / 0 / 5** without their translation.
- **Ernest conceded `/mcp` and sent the price-band correction; it dissolved under
  measurement.** The three inputs he sells are public (`quality.l30DaysTotalCalls`,
  `l30DaysUniquePayers`, `accepts[0].amount`), so the table was rebuilt over the
  **whole listing — 88,074 rows** — and then grouped by host: **`$0.02` alone is
  59.6% of every call in the listing, 81.7% of it one host on one route**, and the
  sub-cent band is **one operator holding 44,507 of its 46,845 routes**. No band is
  a market, so **no price move is justified in either direction**. The listing also
  publishes 26 rows for our host, always *lower* than our ledger and never higher
  (§131).
- **Assessed the x402 Foundation** (Digital Garage joined): membership is $25,000
  and up, the free tier is academic-only, but working groups and the spec repo are
  open — and **"sell judgement" was found to be crowded, with nine vendors already
  listed**. Recorded Explee as an outbound-lead tool whose API would cost ≈$5 to
  reach every x402 member company's decision-makers.
- **Measured whether x402 discovery tells the truth** (`docs/DISCOVERY_TRUTH.md`):
  87,419 rows, median row 5.95 days stale, **1 listing in 20 cannot be bought
  from**, **0 of 10,000 rows carry a call method** (so a naive GET reaches 60%),
  14.7% misdescribe the product and one overquotes by **15×**. Our own first
  number (21.5% unreachable) was our probe's error and is published corrected to
  5.0%.
- **Reproduced Abdellah's cross-run instead of trusting its number.** His frozen
  draft-3 vector set (`94b07672bfd9…`) through **his own adapter, unmodified**,
  against our fixture revision `3d76d803…`: 22 same, 14 allowed differences, 0
  outside — and the output is byte-identical to the one his repository recorded,
  except the line that echoes the filename. Published as `CROSS_RUN_RESULT.md` in
  the same gist, with the artifact's bytes unmoved. The fingerprint had been read
  in §95 as an unreadable private-gist address; it is the SHA-256 of the vector
  set itself.
- **He then listed our own reading as a second row, and two sentences in it could
  not be read back.** His `RESULTS.md` (file commit `cc986dd2`, PR #126) now carries
  our reader's result — **22 / 14 / 0 / 5**, matching — with our limits as written.
  The rest of the row was verified from his bytes: the four files of revision
  `af6af9ee149f` hash to what it claims and the 13 tests pass here too. Two
  corrections went back as **issue #127**: *"an earlier state of this reader"* was
  never published (all four gist revisions that carry it serve the same 13 234
  bytes) and the published reader cannot run against v4 at all
  (`TypeError … 'recovering'`), so **19 / 14 / 3 / 5 is reported, not
  reproducible**; and the outside count was **5 before it was 3**, because an
  earlier reader bound the payment by the transfer's `from` instead of the
  payment's own payer, which made the binding unfalsifiable. Both limits were added
  to `OUR_OWN_READING.md` and the gist republished (HEAD `6d1fe258a0fc`).
- **Four channels opened in one evening, and one of our own lines corrected** (§133).
  The last two §P letters went out, **cut for each product rather than renamed**:
  x402r's arbitration layer needs the failure population (135 attempts read, and the
  dangerous class is a payment that landed but was answered as refused), and Tanilo's
  spend-cap guard needs the base rate of actual spend (457 agents arrived, 12 payments
  happened, so a cap built from catalogue prices almost never fires). No bounce. The
  **x402 Foundation's Domain Discovery working group** stopped being a plan and became
  channels: the mailing-list subscription is **confirmed**, a **public meeting
  invitation arrived — next 30 November, 18:00 EET, Zoom via LFX, with the public
  minutes** — the discovery measurement went in as `wg-domain-discovery#19` and to the
  list, and the repo already carries outsider measurements, so that is the expected
  shape. **Glama was asked by email for the first time in three months**, with the
  facts measured the same afternoon (connector 200, **TDQS A 4.4/5.0 scored that morning
  across 7 tools**; the servers path for us 302s to the registry index; the
  connector-shaped servers path 404s). And **Olas was measured, which corrected our own
  line**: the "14 323 settlements" are `cluster-protocol`'s calls, not Olas's — Olas does
  support Base and USDC with no OLAS needed, but Mech's 402 is `olas-prepay` escrow
  rather than x402, and demand is 8 daily active agents with **11,920,962 of 12,333,115
  requests from Predict alone**. Deferred with numbers.

### 26 Nov — the failure became a document, and two threads closed themselves

Wrote `docs/SIGNAL_RECORD.md`, which was the one item `NEXT_ACTIONS.md` marked
"Next": the engine's failure as a first-class document instead of a footnote. Every
number was read from the live feed at **05:29Z**, not from notes — **272 issued, 132
carried by the feed, 99 scored: 1 hit, 12 misses, 86 flats, hit rate 1.0%**, average
move **+3.862% on a hit against −5.625% on a miss**, mean 24h move **−0.570%**,
positive/negative **49/50**. The outcome rule was **verified against the bytes** rather
than described (move beyond the per-signal volatility threshold with the call is a hit,
against it is a miss, inside it is a flat — **0 violations of 99**), and the frozen
thresholds were removed as an explanation by testing fixed bars, where misses outnumber
hits everywhere (0.5%: 25/28 … 5%: 1/7). Two findings it had to carry: confidence does
not sort outcomes (the 0.6–0.8 band holds the only hit **and 10 of the 12 misses**), and
the published totals **do not close** — 132 records + 138 non-directional = 270 against
an `issued` of 272 — so the document says so and does not guess. Next checkpoint is
**100 scored**, so it is superseded by that and not by an argument.

**Ernest dropped `/mcp` completely and the correction went the other way.** His words:
*"You're right on /mcp and I'm dropping it… my HTTP-402 prescription would have broken
compliant clients… Validator 25/25 is the proof. No charge, nothing owed."* The defect
that mattered was `GET /mcp` serving a free document on the URL our eight rows are
indexed against — found and fixed by us (§128). So the **$15 change-sheet is declined on
the merits**, not on price. He also delivered the band correction we asked for, with
**payers** as the denominator over 34,886 routes (repeat-use peak `$0.02–0.05`, 49
calls/payer) and withdrew his "$0.005 is the worst band"; our reply had already rebuilt
the table from the public field — **88,074 rows**, and `$0.02` alone is **59.6% of every
call in the listing** — so the **$25 / $15-a-month ranking is declined because it is
computable**. The one half neither side can buy is payer *identity*, which lives in the
seller's request log.

**Abdellah closed our corrections as completed** (issue **#127**, commit **`d48eaa1`**):
both points are in his `RESULTS.md` in our own words, the row pointing at gist revision
`6d1fe258a0fc`. Nothing owed in either direction.

**Both x402 Foundation lists confirmed** — `main@` (the parent) and
`Domain-Discovery@` — and **§Z3 was sent 16:46:47Z on 25.11**, one minute after the
confirmation, so it is in the first-post moderation queue. The working group's own
invitation arrived the same evening: bi-weekly Mondays, **next meeting 30.11 18:00 EET**
(LFX/Zoom, public minutes). We can post to the list; we cannot attend a call.

**A directory found us instead.** **SealKeeper** (26.11 05:09Z) checks public A2A agents
and listed ours on its own: **Bronze SEAL, uptime 100% — 145 of 145 checks, 7 of 7
skills answered**, card `/.well-known/agent-card.json`, endpoint `/a2a`, A2A 0.3.0. It
also states **`Owner not verified`** and **Trust Score 0**, because the score counts
verified tasks the agent solves. Claiming needs a signed-in account, so it is not
automatable from here; the link is with the owner. Our **service** is not listed there.

**Glama's submission path was measured, not assumed.** `/mcp/servers/add` **301s** to a
search query; the `Add Server` control is a client-side **`<button>`** with no `href`,
`<form>`, `method`, `action`, `fetch(` or `/api/` call in its route chunk; the public API
is **GET-only** (`/api/mcp/v1/servers` now **401**). A fresh submission needs the
**owner's browser** or Glama creating the record. The connector itself is in the public
search index and its badge returns **200**, rendering *"rated A on Glama"*.

**The last six trust-layer vendors were reachable after all, and the table had said they
were not.** §P listed nine vendors who sell trust about x402 sellers; three had been
written to, and six were recorded as **"none published"** — a claim measured against
their *websites* and stopped one source too early. **The npm registry publishes
maintainer addresses**, and five of the six ship a package. `scripts/vendor_contacts.py`
reads the registry and prints the fields with their provenance, which produced
`teppidotxyz@gmail.com` (Teppi), `zpointz777@gmail.com` (zauth),
`peacprotocol@gmail.com` (PEAC), `atom@oma3.org` (OMATrust) and `kris@affix-io.com`
(AffixIO); Elara's came from the repository owner's public GitHub profile, since its
crate has **no owners** and its commits are signed by a domain noreply — recorded as the
weakest route of the nine, and its repository was last pushed six weeks ago. **Six
letters written (§P4–§P9), personalised to the product each vendor actually sells, and
sent 07:46 EET**, all six accepted, all six in the Sent folder, no bounce at the time of
writing. So the whole category — **nine of nine** — has now been asked directly, and the
correction is written into §P and into NEXT_ACTIONS rather than quietly dropped.

**The census took its first payment, and it was ours.** `/api/v1/demand-census` — the
$0.25 dataset, the dearest call the service sells — was paid once, settled on chain (tx
`0x4293b30c…0a97`, block 62409944, $0.25 from our gas wallet to the bound receiver, both
balances read before and after and moved by exactly $0.25), and it delivered the full
document. **It is not a sale**, because the payer was our own wallet, so the route stays
out of the vitrine: the repo's own promotion rule requires a paid canary and its
precedent was paid by a third party. Two measured findings came out of the attempt. The
census is **absent from all four machine-readable catalogues we publish** — and that is
deliberate, not an oversight, because the promotion rule keeps it out. And the index
**did not create a row for it**: 20 rows before the payment and 20 after, none carrying
"census". The one decision it leaves is the owner's, because promoting the route moves
the advertised price range on *every* route from `$0.005–$0.05` to `$0.005–$0.25`.

**He said yes, and the promotion turned out to be bigger than two lines.** The census is
in `REAL_X402_ROUTES` from 26.11, with the canary's tx and block in the note and the
honest line that **the payer was our own gas wallet** — so the route is catalogued for
being payable, not for being wanted. Four surfaces generated from that list gained it by
themselves; two that are hand-written had to be edited by hand and **both were caught by
tests rather than by reading** (`/.well-known/x402`'s `resources[]`, and `/mcp.json`'s
tool list, which named seven while the protocol served eight). The hard limit arrived
immediately: an eighth MCP tool took the Registry's publisher extension to **4094 bytes
against a 4096-byte cap** with a 200-byte headroom rule, so the block was trimmed under
its own written rule — *"trim repetition, not facts"* — by removing two discovery URLs
already present in the document's own `remotes` and three cross-reference tails repeated
across tool descriptions. **3,827 bytes, 269 of headroom, eight tools**, measured. The
price is now visible on every route: the advertised range is `$0.005–$0.25`. Nine tests
failed and eight of them were hardcoded counts of seven; the ninth was real — the first
OpenAPI description was 439 characters, inside the band where x402lint's length warning
starts, and is now 330.

---

## Hanging in the air

| idea | state | what it waits for |
|---|---|---|
| Demand census at $0.25 | **promoted into the vitrine 26.11 with the owner's yes** (§138): in all four catalogues, the eighth MCP tool and the eighth A2A skill; the advertised range on every route is now `$0.005–$0.25`. The canary that unlocked it was paid by **our own gas wallet**, so the route is catalogued for being payable, not for being wanted | **one third-party payment at $0.25** — the only thing that turns a canary into a sale; December-vs-November delta on 20.12 |
| Discovery-truth report | **posted 25.11 16:46:47Z** as `wg-domain-discovery#19` and to the group's list; **both lists confirmed** (`main@` and `Domain-Discovery@`), so the post sits in the first-post moderation queue | the group's response to the three asks; the meeting of 30.11 18:00 EET, which we cannot attend — anything we want in it goes to the list first |
| Signal engine record | **`docs/SIGNAL_RECORD.md` written 26.11 from the live feed** (272 issued, 99 scored, 1 hit / 12 misses / 86 flats, 1.0%) | the next declared checkpoint, **100 scored signals** — it supersedes the document |
| SealKeeper (A2A directory) | **listed on its own since 26.11**: Bronze SEAL, uptime 100% (145/145), 7/7 skills, but `Owner not verified` and Trust Score 0 | the owner claiming it — the claim page needs a signed-in account, so it is not automatable from here |
| Listing-truth monitoring as a product | identified, unoccupied by the nine vendors | a price decision by the owner |
| Marx / Engels programme | requested 25.11 | stage 1 delivered; stages 2–3 are reading and synthesis |
| §O to HIVE402, §P to Hosannaith, x402r, Tanilo | **all sent** | replies; check 28.11 |
| §P4–§P9 — the six vendors the table called unreachable | **addresses found in the npm registry and all six sent 26.11 07:46 EET** (Teppi, zauth, PEAC, OMATrust, AffixIO; Elara via a GitHub profile, the weakest route) | replies; check 28.11 |
| Glama `/mcp/servers/` record | **Frank answered 25.11: the record was removed at our own request — verified in our Sent folder, asked twice (1 and 3 Nov), withdrawn in writing 17 Nov (§134).** Badge went from a grade on 4 Nov to "not listed" on 26 Nov, so the row died after the withdrawal. Reply §AB sent; ask narrowed to three actionable outcomes. **Submission path measured 26.11: it is browser-only** (`/mcp/servers/add` 301s to a search query; `Add Server` is a client-side button with no form, route or fetch; the public API is GET-only and `/api/mcp/v1/servers` is 401) | Glama's answer to §AB (#160212386) — resubmit, create the record, or state that a hosted endpoint can only live under `/mcp/connectors/` — which unblocks PR #13219 either way. **If the answer is "resubmit", it needs the owner's browser** |
| Olas Mech | **measured 25.11 and deferred with numbers** (Base + USDC, no OLAS, but `olas-prepay` not x402; 8 daily active agents, 96.7% of requests one agent) | an owner decision to build a mech; nothing from us now |
| Explee lead API | measured, priced | the owner creating the API key (+$30 free credit) |
| §Q public thread | written, ready | the owner's X account |
| Base Batches | open question | whether to apply, and how to frame numbers that fail a screen |
| Fixture 1 / OmniDome | **closed by him 25.11 20:13Z: issue #127 completed via `d48eaa1`**, both wording corrections in his `RESULTS.md` in our own words, the row pointing at gist revision `6d1fe258a0fc` | nothing from us |

## Must happen next

1. ~~Decide whether the discovery-truth report goes to the Domain Discovery working
   group, and join its public mailing list~~ — **done 25.11**: posted as issue #19 and to
   the list, both lists confirmed, the post in moderation.
2. Remove `X402LIST_VERIFICATION_TOKEN` after 26.11 15:06Z — **today, 17:10 EET**.
3. Send the remaining §P recipients; check for replies on 28.11.
4. Snapshot the census again on 20.12 — a month not snapshotted is gone.
5. PayAPI: three rejected listings to delete; the page still shows September.
6. Glama `/mcp/servers/` record still missing — it blocks PR #13219, and the
   submission path is now measured as **browser-only**, so it needs the owner.
7. Olas is still the one of the first six that was never contacted.
8. Oracle/Foresight revival is blocked on the GLM balance, which is an owner action.
9. **Owner actions, all three one click each:** claim the SealKeeper agent, resubmit on
   Glama if Frank says to, and remove the x402-list token if the scheduled script has not
   already run.
