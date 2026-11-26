# The x402 demand census — what 457 agents actually did in front of a paywall

**Measured 24.11.2026.** Every number here comes from a production ledger, not from
a survey: `request_log`, `onchain_sales` and `payment_attempts` on a live x402
service on Base, read with read-only SELECTs. The service is ours, which is the
only reason the data exists at all — a seller can see its own traffic, and nobody
publishes it.

**Why this document exists.** Every x402 seller can measure what it *sells*.
Almost nobody can say what the *demand side* does, because seeing it means running
a paywalled service for months and keeping the ledger. We did, so we are
publishing the aggregate and the method. The agent-level detail — every user
agent, its cadence, its exact attempts and its outcomes — is the part we keep.

---

## 1. The headline

Over 84 days, a live x402 service selling seven DeFi data routes at
$0.005–$0.05 — the window these figures describe, and the state of the catalogue
before this census route itself existed (it was added on 24.11 at $0.25, and from
26.11 the paid catalogue runs to $0.25):

| | |
|---|---|
| requests to the service (last 30 days, which is the retention limit) | 1,246,641 |
| typical day | ~30,000 |
| distinct user agents that reached a `402` paywall | **457** |
| distinct user agents that received content | 163 |
| payments received, lifetime | 180 |
| revenue, lifetime | **$1.983** |
| of which paid by the operator's own test wallet | **$1.785** (131 payments) |
| genuinely external money, lifetime | **12 payments, $0.054** |

Read that again carefully, because it is the whole story: **457 machines found the
product, and twelve wallets — ever — paid for it.** The problem is not discovery.
Discovery worked long ago.

## 2. Who is at the paywall

The 457 agents split into 206 whose user-agent string names them as
probe/monitor/health/index/crawl/scan/uptime/bazaar software, and 251 "other" —
and reading the top of the "other" list finds the hosting provider's own health
checker, the operator's own coding agent, `python-requests`, `node`, `axios` and
`Go-http-client`.

**The overwhelming majority of the traffic is infrastructure telemetry about the
seller, not demand for the product.** Monitors outnumber buyers by two orders of
magnitude, and the monitors are the ones generating the impressive request counts.

Named third parties that probed the service, unprompted, having found it on their
own: agent402.tools, x402station.io, x402-list.com, mcpbeat.com, mcptry.com,
alalanet.com, nohumans.directory, PayAI Bazaar, mekler.ai, toolvet.app,
botsrated.com, kertivo.com, lumierepaycheck.org, agenteconomy.report, agentlair.dev,
brick.blue, agenstry.com, ai-powered.com, addrbook.com, nitrograph.com,
carbon-cashmere.de, glimind.com, x402-trust.com, x402-router and zero.xyz —
twenty-five of them, and we submitted to none.

## 3. Nobody was turned away by a bug

`payment_attempts` records every credential ever presented. It was created on
8 November, so it covers the last two weeks.

| outcome | attempts | payers |
|---|---|---|
| settled | 98 | 7 |
| rejected | 30 | 3 |
| settle_failed | 7 | 2 |

Every refusal was read individually, because a refusal to a real buyer is a lost
sale and a refusal to a fuzzer is not. They are only ever two things:

- **Adversarial conformance testing.** One address made six attempts inside four
  seconds, including `authorization.to != payTo` using the junk address
  `0x1111…1111`, `amount below price: 1 < 5000`, a forged EIP-712 signature and an
  over-long authorisation window. Twenty-seven further attempts carry an empty
  payer and the detail `payload_undecodable`, from a self-described conformance
  tester that made 13,452 challenged calls. The rail refused every one correctly.
- **The operator's own testing**, failing on a third-party facilitator being
  unreachable and on a settlement deadline.

**Not one refusal is an ordinary buyer with a valid signature and a funded
wallet.** There is no broken link in the funnel to repair.

## 4. What this means for x402 sellers

Three independent measurements now agree, from three different directions:

