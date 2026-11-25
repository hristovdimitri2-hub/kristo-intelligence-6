# Outreach drafts — ready to send

Prepared 24.11.2026. Nothing here has been sent. The agent has no email
credentials, so every item below is for the owner to send or post.

Facts used in these drafts were verified on 24.11.2026 against the live service
and against the third-party pages named. Where a claim is quoted from a
third party, the source is given so it can be re-checked before sending.

---

## A. Reddit comment — r/x402, the Payability Report 15 thread

**Where:** the thread by u/IllWar5047, "Agent base costs rose nearly fourfold this
week…" (posted 23.11, ~23 hours before this draft).
**Why:** it is the one thread this week where the people who measure x402
activity are reading. A comment there is seen by the people who build buyers.

```
The 12,975 transactions on agent402.tools is the number I would look at, not the
190k USDC.

We run a paid x402 API on Base (seven routes, $0.005 to $0.05). We have had zero
sales. When I looked at why, the answer was not discovery — we are in CDP's
Bazaar, the MCP registry, Glama, and two directories. The answer was that our
routes are things an agent looks up once and never needs again. A quote, a stat,
a status. Nobody calls those twice.

What does get called twice is either very expensive and rare (one integration,
hundreds of dollars per call) or very cheap and woven into somebody's pipeline
(tens of thousands of calls). Your own data shows the same shape: 95% of the
volume in ten services, 70% in one. The middle — cheap, useful, on-demand — is
where the demand is thinnest, and that is where most of us are building.

So the number I would publish next to the volume is the repeat rate: how many
payers called the same resource more than once in the week. That separates a
service somebody integrated from a service somebody tried. The second one is not
a business, however good the 402 looks.

One correction on the strict rule, in case it matters to your count: a transfer
that consumes an EIP-3009 authorization is matched by the AuthorizationUsed event
in the same receipt, and the authorizer is the payer. We do that lookup in
production, and we found the same transaction carries both events — so the
matching is sound. The one case it cannot resolve is a facilitator that settles
through a contract which does not emit the event, and those will silently drop
out of your 190k.
```

**Do not** add a link to the service. Reddit removes promotional comments in this
subreddit and the comment is stronger without one.

---

## B. Email to Ernest — `ernest@nolimbsfighting.com`

**Subject:** Re: Kristo fix-sheet — yes to the CDP request, and one thing I would like to try with you

```
Ernest,

Thank you for the measurement. I reproduced it independently before replying, and
it holds: 20 rows on 0xB4Fc...C844 (12 HTTP, 8 MCP), 6 on 0xd4cd...d08f, and all
12 HTTP routes answer a live 402 with amounts matching what CDP has declared, to
the atomic unit. The migration did not slip.

Yes — please write the CDP support request and send it to me. The six rows on the
retired address are the part I care about most: a public directory still
attributing resources to an address we no longer control is the shape that reads
as a hijack from outside.

One thing for the same ticket, in case support can act on it. Every MCP row in
CDP's Bazaar still carried our pre-23-November tool descriptions. The live server
has served the current ones since 23 November; the Bazaar copy is written from the
extensions echoed by the last paid call. I have since refreshed six of the seven
by paying through them. The seventh, /mcp#get_whale_flow#get_whale_flow, is a
duplicate row that no paid call can reach — only support can remove it.

And a question, since you measure sellers for a living. I have seven paid routes
and no sales. The routes that make sense to me as a business are the ones that
read the chain rather than quote a price: arbitrage opportunities across Base
pools, whale transfers, and receiver verification before money moves. The last one
seems to me the only one a platform would pay for, because it is a pre-payment
check and the alternative is losing the payment. Do you see buyers for that in
your own work, and would you be willing to try it in one of your flows at no cost?
I would rather have one real integration than fifty listings.

Dimitri
```

---

## C. Virtuals Protocol — Agent Commerce Protocol

**This is not an email first.** ACP is self-serve: `acp-cli` lets an agent publish
"offerings" (a job it can be hired to do, with price, SLA, requirements and
deliverable) and "subscriptions" (reusable access packages), and buyers hire
through on-chain USDC escrow. That is a marketplace where agents *hire*, not a
catalogue where they browse — which is the difference between the channels we are
already in and the one we are not.

**What it costs us to find out:** an agent has to be created, a signer approved
through a browser flow, and an offering published. The signer approval is
interactive, so this cannot be done unattended.

**Question to ask their team** (via the Virtuals Discord, or the `acp-cli` repo
issues — not an invented address):

