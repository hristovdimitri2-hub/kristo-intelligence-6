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
$0.005–$0.05:

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

The consistent reading: **being listed, being found, being crawled and being
healthy are all solved problems, and none of them is a sale.** An x402 seller with
commodity data has no distribution problem left to solve — it has a demand problem
that more distribution cannot touch.

The two things that survive every measurement are the ones the analyst named: data
a buyer cannot get elsewhere, and the measurement itself. This document is the
second one.

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

---

*Kristo Intelligence — `kristo-intelligence-api.onrender.com` — a live x402 service
on Base, USDC, `eip155:8453`.*
