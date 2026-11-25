# The state of x402 discovery, measured 25.11.2026

**Source:** CDP's public Bazaar listing,
`GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources`. It
reports **87,419 rows**; 10,000 were read (the first 50 pages of 200) and **200 of
those were probed live**, unpaid, once each, using the method the row itself
declares.

**Why this exists.** Our own catalogue row kept advertising a description we had
already changed, and the only thing that updated it was a new settled payment.
One seller's bad luck is an anecdote; a property of the layer is a claim worth
publishing. This measures the layer.

## 1. Freshness — the listing is mostly not recent

`lastUpdated` across 10,000 rows:

| age of the row | rows | share |
|---|---|---|
| under 1 day | 1,569 | 15.7% |
| 1–3 days | 2,401 | 24.0% |
| 3–7 days | 1,343 | 13.4% |
| 7–14 days | 1,783 | 17.8% |
| 14–30 days | 2,880 | 28.8% |
| 30–90 days | 18 | 0.2% |
| over 90 days | 6 | 0.1% |

Median **5.95 days**, mean 9.64, oldest 209.7. **47% of rows are older than a
week and 29% are two to four weeks old.**

Read correctly, this is not a maintenance statistic. If `lastUpdated` moves when a
settlement touches the row, then **most x402 listings have had no paid call in
over a week** — the same finding the rest of our work reports from the demand
side, arriving here from the catalogue's timestamps instead.

## 2. Reachability — 5% cannot serve a request at all

Of 200 probed rows, **190 (95.0%) returned a parsable `402` with an amount**.

| outcome | rows | share |
|---|---|---|
| `402` with a parsable challenge | 190 | 95.0% |
| HTTP 400 | 4 | 2.0% |
| HTTP 404 | 2 | 1.0% |
| `402` without a parsable challenge | 1 | 0.5% |
| HTTP 500 | 1 | 0.5% |
| HTTP 403 | 1 | 0.5% |
| unreachable | 1 | 0.5% |

So **one listing in twenty points at something that cannot be bought from** — dead
URLs, server errors, or a `402` an agent cannot parse.

## 3. The listing does not say how to call what it lists

This is the finding with a specification consequence.

| | rows | share |
|---|---|---|
| declares `GET` | 6,003 | 60.0% |
| declares `POST` | 3,992 | 39.9% |
| declares `PUT` | 4 | 0.0% |
| method absent | 1 | 0.0% |

- **Rows carrying a top-level `method` field: 0 of 10,000.**
- **Rows carrying the method inside `extensions.bazaar.info.input.method`: 9,999.**

The method exists, but only inside a nested extension. An agent that reads the row
and issues the obvious `GET` to the listed URL **reaches 60% of the layer**; the
other 40% answer `405 Method Not Allowed` — not because those endpoints are
broken, but because the listing did not say how to call them. A row's `type` is
`http` for 9,999 rows and `mcp` for 1, and carries no other routing hint.

## 4. Truth — 15% misdescribe the product, 3.7% misstate the price

Of the 190 rows that answered with a parsable `402`, comparing the live challenge
against what the catalogue stored:

| comparison | rows | share |
|---|---|---|
| description and price both match | 159 | 83.7% |
| description differs only | 24 | 12.6% |
| description and price both differ | 4 | 2.1% |
| price differs only | 3 | 1.6% |

**Description differs in 28 of 190 (14.7%). Price differs in 7 of 190 (3.7%).**
Selected examples, with the catalogue row's own age:

| resource | catalogue | live | row age |
|---|---|---|---|
| `aizamon.com/x402/v1/bot-fuel-day` | **1,490,000** atomic ($1.49) | **100,000** ($0.10) | 29 days |
| `probeline.io/v1/implants/peri-implant` | peri-implant clinical status, 150,000 | **dental implant specifications**, 50,000 | 8 days |
| `api.agentpaywire.com/v1/updates` | "Library entries and articles…" | *(empty)* | 2 days |
| `geospatial.openverbs.com/v1/resolution` | ground resolution of map tiles | *(empty)* | 2 days |
| `markt.halowerk.com/snapshot` | venue-by-venue ticker description | rewritten | 2 days |
| `onchainproof.dev/v1/signal/ENA` | "This DeFi token…" | "ENA (Ethena): price-neutral net flow…" | 2 days |

The first two are the damaging shapes: an agent budgeting from the listing is
quoted **fifteen times the real price**, and one URL now sells a completely
different product while the catalogue still advertises the old one.

## 5. A methods note, because the first version of this was wrong

The first pass probed **every** row with a `GET` and counted `405` as a dead
listing. That reported **21.5% of rows unreachable** and looked like a much better
story. It was my probe, not their layer: **84 of the 200 rows declare `POST`**, and
a `GET` to a POST-only endpoint correctly answers `405`. Re-probing with each
row's declared method moved the failure rate from 21.5% to **5.0%**.

The correction is published rather than quietly fixed because the mistake is the
finding's own best argument for the next section: **nothing in the row told the
probe how to call the endpoint, so a competent caller got the method wrong four
times in five attempts** — the exact trap the 40% figure describes.

## 6. What this implies for the specification

Proposal for the **Domain Discovery** working group, with the measurements above
behind it:

1. **Surface the call method at the row level, or require it.** A listing that
   tells an agent where to pay but not how to call is 40% unusable by the obvious
   route. Making `method` part of the resource row (not only of the optional
   `bazaar` declaration) is a small schema change with a measured payoff.
2. **Publish row freshness as a discovery field.** `lastUpdated` already exists
   internally; exposing it lets an agent prefer a row that has been validated
   recently over one from four weeks ago.
3. **State a conformance expectation for indexers.** A row is a snapshot of the
   last settled echo, so it cannot follow a seller's current declaration. Either
   indexers re-read on change, or the specification should say plainly that a
   catalogue row is a historical record and not a live claim.

## Limits, stated

- One index (CDP's), not every catalogue. HIVE402 reports 47,041 of 56,080
  endpoints payable (16% not payable), which is the same order of magnitude as
  our 5% but measured differently and on a different population.
- The 10,000 rows read are the **first** 50 pages, and the listing appears to be
  ordered by recency — so this is the *freshest* slice of 87,419. Freshness and
  quality figures are therefore likely to be **optimistic**, not exaggerated.
- 200 live probes is enough to state a rate to roughly ±5 percentage points, not
  to characterise any individual seller.
- `402` challenges were parsed from both the response body and the
  `PAYMENT-REQUIRED` header; one row answered `402` in a form neither parser
  understood and is counted as a failure rather than guessed at.