| measurement | source | finding |
|---|---|---|
| seller-side census of a public index | a third-party analyst, paid work | the top 10 rows take 92% of spend; the median row earns $0.01 per 30 days |
| views of one marketplace listing | a marketplace, 7 days | 6,323 views, **0** payments |
| demand-side ledger of a live service | this document | 457 agents at the paywall, 12 external payments, 5.4 cents, 84 days |
| settlements across a public marketplace | that marketplace's own settlement index, 5 weeks | **919,457** settlements, and the median seller earned almost nothing |
| payability of everything listed in a public catalog | that catalog's live probes | of **56,080** listed endpoints, **47,041** reproduced a payable challenge at all — one listing in six cannot take money |

The last two come from Script Master Labs' HIVE402, which publishes a live catalog and
its own settlement records — read directly from their public endpoints on 25.11.2026,
not quoted from a summary. Their report also records the settlement count rising 5.4×
week over week (103,317 to 557,258), which is the clearest available statement that
the *payments* are growing while the *sellers* are not.

The consistent reading: **being listed, being found, being crawled and being
healthy are all solved problems, and none of them is a sale.** An x402 seller with
commodity data has no distribution problem left to solve — it has a demand problem
that more distribution cannot touch. A catalog of 56,080 endpoints, where one in six
cannot even take a payment and the median seller earns nothing, is what "more
distribution" produces at scale.

The two things that survive every measurement are the ones the analyst named: data
a buyer cannot get elsewhere, and the measurement itself. This document is the
second one.

**What the ecosystem's own launches say.** A Base ecosystem digest for 24 November
2026 reports a scanner whose security work is paid for continuously out of token
fees, and an operator extending an *evaluation* API — judgement sold as a service.
Neither is our measurement and both come from a secondary source, so treat them as
a pattern rather than as evidence: they are the shape this section argues for, and
the opposite shape to a listing that can report calls or views and no revenue. What
gets paid for repeatedly is a recurring service or a judgement. What does not get
paid for is a feed of numbers that anyone can crawl.

## 5. Method, so the numbers can be checked

- Requests, user agents, paths, referers and statuses: `request_log`, which retains
  30 days. `MIN(ts)` is reported rather than assumed, because 30 days is the real
  limit on any claim made from it.
- Payments and payer classification: `onchain_sales`, which stores its own
  `payer_class` and `payer_label`. Cross-checked by decoding the USDC `Transfer`
  logs of the most recent fifteen receipts directly from Base: the `Transfer.from`
  is the operator's wallet in all fifteen, while `tx.from` differs each time
  because that is the facilitator's relayer.
- Attempts and refusals: `payment_attempts`, with the `detail` column read row by
  row.
- Read-only throughout. The audit scripts are in `scripts/`:
  `inbound_traffic_audit.py` (the ledger) and `placement_audit.py` (every public
  surface where the service is listed).

**What is deliberately not here:** the per-agent table — name, first seen, last
seen, cadence, route preference, attempt outcome — and the per-wallet payment
history. That is the dataset. The aggregate is this document.

## 6. How to buy the part that is not here

The table is sold rather than published, because a dataset nobody pays for is the
mistake this document is about.

- **Buy:** `GET /api/v1/demand-census` — **$0.25** in USDC on Base (`eip155:8453`),
  x402 v2. An unpaid call answers `402` with the offer; a paid one returns the
  document. It carries the **1,494-row per-agent table** (`user_agent`, `first_seen`,
  `last_seen`, `requests`, `challenged`, `delivered`, `ever_paid`), all 135 payment
  attempts by outcome, the payment history by payer class, and the measurement
  window. `totals` is derived from the rows, so a buyer can re-add the table and
  check it against the summary it arrived with.
- **Look before paying:** `GET /api/v1/demand-census/sample` — free, no credential,
  the same document shape with a synthetic agent list. It exists so the fields, the
  size and the provenance lines can be judged before the price is paid; the
  aggregate figures in it are the ones already published here.
- **The served copy is the measured copy:** the snapshot is dated
  `2026-11-24T20:42:29Z` and served from disk unchanged. It is produced offline by
  `scripts/build_demand_census.py`, which reads the production ledger
  (`request_log`, `onchain_sales`, `payment_attempts`) read-only; the route itself
  only serves the file.

---

*Kristo Intelligence — `kristo-intelligence-api.onrender.com` — a live x402 service
on Base, USDC, `eip155:8453`.*