```
We run a hosted x402 API on Base (kristo-intelligence-api.onrender.com), seven
paid routes, live 402 on all of them, and an A2A agent card at
/.well-known/agent-card.json. We are not an on-chain agent with a token; we are an
HTTP service that takes x402 payments.

Can a hosted HTTP service be published as an ACP offering — that is, can the
deliverable be "the buyer calls this URL and gets the data", with escrow released
on a delivered response — or does ACP assume the provider is an agent running the
CLI?

If the former, what is the minimum setup: an agent record, a signer, an offering
with a deliverable URL? If the latter, is there a documented way for an HTTP
service to be wrapped by a thin agent that does the job on its behalf?
```

**Why this is the best lead of the five:** ACP is Base-native, it is where agents
hire each other, and an offering with a price and an SLA is structurally the same
thing as our paid route. The other four channels are listings; this one is a
transaction.

---

## D. Olas — Mech Marketplace / Pearl

**What they have:** 8.8 million agent-to-agent transactions through Mech
Marketplace, and x402 integrated with their own facilitators. Pearl v1 is
positioned as an "AI agent app store".

**Why it matters:** 8.8M transactions is demand that already exists and already
pays per call. An x402-native service is exactly what their integration was built
for.

**Question to ask** (via their Discord or the `olas.network` contact — not an
invented address):

```
Olas agents already pay per call through Mech Marketplace, and the x402
integration means they can also pay off-chain services directly. We run a hosted
x402 API on Base with seven paid routes — chain-read data (arbitrage across Base
pools, whale transfers, receiver verification before payment), not price quotes.

What does a service need to do to be callable by a Pearl agent? Is there a
registry of x402 services the agents select from, or does the agent's tool
configuration name the URL directly? If the second, we would rather give you a
working integration than a listing.
```

---

## E. x402scan (Merit Systems) — listing application

**Where:** the submission form on x402scan, or the repo's listing issue.
**Status:** the application text was drafted earlier in the session and is in
`docs/SCAN_LISTING_DRAFT.md`. Re-read it before sending — the prices in it were
corrected to $0.005–$0.05 and seven routes.

---

## F. What the agent cannot do without the owner

| Item | Why |
|---|---|
| Send any of the emails above | No email credentials in the workspace; `smtplib` is available but there is no account or app password to use |
| Post the Reddit comment | Requires the owner's Reddit session |
| Approve an ACP signer | Browser flow, interactive |
| Publish to PyPI | Needs an account decision |

---

## G. Order I would send them in

1. **Ernest** — warm, already measuring us, and he may know buyers. Cheapest.
2. **Reddit comment** — free, and the audience is the buyers.
3. **Virtuals ACP** — the only real marketplace. Ask the question before building.
4. **Olas** — same question, larger existing demand.
5. **x402scan** — listing only; do it last, because it is the least likely to
   produce a call.

---

## H. Radar digest replies (23.11) — two comments, ready to post

The radar digest of 23.11 listed nine issues. Two are worth a comment; the rest
are either closed or are vendor pitches where a third voice adds nothing.

### H1. `vAPI-Network/vapi-network#86` — "valid SIWE signature rejected"

Zero comments, open, and the reporter has already done the work: rebuilt the
flow by hand, ruled out the CLI and the wallet, and got a 401 on a signature
that recovers correctly. This is a signature-verification bug in our own domain,
and we hit the same class of failure in our settlement path.

```
The 401 is most likely the server rebuilding a different message than the one you signed, not the signature being invalid. You have already recovered the signer locally, so the signature is sound, and the only remaining variable is the message the server reconstructs.

Of the eight fields in a SIWE message, five are fixed by the spec and three are the usual suspects: the URI (trailing slash), the statement (whitespace), and Issued At (millisecond precision). JSON serialisation can change the string between what you signed and what you send, and newline escaping is the classic.

Two tests that isolate it in one request each:

1. Send a deliberately malformed siweMessage. If the error is still "signature could not be verified", the server is not reaching the recovery step at all — it is failing earlier, on parsing or on the nonce lookup. A server that cannot tell "bad message" from "bad signature" is not verifying signatures.

2. Recover the signer from the literal string in your JSON body, not from the string you built. If those differ, you have found it.

One structural note. We had the same class of failure in our own settlement path, and the fix was to stop comparing strings. The server should reconstruct the message, recover the address, and compare that to payoutWallet. If it compares message text instead, it will reject valid signatures forever, and the error will keep saying "could not be verified" while the real problem is that it never tried.
```

### H2. `AsterPay/attest#1` — detached XDR-1 receipts

Open, zero comments. The proposal is a competitor's pitch (`hcrb.in`), and the
comment is not a counter-pitch — it is the one design gap in the receipt, which
is the thing we spent a day proving with the conformance fixtures.

