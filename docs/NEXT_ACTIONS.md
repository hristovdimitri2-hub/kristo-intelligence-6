# Next actions — consolidated

**Compiled 24.11.2026, 15:20 EET; updated 25.11.2026.** This supersedes
`docs/ACTION_BOARD.md` (03.11.2026), which is kept as history. One page, in the
order to work through it. Full text of every message is in `docs/OUTREACH_DRAFTS.md`.

---

## Measured 25.11.2026 — the target list changed, and why

The owner forwarded Digital Garage's press release: the first Japanese business
company to join the **x402 Foundation** as a General Member. x402 is now a Series
of LF Projects, LLC, launched with around 40 members. Three facts, all read off
the foundation's own pages:

- **We cannot buy our way in.** Premier $200,000; General **$25,000/yr** (under
  250 employees); Associate is **$0 but limited to academic and nonprofit
  institutions**, and we are neither.
- **Participation is free.** The TSC and working-group meetings are open to the
  public, there is a public Slack and public mailing lists, and
  `github.com/x402-foundation/x402` (6,826 stars, 895 open issues, pushed
  24.11.2026) takes issues and PRs. The working groups are **Domain Discovery**,
  Identity, Tax and Card Acceptance — Domain Discovery is our subject.
- **"Sell judgement" is not open space.** The repo's own
  `docs/dev-tools/third-party-extensions.md` keeps a *Third-party utilities*
  table and **nine vendors already occupy it**: Hosannaith, Teppi, zauth, Tanilo
  x402 Guard, PEAC Protocol, OMATrust, AffixIO, Elara, x402r. Every one measures
  the **supply** side. None measures the demand side — checked in their READMEs,
  not inferred from the table.

So the correction to §119/§120: judgement is crowded, and the buyer of the demand
side is not the ordinary seller. It is the **trust-layer vendors and marketplace
operators** — businesses that already exist, already need a base rate for whether
anyone pays, and cannot get it by crawling. Full reasoning in `HANDOVER.md` §122.

Ordered plan, cheapest first:

