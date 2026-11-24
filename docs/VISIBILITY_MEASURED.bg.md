# VISIBILITY, MEASURED — 2026-11-10

An answer to the owner's question: *"whether agents are looking for exactly this and
whether we are more visible than the 518 other MCP entries and 32 698 HTTP entries
around us"*.

Everything here is measured from the outside, by reading public catalogs. Nothing was
paid for, nothing was published, nothing in the code was changed. The raw outputs are
in `_forensics/*.out.txt`.

---

## 1. The two halves of the catalog behave fundamentally differently

`GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?type=…`

| | MCP half | HTTP half |
|---|---|---|
| rows | **518** | **32 700** |
| paid calls / 30 days | (no total published) | **918 645** |
| median calls per row | **1** | 2 |
| median unique payers | **1** | 2 |
| rows with ≥2 unique payers | **17 of 518 (3%)** | ~51% of the sample |
| maximum payers on a single row | **4** | **667** |
| rows with zero calls | 7 — **exactly our seven** | 70 (0.2%) |

**A median of 1 call / 1 payer is the listing settlement itself** — the payment that
creates the row. That is, 511 of the 518 rows in the MCP half were paid exactly once:
by their own owner, in order to appear. There is no market there.

That is why the phrasing "are we more visible than the 518" is pointless: in the MCP
half, first place means **4 payers**. We are at 512–518, but the difference between
518th and 1st place on that surface is between zero and four people.