```
One thing in the XDR-1 design is worth pinning before this goes wider: the receipt carries nonce in its payload, and carrying a nonce is not the same as binding to it.

A receipt that says "this payment had nonce N" is an assertion by the issuer. The proof is that the transaction behind the receipt is the one that consumed authorization N. On Base that means the same receipt contains the AuthorizationUsed(address,bytes32) event for (payer, N) and the USDC Transfer to the recipient. Without it the same receipt can be presented against a different payment, and the verifier has no way to tell.

The event topic is keccak("AuthorizationUsed(address,bytes32)") = 0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5, and the authorizer must equal the payer the receipt claims. Two Base receipts that carry both events in one transaction, for checking the shape: 0x3b4f77a4dc91541a13ee425b1df7ea6ac51e124f052b263f65668b0ec208e218 and 0x5b8030c9a87ec1b02ed0eba28fdb8d8225d3afce4b01db53a919dca103c996be. Both were re-checked on 24.11: one AuthorizationUsed and one Transfer each, same block, 0.02 USDC.

If nonce is filled from the facilitator's response rather than from the chain, the receipt is only as good as the facilitator. That is the difference between a receipt that records a payment and one that proves it.
```

### H3. The one that is not worth a comment

`MikeyPetrillo/Agent402#2058` — the malformed duplicate route. It is **closed**
and already has a reply. Nothing to add.

The rest of the digest is either a documentation refresh
(`api-evangelist/ibanforge#2`), a vendor pitch by the same author
(`oneshot-agent/sdk#10`), or a listing submission. A comment there would be
noise.

---

## I. Exact destinations — verified 24.11.2026

Every link below was opened or resolved through the GitHub API on 24.11.2026.
Where a repo name was wrong in an earlier draft, the correction is noted.

| # | Destination | Exact link | State |
|---|---|---|---|
| 1 | Ernest | `ernest@nolimbsfighting.com` | warm thread, reply to his message |
| 2 | r/x402 | https://www.reddit.com/r/x402/ | thread about the fourfold increase, posted 23.11 |
| 3 | Virtuals ACP | https://github.com/Virtual-Protocol/acp-cli/issues/new | **note the hyphen**: `Virtual-Protocol`, not `Virtuals-Protocol` |
| 4 | Olas | https://t.me/olaschat | Telegram; also https://olas.network/mech-marketplace |
| 5 | x402scan | https://github.com/Merit-Systems/x402scan/issues/1270 | **our listing request already exists** |
| 5b | x402scan | https://github.com/Merit-Systems/x402scan/issues/1340 | dead-host cleanup, already open |

**Two corrections to the earlier drafts.**

`Virtual-Protocol/acp-cli` — the org is `Virtual-Protocol` with a hyphen. The
`Virtuals-Protocol` spelling resolves to nothing. The repo has 45 stars, 37 open
issues and issues enabled.

**x402scan already has our listing request.** Issue #1270 is open and titled
`[Listing Request] Kristo Intelligence — live DeFi signals & whale-flow API (x402
v2, Base)`. Do not open a second one — comment on #1270 with the current host and
the seven routes. Issue #1340, `Remove dead listings: 16 resources on a 404 host
(kristo-intelligence.vercel.app)`, is also open and is about the host we left; a
short comment there confirming the migration closes it honestly.

---

## J. Two more messages, approved 24.11.2026

### J1. PayAPI — the structured Price field is stale

**Where:** `hello@payapi.market` (the only address on the site; the listing form is
`https://payapi.market/list`). The owner approved sending this.

**Subject:** `Kristo Intelligence listing — the structured Price field still shows the old prices`

```
Hello,

I operate the Kristo Intelligence listing (kristo-intelligence-api.onrender.com) and I am writing about an inconsistency on the listing page itself.

The prose description is correct: seven paid routes, $0.005 to $0.050. But the structured Price field still reads "$0.003 to $0.005" and "3 endpoints". A buyer or an agent that reads the structured field rather than the text sees a price we no longer charge and an endpoint count we no longer have.

The routes today: /api/stats, /api/sales, /api/arb/opportunities and /api/bot-status at $0.005; /api/v1/signal and /api/v1/whaleflow at $0.01; /api/v1/verify-seller at $0.05. All seven return a live 402 on request.

Could the structured field be refreshed to match? If it is generated from the submitted listing, tell me which field to correct and I will resubmit; if it is set by hand, this is the request. And if there is a way to keep the listing current without a support ticket each time, I would rather do that.

Thank you,
Dimitri Hristov
```

### J2. Jamenbin — the fixture moved after he verified it

**Where:** `https://github.com/VibeMirror-coder/n8n-nodes-omnidome/issues/3`
The owner approved sending this. He verified v1 (`d76537a7…b524e`) and was never
told it changed.