1. **Carry a measured finding into the spec repo** (free). The planned
   documentation nit is superseded: `docs/DISCOVERY_TRUTH.md` now holds the first
   measurement of whether x402 discovery tells the truth — **0 of 10,000 rows
   carry a top-level method** (so a naive GET reaches only 60% of the layer), 5%
   of listings cannot serve a request at all, 14.7% misdescribe the product and
   3.7% misstate the price, with a 15× overquote as the worst case. That, not a
   docs typo, is what the Domain Discovery working group is for.
   **Done 25.11.2026:** posted as `x402-foundation/wg-domain-discovery#19` (5 412
   bytes, read back through the API) and sent to the group's list as §Z3. The repo
   already carries outsider measurements (#1, #15), so this is its expected shape;
   GitHub Discussions is not enabled there, and the spec repo's own measurement
   issue #4284 is about **dynamic route templates** (5.3% unusable), a different
   finding from ours.
2. **Join the Domain Discovery working group's public mailing list and Slack**
   (free) — the only place our measurements could shape a specification.
   **Mailing list done 25.11.2026:** subscription confirmed (Groups.io confirms by
   reply), three welcome messages, and **an invitation to the group's recurring
   public meeting — every second Monday, 10:00 America/Chicago, next 30 November
   (18:00 EET), Zoom via LFX**, with the public minutes document. Slack is the one
   step left and it needs a Slack account.
3. **§P: the trust-layer vendors — all nine are now written to.** 25.11: Hosannaith
   `cameron@hosannaith.com` (§P), x402r `hi@x402r.org` (§P2, the failure population an
   arbitration layer will see), Tanilo `joe@tanilo.io` (§P3, the base rate a spend cap is
   set without). **26.11: the other six, whose addresses the table had recorded as
   "none published" — that was checked against their websites only, and the npm registry
   publishes maintainer addresses** (`scripts/vendor_contacts.py` prints the fields):
   Teppi `teppidotxyz@gmail.com` (§P4), zauth `zpointz777@gmail.com` (§P5), PEAC Protocol
   `peacprotocol@gmail.com` (§P6), OMATrust `atom@oma3.org` (§P7), AffixIO
   `kris@affix-io.com` (§P8), and Elara `aivelikivodja@gmail.com` (§P9 — the weakest
   route: no crates.io owners, commits signed by a domain noreply, so the address is the
   repository owner's public GitHub profile one). All six accepted by the server, all six
   in the Sent folder, no bounce at the time of writing. §O to HIVE402 waits for a reply.
4. **Unchanged:** the census stays at $0.25, and December-vs-November is the
   first sellable change.

## Tested 25.11.2026 — the tool that reaches the named buyer, and what it costs

The §122 conclusion produced a target class (trust-layer vendors, marketplace
operators, the 40 x402 members) and immediately hit the real gap: we have the
**companies** — the member list is public — and almost no **people**. §P reached
Hosannaith only because its founder publishes his address; of nine trust-layer
vendors, two publish an address at all.

**Corrected 26.11.2026, and the correction is the point:** "two publish an address" was
true of their **websites** and false of the vendors. **Five of the remaining six publish
a maintainer address in the npm registry**, and the sixth publishes one on its GitHub
profile — so the count was **nine of nine**, and the "gap" that made Explee worth buying
was partly a search that stopped one source too early. `scripts/vendor_contacts.py` now
does that lookup, and §P4–§P9 were sent on the strength of it. What remains genuinely
hard is not finding an address but finding a **person** at a company that publishes only
a role mailbox — which is a different problem from the one this section originally
stated.

**Explee** (explee.com, Explee LTD, London) is an AI outbound agent, and it is the
first tool in this whole search that closes exactly that gap with a documented,
public API. Measured from its own OpenAPI spec rather than from its marketing:

- `POST /public/api/v1/search/companies-by-domains` — up to 1,000 domains, **0.5
  credits per company found, 0 credits for domains not found**
- `POST /public/api/v1/search/people-by-domains` — the same domains plus up to 20
  job titles with **semantic matching** ("Head of Sales" matches "VP Sales"),
  `people_per_company` up to 1,000
- `POST /public/api/v1/find-and-enrich` — **1.5 credits per found email** (basic
  preset) or 5 (premium), up to 500 contacts per call
- Auth is `X-API-Key`; a live call without one answers **401**, so there is no
  anonymous access. The key is issued at `explee.com/app-auto-gtm/api-keys`.

Their published rate is **$0.04 per email** (750 emails for $30), which prices one
credit at ≈$0.027. So the whole class is cheap: the **40 x402 member domains →
company profiles ≈ 20 credits ≈ $0.53**, and three decision-makers with verified
emails at each ≈ 180 credits ≈ **$4.80** — inside the $30 of free credit.

**How to use it, and how not to.** Search and enrich only: find the named person at
a named company. **Not** the campaign machinery (`autogtm`), because the letters
are the asset precisely because they are researched and honest — §P argues from our
own losing record — and a volume campaign would spend the one credential we have.
Cold-writing to Visa, Circle and PayPal is also a different act from their florist
customers; the "~1 meeting per $30" on their landing page will not transfer.

**The smallest test first:** `search/companies-by-domains` on three known domains
(≈$0.04), then one people search for payments and partnership titles at those
companies. If their 105M-company database is thin on financial institutions, that
costs pennies and closes the question.

**Blocked on one owner action:** create the API key — signup plus the free $30
credit at `explee.com/app-auto-gtm/api-keys`. After that, everything above is a
script.

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
- **The money is not there.** Lifetime: 187 payments, $2.288. Of that, **$2.08 is
  our own wallets** (137 payments: the demo key, and the $0.25 census canary the gas
  wallet paid on 26.11). Genuinely external, lifetime: **13 payments, $0.064 from 10
  wallets** — corrected on 26.11 from "12 payments, $0.054 from 9 wallets", because the
  classifier had been counting our own gas wallet as demand and a thirteenth external
  payment had arrived (see the bullet below).
- **The newest external payment, and what it did.** `0x6c57df…40f3` paid **$0.01 for
  `/api/v1/whaleflow` on 25.11 at 17:27:01Z** through the **proof rail**
  (`payment_guard`), and the whaleflow Bazaar row's `lastUpdated` is **17:26:58Z** — three
  seconds earlier. An unknown wallet bought a route and the index refreshed the row as a
  result. The classifier calls it `external`, which is the correct stance: a real customer
  until proven otherwise.
- **A defect in a public claim, found and fixed on 26.11.** Paying the census canary from
  the gas wallet exposed that the gas wallet was **not** in `KNOWN_PAYERS`, so
  `/api/v1/settlement-classes` published **external: 14 settlements / $0.314 / 11 payers**
  where the truth was **13 / $0.064 / 10** — our own $0.25 counted as demand, inflating
  published third-party revenue **5×**. `/api/v1/seller-audit` was wrong the same way. Both
  are corrected on the live service, and the rule is now written in the classifier: *any
  address whose private key we hold is us* (demo, gas, receiver; the retired receiver is
  absent because its key is lost).
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
price instead of proposing one. `scripts/send_draft.py` sends a section body
extracted from `docs/OUTREACH_DRAFTS.md` verbatim, so the sent text and the record
cannot drift apart. It takes the section letter and the recipient on the command
line, so the address chosen at send time is printed at send time.

### The second buyer wrote the question first (25.11.2026)

Script Master Labs (HIVE402) published, on 24.11.2026, Episode 1 of *402 Daily*:
**"x402 Settlements Top 919,457 — So Why Did the Median Seller Earn Zero?"** They
asked our exact question in public, the day before we wrote to them. Three facts
made them the next recipient rather than a bigger catalogue: their probe-intelligence
feed sells aggregate stats free, **$0.05 per page and $0.25 for the complete
snapshot** — the same price and shape as our census, which is independent evidence
that the price is real; their sales feed excludes their own wallets while their
activity feed marks their own settlements `SELF-PROOF`, which is our discipline, not
theirs to be taught; and their trust formula already prices **demand at 20 of 100**,
which is the exact component the census measures and no index can see.

Draft §O answers their question with our numbers rather than with a pitch. Sent
25.11.2026 to `tim@scriptmasterlabs.com`, the LLC's canonical organization address,
with the product's published inbox `ScriptMasterLabs@gmail.com` on Cc.

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
in the MCP tool description served at `/mcp` — which is the text a CDP Bazaar row copies
on the next paid call, and which was for several hours only in the generated
`server.json` (see §121 in HANDOVER.md).

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
2. **Done 26.11.2026** — the failure is a first-class document: `docs/SIGNAL_RECORD.md`,
   written from the live feed at 2026-11-26T05:29Z (272 issued, 99 scored, **1 hit / 12
   misses / 86 flats**, hit rate **1.0%**, avg hit +3.862% against avg miss −5.625%), with
   the method, the outcome rule **verified against the bytes (0 violations of 99)**, the
   bar test that removes the thresholds as an explanation, the two things it proves and
   the three it does not. It also states its own limit: the published totals do not close
   (132 + 138 against 272) and the document does not guess where the other two are.
3. **December** — the second census snapshot creates the first real delta product.
   **The $0.25 route's paid canary was taken on 26.11 and settled on chain** (tx
   `0x4293b30c…0a97`, block 62409944, $0.25, both balances moved exactly), but the payer
   was **our own gas wallet**, so it proves the plumbing and not demand. **The owner
   approved the promotion the same morning with the range change stated, and the census is
   in the vitrine from 26.11** (§138): it is in all four generated catalogues, it is the
   eighth MCP tool, it is the eighth A2A skill, and the advertised range on every route is
   now `$0.005–$0.25`. What it needs next is the thing the promotion was for: **one
   third-party payment at $0.25**, which is the only thing that turns a canary into a sale.

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
mention of its record, while the vitrine pages, README and the paid response all stated
it — and the MCP-served description did not state it either, which the row's own
refresh later exposed (§121 in HANDOVER.md).

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

**Closed 25.11.2026, and the attempt found something worse than a stale row.** Before
paying, the `bazaar` extension in the live challenge was read rather than assumed — and
it carried the *pre-honesty* description, because the MCP text comes from
`discovery._mcp_tools()` while the sentence had been written into `server.json`, a
**generated** file whose source was never edited. So the paid refresh would have
republished the same text politely. `discovery.py` now serves *"Its own measured record
is public and losing: /public/signals/history — read it before acting on a signal."*,
`server.json` is regenerated, and two tests compare source against artifact (§121 in
HANDOVER.md).

The refresh then failed twice and spent nothing, which looked like a payment defect. The
log said otherwise: *"x402 payment NOT taken: endpoint=/api/v1/signal ip=127.0.0.1 — the
route has nothing to deliver right now"*. The MCP tool forwards the buyer's header to
the HTTP route, and that route refuses **before** settlement while its signal engine is
cold after a deploy — so the answer was 45 seconds of waiting, twice. Third attempt
delivered, tx `0xbb454d929ca7ef712d2ac7976b2799bee7799825653e4dcc9f7513cacb455bc4`,
$0.01, and the index row now carries the sentence at `lastUpdated
2026-11-25T08:00:53.795Z`. `scripts/mcp_paid_refresh.py` is committed with a `--verify`
mode that compares the index row against what `/mcp` serves.


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
- **Virtuals ACP** — offerings with escrow, `Virtual-Protocol/acp-cli`. The one question
  that decides whether we can be there at all — can a hosted HTTP service be an ACP
  offering, or does it need an agent wrapper? — is `Virtual-Protocol/acp-cli#111`, open
  since 24.11, still unanswered.
- **Olas Mech** — measured 25.11 from Olas's own pages, and the answer changed the line.
  **Base is supported** and so is USDC: `mech-client` lists Base as a marketplace chain,
  `marketplace.olas.network/base/ai-agents` resolves, and anyone can run a mech
  (`pip install mech-server` → `mech setup -c base`, Python 3.10/3.11 + Docker, **no OLAS
  needed for USDC payment and no published staking minimum**). Three things stand against
  it: **Mech's own 402 is `olas-prepay` escrow, not x402** (no `X-PAYMENT`, no EIP-3009,
  no facilitator); a "tool" is a Python function inside the mech, not a passthrough to our
  URL; and the demand is thin and concentrated — **12,333,115 requests, 10,379,011
  deliveries, 8 daily active mech agents, of which 11,920,962 requests are Predict alone**,
  at 0.001 USDC per request (fee 15% per a third party's contract read). **Deferred with
  numbers rather than dropped:** the build is small, but at a thousand requests a month
  the gross is about a dollar. The smallest real step, if we ever take it, is
  `mech setup -c base` on a throwaway wallet.
  **Attribution correction:** the "14 323 settlements" this line used to carry are
  `cluster-protocol`'s calls in the §108 table, not Olas's.

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
| 3 | **`X402LIST_VERIFICATION_TOKEN`** | **DONE 26.11.2026.** The token expired 15:06Z and the variable had no expiry check, so the path kept serving it. `_tools/remove_x402list_token.py --apply` deleted the variable (`DELETE /env-vars/{key}` → **204**), triggered deploy **`dep-dc4id9u1egvs738hr8r0`**, and `/.well-known/x402list.txt` returned **404** on the fifth poll (~75 s). Verified after the redeploy: `/health` 200, `/validation` 200, `/.well-known/sealkeeper-claim.txt` still the same 43 bytes / sha256 `fc8b6323…`. |
| 4 | **PayAPI's `Price` field** | **DONE 26.11.2026.** The price edit went through on 24.11 (`$0.005 – $0.05`), and the stale `verified_routes` line that still printed `$0.003 – $0.005` **was fixed by Chet on 26.11** — see §2c. The four routes missing from the settlement-verified line are being added by PayAPI at their own cost. |

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

### 2c. Chet answered on 26.11 — the price defect is fixed, and PayAPI pays for the missing four

Chet Parker replied on **26.11 16:23Z** to that message, and both measured defects
are closed on his side:

- **The stale price is gone.** The route records for `/api/v1/signal` and
  `/api/v1/whaleflow` still held the September `$0.003`; their health check
  compared the live `$0.01` quote against that stale number and flagged a
  mismatch. He updated both to `$0.01`.
- **He probed all seven routes the same day:** each returned a clean `402` on Base
  to our wallet, at `$0.005`, `$0.01` or `$0.05` as listed. The listing is live on
  the same card.
- **The four missing routes will be added to the same card, at PayAPI's cost.**
  They pay a small test on each from their own wallet — all four are at or under
  `$0.05`, so no deposit is needed from us — and the routes join once tested.
  **No second card.**
- **Reliability is not refreshed.** The uptime figure and the "degraded" label come
  from a stored reliability window that has not been recomputed since September; he
  has not refreshed it yet.
- **The three rejected listings are not public.** He has noted the deletion request;
  **nothing has been removed yet.**
- Free to list, and PayAPI takes **0%** of each job.

So the only open half is the reliability window, and recomputing it is his to do —
it is not something we can `PUT`.

**Verified against the page and the API on 27.11**, rather than taken from the email:

| claim | measured |
|---|---|
| the stale price is gone | ✅ the listing page now reads `3 of 3 routes settlement-verified · $0.005 to $0.05 USDC/request · 3 endpoints / 4 tools`, and the record's `price` is `{min: 0.005, max: 0.05, unit: per_call}` with `payment_verified: true` |
| the four routes join the same card | ⏳ **not yet.** `endpoints_count` is still `3`, `verified_routes` still holds the three September tests, and the page still prints `3 of 3 routes … 3 endpoints`. The individual `$0.003` lines are the September **receipts**, so they are historical, not stale prices. |
| the three rejected listings are not public | ✅ **out of the API catalogue** — paged all **3,119** entries of `/api/listings`, exactly **one** is ours. ⚠️ One page that matches a rejected name still renders and is linked from the agent-marketplace index: `/agent-marketplace/kristo-seller-audit-verify-an-x402-seller-before-you-pay` (HTTP 200, canonical, `og:title`). `/api/listings` carries only `api/…` URLs, so it cannot see that surface either way. |
| — | ✅ the advertised `mcp_endpoint` is real: `/mcp/sse` answers `event: endpoint` plus `data: …/mcp/message?sessionId=…` with keepalives. |

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
| 1 | Abdellah | **Done on both sides.** He reproduced the cross-run from the raw bytes (same tally, same one-line difference) and put our line in his results file with our name, the date and the fingerprint. He also offered a new column for **our own reading without his adapter** — written and published on 25.11 (§130): it found **three vectors where our own artifact refused a payment that had landed**, the artifact was fixed to v5 (`ccdfea67…`, 13 tests), and our reader now returns 22 / 14 / 0 / 5 from the gist's own bytes. He then listed that reading as a **second row** in `RESULTS.md` (PR #126, file commit `cc986dd2`) with our limits as written; we checked the row against his bytes (the four files of revision `af6af9ee149f` hashed, 13 tests pass here) and sent **two wording corrections as issue #127**: the earlier reader state the row names was **never published** and the published reader cannot run against v4 at all (`TypeError … 'recovering'`), so 19 / 14 / 3 / 5 is a reported number rather than a reproducible one; and the outside count was **5 before it was 3** (an earlier reader bound the payment by the transfer's `from` instead of the payer). Both limits now sit in `OUR_OWN_READING.md` (gist HEAD `6d1fe258a0fc`). **Closed by him on 25.11 20:13Z: issue #127 completed via commit `d48eaa1`**, and his comment confirms both points are in `RESULTS.md` in our own words — the earlier reader state and why the published reader cannot run against v4, and the earlier defect that answered 5 outside — with the row pointing at `6d1fe258a0fc` and the check-name sentence at `af6af9ee149f`. Nothing owed on either side. |
| 2 | Ernest | **Every reply between 24.11 19:52Z and 25.11 was undelivered** — the address in this repo (`ernest@nolimbsfighting.com`) rejects mail (`554 5.7.1 … does not exist`); he writes and replies from `ernest-earnordie@agentmail.to`. §R, §S, §T, §U and §V bounced; **§W is the consolidated resend** (the `/mcp` answer plus the three points that were never read), and no new bounce came back. `send_draft.py` now refuses the dead address. **`/mcp` is closed in our favour (25.11 14:57Z): he dropped it in writing** — the MCP transport spec does put `PaymentRequired` in the tool result, his HTTP-402 prescription would have broken compliant clients, and **validator 25/25 is the proof**; the defect that mattered was `GET /mcp` serving a free document on the URL our rows are indexed against, which we found and fixed ourselves (§128). **No charge, nothing owed**, so the $15 change-sheet is declined on the merits. He also delivered the **band correction with payers as the denominator** (34,886 routes; the repeat-use peak is `$0.02–0.05` at 49 calls/payer) and withdrew his earlier "$0.005 is the worst band"; our reply **§X was sent 25.11 15:09Z** with the table rebuilt from the public field (88,074 rows) and dissolved — `$0.02` alone is 59.6% of every call in the listing. The **$25 / $15-a-month ranking is declined because it is computable**, and payer *identity* is the only part neither side can buy. Two questions are still with him and unanswered: is the sniperx 5,538 payer-classified, and **what is his share if we supply and he sells?** |
| 2b | **verify-seller** | §L2 dropped it on Ernest's earlier read; our own books reverse that (§126/§T). Not a pricing question — the route is already `$0.05` — but a positioning one, and the demand behind it is 11 payments / `$0.072` / six addresses in thirty days. |
| 2c | **Seller-side demand ledger as a service** | Product shape confirmed three times in one week (§118, §R, §127): the buyer of demand-side measurement is a seller, and what they buy is due diligence, not a forecast. We have the method, the extraction and a live dataset; **the channel is what we do not have** — which is what Ernest has. §U asked him to name his share. Two paths, no decision taken: supply him and take a cut, or sell directly to the few sellers we can reach. |
| 3 | x402-list | Manual review; the FORTE tier cannot be bought yet (§101). |
| 3b | **CDP ticket #881** | Ernest answered it publicly: there is **no delisting mechanism**, so a row moves only when a paid call re-indexes it, or it decays. His proposed "redirect the old /mcp URLs" does not apply — measured, the retired rows are on the **same host and path** as the live ones and differ only by the payTo they were indexed under (§128). The six can only age out. What DID change: `/mcp` now passes Coinbase's preflight 25/25, so the eight live MCP rows can be re-validated instead of decaying on a failed check. |
| 4 | Glama | The `/mcp/servers/` record — **asked directly by email on 25.11.2026** (`support@glama.ai`, cc `frank@glama.ai`, draft §AA) with the facts measured that afternoon. Glama's Intercom answered in **seven minutes** with ticket **#160097735** ("Submitted — we'll pick up your ticket soon"); that is an acknowledgement, not an answer. **Frank answered the same evening (§134): the record was removed because "someone from your team requested its removal" — and he is right.** Our own Sent folder shows the request twice (1 Nov "either publish/unstuck … or remove the stale duplicate"; 3 Nov "Could you purge it completely?") and **a written withdrawal on 17 Nov** ("I will not resubmit or remove anything … please activate the existing listing"). **Reply §AB sent 26.11 06:55 EET**, owning it and narrowing the ask to three actionable outcomes (fresh submission accepted / Glama creates the record / a plain statement that a hosted endpoint can only live under `/mcp/connectors/`); Intercom turned it into ticket **#160212386**. The Discord message in §K cannot be posted from here (the account is not approved to send). |
| 5 | Glama | Tool Count 4/5 — decision taken: do not chase it. Removing response fields to buy 0.1 of a third-party score is not worth changing a paid endpoint. |
| 6 | Glama, the `/mcp/servers/` record | The connector is listed and rated A; the `/mcp/servers/` record **was removed at our own written request and now no longer exists in any form**. `quality` is computed only for `/mcp/servers/`, so `awesome-mcp-servers` PR #13219 cannot merge. **Measured 26.11.2026:** the connector page returns 200 with **TDQS A 4.4/5.0 across 7 tools**, uptime 100%, last tested 04:51; `/mcp/servers/<owner>/<repo>` **302-redirects to the registry index** (638 KB fetched, no "kristo" in it). **The badge is what dates the removal:** on 4 Nov `…/kristo-intelligence-6/badges/score.svg` still rendered a grade, and on 26 Nov it renders **"This MCP server is not listed on Glama"** — so the backend row died between those two readings, after the 17 Nov withdrawal of the removal request. Put in front of Glama by email (§AA, then §AB); tickets #135407945 (September), #160097735 (25.11), #160212386 (26.11). **The submission path was then measured, and it does not exist from here:** `/mcp/servers/add` **301s** to `/mcp/servers?query=author%3Aadd`, the `Add Server` control on `/mcp/servers` is a **`<button type="button">`** with no `href`, no `<form>`, no `method`/`action` and no `fetch(` or `/api/` call anywhere in its route chunk (25,765 bytes), the route table contains no add path, and the public API is **GET-only** (`/api/mcp/openapi.json`; `/api/mcp/v1/servers` now **401**). So a fresh submission needs **the owner's browser**, or Glama creating the record — while the connector itself is measured healthy: **in the public search index** for `kristo`, badge **200** rendering *"rated A on Glama — ownership verified, tool definitions rated A, endpoint responding at last check, 7 tools"*. The gap is one record type, not the listing. |