The HTTP half is a different country: 918 645 paid calls over 30 days. There we are,
with 7 HTTP rows: 1 payer each (again the owner's own listing settlement).

## 2. What is actually bought (full census, 32 699 rows)

| category | rows | paid calls | share |
|---|---|---|---|
| transfers / wallets / onchain send | 5 436 | 250 525 | 27.27% |
| enrichment / data APIs | 2 910 | 194 574 | 21.18% |
| web search / scraping | 4 119 | 156 221 | 17.01% |
| inference / LLM | 1 669 | 133 102 | 14.49% |
| other | 12 732 | 115 055 | 12.52% |
| blockchain RPC / chain data | 2 409 | 22 319 | 2.43% |
| time / maps / geo | 1 601 | 21 530 | 2.34% |
| social / sentiment | 327 | 8 067 | 0.88% |
| images / media / voice | 1 017 | 7 875 | 0.86% |
| **crypto intelligence (our niche)** | **111** | **6 211** | **0.68%** |
| email / messaging | 368 | 3 166 | 0.34% |

In our niche, 6 211 calls, of which **5 641 (91%) are on a single row**
(`x402.sniperx.fun/.../smarttrader`, 2 payers). The remaining 110 rows share
~570 calls per month.

The best sellers: Token Verdict 128 968 calls/306 payers; blockrun chat
completions 84 780/301; Exa search 33 534/142; checkout 21 510/313.
The prices of the rows that actually sell (≥1000 calls): **$0.001–$0.070,
median $0.005**. Ours: $0.003–$0.10 (the only one above the ceiling is
`verify_seller_receiver` at $0.10).

## 3. The demand exists — and it does not find us

`GET /discovery/search?query=…` is a live **hybrid (semantic + textual) search**
(`searchMethod: "hybrid"`, `limit` ceiling = 20).

27 queries with the buyer's words. We were found in **10 (37%)** — and all 10 are
queries with 2–4 competing rows or our own name. For every query with real
competition we are **absent**:

| buyer's query | rows | we |
|---|---|---|
| whale / whale flow / whale alerts | 16 / 11 / 12 | **absent** |
| crypto market stats / market data / market overview | 14 / 10 / 11 | **absent** |
| token price and volume | 7 | **absent** |
| trading signal / crypto trading signals / buy sell signal | 11 / 11 / 6 | **absent** |
| verify seller / is this seller legit | 9 / 5 | **absent** |
| bot health check | 9 | **absent** |
| nft sales data | 5 | **absent** |
| onchain sales | 2 | **#1** |
| trading bot status | 2 | **#1** |
| arbitrage opportunities | 13 | **#3** |

Where we are #1, we are #1 because almost nobody else uses exactly our word.

We also rule out the explanation "we are simply new". Phrases that exist **only in
our own published descriptions** also do not find us:
`treasury-sized flows` → 5 rows, we are absent (#1 is `api.agentstools.dev/treasury/cash`);
`labelled counterparties` → 10 rows, absent (#1 is
`api.nansen.ai/.../address/counterparties`); `refreshed under 5 minutes` → **0 rows**.

The control: a phrase from a competitor's description finds them
(`What can go wrong with a memecoin` → #1 `agent.pocket.network/v1/pump-check`).
So descriptions **are** indexed — they simply do not weigh as much as the URL.

## 4. The discovery: the field that decides is the URL, not the prose

All **16 rows above us for the word "whale"** have `whale` in the host or the path:
`mcp.dropenginehq.com/api/analyze-whale-activity`,
`bess-x402.onrender.com/v1/crypto/whale-transfers`,
`whale.lonestaroracle.xyz/whales`, `whale.hugen.tokyo/whale/movements`,
`402.com.tr/api/x402/whale-flow`, `apexfaucet.xyz/api/x402/whale-ticker`…

We named our path **`/api/v1/whaleflow`** — one word. "whale" is not a token in
it. And our live paths today (verified):

```
/api/v1/whaleflow              402      /api/v1/whale-flow              404
/api/v1/signal                 402      /api/v1/trading-signals         404
/api/v1/verify-seller          402      /api/v1/seller-check            404
/api/arb/opportunities         402      /api/v1/arbitrage               404
/api/sales                     402      /api/v1/onchain-sales           404
/api/stats                     402      /api/v1/crypto-market-stats     404
/api/bot-status                402      /api/v1/bot-health              404
```

We are #1 for: `kristo`, `Kristo Intelligence`, the host, `whaleflow`,
`get_whale_flow`, the combination of our tags. That is, we are found **only by those
who already know our name** — which is not discovery but an address book.

## 5. Agents pay an agent to recommend an API to them

At the top of the HTTP half: `api.agents-trust.com/recommend` —
*"API recommendation and x402 discovery for your task. Required query: need. Which
API should I call?"* — **16 144 paid calls, 62 unique payers** over 30 days,
price $0.01. This is the literal answer to "are agents looking for exactly this": yes,
agents pay an agent to tell them which API to call. Whether it recommends us —
has not been checked (it is paid; see the levers).

## 6. The directories outside x402

| place | state | detail |
|---|---|---|
| Official MCP registry | **we are present** | `io.github.hristovdimitri2-hub/kristo-intelligence`, description "DeFi trading signals and market intelligence for Base with x402 pay-per-call access." |
| ↳ search "whale" | **does not find us** | 42 entries / 17 unique, we are not among them — our description does not contain "whale" |
| ↳ "whale flow" / "market data" / "trading signal" | 0 entries in the entire registry | the registry is small and literal |
| Cline marketplace | **we are absent** | 199 servers, we are not among them |
| mcp.so | **we have a page** | `https://mcp.so/server/kristo-intelligence` (34 occurrences of the slug, 16 of `onrender`) |
| ↳ search "kristo" in mcp.so | **does not find us** | returns AgentCrush, kristofferv98 — not us |
| Smithery | **unverifiable** | the URL from `DISTRIBUTION_STATUS.md` gives 404; the site's scheme has changed, a browser/account is needed |
| Glama | live | the page answers 200 |

## 7. Levers, ordered by measured strength

1. **URL lexicon (strongest, measured).** Give the seven endpoints paths with the
   buyer's words, separated: `/api/v1/whale-flow`, `/api/v1/crypto-market-stats`,
   `/api/v1/trading-signals`, `/api/v1/arbitrage-opportunities`,
   `/api/v1/onchain-sales`, `/api/v1/bot-health`, `/api/v1/seller-check`.
   The same prices, the same `payTo`, the same data — only the name of the path
   changes. For them to enter the catalog: 7 settlements × $0.003 = **$0.021**.
   Verification: the same probe with `do_buyers_words_find_us.py` afterwards.
2. **The description in the official MCP registry (free).** "DeFi trading signals and
   market intelligence" contains neither "whale", nor "on-chain sales", nor
   "seller verification" — that is why a search for "whale" gives 17 others and not us.
3. **Surface (measured pattern).** Whoever wins in our niche holds a **fleet of narrow
   rows**: `api.signalfuse.co/v1/signal/BTC|ETH|SOL|DOGE|OP` (11+ rows),
   `api-xpay.com` with eight trivial endpoints (`/time`, `/uuid`, `/random`, `/ip`,
   `/ping`…) at ~5 500 calls and 200+ payers each. We have 7 broad rows.
4. **The paid discoverer.** $0.01 to ask `agents-trust/recommend` with
   "I need whale flow on Base — which x402 API should I call?" and see whether it
   recommends us. 62 payers/month means that this is a channel with measured demand.
5. **The owner's radar** as demand interception: its log shows that
   the demand in public threads is (a) data endpoints for trading agents and
   (b) preflight/verification of endpoints. (b) is literally `verify_seller_receiver`.

## 8. What is NOT the solution

- More listings. We are already in CDP (7 MCP + 7 HTTP), PayAI, mcp.so, Glama, the official
  registry. Adding one more catalog does not create demand.
- Rewriting the prose. Descriptions are indexed, but they lose to the URL; phrases from
  our own description do not find us.
- Waiting. The niche is 0.68% of turnover, and the best in it has 15 payers per month.

## 9. The honest boundary

Even perfect execution of points 1–3 leads to **single-digit payers**, because
that is how many our neighbors have. The measure remains **distinct external payers per week**
(now 0 as of 2026-11-02). The catalog is the entry ticket; demand is won with lexicon and
surface, not with presence.

## 10. Measured after lever 1 (URL lexicon), 2026-11-10

Lever 1 has been executed: five alias paths to the same data, the same prices, the same
`payTo`. **Four** settlements were paid = **$0.016**; `/api/v1/seller-check` is
deliberately unpaid (price $0.10 — 33× the rest).

The same probe, the same queries, `limit=20`:

| query | before | after |
|---|---|---|
| whale flow | absent | **#11** |
| whale flow base | absent | **#13** |
| track large usdc transfers | absent | **#11** |
| whale alerts | absent | **#13** |
| onchain sales | #1 | **#1 + #2** |
| sales analytics crypto | absent | **#4 + #5** |
| arbitrage opportunities | #3 | **#3 + #14** |
| arbitrage base dex | #3, #11 | **#3, #8, #11** |
| find arbitrage | absent | **#7 + #15** |
| trading signal | absent | **#12** |
| crypto trading signals | absent | **#12** |
| buy sell signal | absent | **#7** |
| verify seller | absent | absent — `seller-check` is not paid |

**The positions are held by the aliases, not by the canonical paths.** Verified
explicitly — which of our URLs carries each new position:

| query | which of our URLs wins |
|---|---|
| whale flow / base / large usdc transfers / whale alerts | `/api/v1/whale-alerts` |
| trading signal / crypto trading signals | `/api/v1/trading-signals` |
| arbitrage opportunities / arbitrage base dex / find arbitrage | `/api/v1/arbitrage-opportunities` (already **#1**) |
| onchain sales | `/api/v1/onchain-sales` (**#1**) + `/api/sales` (#2) |

That is, **the name of the path** won, not the prose in the description — exactly as we
measured in §4. Two hours later the same probe gives even better positions
(`whale flow` #8, `whale flow base` #6, `track large usdc transfers` #3,
`whale alerts` #5, `arbitrage opportunities` #1, `find arbitrage` #1,
`trading signal` #7, `crypto trading signals` #2) — the ranking at 11–16 rows is noisy.

**Two corrections to previously recorded beliefs:**

1. `https://api.agents-trust.com/inspect` **is not a reliable test for indexing.**
   It returns `404 ENDPOINT_NOT_INDEXED` for all four paid aliases, while
   the same URLs hold #1 in CDP search. Its own crawler is
   separate from the CDP index — as an oracle for "are we in the catalog" it does not work.
2. The full crawl of `type=http` is **completely reliable if requested correctly.**
   I recorded earlier that it is fragile, because on two out of three runs the network failed and
   the result looked like "only 7 of our rows". The reason was not the catalog, but my
   method: `limit=20` makes 1637 requests and some fail. `limit=1000` is accepted
   (above 1000 it gives HTTP 400), so the entire market of **32 737 rows is read with 33
   requests** — without a single odd offset, without duplicates, `pagination.total`
   matches exactly. The error was mine, not the data's.

The conclusion for §8 is confirmed: the lexicon works, the presence does not. But a position in a
list of 11–16 rows next to a neighbor who has 2 payers is still not distribution.

## 11. Lever 2: `/api/v1/seller-check` — paid and measured

The owner approved $0.10 (one-time), even though it is 33× the rest: this is
the only niche in which the neighbors have **real** payers. Paid and confirmed
on chain; the balance of the demo key became **$1.443515**.

The row entered the catalog. The position, however, is **last**:

| query | rows | our position |
|---|---|---|
| seller check | 17 | **#17** |
| seller-check | 15 | **#15** |
| seller verification | 14 | **#14** |
| verify seller | 9 | absent (below the cutoff) |
| is this seller legit | 5 | absent (below the cutoff) |

This is the measurement worth recording: **`tokencheck.402api.dev/v1/seller-check`
has literally the same words in its path and is #1.** The difference is not the lexicon — that is
already proven. The difference is the usage signals: the neighbor has 2 payers and 2
calls, we have 1 (our own listing). **A payment buys entry, not rank;
rank is bought with payers.** That is also why the 11–16 rows from §10 are a ceiling, while
there are no external payers.

One side observation from the payment itself: the paid call returned **HTTP 400
`receiver_required`** — because `/api/v1/seller-check` inherits the canonical
`/api/v1/verify-seller`, which requires `?receiver=`. This is the honest guard of the
product, not a defect in the payment (the money settled, the nonce is on chain), but it
means that an agent that discovers us in the catalog and calls us without a parameter pays
$0.10 and gets an error. If anyone ever pays that row, the first thing to fix is
this.

## 12. How payers are won — measured on the entire market (32 737 rows)

A full read of `type=http` with `limit=1000`: 32 737 rows, 3 251 hosts, without
unread offsets. This is the most important measurement in the document, because it answers the
question that really stops the business.

**The distribution is brutal.** The median is **1 payer per row**. 60.7% of the rows
have exactly one. Only **249 rows (0.761%)** have ≥20 payers; 100 rows have ≥50;
64 rows ≥100; the maximum is 678. The top 50 rows by payers sit on **eight hosts**.

**What wins payers is the opposite of what we do:**

| trait | top 50 rows | the rest of the market |
|---|---|---|
| has `serviceName` | **30%** | 64% |
| ≥3 tags | **26%** | 58% |
| description ≥200 characters | **6%** | 55% |
| description <40 characters | **18%** | 2.3% |
| `bazaar.category` | **0%** | 5.5% |

The winners are single-line primitives — "Health check ping" (219 payers),
"Current server time in UTC" (212), "Generate a random UUID v4" (211). We have
long, rich, thematic descriptions — exactly the opposite of what wins.

**Three hypotheses that turned out to be false:**

1. **Publishing machine-readable documents is not an advantage.** Verified
   live and validated by content: top hosts 91/100, the middle class 93/100.
   This is entry, not a differentiator.
2. **Search rank does not correlate with payers.** A symmetric test: 12.5% of
   top hosts appear for 25 generic queries, versus 22.2% of a control
   group with <20 payers. Search is won by mass-listing factories, not by
   the leaders by payers.
3. **Price is almost irrelevant.** Spearman(price, payers) ≈ −0.22…−0.24.
   Registering hundreds of hosts also loses: a single operator holds 296 hosts and
   his maximum is 7 payers.

**The only clear flag with a large effect: `curated: true`.** 65 rows carry it —
**30.8% of them have ≥20 payers versus 0.76% of the market, ≈40× lift**. The curated
hosts are recognizable brands (nansen, messari, exa, zerion, coingecko,
coinmarketcap, tavily). It is neither necessary nor sufficient (the row with 678 payers
is not curated), but it is the only **explicit** trait we measure.

**Position in the catalog is the strongest correlation, but the direction is unproven.**
57.8% of the rows with ≥20 payers are in the first 200; 83.5% in the first 1000; not a single one
is after 19 419. Verified that the feed is not sorted by payers or activity. It cannot
be ruled out, however, that position **follows** payers instead of creating them —
the most likely explanation is age: the first rows were listed earliest and have
accumulated one-time payers over months. That is why I do not accept position as a lever.

**Payments are one-time.** The median `calls/payer` is **1.00**, and for the
top 10 rows it is 1.00–1.03. "Many payers" is not retention, but many different wallets
with one payment each. Nobody comes back.

**What follows for us.** Levers 1 and 2 (URL lexicon, search rank) work
measurably — but search rank does not correlate with payers. So we improved something real
and it is not the most important thing. The only proven lever is **curation by CDP**, and
it requires ≥99% uptime for 30 days — which takes us straight into the memory problem.
Our detailed descriptions are an obstacle, not an advantage: the winners are under 40 characters.

## 13. Who has actually paid us — read from the chain (2026-11-10)

Until now "0 external payers" was written. That was true only for the last week.
The full read of incoming USDC transfers to the receiver (96 transfers, the window
covers from 02.09 onward) gives **15 distinct senders**:

| what | addresses | amount |
|---|---|---|
| our demo key | 1 (`0xe50c…`) | **$0.794** |
| recognized machines (crawler/canary, by `KNOWN_PAYERS`) | 5 | $0.074 |
| **"human customers" by our own documentation** | 2 (`0x4db7`, `0x902dcf34`) | $0.008 |
| unclassified | 7 | $0.044 |
| **total outside our key** | **14** | **$0.126** |

The most recent external payment is **2026-11-02** (`0x9a1066fe`, $0.003).
The two human customers paid on 06.09 and 12.09.

**The channel is not CDP.** Every one of our pages in CDP shows `payers=1`, while the latest
calls are our own (9–10 November). The payment from 2 November is not in
CDP — so it went through **another rail** (most likely PayAI). This is the important
conclusion: **all of our external payments have come from outside the catalog that
we optimized.** The work on levers 1 and 2 improved our position in CDP, but CDP never
brought us a payer.

**The honest boundary:** "external agent" includes machines, and machines pay for many
services — that is why the project itself tracks them as a separate class and does not count them as customers.
The 7 unclassified ones are not yet fingerprinted (the threshold is 50 distinct receivers), so
I do not know whether they are new customers or new crawlers. To call them customers without a
fingerprint would be exactly the mistake that this document describes.

## 14. Verification of our own claims from §12–13 (2026-11-10)

I read the **official CDP documentation** (`docs.cdp.coinbase.com/x402/seller/
get-discovered`) instead of relying on my own conclusions. The two claims in §12–13
that determined priorities turned out to be false.

### 14.1. Memory is NOT the blocker — availability is ~99.95%, not ~98.3%

§12 said: "the only proven lever is curation, and it requires ≥99% uptime for
30 days — which takes us straight into the memory problem". That was an **estimate**
(kills per hour × an assumed restart length), not a measurement. I measured
the same thing from the data we already have — the probes that Render makes are
recorded in the gunicorn log:

```
10.233.16.27 - - [10/Nov/2026:15:32:22 +0000] "GET /health HTTP/1.1" 200 445 "-" "Render/1.0"
```

| what | measured |
|---|---|
| probe interval (quiet hour, 71 probes) | median **5.0 s**, p90 6.0 s, max 6.0 s |
| responses other than 200 around the 5 OOM kills | **0** |
| windows without a single missed probe | **3 of 5** |
| missed time, total over 70 minutes | **~43 s** → ~8.6 s per incident |
| at 5 incidents/day | 43 s/day = 0.05% of the day |
| **availability (proxy by probes)** | **≈ 99.95%** |

The threshold for priority placement is >99.5%. We are above it. **The question of
memory remains real (5 kills per day), but it is no longer on the critical path.**

*Honest boundary:* this is `/health`, while CDP probably measures the paid URL itself. And
the two are the same process, so the downtime is shared — but this is a **proxy**, not
CDP's number. The first version of this check measured "seconds between two
arbitrary lines in the log" and gave 66% unavailability. That is the wrong question: a quiet
process justifiably writes nothing for minutes. A metric that declares the service
dead for two thirds of the day while it answers with 200 is not conservative,
it is a different metric.

### 14.2. Two defects in the listing, and both documented

**The icon was in an unsupported format.** The documentation, verbatim: "Supported
formats are JPG, JPEG, PNG, WebP, and GIF. SVG is not supported." We
published `/static/icons/kristo.svg` — the only format that the catalog
rejects. We also had a test that **guarded exactly this** (`test_icon_url_asset_serves_svg`).
A test can lock in a bug just as well as a fix.
Now `iconUrl` is a 512×512 PNG, generated by `scripts/make_brand_icon.py` (so that it is not
a binary file that nobody can reproduce), while the SVG remains the favicon
of the site — the browser is not Bazaar.

**Not a single one of the 12 paid paths said WHEN to use it.** This is an
explicit metadata requirement for curation and is an input for ranking: "Write a
natural-language description of what the endpoint does and *when to call it*."
I measured the market: of **33 392** rows, **9.3%** have such a phrase. We were in
the remaining 90.7% — 17 of 19 rows. Now 12 of 12.

**The 500-character ceiling is not for ranking, but for the money.** Above it the facilitator
rejects `verify` AND `settle`: the payment itself is lost, not just the position. Our
12 descriptions are now 176–389 characters.

Three new guards protect this (`tests/test_listing_says_when_to_use.py`), and
I verified that they really catch the defect: against the 10 old descriptions the first one fails
10/10, while against the two that already had the phrase, it passes.

### 14.3. Correction to §12: "the winners are under 40 characters" is a correlation, not a mechanism

§12 concluded that our detailed descriptions are an obstacle. The data do indeed show
that the top rows have short descriptions — but the documentation says the opposite:
a description that says what the endpoint does and when to call it **raises**
the quality of the metadata, while "bare names and placeholder text" give zero.
The simplest explanation for short descriptions among the top rows is the age of the
listing, not quality. I do not change the product based on a correlation when there is a
documented rule.

### 14.4. What this means for the goal

We now cover all five documented requirements for curation:

| requirement | state |
|---|---|
| live x402 payments on mainnet | ✅ 14 external senders, $0.126 |
| availability ≥99% for 30 days | ✅ measured ≈99.95% |
| passes health probe | ✅ 0 non-200 responses |
| passes `validate` | ✅ 12/12, `outcome=accepted` |
| agent-ready metadata | ✅ fixed today (§14.2) |

Curation, however, remains **editorial**: "Meeting these qualifies an endpoint for
review — listing remains editorial, based on service quality, category coverage,
and ecosystem fit." There is no application form. So the channel is not yet
automation, but an argument before CDP and landing in a category they want to
cover. This is also the answer to the question "how are the first external payers won":
not through more search optimization, but through curation, and curation is granted.

**What is still not proven:** that curation will bring payers. 65 curated rows,
30.8% of them with ≥20 payers versus 0.76% of the market (≈40×) — but the sample is 65 rows
and the direction (curated → payers or payers → curated) is not established.

**Next steps.** (1) One paid call through the CDP facilitator, to
refresh the catalog entry with the new metadata — the description that Bazaar
records comes from `paymentPayload.extensions.bazaar` at settle, not from a free
crawl. (2) A request for curation with the evidence from the table above.

### 14.5. The paid refresh — done, and what the facilitator answered

I made one paid call to `/api/v1/whaleflow` ($0.003) after the deploy,
because without it the new metadata exists only in our 402, not in the catalog
entry. First a dry run (amount, `payTo`, signer, signature recovery —
everything matches), then payment:

| what | value |
|---|---|
| HTTP | **200** |
| tx | `0xa2864c7269e000bdf29884cc0a29d55783942875040e6db4b3d3df128ad94083` |
| payer | `0xE50c…` (our demo key) |
| `EXTENSION-RESPONSES` | **`{"bazaar": {"status": "processing"}}`** |
| wallet before → after | 1 443 515 → 1 440 515 atomic ($1.443515 → $1.440515) |
| receiver before → after | 920 000 → 923 000 atomic |

**This is the first live reading of `EXTENSION-RESPONSES`.** The documentation describes it
as the way to find out whether the claim was accepted: `success` (validated
and cataloged), `processing` (accepted, cataloged asynchronously), `rejected`
(rejected — see `rejectedReason`). We got **`processing`**, that is, our
claim **is not being rejected** — it passes the schema and the content check
on submission. (If it had been `rejected`, that would have been a concrete defect with a concrete
reason; it is not.)

Indexing takes up to 15 minutes per the documentation, so "submitted" is not
"recorded" — the entry is checked separately after the window.

**Checked after the window: the catalog took the new metadata.**

| row | description in the catalog | was |
|---|---|---|
| `/api/v1/whaleflow` (paid today) | **278 characters, with the phrase "Worth reading when…"** | 192 |
| the remaining 18 rows | the old texts (83, 95, 110, 123, 154, 158, 162, 190, 239, 258, 297) | — |

This is the important thing: **the refresh is per row and is triggered by settle, exactly as
the documentation says** — one paid row changed, eighteen did not, with one and the
same deploy. So the metadata is not propagated by crawl, but by payment.

The cost to refresh the remaining 9 HTTP rows that do not yet have the phrase is
**$0.039** (6 × $0.005 + 3 × $0.003). `/api/v1/verify-seller` and
`/api/v1/seller-check` ($0.10 each) already have the phrase and would win only one
sentence — I am leaving them. Separately, **every row must have at least one
payment per 30 days, otherwise it drops out of the catalog and out of search** — this is a constant
expense (≈$0.036/month for 12 rows), not a one-time one.

## 15. Why CDP shows `payers=1` — corrected twice in one day (2026-11-10, late)

§13 left a question: the external payments exist on chain, while CDP shows
`payers=1` on every row of ours. The first explanation I wrote here was that
PayAI settles instead of CDP and that is why CDP does not see our money. **It does not hold.**
I am keeping both the error and the correction, because the way it broke is more useful
than the conclusion itself.

### 15.1. The first version, and why it was wrong

I relied on one line from the log — the most recent external payment (04.11 02:46 UTC):

```
standard x402 settled via payai: tx=0x2ca6e79f46943070f8d903f028c14fbf72e47bea…
```

and from it I concluded: the default chain in `services/connectors.py` is
`[payai, cdp]`, PayAI is first, so CDP never sees anything of ours, hence
`payers=1`, and therefore curation is structurally unattainable.

**One line is not a measurement.** I checked all the settlements we have in our logs,
and **every single one since 09.11 says `settled via cdp`** — ten events
(09.11: 14:14, 15:11, 16:29, 16:30 …; 10.11: 08:12:53, 08:12:57, 08:13:00,
08:13:04 …), zero `settled via payai`. The line from 04.11 is the only exception in
our entire history and it predates the changes along the verification path.

### 15.2. What the application actually does

The full sequence of one paid call, 10.11 08:12:52–53 UTC:

```
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
```

Three things we did not know:

1. **Verification is local.** `_local_recover_signer` + "canonical EIP-712, no
   facilitator needed for verification" — during verify there is no talking to the
   facilitator at all. That is why "the chain `[payai, cdp]`" does not describe the settlement.
2. **Self-broadcast has been broken for months.** The gas wallet
   `0x9c1eb97e121a6836200C539a1BF0ecdC37F750dd` has **0.00000000 ETH** (verified
   on chain too), so our own broadcast always fails and the flow
   continues downward.
3. **CDP is the rail that actually settles** — and successfully, in ~1 second.

### 15.3. The corrected conclusion

**CDP sees our money. It is just that the only payer it has ever seen is
us.** Every one of our 19 rows in the CDP merchant view reads
`l30DaysUniquePayers = 1`, `l30DaysTotalCalls` 1–5, and `lastCalledAt` matches to the
second with our own canaries (`payer=0xE50c5212e8211639C49276dA190E248B83935763`
= the demo key). Aggregate: **34 calls / 19 unique payers over 30 days**, where
the "unique" ones are a sum of 1 per row, not separate people. Rows with ≥2 payers:
**zero**.

So `payers=1` is not a verdict on the rail. It is the exact record of the fact that
**no external payer has ever paid through CDP** — and not that CDP has not seen
our payments. The two statements sound similar and lead to opposite
decisions.

### 15.4. What falls away and what remains

**Falls away:** the need to "activate the CDP rail". It is already active and settling —
`FACILITATOR_CDP_API_KEY_*` are obviously available in the environment, because the JWT is built with
a real `kid=organizations/3dc43ce6-0…/apiKeys/ad07bd0b…` and `PEM=True`. No
owner decision is needed; I am not touching the environment.

**Remains, and is more serious:** our settlement depends entirely on one external service,
because the fallback path (self-broadcast) is disabled by an empty gas wallet.
If CDP drops out in the window of 14 November, there is no second working path. Loading
a little ETH to that address restores the independent path, but that is spending and requires your
decision.

**Remains, and it is the main thing:** the only lever with a large measured effect (§12) is
curation, and it is granted editorially. What CDP sees today is the demo key — that is,
from the platform's point of view we look like a seller who buys from himself.

## 16. Two independent measurers (2026-11-10)

We also registered with **x402dash** (`POST https://api.x402dash.com/v1/register`),
where until today there were 1 895 providers and **not a single one was ours** (`/v1/providers?q=kristo`
→ 0). The first 4 endpoints were accepted, HTTP 201, `verified: true` (the remaining 8
are waiting for the 5/hour limit):

| endpoint | result |
|---|---|
| `/api/v1/whale-alerts` | registered, verified |
| `/api/v1/trading-signals` | registered |
| `/api/v1/arbitrage-opportunities` | registered |
| `/api/v1/onchain-sales` | registered |

**x402-list.com has indexed us since 29.10** and gives independent numbers that
correct §14.1:

| their measurement | value |
|---|---|
| compliance | **A, 14/14 checks, zero failed** |
| `payment_ready` | true |
| `verified` | **false** (their FORTE layer pays for a real x402 call — only 13 of 1 271 services) |
| `reliability_uptime_30d` | **98.6%** |

Day by day: **11-09 and 11-10 are 100%**, while the entire deficit is in **11-07 (92.13%) and
11-08 (89.39%)** — the days of the SQLite/dashboard incidents, before the fixes.
Their check is every ~16 minutes (67–90 per day), so the 8-second
restarts during OOM are practically not caught; the two bad days were ~2 hours of real
downtime each.

**Correction to §14.1:** there I wrote "≈99.95%, memory is not a blocker". That was a
measurement over one day and 70 minutes. A third party measures **98.6% over 30 days**.
The truth is in between and more useful: **today and yesterday we are at 100%, while below 99% we are
held by two specific days that are before the fixes.** The memory question is not
closed — it is "currently healthy, historically below the threshold", and the 30-day number
will rise only if 07–08.11 age out without a new incident.

## 17. The first machine buyer that pays without a human choosing us (2026-11-10)

This is the closest thing to an answer to the question "how are the first external payers won",
because it describes a channel in which **a machine pays, not a human**: the Smart Order Router of
`agent402.tools`.

### 17.1. We are already in their index, and that is not the news

`GET https://agent402.tools/api/index?seller=kristo-intelligence-api.onrender.com`:

```
routable = true          health = 1 (the last 5 crawls: [1,1,1,1,1])
toolCount = 22           of them paid 19
networks = [eip155:8453] payTo = 0xd4cdA900…
discoveryPath = /.well-known/x402     lastVerifiedAt = 2026-11-10T18:45:52Z
routerDispatchEligible = false
routerDispatchReason   = settlement_required — "below the settlement floor"
```

Registration is not needed: they crawl `/.well-known/x402`, discover 22 routes and
check the liveness of each every 30 minutes. Their only paid seller entry point is
`POST /api/index/register`, which returns `400 bad-request` for us — because we are already
in the index.

### 17.2. What `settlement_required` means

From their own legend:

> on Base the router pays sellers with on-chain settlement history above the floor
> from enough distinct payers; a seller below it is tried only under the small
> unproven ceiling **when its verdict carries unprovenTier**.

Line by line, our $0.003 and $0.005 routes carry:

```
routerDispatchEligible      = false   (reason: settlement_required)
executeViaCallableNow       = true
executeViaLane              = "unproven"
unprovenTier                = true    unprovenMaxUsd = 0.05
```

And our **$0.10** routes (`/api/v1/verify-seller`, `/api/v1/seller-check`) carry:

```
executeViaCallableNow = false      (without unprovenTier — above the ceiling)
```

**That is: the $0.10 price mechanically excludes us from the only channel with machine
buyers.** The threshold for an unproven seller is **$0.05 per call and $0.25 per day**,
and only after all verified sellers for the task have been skipped.

Their ranking (7-day window, 3 800 crawled sellers, 33 391 rows in Bazaar)
shows how far "verified" is: 50th place is `www.blockchainiq.co` with **93
calls / $21.23 / 18 buyers** per week, while the first is 630 596 calls and
$12 382 with 1 689 buyers. We are not in the top 50 (34 calls over **30 days**, almost
all of them our own).

By comparison, a seller that is `eligible: true` — `x402.ottoai.services`, 74
routes, `{"eligible": true, "reason": "eligible"}`.

### 17.3. Why I did not trigger a payment artificially

`POST /api/route/execute` is a documented channel in which **their router itself
buys the result from an external seller** and resells it to us. Technically I could have
called it with a task that matches one of our routes, and the router would pay to our payTo
$0.003 — the first external payer of the day.

**I did not do it, and the reason is one of principle.** It is self-funding through an
intermediary, and both platforms check for it explicitly: AgentCheck advertises
"who has real repeat buyers and **who funds their own customers**", while agent402 has
an entire rule `settlement_self_funded` — "a payment made with USDC that the wallet
it pays had sent the payer earlier is the seller's own money coming home and does
not count". A payment we arranged ourselves is not an external payer; it would
pollute the only number that the goal measures.

### 17.4. What follows from this

The channel is real and it is machine-driven — `/api/route/execute` pays external sellers with
its own wallet. To enter its paid part, two things are needed, and both are already
on the table:

1. **the price** — $0.10 is above the ceiling of the unproven layer; $0.003–0.005 are within it;
2. **genuinely distinct payers** — the "settlement floor" is the same wall that the
   goal also measures.

In parallel: their documentation says that the router ranks by **matching the
description to the task** — "an accurate description is how you win it". That is, the
descriptions are the lever we have already started to fix, not a new one.


## 18. Correction to §17: price is NOT the gate, and our own payments buy nothing (2026-11-10, even later)

§17.2 ends with the sentence "the $0.10 price mechanically excludes us from the
only channel with machine buyers", while §17.4 ranks "the price" as the first of the
two necessary levers. **This is wrong and is withdrawn.**

### 18.1. How to measure correctly

The router accepts `top: 25` (although `limit: 25` is ignored) and then returns not 5
but 25 candidates — enough to see not only who wins, but also with which flag
they enter. The task "whale flow on Base: USDC transfers over 5 million" with `top: 50`:

| task | our rank | price | `routerDispatchEligible` |
|---|---|---|---|
| live DeFi trading signal for ETH | **1/5** | $0.003 | **false** |
| arbitrage spreads between Base DEX venues | **1/5** | $0.005 | **false** |
| audit incoming USDC payments of any Base address | **1/5** | $0.10 | false |
| is this x402 seller really being paid… | **1/5** | $0.10 | false |
| on-chain USDC sales and revenue history | 3/5 | $0.005 | **false** |
| verify a seller before paying it on Base | 5/5 | $0.10 | false |

Six rows, three first places, three different prices — and for all six
`routerDispatchReason = "settlement_required"`.

### 18.2. Three independent proofs that price does not decide

1. **Our $0.003 row is #1 and is still `false`.** If the $0.05 ceiling were the gate,
   this row would be `true`.
2. **The same price, opposite verdicts** — measured on 200 rows from 8
   tasks: at $0.001, $0.002, $0.003, $0.005, $0.01, $0.02, $0.03, $0.05, $0.10
   and $0.15 there are both `eligible: true` and `eligible: false` rows.
3. **The number of payers is not the gate either.** Among `eligible: true` there are **5 rows with exactly
   1 payer** (e.g. `insider` on FilingsPulse — $0.10, 1 payer, 14 calls,
   `eligible: true`, the same price as our `verify-seller`). Among `eligible:
   false` there are rows with up to **304** payers.

### 18.3. Our own payments buy nothing

Traced on chain over the last 800 000 blocks of Base:

```
payer -> receiver    47 payments, 0.7590 USDC, blocks 55 082 300 .. 55 712 490
receiver -> payer     0
anyone -> payer       0        (the demo wallet has not received USDC in this window)
anyone -> receiver   47        and all of them are from the demo key 0xE50c5212…
```

That is, the literal reading of their rule `settlement_self_funded`
("receiver has sent to the payer") does **not** explain the refusal — there is no such transfer. But the
conclusion is worse than the explanation: **47 own payments and zero open gate.**
Whatever the condition is, it does not count our own money and is not bought
with it.

### 18.4. What remains true and what follows

Withdrawn: "$0.005 pilot makes `verify-seller` routable". It does not —
our $0.003 is already #1 and is still excluded.

Remains true: the router is a real machine channel and **already ranks us first for 4 of
10 real tasks**, but does not dispatch us. The gate is the quality of the settlement
history, which **cannot be self-produced** — so the first external payer cannot
come from there. It must come from a surface that **does not check
our history in advance**, but chooses by name and description: search in the CDP
catalog, `x402scan`, AgentCheck. There we are already #1 for our own name and
absent for the words the buyer writes — and that is the lever that remains.

Price does not disappear as a question, but it changes its role: it does not open the machine
channel, but decides whether the buyer will choose us in the catalog, where 163 competitors for
"is it safe to pay" have a median of $0.010, while we ask $0.10.


## 19. CDP search does NOT read the URL — it reads `tags` and the description (2026-11-10, late)

§17 and §18 leave one lever: discoverability in the catalog. This section shows exactly how
it works and what was broken on our side.

### 19.1. The proof that cannot be explained otherwise

We search the CDP catalog for the string **"verify seller"**. Our resource is
`/api/v1/verify-seller` — the string is literally a substring of the path. If the ranking
read the URL, this row would be first. **It is not among the nine returned rows at all.**

And the row that is second for the same query is `/api/v1/seller-check` — **the same
handler, the same price, the same service**. The only difference between the two rows is
what they say:

| | `tags` | description (the beginning) |
|---|---|---|
| `/api/v1/verify-seller` | `crypto, whale-tracking, x402, arbitrage, signals` | "On-chain audit of any Base address you name…" |
| `/api/v1/seller-check` | `seller-check, seller-verification, x402-seller, onchain-audit, base` | "Check whether an x402 seller is really being paid before you pay them…" |

The winner for each query contains the buyer's words **verbatim** in `tags` or in the
description: `dex-arbitrage` for "dex arbitrage", `seller check` for "seller check",
`is this token safe` for "token safety".

### 19.2. What else was broken: seven identical rows

`X402_RESOURCE_TAGS` had entries only for the five aliases. All **seven
canonical** paid routes fell back to `X402_DEFAULT_RESOURCE_TAGS` and published
the same five words — `crypto, whale-tracking, x402, arbitrage, signals`. Not one
of the five is the work that the respective route does. Our most expensive route
(`verify-seller`, $0.10) was found by the words of someone else's work.

Measured on 20 queries with buyer intent, top 20 rows: **we appear for 11 of
20 — and every time through an alias**, never through a canonical route.

### 19.3. The fix

Every canonical route now carries its own five `tags` and a description that **begins with
the words with which the work is searched for**, and then states the honest scope (the dash is not
changed):

```
/api/v1/verify-seller   verify-seller, seller-audit, x402-seller, payment-evidence,
                        due-diligence
                        "Verify an x402 seller before you pay it — a seller audit on chain: …"
/api/v1/whaleflow       whale-flow, whale-transfers, large-transfers, smart-money, base
/api/v1/signal         defi-signals, trading-signals, market-signal, crypto-signals, base
/api/bot-status        telegram-bot-status, sales-bot, heartbeat, uptime, service-status
/api/arb/opportunities dex-arbitrage, price-spread, cross-venue, defi, base
/api/sales             usdc-revenue, onchain-sales, settlement-history, payment-history, base
/api/stats             service-stats, usage-stats, market-snapshot, fear-and-greed, base
```

The two honest boundaries are preserved and are now **tests, not intentions**: `/api/stats` must
not claim "market stats", because it does not return market capitalization and volume, while
`/api/bot-status` continues to say that it is for **our** bot, and not a general check of the
buyer's bot.

### 19.4. What must be checked next round

CDP already shows the new descriptions (the 10.11 upgrades with "when to use" are visible in the
catalog rows), so it re-reads the live 402 and there is no need to pay for a
refresh. **§20.1 corrects exactly this sentence** — it turned out that CDP snapshots the 402
at settlement, not at crawl. The claim that remains to be measured is whether
after the fix `/api/v1/verify-seller` enters the results for "verify seller" and
whether the canonical rows win positions that until now were won only by the aliases.


## 20. The third field: `serviceName` was the same for all twelve (2026-11-10)

§19 fixed `tags` and the description. The third field remains, the one that CDP returns for each row and
by which it also searches: `serviceName`.

**It was hard-coded.** `main.py` published `"serviceName": "Kristo Intelligence"` for
every paid route. A company name does not match a single word that the buyer
writes. In the CDP index, the winning rows are named after their work — "Check an
x402 seller's trust", "x402 seller dossier", "x402 seller check", "PennyAPI x402
Seller Preflight", "Token Safety Check", "Crypto Market Signals" — and **one seller
carries several such names at once** (agent402 has four different
`serviceName` on four routes). So a route name is the normal form, while a single
shared name for twelve rows was the defect.

**The fix** (`X402_RESOURCE_SERVICE_NAMES`, brand + work, within the 32-character limit):
`Kristo x402 seller audit`, `Kristo whale transfers`, `Kristo crypto signals`,
`Kristo DEX arbitrage`, `Kristo USDC revenue`, `Kristo market snapshot`,
`Kristo telegram bot status`, `Kristo whale alerts`, `Kristo trading signals`,
`Kristo DEX arbitrage spread`, `Kristo seller check`, `Kristo onchain sales`.
The test requires every name to be distinct and not to be just the brand.

The descriptions of the three routes that come from `REAL_X402_ROUTES` (and not from
`CHALLENGE_DESCRIPTIONS`) also now begin with the buyer's words — this is also
the text in `/.well-known/x402.json`.

Verified live: **12 of 12** routes publish the new `serviceName`.

### 20.1. When these words reach CDP — and why this matters for the money

CDP **snapshots the live 402 at the moment of settlement** and keeps that copy until the row is
settled again. The proof is in their own rows: `lastCalledAt` of
`verify-seller` is 09.11 07:10 and the description there is the old one from 09.11; `whaleflow` was
settled 10.11 17:47 and carries the text that was live at 17:47 — while the change of
the descriptions happened after that.

The consequences are two, and both practical:

1. the surfaces that **crawl** (agent402 every 30 minutes,
   `/.well-known/x402`) pick up the new words on their own and for free;
2. **CDP — the only catalog in which the buyer chooses and pays — picks them up only
   at the next settlement of the respective row.**

So the refresh is not "maintenance of the live rows", but **the only way
for the fix to reach the place where the choice is made**. Its cost is the cost of the routes
themselves: the ten cheap rows are a total of **$0.042**, while the two expensive ones
(`/api/v1/verify-seller` and `/api/v1/seller-check`) add **$0.20**.

If the price of these two rows drops to $0.01 for the pilot, the same refresh costs
**$0.062** instead of $0.242 — and matches the median of $0.010 of the 163 competitors in
the "is it safe to pay" category.


## 21. Three catalogs, one rule: metadata travels only with settlement (2026-11-10)

### 21.1. There is a second live catalog, and in it we are further ahead

PayAI holds its own Bazaar with search:
`GET https://facilitator.payai.network/discovery/search?query=…&limit=…`. There
our ranking is better than in CDP:

| query | our rank in PayAI | number of rows |
|---|---|---|
| `verify seller` | **1** | 5 |
| `trading signal` | **1** | 18 |
| `telegram bot status` | **1** | 2 |
| `onchain sales` | **1** | 3 |
| `arbitrage` | **1** | 50 |
| `whale flow` | 3 | 24 |
| `whale alerts` | absent | 19 |

Seven of eight queries find us, five of them in first place. This is a surface on
which a buyer can choose us — and until now it was not measured.

### 21.2. But there too the metadata is old — and two of them are broken

PayAI also keeps a copy from the moment of settlement. The proof is stronger than
a date: the rows `/api/sales` and `/api/stats` there still carry the **placeholder**
"`Kristo Intelligence - paid API data (/api/sales)`" — text that the code stopped
producing on **05.11**. So the copy is from before that fix and has not been
refreshed.

In practice: in PayAI's live commercial catalog, two of our rows still present themselves with
a sentence that says nothing about the product. The same two rows in CDP are also from 09.11.

### 21.3. The free validator does NOT refresh (verified, not assumed)

The only free entry point to CDP is the validator
(`POST https://api.cdp.coinbase.com/platform/v2/x402/validate`, body
`{"resource": …, "method": "GET"}`). It answers `valid=true` for our routes —
but it does not touch the recorded copy. The experiment: three test rows, validated once each,
and two **control** rows that were not validated; after 12 minutes, a comparison.
Result: **not a single row changed, neither test nor control.**

So there is no free way to publish the new words. Publishing has a cost.

### 21.4. The exact price of publishing

| what | rows | price |
|---|---|---|
| only the cheap HTTP rows | 10 | **$0.042** |
| all 12 HTTP rows | 12 | **$0.242** (of which $0.20 are the two seller-audit rows) |
| all 19 rows (with the 7 MCP) | 19 | **$0.368** |
| the same, if the three $0.10 rows become $0.01 | 12 / 19 | **$0.062** / **$0.098** |

The tool already exists, no new one is being written:
`scripts/phase1_paid_call.py --path <path>` makes exactly one paid call, so
the refresh is once per row. Without an explicit "yes" from the owner, nothing is
executed and nothing is spent.


## 22. What is paid TODAY — measured, not judged (2026-11-10)

The pricing decision hung on one number: the median of $0.010 among 163 competitors in
the "is it safe to pay" category. A median over all rows, however, is not the
same as a median over the rows that someone **actually paid for recently**.

Therefore: I took 12 000 rows from the CDP catalog (12 pages of 1000, `type=http`) and
split them into paid in the last 48 hours and untouched. `quality.lastCalledAt` is
the date of the last payment, so this is a direct measure.

### 22.1. The numbers

```
12 000 rows, paid in the last 48 hours: 2 325 (19.4%)
  median price of the paid ones:  $0.0085   (p25 $0.0028, p75 $0.0200)
  median of payers:               3         (72.8% have >=2 payers)
  across all rows:                66.1% have >=2 payers
```

Share of paid rows by price band:

| price | rows | paid ≤48h |
|---|---|---|
| $0.001–0.005 | 4 141 | 17.2% |
| **$0.005–0.01** | 1 823 | **25.7%** |
| $0.01–0.02 | 2 146 | 22.0% |
| $0.02–0.05 | 1 541 | 21.0% |
| $0.05–0.099 | 968 | 18.4% |
| **≈$0.10** | 470 | **14.3%** |
| >$0.10 | 847 | 11.1% |

### 22.2. What this means for our $0.10

**$0.10 is paid — but less often.** In the band around $0.10, 14.3% of the
rows are paid versus 25.7% in the $0.005–0.01 band, that is, **about half the chance**.

And more specifically, in our category (tags containing security/audit/safety/trust/
risk): **170 rows were paid recently, of which 46 at $0.01 and only 10 at $0.10.**

So the $0.01 pilot is not a matter of taste, but the place where the largest group of
bought rows in our category is found — and where 46 versus 10 rows means that
the buyer compares within that band.

### 22.3. Separately: the median of payers is 3, and we have 1

72.8% of the recently paid rows have **≥2** distinct payers (66.1% of all
rows). Our twelve rows have 1 each — below the norm by which the router ranks
(§18) and by which AgentCheck counts buyers.

### 22.4. The limitation of the measurement

The sample is 12 000 of ~33 000 rows, taken on consecutive pages of 1000 —
it is not a random sample, but a slice. That is why the numbers are read as "in this slice", not as
"in the whole catalog". The direction, however, is consistent in every band and in the category:
the more expensive is paid less often, while $0.01 is the densest paid band in our kind
of work.


## 23. Who looks at us and does not pay — and can a standard client pay us at all (2026-11-10)

Until now everything measured our side (what we publish) or the catalogs (where
we stand). Nothing measured the side that decides the goal: the agent that arrives,
sees 402 and leaves. These requests **are visible** in Render's access log (a request with
a valid signature is not visible; every unpaid one is visible), together with the user
agent.

### 23.1. Three hours of logs: who touches us

1187 access lines in three hours. Distinct user agents that touch **paid**
routes (all of them receive 402):

```
Agent402/1.0                     CarbonMonitor/0.1 healthcheck
x402station/0.1                  AgentRankProbe/0.1 (spark.tail6ec125.ts.net)
alalanet-prober/1.0              SentinelOracle/0.1 (glimind.com)
mcp-health-probe/0.1             agents-trust-probe/1
lumiere-paycheck-prober/1.0      nohumans.directory-probe/1.0
mcpbeat/0.1                      mcptry.com indexer
CreoraPublicReader/1.0           JarvisClaw-HealthCheck/1.0
Mekler-Conformance/1.0           InterfaceDeltaBot/1.0 (interfacedelta.com)
x402-list-monitor/1.0            protogrid-probe/0.1
copilot-cli/1.0.103-unstable
```

That is, **about twenty automated agents crawl us every hour and not a single one
pays.** All of them are catalogs, liveness monitors or rankings — not buyers.
One exception is telling: `nohumans.directory-probe` first downloaded the free
`/sample` routes (200), then the paid ones (402) — that is, there are agents that check
what they will get before deciding.

The public landing pages of these sites do not contain our name in server-rendered
HTML (14 checked), so whether they **include** us in their lists, and not merely crawl us,
remains unmeasured — this is a difference worth a next round.

### 23.2. Can a standard client pay us? Yes — our 402 is in order

The hypothesis "they do not pay us because our 402 is unreadable" has been checked and **falls
away**. The live response for `/api/v1/signal`, `/api/v1/verify-seller` and `/api/v1/whaleflow`:

* the `PAYMENT-REQUIRED` header exists, is decoded from base64 and contains a valid
  v2 object with keys `x402Version, error, accepts, resource, extensions`;
* the header and the body **match on every payment field** — `scheme=exact`,
  `network=eip155:8453`, `amount` in atomic units, `payTo`, `asset`,
  `maxTimeoutSeconds`, `extra={name: USD Coin, version: 2}`;
* `www-authenticate` is also correct.

So the question "should we clean up the three copies of `accepts` and the manual `X-Payment-Proof`"
**is not a blocker** — it is cosmetic. A standard client can pay us today.

### 23.3. The conclusion that these two measurements give together

Discoverability is not the brake. The brake is **being chosen**: twenty agents
see us every hour, nobody buys; in the catalogs we stand in first places for the words
we sell; the 402 is in order. Two levers remain and both are outside the code — the price
(§22: in our category 46 paid rows at $0.01 versus 10 at $0.10) and someone
being asked to try.


## 24. State at the end of the session (2026-11-10, 23:30)

One concluding measurement, so that nothing from here on is repeated.

### 24.1. The number of the goal

```
CDP rows 19   calls 30d 34   distinct values of payers: [1]
rows with >=2 payers: 0
on chain, the last 120 000 blocks of Base:
  0xe50c5212…  2 payments  0.1030 USDC  last block 55 712 490  = the demo key
```

**There is no external payer** — neither in the CDP quality, nor on chain.

### 24.2. What is live and what is frozen

| | state |
|---|---|
| the live 402s (12 routes) | the new `tags`, `serviceName` and descriptions — **published** |
| `/.well-known/x402` and `x402.json` | the new descriptions |
| PayAI Bazaar | **first places** for `verify seller` (1/5), `onchain sales` (1/3), `whale flow` (3/24) — but with the **old text** |
| CDP catalog and search | **frozen** at the copy from the last settlement of each row; that is why we are absent for `verify seller`, `x402 seller audit`, `token safety` |
| agent402 | has **not re-read** the metadata two hours after the deploy |

### 24.3. Correction to one of my claims from §20

In §20 I wrote that agent402 "crawls every 30 minutes" and therefore picks up the new words
for free. **It does not.** Verified two hours after the deploy: its index is byte for
byte identical (32 798 bytes), the names are the old ones (`Kristo Intelligence` ×5,
`Live whale flow` ×3). Its thirty-minute cycle is for **liveness**, not for metadata.

### 24.4. What remains and how much it costs

1. **Publishing in CDP** — the only way for the new words to enter the place where the
   buyer chooses: one paid call per row. $0.042 for the ten cheap ones,
   $0.242 for all twelve HTTP, $0.368 for all 19. Tool:
   `scripts/phase1_paid_call.py --path <path>`.
2. **The price** — §22: in the "is it safe to pay" category, 46 paid rows at
   $0.01 versus 10 at $0.10. If the two seller-audit rows become $0.01 for the pilot,
   publishing costs **$0.062** instead of $0.242.
3. **Someone to be asked to try** — the only channel with a short reaction
   time; requires an explicit "yes" from the owner, because it is external sending.

None of the three can be executed without his decision. Nothing has been spent and
nothing has been sent.


## 25. Executed: the pilot and the publishing — and what it gave (2026-11-11)

The owner said "yes" to the pilot option. Executed and measured the same day.

### 25.1. The price — only deployment, without a code change

`KRISTO_VERIFY_SELLER_PRICE=0.01`, set as a **single** env key on Render
(38 → 39 variables, nothing else changed; the collective `PUT /env-vars`, which
replaces everything, was not touched). `config.py` remains untouched, because the constant already
reads `os.getenv` — so the live 402 **and** the manifests that are built from the same
constant publish $0.01, while the repository keeps its default value and
the test "verify-seller is the most expensive route" remains true.

Note: changing the env **does not trigger a deploy by itself** — an explicit
`POST /services/<id>/deploys` was required. Verified live: the two seller-audit routes ask for
`10000` atomic units = **$0.01**. Revert: 11.12.2026, with a reminder.

### 25.2. The publishing: 12 paid calls, $0.062

| routes | price |
|---|---|
| signal, whaleflow, whale-alerts, trading-signals | $0.003 ×4 |
| arb/opportunities, arbitrage-opportunities, sales, onchain-sales, stats, bot-status | $0.005 ×6 |
| verify-seller, seller-check | $0.010 ×2 |
| **total** | **$0.062** |

Eleven of twelve returned `{"ok":true}` with a tx hash. The twelfth
(`/api/v1/verify-seller`) **paid and did not deliver**: the route requires the parameter
`receiver`, the helper did not supply it and got `receiver_required` — $0.01 for nothing.
Repeated correctly with `?receiver=…` on the alias `seller-check` ($0.01), which
returned `ok:true`.

Verified on chain: 12 transfers from the demo key to the receiver, exactly $0.062.

### 25.3. The result: CDP now finds us

First the metadata. Minutes after the settlements the catalog view still showed the old one;
after ~20 minutes **all 12 rows** carry the new `serviceName`.

Then the search, which is the real measure:

| query | before | after |
|---|---|---|
| `verify seller` | **we were absent** from 9 | **rank 3/11** |
| `x402 seller audit` | **we were absent** from 17 | **rank 4/17** |
| `defi signals` | absent | **rank 1/6** |
| `market stats` | absent | **rank 2/4** |
| `whale flow` | rank 9/12 | **rank 3/13** |
| `whale transfers` | — | rank 3/9 |
| `seller check` | — | **rank 1/15** |
| `telegram bot status` | — | **rank 1/13** |
| `onchain sales` / `usdc revenue` | — | **rank 1/3** / **rank 1/6** |
| `dex arbitrage` | — | **rank 1/14** |
| `trading signal` | — | rank 4/12 |

**12 of 14 queries find us, five of them in first place.** We remain absent only
for `is this seller safe to pay` and `token safety` — and both honestly: we do not give a verdict
"it is safe" and we do not check tokens.

### 25.4. The defect this discovered

A payment to `/api/v1/verify-seller` **without** `?receiver=` takes the money and returns
`receiver_required` — the buyer loses the call. The parameter is declared in the bazaar
extension, so a disciplined agent will supply it, but the refusal is on our side.

**Fixed on 11.11.2026** (after the owner's explicit "yes", commit `e3590b5`).
The rule: **a request we cannot serve is never settled.** The check
is triggered only when there is a payment identifier, because the unpaid GET on the bare
path must continue to return the canonical 402 — that is exactly what the catalogs read in order to
index the route. Verified live:

| request | response |
|---|---|
| bare path, without an identifier | **402** (the catalogs continue to see the challenge) |
| fake identifier, without `receiver` | **400 `missing_required_parameter`** |
| the same through the alias `seller-check` | **400 `missing_required_parameter`** |
| fake identifier, **with** `receiver` | 401 (reaches the check, as it should) |
| route without required parameters | 401 (the check does not apply) |

And the proof with money: a real signed payment without `receiver` returned
`missing_required_parameter`, while the balance of the demo wallet remained **1.378515 USDC**
(1.378515 before, 1.378515 after) — **$0.00 spent**. Before the fix, the same request
cost $0.01 and delivered nothing.


## 26. Dashboard audit: the payment at 02:47:06 — where it is from and whether it is labelled correctly (2026-11-11)

The owner saw it in the morning: `2026-11-11 02:47:06 · $0.003 · market check, robot
— not a customer`, and asked me to check where it is from. Checked along three independent paths.

### 26.1. What exactly happened

From the chain and from the service's own logs:

```
block 55 874 253   tx 0xdc6dea0e…c2cd74b   0.0030 USDC
payer  0xA19F621581DBc851a21D6179868111709a52aCCC
02:46:58  x402 payment required: endpoint=/api/v1/signal, price=$0.003
02:47:04  standard x402 locally verified: payer=0xA19F…aCCC
02:47:06  standard x402 settled via cdp   (x402 settle TOTAL 1.36s)
02:47:06  Recorded real sale: USDC $0.003000
```

That is: **a real x402 payment, for the route `/api/v1/signal`, settlement through CDP in
1.36 s, with a locally verified signature.** It is not an artifact and it is not ours.

### 26.2. The "robot" label is a judgment — that is why I checked it again

The address is in `KNOWN_PAYERS` as `market_crawler_a19f`, and the label was applied on **17.09**
based on the fingerprint at the time: 125 outgoing transfers to 98 distinct receivers over 30 days.
The file itself says "fingerprint first, label second", so the judgment is subject to
revision — especially since this is its **second** payment to us (the first was
09.09).

A fingerprint from today, the last 1 000 000 blocks (2.3 days):

```
508 outgoing USDC transfers to 269 DISTINCT receivers   (~220 receivers per day)
our receiver is among them
```

**The label holds.** This is market infrastructure that crawls the entire market; its
transfer means "we are included in the crawl", not "someone chose us". That is also why
the dashboard shows it as "robot — not a customer", and that is true.

### 26.3. The dashboard numbers are correct

Read from its own API, not from a screenshot:

```
{"date": "2026-11-11", "requests": 11671, "sales_count": 13, "sales_volume_usd": 0.065}
```

13 sales = **12 from our refresh ($0.062) + 1 from the robot ($0.003)**. The sum comes out
exactly and the classification loses nothing: our demo key is a separate class (`own_key`),
the robot is `sampler`, while "real customer" remains empty.

### 26.4. The honest note

By the **literal text** of the goal ("measured with a different payer … on chain") this
payment satisfies it: the payer is different from the demo key and is a real external agent.
By its **meaning** — "one who chooses us" — it does not satisfy it: the same address pays to 269
distinct receivers in two days. Both readings are on the table and the choice is the owner's;
I do not make it instead of him.

A note on CDP: the `quality` block has not yet reflected today's settlements (still
`l30DaysUniquePayers = 1`, `lastCalledAt = 09.11`), although the metadata of the row has
refreshed. So the metadata and the quality are updated on a different schedule.

A new catalog in the logs: `x402rank-probe/1.0 (+https://x402rank.com/methodology)`.

## 27. x402scan.com — does it show us as paid or free (11.11.2026)

The owner's question: if x402scan shows us as free, that makes us
"free" in a catalog with thousands of paid ones and is a real reason not to pay us.

**Answer: it shows us as paid.** Measured with the public tRPC requests that
the application itself uses (`_forensics/what_x402scan_shows_about_us.py`,
read-only, without payment):

* Our server is `https://kristo-intelligence-api.onrender.com`,
  id `0c176841-4de1-4087-906d-e5d41f414ace`, 15 rows.
* **7 rows carry a price** (`< $0.01` for $0.003/$0.005 — their `formatCurrency`
  collapses everything below a cent) and a stored 402 response with `accepts` to our `payTo`.
  All 7 answer 402 on the live host; all 8 free rows answer 200.
* The remaining 8 rows are our documents (`/openapi.json`, `/llms.txt`, `/health`,
  `/dashboard`, `/.well-known/x402`, `/.well-known/x402.json`, `/api/mcp/manifest`,
  `/api/v1/agents`) and carry the **Public** badge, not "Free". They are genuinely free.
* The "Activity" section of our page shows **84 transactions, $0.904,
  8 unique buyers over 30 days** (for all time: 97 / $0.923 / 14, last
  2026-11-11T06:04:32Z).

So the hypothesis is not confirmed. The catalog is 221 987 rows, of which
198 120 have `accepts` (198 076 live).

Three real defects, however, came out of the same check, and one of them is already
fixed:

1. **`/api/v1/verify-seller` was missing from x402scan.** Their own discovery
   reads our `openapi.json` (15 endpoints, `authMode=paid`, `price=0.010 USD`)
   and said 14 registered / **1 unregistered** — exactly the pilot route.
   Our rows were frozen at 2026-11-04T17:37; their facilitator sync is
   paused (`FACILITATOR_SYNC_PAUSED = true`), so it does not refresh by itself.
   **Fixed**: I ran the public mutation `public.resources.registerFromOrigin`
   (the same request that the "Refresh" button on the page makes) with
   `origin=https://kristo-intelligence-api.onrender.com`. It answered
   `success:true, registered:7, publicCount:8, failed:0, skipped:0, deprecated:0,
   total:15`; the row `/api/v1/verify-seller` now carries `amt=10000`,
   `price=0.010 USD`, while `updatedAt` of the origin became 2026-11-11T18:11:18Z.
   Nothing was deprecated.
2. **A dead second copy of us**: x402scan holds a separate server
   `https://kristo-intelligence.vercel.app` (id `73148ccf-…`), **16 rows, 12 of
   them paid** ($0.05–$0.10, `success=true`, last crawl 05.08.2026),
   pointing at a host that returns `404 DEPLOYMENT_NOT_FOUND`, and **0 transactions**. Every
   agent that lands there sees a ruined shop. There is no public way for us to
   remove it.
3. **An MPP compliance warning.** The registration returned `warningDetails`
   for all 7 paid rows: `MPP_NO_PAYMENT_CHALLENGES`, severity `error`,
   "WWW-Authenticate header contains no Payment challenges". Our 402 sends
   `WWW-Authenticate: x402 realm="kristo-intelligence", …` — the old x402
   scheme, not the MPP `Payment` challenge. An x402 client is not affected; an MPP-native
   client (mppx, Tempo) does not see a payable offer. This is a real hole, but not a
   blocker — the badge remains "Paid", because it is derived from `accepts[0].amount`, not from
   the warnings.

In addition: our prices are rendered as `< $0.01`, so the catalog never
shows the real $0.003/$0.005.

A note: the number "689 paid" that was circulating is for x402scan itself as a
seller, not the size of the catalog.