```
Jamenbin — the fixture moved after you verified it, and I owe you a direct note rather than a change you have to notice.

The hash you measured, d76537a7...b524e (7 tests, 22 973 bytes), was revision 1. Since then the file has been revised three times. The current one is 3d76d8030efc10cbbfcfe3a739078ee5fa4a8af417712a583b934789f37d170a — 11 tests, 37 862 bytes. The REVISIONS block inside the file records every step, so the hash you verified stays inside the bytes rather than being replaced by them.

What changed, in order:
- v2 binds a transfer to the payer: a payment to the right address from the wrong sender is not ours.
- v3 compares atomic units, no epsilon, and carries the MIT licence.
- v4 binds the authorization rail to the nonce. The receipt that settled a payment is the one that consumed the authorization — AuthorizationUsed(payer, nonce) in the same receipt as the Transfer. Two tests, by name: test_a_transfer_that_consumed_another_nonce_is_not_this_payment and test_the_receipt_that_consumed_this_nonce_is_the_one_that_delivers.

Same URL: https://gist.github.com/hristovdimitri2-hub/0d2f4436cc73a14d837c39f88168a5bf

If you integrated against the first revision, nothing breaks: the signature is backward compatible and everything new is a keyword with a default. But the hash you recorded is no longer the current one, and you should know that before you cite it.

Dimitri
```

---

## K. Glama Discord — the `/mcp/servers/` record that cannot be created

**Where:** the Glama Discord (`https://glama.ai/discord`), in the channel where the
team handles listing and duplicate requests. Verified 24.11.2026 that the team
answers there — the channel shows concrete fixes being done for Clifty
(`io.justroadmap/just-roadmap` vs `io.justroadmap/justroadmap`) and CodersTalk
(`com.keepplain` listed twice), both by naming the duplicate and saying what to keep.

**Why it is the only remaining path.** The connector is listed, healthy and rated A,
but `awesome-mcp-servers` PR #13219 needs the `quality` field, and Glama computes
`quality` only for `/mcp/servers/` entries. That record does not exist and we cannot
create it: both Add Server paths reject the endpoint because it is already a connector.

**Verified 24.11.2026, so the message carries facts and not claims:**

| URL | Result |
|---|---|
| `/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence` | 200 — ownership verified, tool definitions rated A, 7 tools |
| `/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6` | 200, but renders the registry index (127 068 servers, zero "kristo") |
| `/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6/badges/score.svg` | 200, renders "This MCP server is not listed on Glama" |
| `/mcp/servers/com.onrender.kristo-intelligence-api/kristo-intelligence` | 404 |

**Message to post:**

```
Kristo Intelligence — the /mcp/servers/ record for a hosted endpoint does not exist, and we cannot create it

Our server is a hosted x402 endpoint: https://kristo-intelligence-api.onrender.com/mcp — 7 tools, streamable HTTP, Base mainnet.

It is listed and healthy as a connector, and we would like to keep that record exactly as it is:
https://glama.ai/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence
(ownership verified, tool definitions rated A, 7 tools, TDQS 4.4/5.0)

The problem is the /mcp/servers/ record. It does not exist:
- /mcp/servers/hristovdimitri2-hub/kristo-intelligence-6 renders the registry index — no "kristo" on the page
- /mcp/servers/com.onrender.kristo-intelligence-api/kristo-intelligence returns 404
- both Add Server paths reject with "already listed as a hosted connector"

Why it matters: awesome-mcp-servers PR #13219 cannot merge because the listing's `quality` field shows "?", and quality is computed only for /mcp/servers/ entries. Ticket #135407945 has been open since September.

What we are asking for, either way:
1. create the /mcp/servers/ record for the repo, pointing at the same hosted endpoint — keep the connector, add the server record alongside it; or
2. compute `quality` for the connector listing.

The repo carries a Dockerfile and a stdio bridge (Dockerfile.glama, scripts/mcp_stdio_bridge.py), verified end to end: initialize → tools/list returns all 7 tools with full schemas, so the introspection check should pass. Nothing else is pending on our side.

Thank you.
```

---

## L. Ernest's CDP ticket — verified, with one correction (24.11.2026)

Ernest sent the ticket ready to paste, and it is **exact**: we re-measured every
number through CDP's own discovery API before touching it. One part is now
outdated and would have made the ticket wrong.

**Verified 24.11.2026, 19:0x EET:**

| payTo | rows | composition |
|---|---|---|
| `0xB4FcF8ef…C844` (current) | **20** | 12 HTTP + 8 MCP |
| `0xd4cdA900…d08f` (retired) | **6** | 6 MCP, every one double-hashed |

The six retired rows carry exactly the timestamps Ernest lists (07:17:16Z through
07:17:42Z on 10.11.2026). The duplicate under the current address is
`/mcp#get_whale_flow#get_whale_flow`, last updated 17.11.2026 06:31:02Z, and the
correctly named `/mcp#get_whale_flow` exists beside it at 24.11.2026 06:51:53Z.