| 7 | **SealKeeper** | A directory of public **A2A** agents and services that found us on its own and wrote on 26.11 05:09Z. **It lists THREE records for our domain, not one**, and the claim screen names them: `kristo-intelligence-api-onrender-com` → `/.well-known/x402` with **49 of 49 task checks answered**, `kristo-intelligence-api-onrender-838051` → `/mcp` with **52 of 52**, and `kristo-intelligence` → `/.well-known/agent-card.json` with **56 of 57** (Bronze SEAL, uptime 100% — 145 of 145 checks — 7 of 7 skills, median 251 ms). **A correction: an earlier note here said our service was not listed because `/services/kristo-intelligence-api.onrender.com` returned 404 — the URL shape was wrong (dots become dashes), not the coverage.** So a third party independently verifies the x402 discovery, the MCP transport and the A2A card, and the first two pass every check. **The claim is domain control, not a captcha:** the page says *"put a claim token on your site to prove you control this domain"* and offers **Get a claim token**; sign-in (GitHub / GitLab / Google / email) is still a browser step and the page carries a Cloudflare Turnstile key, so the two browser steps stay with the owner. | **DONE 26.11.2026.** The owner signed in as `hristovdimitri2-hub`; the claim token `TiWnGbTIyWNrNa6ClzsTEp-T8V6CiVldBLTr0a2RORs` is served at `/.well-known/sealkeeper-claim.txt` (**43 bytes, last byte `s`, no trailing newline**, sha256 `fc8b6323f60b46d62d01df7dfd693a3068fa1e777c2d91c0905386912f907d00`), and the live pages for **all three records** now read `Owner verified`, **Claimed 26 Nov**, proof linking to that URL. **Correction to the earlier note in this row:** it said Trust Score stays 0 after claiming — measured on the live page now, it reads **Trust Score 200** (delta 0, "0 in the last 7 days"), while the record also shows 0 verified tasks. So the "stays 0" claim was wrong; whether the claim moved the score or the earlier reading was wrong cannot be told from the bytes we kept, so it is recorded as measured, not explained. **New on 26.11, after the claim:** the `/mcp` record `kristo-intelligence-api-onrender-838051` now reads **SEAL Suspended** — *"SealKeeper has withheld this service's SEAL while the latest change to its definitions waits"* — and its "Latest change" is classified **Silent**: *"A definition changed, or some appeared while others went away, and the server's version stayed the same."* The cause is ours: the census promotion added an eighth tool (`get_demand_census`) and `SERVICE_VERSION` is still `6.3.1`. The other two records are unaffected — x402 **Bronze SEAL Active**, 25 valid checks; agent **Bronze SEAL Active**, Trust 200, 67 tasks over 17 of 30 days. The Guardian email is this suspension's notice, not a new problem. Two fixes: confirm the definition in the signed-in dashboard (the email's own instruction), or bump `SERVICE_VERSION` when the tool surface changes so the change is announced — the second is durable but leaves the published MCP-registry row at 6.3.1 until republished. **Resolved 27.11:** the owner clicked the **five per-row white `Confirm as intended` buttons** on `/me?listing=…` (the link the notification email carries) and the hold cleared. Verified from outside, not from the screen: the record page now reads **`SEAL · Active`**, *Issued 27 Nov · expires in 23 h 59 min*, and the definitions block is gone. **The orange `Confirm change` in the top bar is the `Needs you` column text, not a button** — it does not click; the only controls are the five white per-row buttons. **No version bump was needed**, so the published MCP-registry row stays `6.3.1`; the bump is the durable habit for next time, not a prerequisite. |
| 8 | **Glama `#support` (Discord)** | **The channel is where Frank answers personally** (he fixed TheGodHand's app permission there on 22.11) while the ticket queue is agent-handled at 200+ a day. **`glama.json` has been in the repo root since 17.09.2026 and did not restore the record** — the maintainer file binds an existing record, it does not create one, which closes the last self-serve route. Measured again 26.11: the servers path serves the registry index (**641,587 bytes, zero "kristo"**), the score badge renders **"not listed"**, and the **card badge is a pure-path SVG with no text nodes**, so its grade cannot be read from the bytes — the README keeps the readable score badge. | **SENT 26.11.2026 by the owner** — §AC posted to Frank in `#support`; our account cannot send there. Waiting on his answer. |
| 9 | **Stabledrop.me** | An escrow-payments product on Base, found through an r/ethdev thread on card-to-crypto orchestration. Measured 27.11: *"Protected payments for everyone, for 1%"* — time-delayed escrow, checkout by one script with no backend, footer *© 2026 Conduit UCPI · Company No. 8803019*; **AP2** settle API is public (`api.stabledrop.me/api/ap2/settle/doc`), contracts are public (`github.com/conduit-ucpi/contracts`), the partner page mentions MCP four times, and **x402 appears nowhere on the site** (six pages, zero occurrences). **§AD sent 27.11 07:41Z** from the owner's address to `info@stabledrop.me`, confirmed in the Sent folder; it leads with the free ledger, offers to add their repo to the AP2 radar, and names where it may be wrong rather than pretending a fit. No reply and no bounce yet. |
| 10 | **`x402-foundation/x402` #4367** | The buyer-side measurement thread (25,011 paid calls, 1,036 sellers, opened 21.11 by `sarmadahsan`/paidfor.dev, 15 comments) — the same audience as the r/ethdev thread the owner cannot answer without a Reddit account. **Comment posted 27.11 07:50:55Z as `hristovdimitri2-hub`, id `7212878372`, 3,628 chars, read back clean (6 em dashes, 0 Cyrillic).** It does not repeat `hwcho310`'s split of the 507 `overcharge` calls or Ernest's catalogue cut; it closes the gap they leave — **the listing is not ground truth** — with our own timestamped row (`lastUpdated` 25.11 17:26:58Z vs settlement 17:27:01Z), the PayAPI `verified_routes` case, a durable operator-side claim for the transfer rail (`payment_guards`), and our payer taxonomy. No reply yet. **Followed by two more comments the same day:** `7225281930` (3,518 chars) correcting our own read — `minia2auk` came back with a stronger version of the evidence (their `lastCrawledAt` equals their settlement timestamp to the millisecond, ours was three seconds) and answered the question we closed on: **the overcharge half is not seller behaviour in their data, every traceable discrepancy is index-side** — plus a measurement that Ernest's Blockscout method is **403 behind Cloudflare** for programmatic callers, and the full current/retired payTo pair only we can supply; and `7225320498` (1,877 chars) reporting a **self-inflicted instance of the lost-response class** from our own route, with both hashes. |
| 11 | **Ernest — the $15 reconciliation** | Read our live `/api/v1/seller-audit` at 18:53Z and verified it **against the chain**, with a sharded `eth_getLogs` over a published block range (59,620,061 → 63,075,958; USDC on Base, `to` == our current payTo). **His rows and ours agree exactly:** external payer `0x6c57df77…40f3` 1 tx / $0.01, own keys `0xe50c5212…5763` 16 tx / $0.245 and `0x5f6d3f20…ee74` 1 tx / $0.250. He also withdrew his own method in writing: Blockscout `/api/v2` is **403 behind Cloudflare** for programmatic readers, so it could not be recomputed by a third party; the replacement is the keyless sharded `eth_getLogs`. **Offer: $15 for a one-month reconciliation of our ledger against the chain — delivered before payment, then $15/month.** **§AF sent 27.11: the first accepted, the monthly declined for now** and reversible without being asked, on the honest ground that lifetime third-party revenue is **$0.208** and $15/month is seventy times it. **The next step is ours:** send one row per settlement (route, amount, timestamp, tx hash) — the hash is the join key. We also corrected his split: by our published 50-receivers-in-30-days rule all three wallets he calls external (141 / 191 / 376 receivers) look like samplers, and `0x54E163e9…` is already labelled `market_crawler_54e1`; the open question is whether his breadth is 30-day or all-time, because our threshold is a 30-day fan-out. |

---

## 5. Technical — open, not urgent

| # | Item | State |
|---|---|---|
| 1 | Two-process deploy overlap | Render runs old and new instance together during a deploy, so log streams interleave. Harmless; makes "which process answered" non-deterministic from outside. |
| 2 | `autoDeploy` is on | Every push deploys production. Documentation commits carry `[skip render]`; verified to work. Build filters would be better but risk blocking real deploys. |
| 3 | **`/api/v1/verify-seller?days=30` did not answer inside 120 s** | **FIXED 27.11.2026.** Measured by paying it ourselves: the call **settled on chain and returned nothing** (`0xe3ffa9…`, 18:10:47Z, $0.05) while a 7-day window answered normally (`0x8a2aaa…`). Two changes: `_get_logs_adaptive` now queues chunks **newest first**, so a short read covers the recent end instead of the stalest one, and it takes a **wall-clock budget** (`max_seconds`), which the audit passes as `AUDIT_TIME_BUDGET_SECONDS = 45.0`; the report then reads `partial` and names the block ranges it never read. Four new tests (**1488 → 1492**, published count moved with them). **Do not retry** a timed-out paid call — the nonce is consumed and a retry is a second payment for the same intent. |

---

## 6. Done — so it is not reopened

| | |
|---|---|
| MCP Registry | `6.3.1` published, verified in the registry: 6 new descriptions, 0 old |
| CDP Bazaar | rows carry the descriptions served on the last paid call, so a row is only as current as that call. The signal row was re-indexed 25.11.2026 and now carries the engine's measured record on both resources (`/api/v1/signal` and `/mcp#get_trading_signal`). |
| Two unbuyable routes | `/api/arb/opportunities` and `/api/v1/signal` refused every buyer because the serving process never started its producers; fixed, both now sell |
| Free samples | 7/7 return 200 |
| Documentation | `scripts/doc_language_audit.py` exits **0**: **zero markdown files contain Cyrillic**, out of **105 tracked** before `docs/SIGNAL_RECORD.md` was added. The row used to quote a fixed "95/95"; it now quotes the audit's own verdict, which cannot go stale. **With one named exception since 24.11**, see below |
| Suite | **1485 passed, 1 skipped** (run 26.11.2026, exit 0); language audit exit 0 |
| Python client | `scripts/` + `docs/` — a paid call proven end to end |
| Document language rule | Now enforced by CI (`language` job). `docs/AP2_RADAR.md` is exempt: it is generated by `scripts/ap2_radar.py`, which writes Bulgarian, and it is a report to the owner, whom the rule keeps in Bulgarian. The exemption lives in `OWNER_FACING_GENERATED` in `scripts/doc_language_audit.py` and is printed by every run, so it cannot grow quietly. |

---

## 7. Today's clock (26.11.2026)

- **17:10 EET — remove `X402LIST_VERIFICATION_TOKEN` from Render.** The directory's
  review window closed at **15:06Z**; the removal script is dry-run verified
  (`_tools/remove_x402list_token.py --apply`). Reminder is set.
- **Reply checks.** §O Script Master Labs — **29.11 10:00 EET**; **§P, §P2–§P9 (all nine
  trust-layer vendors) — 28.11**; the working-group post §Z3 sits in moderation, so no
  reply is late yet.
- **§Z3 moderation, with a date on it.** The post was sent 25.11 16:46:47Z and the list
  has not distributed it — checked 26.11 by looking for our own copy in the inbox, which
  is what a member receives when a message is let through. A first post from a new member
  is held by design, so nothing is wrong yet; **if it is still not distributed on 27.11,
  ask `Domain-Discovery+owner@lists.x402.org` whether it is held**, because the working
  group meets on 30.11 and anything not on the list by then misses the meeting.
- **Mon 30.11 18:00 EET — x402 Domain Discovery WG** (bi-weekly, LFX/Zoom, public
  minutes). We can post to the list but cannot attend a call, so anything we want in
  that meeting goes to `Domain-Discovery@lists.x402.org` **before** it.
- **Next checkpoint for `docs/SIGNAL_RECORD.md` is 100 scored signals** (99 today), and
  the **second census snapshot** is due **20.12** (`scripts/build_demand_census.py`),
  which is what creates the first real delta product.
