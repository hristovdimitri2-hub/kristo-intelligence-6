# The rolling ten days

**Purpose.** The owner starts unrelated tasks, one after another. This file exists
so the answer to "where are we" never depends on anyone's memory: it always holds
the last ten days, what is still hanging in the air, and what happens next.

**Rule for whoever edits it:** the window moves. When a day is added, the oldest
day leaves. Curated prose is expected here; the factual base is reproducible with
`python scripts/rolling_10_days.py`, which prints the commits grouped by day.

**Window: 16.11.2026 – 25.11.2026** (152 commits).

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
  our own key**), which is the same blindness every index has, his included.
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

---

## Hanging in the air

| idea | state | what it waits for |
|---|---|---|
| Demand census at $0.25 | live, zero sales so far | one buyer; December-vs-November delta on 20.12 |
| Discovery-truth report | measured, written, committed | sending it to the Domain Discovery working group |
| Listing-truth monitoring as a product | identified, unoccupied by the nine vendors | a price decision by the owner |
| Marx / Engels programme | requested 25.11 | stage 1 delivered; stages 2–3 are reading and synthesis |
| §O to HIVE402, §P to Hosannaith | sent 25.11 | a reply; check 28.11 |
| Remaining §P recipients | drafted with addresses | sending to x402r and Tanilo |
| Explee lead API | measured, priced | the owner creating the API key (+$30 free credit) |
| §Q public thread | written, ready | the owner's X account |
| Base Batches | open question | whether to apply, and how to frame numbers that fail a screen |
| Fixture 1 / OmniDome | v4 answered his draft-3 set: 22 / 14 / 0, reproduced here | nothing from us; his rewording PR #123 is merged |

## Must happen next

1. Decide whether the discovery-truth report goes to the Domain Discovery working
   group, and join its public mailing list — the only place our measurements could
   shape the specification.
2. Remove `X402LIST_VERIFICATION_TOKEN` after 26.11 15:06Z.
3. Send the remaining §P recipients; check for replies on 28.11.
4. Snapshot the census again on 20.12 — a month not snapshotted is gone.
5. PayAPI: three rejected listings to delete; the page still shows September.
6. Glama `/mcp/servers/` record still missing — it blocks PR #13219.
7. Olas is still the one of the first six that was never contacted.
8. Oracle/Foresight revival is blocked on the GLM balance, which is an owner action.