**The correction.** Ernest's second request says the MCP descriptions still show
pre-23-November text with 16–17 November timestamps. That was true when he looked;
it is not true now. **Seven of the eight MCP rows under the current address were
refreshed on 24 November** — we paid through each tool, and the row was rewritten
from the extensions the tool echoed. Only the duplicate is still stale, and it is
the one row no paid call can reach, which is exactly why it cannot be fixed from
our side. So the ticket must not claim eight stale descriptions: it would be wrong,
and CDP would answer a question we no longer have.

**Ticket to send — paste as is, add your name:**

```
Subject: Remove stale Bazaar index rows for a rotated payTo, and one stale MCP tool description

Hello,

We operate an x402 seller at https://kristo-intelligence-api.onrender.com. We rotated our receiving wallet, and CDP's Bazaar index (/platform/v2/x402/discovery/merchant) still carries rows under the previous address. We cannot remove them ourselves; please delete the stale rows and confirm.

Current payTo (live, should remain):
0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844 -> 20 rows (12 HTTP + 8 MCP)

Retired payTo (no longer controlled by us; every row has been stale since 10 November 2026):
0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f -> 6 rows, all duplicate /mcp

Please delete these 6 rows under the retired address (all under https://kristo-intelligence-api.onrender.com):
1. /mcp#verify_seller_receiver#verify_seller_receiver (last updated 2026-11-10 07:17:42Z)
2. /mcp#get_trading_signal#get_trading_signal (2026-11-10 07:17:37Z)
3. /mcp#get_arbitrage_opportunities#get_arbitrage_opportunities (2026-11-10 07:17:33Z)
4. /mcp#get_bot_status#get_bot_status (2026-11-10 07:17:29Z)
5. /mcp#get_onchain_sales#get_onchain_sales (2026-11-10 07:17:24Z)
6. /mcp#get_market_stats#get_market_stats (2026-11-10 07:17:16Z)

Also please delete one duplicate row under the CURRENT address:
7. /mcp#get_whale_flow#get_whale_flow (last updated 2026-11-17 06:31:02Z)
(The correctly named single row /mcp#get_whale_flow exists at 2026-11-24 06:51:53Z and must remain.)

Second request, same ticket: one stale tool description.

Our MCP server has served updated tool descriptions since 23 November 2026. Seven of the eight MCP rows under the current address now carry them: we refreshed those by paying through each tool on 24 November, which also confirms how a row is written — the stored description comes from the extensions echoed by the last paid call, not from a crawl.

One row still carries the old text: /mcp#get_whale_flow#get_whale_flow (2026-11-17 06:31:02Z). It is the duplicate in item 7. No paid call can reach it, so it cannot be refreshed from our side; deleting it resolves its description as well.

Question for future rotations: can support update a stored description directly, or is a paid call through the tool the only path?

How we measured this (reproducible):
GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=<address>&limit=100&offset=0
paginated to pagination.total. The row counts and lastUpdated values above are copied from that output.

Thank you,
[your name / organisation]
```

### L2. Reply to Ernest

**Where:** reply in the same Gmail thread. He asked for a straight answer and gave
two free offers; both deserve a direct reply.

```
Ernest,

The ticket is exact. I re-measured every row through the discovery API before sending it: 20 rows on the current address (12 HTTP + 8 MCP), 6 on the retired one, all six with the timestamps you list, and the double-hashed get_whale_flow sitting beside the correct single row. One correction, in your favour: seven of the eight MCP descriptions were refreshed on 24 November, because I paid through each tool. Only the duplicate is still stale, and it is the one row no paid call can reach. I narrowed that half of the ticket rather than send a claim that is no longer true.

Yes to your first offer. Benchmark the seven routes and tell me which, if any, has a design a buyer would pay for. I would rather hear "none of them" than keep guessing.

And thank you for the straight answer, because it is the first one I have had. I am going to act on it: I will stop treating verify-seller-receiver as a business. What you describe — platforms absorbing the cost themselves or running a sanctions screen — matches the shape of your numbers, and your point about visibility is the part I had not understood: a route is invisible until someone has paid through it, so polishing a route nobody can see is work with no output.

On your second offer: I do know sellers with the symptom, but not many who rotated a wallet the way we did. Before I name anyone, tell me how you want the introduction made — directly, or through me relaying your review — because it is their decision, not mine, and I will not hand over someone's name without asking them first.

One question, since you sell the measurement and I have now bought it twice. Of the two things you say actually earn — data a buyer cannot get elsewhere, and the measurement itself — which one would you push a seller toward when the seller has no unique data at all? I am asking because that is where we are, and I would rather build the second thing than a seventh route.

Dimitri
```

## M. PayAPI — the measured follow-up to Chet (24.11.2026)

**Where:** the same thread as the sent message to `chet@payapi.market`.

**Why it replaces the earlier draft:** the first message asked what PayAPI probes to
produce `degraded` / `Uptime 90.4%`. That question is now answered by measurement on
our side, so it is dropped and the message carries the finding instead. Full working
in `NEXT_ACTIONS.md` §2b.

**Subject:** `Kristo Intelligence listing — price is fixed; page text and reliability are still on September data`

```
Chet,

Two things on the Kristo Intelligence listing, and I measured both before writing, so this is a report rather than a question.

The structured price is correct now: the public record reads min 0.005, max 0.05, payment_verified true. Thank you for that.

What is still on September data:

1. The line on the listing page reads "3 of 3 routes settlement-verified - $0.003 to $0.005 USDC/request - 3 endpoints". It is generated from verified_routes, not from price, and verified_routes holds the three test payments from 2 Sep and 21 Sep. Four routes are therefore missing from it: /api/sales, /api/arb/opportunities, /api/bot-status and /api/v1/verify-seller. Could those four be settlement-verified onto the same card? I do not want a second card for the same product, and I understand your rule is one product, one card.

2. The dashboard shows the listing as degraded, with an uptime around 90.4%. The record behind that number is frozen: reliability computed 2026-09-06, last seen 2026-10-12, last verified 2026-09-21, while the listing itself is status live and verification_paused false. That window closed in September, when I was redeploying several times a day, which I think is what it is measuring.

On 24 November I probed the service myself: all seven routes, six requests each, forty-two of forty-two answered the x402 challenge, average 251 to 381 ms with a worst case of 707 ms. HEAD returns the challenge, OPTIONS returns 204, /health returns 200, and the payment envelope decodes with the correct scheme, network, payTo and amount. We are not degraded.

So: will a re-verification refresh the reliability window and the page text, or does that need something from me? If it refreshes on its own schedule, tell me the interval and I will stop asking.

One last item: please delete the three rejected listings under my account - "Verify an x402 seller before you pay it", "Kristo Intelligence AI Gateway" and "Kristo Intelligence AI Agents". They were created in error and one of them carries a claim that is not true.

Thank you,
Dimitri Hristov
```

## N. Ernest — the demand-side dataset (24.11.2026)

**Where:** the same Gmail thread as §L2, after the market audit. He is the one
person in this market who sells the measurement, and the measurement is now the
product.

**Why this is a follow-up and not a new pitch:** he offered a free benchmark and
asked which of the two earning things he would push a seller toward. We built the
answer instead of asking again. He measures the seller side of a public index;
this is the demand side of one live service — the half his own numbers cannot see.

**Subject:** `The other side of your numbers — 457 agents at one paywall, and what they did`

```
Ernest,

You asked which of the two things I should build. I built the second one before answering, and this is the result.

I run a live x402 service on Base. Seven routes, $0.005 to $0.05, and as of today one data product at $0.25. Over 84 days it answered 1,246,641 requests in the last thirty (that is my retention limit, not a quiet period), was found by 457 distinct user agents, and was paid twelve times by nine wallets that are not mine. Total external revenue, lifetime: five and a half cents. I published the aggregate and the method. The per-agent table is the part I kept.

What makes this different from your census is direction. Your numbers describe what sellers earn. These describe what the demand side does at the moment it meets a price: which agents arrive, how often they come back, which route they choose, whether they ever present a credential, and what that credential says when they do. I read all 135 recorded payment attempts one by one. Not one refusal was an ordinary buyer with a valid signature and a funded wallet — they were conformance fuzzers and my own test runs. That is the part I could not see from any index, and I suspect it was missing from yours too.

Two things I want to know, and neither is a favour.

One: you sell this measurement. Is a demand-side ledger worth anything to you or to your clients, and if so in what shape? I stopped asking and answered it instead: the per-agent table is live as a paid route at $0.25 a copy (GET /api/v1/demand-census on the service above). A dataset nobody pays for is the same mistake I have just finished documenting, so I priced it rather than giving it away. If you want to see what a buyer actually receives before you judge it, say so and I will send you one at no cost — you are the one person here whose read of it I want.

Two: the agents are overwhelmingly monitors and crawlers, not buyers. If that matches what you see, say so plainly and I will stop treating the demand side as a market. If it does not match, I want to know what you see instead, because then one of us is measuring the wrong thing.

The aggregate is written up and I will send it in whatever form is useful to you.

Dimitri
```

## O. Script Master Labs (HIVE402) — the answer to their own episode 1 (25.11.2026)

**Where:** `ScriptMasterLabs@gmail.com`, the contact address published on HIVE402.
**Why this one, out of everything in the feed:** their Episode 1 of *402 Daily*
(24.11.2026) is titled **"x402 Settlements Top 919,457 — So Why Did the Median Seller
Earn Zero?"** and was published by Timmy on @TimmyCrypto78. They asked our exact
question in public, one day before this message. Their probe-intelligence feed sells
aggregate stats free, **$0.05 per page and $0.25 for the complete snapshot** — the same
price and shape as our census, which is the strongest evidence we have that the price
is real. And their sales feed excludes their own wallets while their activity feed
labels their own settlements `SELF-PROOF`: the same discipline we use, which is the
reason to write to them rather than to a larger catalogue.

**Subject:** `You asked why the median seller earned zero — one measured answer`

```
Timothy,

Your Episode 1 asks why 919,457 settlements left the median seller earning nothing. I run one of the endpoints in your catalog, so I can answer it from inside a real service rather than from an index.

Seven routes on Base, $0.005 to $0.05, plus a $0.25 dataset. In the last thirty days it answered 1,246,641 requests, was reached by 457 distinct user agents, and was paid twelve times by nine wallets that are not mine. Lifetime external revenue: five and a half cents. I read all 135 recorded payment attempts one at a time. Not one refusal was an ordinary buyer with a valid signature and a funded wallet — they were conformance fuzzers and my own test runs. The traffic is machines checking whether we are still there, not buyers wanting the thing.

Your catalog measures the half of this market that is a listing: whether an endpoint is payable at all. Mine measures the other half, which no index can see: what the demand side does at the moment it meets a price — which agents arrive, how often they come back, which route they pick, whether they ever present a credential, and what that credential says when they do. Your trust score already prices demand at 20 of 100. This is that component measured directly, at one service, with every attempt read individually.

Two things, and neither is a favour.

One: I would rather sell this than give it away, and I have priced it. Get /api/v1/demand-census returns the full document — the 1,494-row per-agent table, all 135 payment attempts by outcome, and the payment history by payer class — for $0.25, which is what your complete probe snapshot costs. The aggregate and the method are already public, so you can judge it before buying anything: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/X402_DEMAND_CENSUS.md

Two: I noticed that your sales feed excludes your own wallets in the source index, and that your activity feed marks your own settlements SELF-PROOF rather than passing them off as outside demand. That is the same discipline I keep — my published figures separate my own demo key from external revenue, and I publish my own signal engine's record, which is a losing one (1 hit against 12 misses, free to read at /public/signals/history). You are the only operator in this market whose numbers I can check in the direction that hurts, which is why I am writing to you and not to a bigger catalog.

I am already carried in your catalog through the CDP Bazaar source. If a demand-side ledger is useful to you — for the demand component of the trust score, or as its own line next to the probe feed — say what shape works and I will cut it that way. If it is not useful, say so plainly and I will stop treating the demand side as a market. That answer is worth as much to me as a sale.

Dimitri
```

## P. The trust-layer vendors — the base rate their scores do not contain (25.11.2026)

**Why this is a different target list from A–O.** Nine vendors already sell trust
about x402 **sellers**, and the x402 Foundation's own
`docs/dev-tools/third-party-extensions.md` lists them (Hosannaith, Teppi, zauth,
Tanilo x402 Guard, PEAC Protocol, OMATrust, AffixIO, Elara, x402r). Every one of
them measures or protects the supply side. **None measures the demand side** —
checking their READMEs individually, Hosannaith's only match for "demand" is
"sells a verified reliability score on demand", and Teppi's only match for
"payer" is a field in a receipt. A reliability score with no base rate for
whether anyone pays cannot separate a correctly payable endpoint from a
commercially dead one, and two sellers with identical uptime can differ by every
dollar they have ever earned.

So the letter sells the census as **an input to their score**, not as a rival
score, and it sells to a business that already needs the number. Sent first to
Hosannaith, the closest fit (a reliability oracle on Base, and the founder's own
address is published on the site rather than a noreply mailbox).

**Recipients and the address each one actually publishes:**

| vendor | what they sell | published address |
|---|---|---|
| Hosannaith | reliability oracle: uptime, correct-402, latency | `cameron@hosannaith.com` (site; repo also lists `security@hosannaith.com`) |
| x402r | refund and arbitration protocol | `hi@x402r.org` (site) |
| Tanilo x402 Guard | pre-payment price and spend-cap check | `joe@tanilo.io` (docs page) |
| Teppi | seller's paid-delivery record before signing | none published — GitHub issue or their docs form |
| zauth | monitoring, verification, refund SDK | none published |
| HIVE402 (Script Master Labs) | probe intelligence + demand-weighted trust score | already written to (§O), awaiting reply |
| PEAC Protocol, OMATrust, AffixIO, Elara | receipts, signed offers, policy gate | none published |

**Subject:** `Your seller score has no demand base rate — measured, from a live paywall`

```
Cameron,

You sell a reliability score for x402 endpoints: uptime, correct-402 behaviour, latency. I run one of the endpoints you would score, so I can hand you the number your score cannot currently contain — and I would rather sell it to you than keep it to myself.

I have run a live x402 service on Base since August: seven paid routes from $0.005 to $0.05, plus a $0.25 dataset. In the last thirty days it answered 1,246,641 requests and was reached by 457 distinct user agents. It was paid twelve times, by nine wallets that are not mine. Lifetime external revenue: five and a half cents. I read all 135 recorded payment attempts one at a time. Not one refusal was an ordinary buyer with a valid signature and a funded wallet — they were conformance fuzzers and my own test runs.

Why that matters to a reliability oracle. Uptime and correct-402 tell you whether an endpoint CAN take money. They cannot tell you whether anyone pays, and the base rate is brutal: at one live endpoint, 457 distinct agents arrived and twelve payments happened, from nine wallets. A score built without that base rate ranks almost every seller identically near the top — correctly payable, correctly fast, and commercially dead. Two sellers with identical uptime can differ by every dollar they have ever earned, and a buyer choosing between them is choosing on exactly that.

I am not asking for a favour or offering a partnership deck. The measurement is a document: GET /api/v1/demand-census returns the full per-agent table — 1,494 rows, the arrival and return behaviour of each user agent, all 135 payment attempts by outcome, and the payment history by payer class — for $0.25. The aggregate and the method are public first, so you can judge it before buying: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/X402_DEMAND_CENSUS.md

Two things stated plainly, because they are why I am writing to you rather than to a catalogue.

First, I would rather this became an input to your score than a competing one. I do not have your uptime coverage and I am not going to build it; you do not have a single demand measurement and, from your side, it is not obtainable — it takes running a paywall for months and keeping the attempt ledger, which most sellers delete.

Second, I hold myself to the standard I am selling. My own signal engine's record is published free at /public/signals/history and it is a losing one: 1 hit against 12 misses across 97 scored calls. I publish it because a record that only appears when it is good is not a record.

If a demand base rate is useful, tell me what shape fits your score and I will cut it that way. If it is not, say so and I will stop treating the trust layer as a buyer.

Dimitri
```

## Q. The public thread — the discovery measurement, ready to post (25.11.2026)

**What this is, and what it is not.** Not outreach to a buyer: there is no
recipient. It is the one channel this project has never touched — a public post —
carrying only numbers we produced ourselves and already published in
`docs/DISCOVERY_TRUTH.md`. It exists because the audience that reads x402 material
(operators, the member companies' staff, the RWA and agentic-payments
commentators) demonstrably reads *lists with numbers*, while our measured reports
have reached almost nobody. Treat it as a test of that assumption, not as a plan:
our own evidence says attention has never been the constraint, so nothing else in
the strategy depends on it.

**Why it is safe to post:** every figure is reproducible from
`scripts/catalogue_truth_study.py`, the limits are stated inside the thread, and
the last post publishes a mistake of ours rather than hiding it — the same
discipline the paid products are sold on.

**Dependency:** posting needs the owner's X account. The text below assumes
nothing else.

```
1/ We measured whether x402 discovery tells the truth. 87,419 listed resources
in CDP's public Bazaar. We read 10,000 and called 200 of them, unpaid, each
using the method the row itself declares. The numbers, including one that was
our own mistake.

2/ Freshness: the median listing was last updated 5.95 days ago. 47% are older
than a week. 29% are two to four weeks old. If that timestamp moves when a
settlement touches a row, then most x402 listings have had no paid call in over
a week.

3/ Reachability: 95% answer a parsable 402 with an amount. One listing in twenty
cannot be bought from at all - 404s, 400s, a 403, a 500, an unreachable host.

4/ The one with a specification consequence. 0 of 10,000 rows carry a top-level
method. 9,999 carry it only inside extensions.bazaar.info.input.method. 40%
declare POST. An agent that reads the row and GETs the listed URL reaches 60% of
the layer; the rest answer 405 - not broken, just never told how to call.

5/ Truth: of the 190 that answered, 14.7% describe a different product than the
endpoint now declares, and 3.7% advertise a different price. Worst case: a route
listed at $1.49 that now charges $0.10. An agent budgeting from the listing
overpays 15x.

6/ Our first pass reported 21.5% of rows unreachable. That was our probe: 84 of
the 200 rows declare POST, and a GET to a POST endpoint correctly returns 405.
Corrected: 5.0%. We published both, because the mistake is the best argument for
finding 4 - nothing in the row told a competent caller how to call.

7/ Limits: one index, and the 10,000 rows are the first 50 pages of a
recency-ordered listing - the freshest slice, so these figures are likely
optimistic. Write-up and the script that reproduces every number:
https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/DISCOVERY_TRUTH.md
```



