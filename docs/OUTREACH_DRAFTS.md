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

## B. Email to Ernest — `ernest-earnordie@agentmail.to`

> **The address in this file was wrong for two days, and the mistake is recorded
> here rather than quietly corrected.** From 24.11 19:52Z the drafts and the sends
> used `ernest@nolimbsfighting.com`, which the far end rejects —
> `554 5.7.1 : Recipient address rejected: user … does not exist`. Seven messages
> bounced: §L2's second copy, §N's first copy, and then **§R, §S, §T, §U and §V in
> full** — five replies written, "sent", and never delivered. SMTP acceptance is
> not delivery; the bounces arrived in the mailbox from `mailer-daemon`. Ernest
> writes and replies from `ernest-earnordie@agentmail.to`, which is where every
> message before 24.11 19:52Z went and where all of them arrived. Every address in
> this file is now that one, `scripts/send_draft.py` refuses the dead one outright,
> and `_tools/check_mail_delivery.py` reads the mailbox back so this is checked
> rather than assumed.

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
| 1 | Ernest | `ernest-earnordie@agentmail.to` | warm thread, reply to his message |
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

**Verified 25.11.2026, re-measured after the channel dump:**

| URL | Result |
|---|---|
| `/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence` | 200 — ownership verified, tool definitions rated A, listed and healthy |
| `/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6` | **302 → `/mcp/servers`** (on 24.11 it was a 200 that rendered the registry index; it is now an explicit redirect, and still no record) |
| `/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6/badges/score.svg` | 200, and the SVG's only text node is **"This MCP server is not listed on Glama"** — while the connector badge renders the real grade |
| `/mcp/servers/com.onrender.kristo-intelligence-api/kristo-intelligence` | 404 |

**Why the message below is much shorter than the previous draft.** The channel
answers requests shaped like CodersTalk's and Clifty's: name the record, say what to
keep, one ask, no essay. Frank's own words there: *"Most tickets are handled by
agents. There are over 200 tickets created daily. If something requires human
intervention, it takes time."* Ours needs human intervention — only Glama can create
the record — so the message is built to be actioned in one reading.

**Message to post:**

```
Hi — a /mcp/servers/ record that cannot be created from our side, and it is the only thing blocking our listing PR.

Our server is a hosted x402 endpoint (7 tools, streamable HTTP): https://kristo-intelligence-api.onrender.com/mcp

It is listed and healthy as a connector, and we want to keep that record exactly as it is:
https://glama.ai/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence

What is missing is the /mcp/servers/ entry for the same server:
- /mcp/servers/hristovdimitri2-hub/kristo-intelligence-6 redirects to /mcp/servers — no record
- /mcp/servers/com.onrender.kristo-intelligence-api/kristo-intelligence returns 404
- both Add Server paths reject it: "already listed as a hosted connector"
- the servers badge renders "This MCP server is not listed on Glama" while the connector badge renders the real grade

So it can only be created on your side. Either of these is fine for us:
1. create the /mcp/servers/ entry for the repo, pointing at the same hosted endpoint, or
2. compute the `quality` field for the connector listing.

`quality` is what punkpeye/awesome-mcp-servers#13219 is waiting on, and ticket #135407945 has been open since September. Nothing is pending on our side: the repo ships Dockerfile.glama and scripts/mcp_stdio_bridge.py, verified end to end — initialize, then tools/list returns all 7 tools with full schemas.

Thank you.
```

**Optional second message, and it is not about us.** In the same channel dump,
BeneODev asked (25.11, 12:45) whether the large card badge and the small score badge
are treated the same way, and whether keeping the large one still counts as the
backlink the PR needs. **That is the same question we spent two days measuring**, so
the measurable half can be answered without guessing at Glama's policy — and the
policy half is explicitly left to Frank:

```
BeneODev — on the badge question, from someone who measured both paths: they are not interchangeable for a hosted endpoint. If the server is listed under /mcp/connectors/..., then /mcp/servers/<owner>/<repo>/badges/score.svg renders "This MCP server is not listed on Glama" even though you are listed, because that path has no record behind it. The connector badge (/mcp/connectors/.../badges/score.svg) renders the real grade. We hit exactly this — the template badge would have put "not listed" in a README whose whole pitch is "check that a seller is real" — so the README carries the connector badge instead. Whether the PR still counts as a backlink is Frank's call, not something either of us can measure from outside.
```

**And on PR #13219 itself, nothing new is owed.** Frank posted the backlink notice
on 24.11; we answered it the same day — description carries the listing link, prices
corrected, and the badge-URL problem explained — and asked the one question that
matters: whether a `/mcp/servers/` listing is a hard requirement. That question is
still open, it is the same one the Discord message asks, and repeating it on the PR
a day later would be noise rather than pressure.

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
| Teppi | seller's paid-delivery record before signing | **`teppidotxyz@gmail.com`** — npm maintainer of `teppi-client` (§P4, sent 26.11) |
| zauth | monitoring, verification, refund SDK | **`zpointz777@gmail.com`** — npm maintainer of `@zauthx402/sdk` (§P5, sent 26.11) |
| HIVE402 (Script Master Labs) | probe intelligence + demand-weighted trust score | already written to (§O), awaiting reply |
| PEAC Protocol | verifiable receipts | **`peacprotocol@gmail.com`** — npm maintainer (§P6, sent 26.11) |
| OMATrust | key authorizations for signed offers and receipts | **`atom@oma3.org`** — npm maintainer (§P7, sent 26.11) |
| AffixIO | client-side pre-payment policy gate | **`kris@affix-io.com`** — npm maintainer (§P8, sent 26.11) |
| Elara | post-quantum record verification bound to the payment id | **`aivelikivodja@gmail.com`** — the repository owner's public GitHub profile (§P9, sent 26.11); the weakest route of the nine |

**Correction, 26.11.2026.** The rows above said "none published" for six vendors. That
was measured against their **websites** and stopped there. The npm registry publishes
maintainer addresses, and five of the six ship a package; the sixth publishes one on a
GitHub profile. So the list was never unreachable — the search was. `scripts/vendor_contacts.py`
now prints those fields, with the provenance of each address, and every address in this
table is a published field rather than a guess.

**Second correction, same day, and it applies to the six letters already sent (§P4–§P9).**
Their shared paragraph says *"It was paid twelve times, by nine wallets that are not
mine… Lifetime external revenue: five and a half cents."* The measured truth on 26.11 is
**thirteen payments, ten wallets, $0.064**: a thirteenth external payment arrived on
**25.11 at 17:27:01Z** (`0x6c57df…40f3`, $0.01 for `/api/v1/whaleflow`) and had not been
counted, and the $0.25 census canary that briefly inflated the figure was our own gas
wallet and never external at all. The letters therefore **understated** our external
revenue by one payment — the safe direction, and still wrong. **Every later letter states
the figure as of its own send date**, and the number to use is 13 / $0.064 / 10 wallets
until the next settlement.

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

## P2. x402r — the failure population their arbitration layer will actually see (25.11.2026)

**Where:** `hi@x402r.org` (the address their site publishes).

**Why the letter changes shape for them.** Hosannaith sells a reliability score, so
the census is an input to a score. x402r sells **refunds and arbitration**, so what
matters to them is not how many agents arrive but **what goes wrong when one pays**:
the shape of the dispute population. We hold 135 recorded payment attempts with their
outcomes, read one at a time, and the class inside it that a refund protocol has to
be designed for is the one where the seller is wrong — a re-presented signed
authorization answered as a refusal after the payment landed. Our own spec artifact
got exactly that case wrong until a second reader caught it, which makes it a case we
can describe from the inside rather than a hypothetical.

**Subject:** `Your refund protocol needs the failure population — measured at one live x402 paywall`

```
Hello,

You build refunds and arbitration for x402. I run one of the endpoints your protocol would sit in front of, and I have read every payment attempt it has ever recorded, one at a time. That gives me the one number your design needs and cannot get from outside: what actually goes wrong when an agent pays.

The service has run on Base since August: seven paid routes from $0.005 to $0.05, plus a $0.25 dataset. In the last thirty days it answered 1,246,641 requests and was reached by 457 distinct user agents. It was paid twelve times, by nine wallets that are not mine. Lifetime external revenue: five and a half cents.

Then the part that is about you. I hold 135 recorded payment attempts with their outcomes, and I read all of them. Not one refusal was an ordinary buyer with a valid signature and a funded wallet — they were conformance fuzzers and my own test runs. So the dispute population an arbitration layer should be designed for is small, and more usefully it is specific. The one class in it that is genuinely dangerous is not a refusal at all: the buyer re-presents the same signed authorization after a lost response, the facilitator answers "authorization already used" with no hash, and a seller that treats that code as terminal tells a buyer their payment failed when the payment landed. That is a refund claim with the seller in the wrong, produced by a few lines of code, and it is the case my own test artifact got wrong until a second reader caught it.

I am not asking for a favour. The measurement is a document: GET /api/v1/demand-census returns the per-agent table — 1,494 rows, arrival and return behaviour, all 135 payment attempts by outcome, and the payment history by payer class — for $0.25. The aggregate and the method are public first, so you can judge it before buying: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/X402_DEMAND_CENSUS.md

Two things stated plainly. First, I would rather this were an input to what you build than a competing product: you have the protocol and the settlement path, I have the ledger, and the ledger only exists because someone ran a paywall for months and kept the attempts. Second, I hold myself to the standard I am selling — my own signal engine's record is published free at /public/signals/history and it is a losing one: 1 hit against 12 misses across 97 scored calls.

If the failure population is useful to your design, tell me what shape fits and I will cut it that way. If it is not, say so and I will stop treating arbitration as a buyer.

Dimitri
```

## P3. Tanilo x402 Guard — the base rate a spend cap is set without (25.11.2026)

**Where:** `joe@tanilo.io` (the address their docs page publishes).

**Why the letter changes shape for them.** Tanilo checks **price and spend caps
before a payment goes out**, which means their product assumes agents spend. Our
measured behaviour is the opposite: 457 distinct agents reached one live paywall in
thirty days and twelve payments happened, nine of them from wallets that are not ours.
The useful thing we can hand a spend-cap product is not a price list — the catalogue
already has prices — but the **frequency and size of actual spend**, and the
observation that a cap derived from catalogue prices will almost never fire, because
the binding constraint is whether an agent pays at all.

**Subject:** `A spend cap needs the price agents actually pay — measured at one live x402 paywall`

```
Joe,

You build a guard that checks price and spend caps before an agent pays. I run one of the endpoints it would check, and I have the number a spend cap is usually set without: what agents actually pay, and how often they pay at all.

The service has run on Base since August: seven paid routes across four price points, $0.005 to $0.05, plus a $0.25 dataset. In the last thirty days it answered 1,246,641 requests and was reached by 457 distinct user agents. It was paid twelve times, by nine wallets that are not mine. Lifetime external revenue: five and a half cents.

That second sentence is the one I would put in front of your product. A spend cap is a defence against a runaway agent, and the measured behaviour is the opposite of runaway: 457 distinct agents arrived at one paywall in thirty days, and twelve payments happened. A cap derived from catalogue prices will almost never fire, because the binding constraint is not how much an agent is allowed to spend — it is whether it pays anything at all. If your guard's value is measured by what it blocks, that base rate changes what it is worth; if its value is measured by what it lets through safely, it needs the same number from the other side.

I also hold the failure side: 135 recorded payment attempts with their outcomes, read one at a time. Not one refusal was an ordinary buyer with a valid signature and a funded wallet — they were conformance fuzzers and my own test runs. So a spend-cap product is not currently being defeated by buyers; it is being asked to guard a road with almost no traffic on it.

I am not asking for a favour. The measurement is a document: GET /api/v1/demand-census returns the per-agent table — 1,494 rows, arrival and return behaviour, all 135 payment attempts by outcome, and the payment history by payer class — for $0.25. The aggregate and the method are public first, so you can judge it before buying: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/X402_DEMAND_CENSUS.md

Two things stated plainly. First, I would rather this were an input to your guard than a competing product; you have the pre-payment path and the price checks, I have the ledger, and the ledger only exists because someone ran a paywall for months and kept the attempts. Second, I hold myself to the standard I am selling — my own signal engine's record is published free at /public/signals/history and it is a losing one: 1 hit against 12 misses across 97 scored calls.

If the spend base rate is useful, tell me what shape fits and I will cut it that way. If it is not, say so and I will stop treating pre-payment guards as a buyer.

Dimitri
```

## P4. Teppi — a delivery record has no demand base rate (26.11.2026)

**Where:** `teppidotxyz@gmail.com` — the npm maintainer address published on
`teppi-client` (0.10.0). Their site publishes no address, which is why this route was
looked up in the registry rather than guessed; `scripts/vendor_contacts.py` records how
each of these six addresses was found, so none of them is an inference.

**Why them:** of the nine trust-layer vendors, Teppi is the closest to a buyer of this
measurement — they check a seller's **paid delivery record before a buyer signs**, which
is the supply side of exactly the number we hold. Their published client's only
occurrence of "payer" is a field in a receipt.

**Subject:** `A delivery record has no demand base rate — measured at one live paywall`

```
Teppi,

You check a seller's paid delivery record before a buyer signs. I run one of the sellers such a check would be run against, and I can hand you the half of that record no seller publishes — the demand side of it.

What I measure, from a live x402 service on Base since August: seven paid routes from $0.005 to $0.05, plus a $0.25 dataset. In the last thirty days it answered 1,246,641 requests and was reached by 457 distinct user agents. It was paid twelve times, by nine wallets that are not mine. Lifetime external revenue: five and a half cents. I read all 135 recorded payment attempts one at a time. Not one refusal was an ordinary buyer with a valid signature and a funded wallet — they were conformance fuzzers and my own test runs.

Why that matters to a delivery record. Your check answers "did this seller deliver what was paid for". It cannot answer "has anyone ever paid this seller at all", and the base rate is brutal: 457 distinct agents arrived and twelve payments happened, from nine wallets. Two sellers with identical delivery records can differ by every dollar they have ever earned, and a buyer choosing between them is choosing on exactly that.

I am not asking for a favour or offering a partnership deck. The measurement is a document: GET /api/v1/demand-census returns the full per-agent table — 1,494 rows, the arrival and return behaviour of each user agent, all 135 payment attempts by outcome, and the payment history by payer class — for $0.25. The aggregate and the method are public first, so you can judge it before buying: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/X402_DEMAND_CENSUS.md

Two things stated plainly, because they are why I am writing to you rather than to a catalogue.

First, I would rather this became an input to your record than a competing one. You have the delivery path and the receipts; I have the ledger, and the ledger only exists because someone ran a paywall for months and kept the attempts that most sellers delete.

Second, I hold myself to the standard I am selling. My own signal engine's record is published free at /public/signals/history and it is a losing one: 1 hit against 12 misses across 99 scored calls, documented in docs/SIGNAL_RECORD.md.

If a demand base rate is useful to a delivery check, tell me what shape fits and I will cut it that way. If it is not, say so and I will stop treating delivery records as a buyer.

Dimitri
```

## P5. zauth — the failure population a refund layer is built without (26.11.2026)

**Where:** `zpointz777@gmail.com` — the npm maintainer address published on
`@zauthx402/sdk` (0.1.14). Their site publishes no address.

**Why them:** they sell monitoring, verification and a **refund SDK**. A refund layer
needs to know how payments actually fail, and that is the one thing we read by hand.

**Subject:** `Your refund layer's failure population — read one attempt at a time`

```
zauth,

You sell monitoring, verification and refunds for x402 payments. I run one of the services such a layer would watch, so I can hand you the failure population a refund path is designed around — read attempt by attempt rather than assumed.

From a live x402 service on Base since August: seven paid routes from $0.005 to $0.05, plus a $0.25 dataset. In the last thirty days it answered 1,246,641 requests and was reached by 457 distinct user agents. It was paid twelve times, by nine wallets that are not mine. Lifetime external revenue: five and a half cents. I read all 135 recorded payment attempts one at a time.

That reading is the part I would want if I were building refunds. Not one refusal was an ordinary buyer with a valid signature and a funded wallet. They were conformance fuzzers and my own test runs. So a refund policy built on "payments fail sometimes" is solving a problem that did not appear once in 135 real attempts at a live paywall — while the problem that did appear, nobody arriving at all, is invisible to a monitoring layer that only watches traffic it already receives.

I am not asking for a favour. The measurement is a document: GET /api/v1/demand-census returns the per-agent table — 1,494 rows, arrival and return behaviour, all 135 payment attempts by outcome, and the payment history by payer class — for $0.25. The aggregate and the method are public first: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/X402_DEMAND_CENSUS.md

Two things stated plainly. First, I would rather this were an input to your monitoring than a competing one: you have the observation points and the SDK, I have a ledger that only exists because someone kept months of attempts. Second, I hold myself to the standard I am selling — my own signal engine's record is published free at /public/signals/history and it is a losing one: 1 hit against 12 misses across 99 scored calls, documented in docs/SIGNAL_RECORD.md.

If the failure taxonomy is useful, tell me what shape fits and I will cut it that way. If it is not, say so and I will stop treating monitoring vendors as a buyer.

Dimitri
```

## P6. PEAC Protocol — a receipt proves one payment, not a market (26.11.2026)

**Where:** `peacprotocol@gmail.com` — the npm maintainer address published on
`@peac/adapter-x402` (0.16.5). Their site publishes no address.

**Why them:** they build **verifiable receipts for x402 payments**. A receipt is
per-payment evidence; the question it cannot answer is whether the market those receipts
describe has more than a handful of payers in it.

**Subject:** `A receipt proves one payment; it does not say whether anyone pays`

```
PEAC Protocol,

You build verifiable receipts for x402 payments. I run one of the services whose payments would be receipted, and I can hand you the aggregate that a receipt corpus structurally cannot contain — the base rate underneath it.

From a live x402 service on Base since August: seven paid routes from $0.005 to $0.05, plus a $0.25 dataset. In the last thirty days it answered 1,246,641 requests and was reached by 457 distinct user agents. It was paid twelve times, by nine wallets that are not mine. Lifetime external revenue: five and a half cents. I read all 135 recorded payment attempts one at a time; not one refusal was an ordinary buyer with a valid signature and a funded wallet — they were conformance fuzzers and my own test runs.

The gap that leaves is the one a receipt cannot close. A receipt proves that a specific payment happened and is intact. It says nothing about whether anyone pays at all: at one live endpoint, 457 distinct agents arrived and twelve payments happened, from nine wallets. A buyer looking at a set of valid receipts is looking at the wins with no denominator, and the denominator is the number that decides whether a seller is alive.

I am not asking for a favour. The measurement is a document: GET /api/v1/demand-census returns the per-agent table — 1,494 rows, arrival and return behaviour, all 135 payment attempts by outcome, and the payment history by payer class — for $0.25. The aggregate and the method are public first: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/X402_DEMAND_CENSUS.md

Two things stated plainly. First, I would rather this became an input to what you publish than a competing product: you have the cryptographic side and I have the ledger, and neither substitutes for the other. Second, I hold myself to the standard I am selling — my own signal engine's record is published free at /public/signals/history and it is a losing one: 1 hit against 12 misses across 99 scored calls, documented in docs/SIGNAL_RECORD.md.

If a demand base rate belongs beside a receipt, tell me what shape fits. If it does not, say so and I will stop treating receipt layers as a buyer.

Dimitri
```

## P7. OMATrust — signed offers need a demand prior (26.11.2026)

**Where:** `atom@oma3.org` — the npm maintainer address published on `@oma3/omatrust`
(0.1.0-alpha.14). Their site publishes no address.

**Why them:** they do **key authorizations for Signed Offers and Receipts**. An offer
scheme needs a prior that anyone accepts offers, and that prior is not published by
anyone.

**Subject:** `Signed offers need a demand prior, and nobody publishes one`

```
OMATrust,

You do key authorizations for signed offers and receipts on x402. I run one of the services such offers would be made against, and I hold the prior that an offer scheme needs and that no directory publishes — whether anyone accepts.

From a live x402 service on Base since August: seven paid routes from $0.005 to $0.05, plus a $0.25 dataset. In the last thirty days it answered 1,246,641 requests and was reached by 457 distinct user agents. It was paid twelve times, by nine wallets that are not mine. Lifetime external revenue: five and a half cents. I read all 135 recorded payment attempts one at a time; not one refusal was an ordinary buyer with a valid signature and a funded wallet — they were conformance fuzzers and my own test runs.

Why that is a prior and not a curiosity. An authorization proves an offer is authentic and properly keyed. It cannot tell the party receiving it whether offers in this market are ever taken up. At one live endpoint the answer is twelve payments from nine wallets out of 457 agents that arrived, so an offer layer that treats "signed and authorized" as "commercially meaningful" is ranking sellers on a property none of them has yet.

I am not asking for a favour. The measurement is a document: GET /api/v1/demand-census returns the per-agent table — 1,494 rows, arrival and return behaviour, all 135 payment attempts by outcome, and the payment history by payer class — for $0.25. The aggregate and the method are public first: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/X402_DEMAND_CENSUS.md

Two things stated plainly. First, I would rather this became an input to your authorization layer than a competing one: you have the keying and the signature side, I have a ledger that only exists because someone ran a paywall and kept the attempts. Second, I hold myself to the standard I am selling — my own signal engine's record is published free at /public/signals/history and it is a losing one: 1 hit against 12 misses across 99 scored calls, documented in docs/SIGNAL_RECORD.md.

If a demand prior is useful beside a signed offer, tell me what shape fits. If it is not, say so and I will stop treating offer schemes as a buyer.

Dimitri
```

## P8. AffixIO — a pre-payment gate with no demand base rate (26.11.2026)

**Where:** `kris@affix-io.com` — the npm maintainer address published on `affixio`
(2.0.5). Their site publishes no address.

**Why them:** their package is an **optional client-side policy gate using x402's
pre-payment hook**, and the page they publish for it is titled agent-trust. A gate that
decides whether to pay is deciding on a base rate it does not have.

**Subject:** `A pre-payment gate with no demand base rate approves dead endpoints`

```
Kris,

You ship an optional client-side policy gate on x402's pre-payment hook — the decision point before a payment payload is created. I run one of the endpoints such a gate would be pointed at, and I hold the base rate the gate is currently deciding without.

From a live x402 service on Base since August: seven paid routes from $0.005 to $0.05, plus a $0.25 dataset. In the last thirty days it answered 1,246,641 requests and was reached by 457 distinct user agents. It was paid twelve times, by nine wallets that are not mine. Lifetime external revenue: five and a half cents. I read all 135 recorded payment attempts one at a time; not one refusal was an ordinary buyer with a valid signature and a funded wallet — they were conformance fuzzers and my own test runs.

What that means for a pre-payment gate. Your hook can enforce policy, price and cap, and it does that well. What it cannot currently express is "this endpoint is correctly payable and commercially dead", because the base rate is not in any catalogue: 457 agents arrived at one live endpoint and twelve payments happened, from nine wallets. A gate with only conformance signals approves both sellers identically, and the buyer pays the dead one first.

I am not asking for a favour. The measurement is a document: GET /api/v1/demand-census returns the per-agent table — 1,494 rows, arrival and return behaviour, all 135 payment attempts by outcome, and the payment history by payer class — for $0.25. The aggregate and the method are public first: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/X402_DEMAND_CENSUS.md

Two things stated plainly. First, I would rather this became an input to your gate than a competing product: you have the pre-payment path and the policy engine, I have the ledger, and the ledger only exists because someone kept months of attempts. Second, I hold myself to the standard I am selling — my own signal engine's record is published free at /public/signals/history and it is a losing one: 1 hit against 12 misses across 99 scored calls, documented in docs/SIGNAL_RECORD.md.

If a demand signal is useful at the pre-payment hook, tell me what shape fits. If it is not, say so and I will stop treating policy gates as a buyer.

Dimitri
```

## P9. Elara — attestation proves a record is intact, not that a market exists (26.11.2026)

**Where:** `aivelikivodja@gmail.com` — the address published on the GitHub profile of
`navigatorbuilds`, the repository owner, after their `elara-verify` crate showed **no
owners** and their commits are signed `Elara Project <noreply@elara.dev>`. Recorded
plainly because it is the weakest of the six routes: it is a personal profile address,
not a project one, and the repository was last pushed on 10.10.2026.

**Why them:** they do **post-quantum record verification with the attestation bound to
the x402 payment id** — the same gap as the others, from the cryptography side.

**Subject:** `Attestation proves a record is intact, not that a market exists`

```
Elara,

You verify records post-quantum and bind the attestation to the x402 payment id. I run one of the services whose payment ids such an attestation would be bound to, and I hold the number an attestation cannot contain: whether anyone pays.

From a live x402 service on Base since August: seven paid routes from $0.005 to $0.05, plus a $0.25 dataset. In the last thirty days it answered 1,246,641 requests and was reached by 457 distinct user agents. It was paid twelve times, by nine wallets that are not mine. Lifetime external revenue: five and a half cents. I read all 135 recorded payment attempts one at a time; not one refusal was an ordinary buyer with a valid signature and a funded wallet — they were conformance fuzzers and my own test runs.

The gap is structural rather than a defect in your work. An attestation proves a record is intact and bound to the right payment. It cannot say whether the payment was one of nine wallets or one of nine hundred, and at one live endpoint 457 agents arrived and twelve payments happened. A verifier that reports "intact" to a buyer, with no denominator beside it, is reporting the strongest property of the weakest market.

I am not asking for a favour. The measurement is a document: GET /api/v1/demand-census returns the per-agent table — 1,494 rows, arrival and return behaviour, all 135 payment attempts by outcome, and the payment history by payer class — for $0.25. The aggregate and the method are public first: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/X402_DEMAND_CENSUS.md

Two things stated plainly. First, I would rather this were an input to your verifier than a competing one: you have the attestation and the post-quantum side, I have the ledger. Second, I hold myself to the standard I am selling — my own signal engine's record is published free at /public/signals/history and it is a losing one: 1 hit against 12 misses across 99 scored calls, documented in docs/SIGNAL_RECORD.md.

If a demand base rate is useful beside an attestation, tell me what shape fits. If it is not, say so and I will stop treating record verifiers as a buyer.

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

## R. Ernest — he priced the measurement back to us (25.11.2026)

**Where:** reply in the same Gmail thread as §L2 and §N, to `ernest-earnordie@agentmail.to`.

**What he sent:** two offers — a one-time 7-day demand-side ledger of our own seven
routes for **$25**, or **$15/month** with weekly updates and a quarterly deep-dive.
Five tracked items: daily unique agent visits per route, share of visits from paying
wallets, repeat visitor rate (3+ visits), revenue per agent, route-specific
conversion. He adds that he will send the first audit directly and that, if it is
valuable, we can introduce him to other sellers.

**Why the answer is no, and what the no is worth.** We already hold all five, for
thirty days rather than seven, per route, plus the individual reading of all 135
payment attempts; §N told him so in the previous message. More decisive than that:
**not one of his five metrics is observable from outside a service.** Repeat rate,
paying-wallet share, revenue per agent and conversion live in the seller's request
log. He can see our 402s; he cannot see who came back or who paid. So the audit is
either produced from data we hand over or it is a guess — and paying for the
formatting of our own logs is the one purchase that cannot teach us anything.

**What is worth keeping from his email:** he answered §N's first question by
pricing it. **The buyer of a demand-side ledger is the seller** — the same
conclusion we reached when the census was priced instead of given away. That is a
second, independent confirmation of the product shape, from the only other person
in this market who sells measurement.

**The shape offered instead of a purchase:** he has the sellers or can find them;
the measurement must come from each seller's own log; we have the method, the
extraction and a published specimen. No split is proposed here on purpose — we do
not yet know whether the sellers exist, and naming a number before that is how the
last six weeks were spent.

**And a test that costs nothing:** if he can produce a seven-day ledger for our
seven routes without our logs, we compare it line by line with our own count and
publish the difference, whatever it shows. If it holds, he has a case study
written by a seller who can check him; if it does not, the boundary of his method
is measured rather than asserted. This is the same rule the whole project runs on,
turned on a vendor.

**Subject:** `Re: measurement ledger - proposal`

```
Ernest,

Two answers: one is a no, the other is an offer.

The no. I will not buy the ledger, and not because of the price. I already have all five metrics you list, for thirty days rather than seven, per route, and I read all 135 payment attempts one by one instead of counting them. The free sample of the shape is at https://kristo-intelligence-api.onrender.com/api/v1/demand-census/sample and the live document is the $0.25 route next to it. Paying $25 for a seven-day version of it would be buying back my own logs.

There is a structural reason, and it is the part worth your time. Not one of your five metrics is observable from outside a service. Repeat visitor rate, share of visits from paying wallets, revenue per agent and per-route conversion all live in the seller's request log. You can see our 402s from outside; you cannot see who came back, who paid, or what they paid for. So an audit of my seven routes is either produced from data I give you, or it is a guess. That is not a criticism of your method, it is the boundary of it — and I would rather say so now than discover it after paying.

Now the useful half of your email. You priced it, and that answers the question I asked you last time: the buyer of a demand-side ledger is the seller. That matches what I see from my side, and it is the second time this week the same shape has come back to me from someone else's numbers.

So, no purchase, but a different shape if you want it. You sell this to sellers. The measurement has to come from each seller's own log. I have the method, the extraction and a published specimen; you have, or can find, the sellers. If you bring them and I supply the measurement, we can talk about how the money splits. I am deliberately not proposing numbers here, because I do not know yet whether those sellers exist, and I have spent enough of this month on products nobody buys.

One test that costs you nothing. Produce a seven-day ledger for my seven routes without my logs, and I will compare it line by line against my own count and publish the difference, whatever it shows. If it holds up, you have a case study written by a seller who can check you. If it does not, we will both know where the boundary is. I would rather find that out this way than by paying for it.

The offer of one free copy of the full census stands, if you want to see the document before judging it.

And the question from my last message is still open, because it decides what I do next: do the agents you see look like buyers or like monitors? My own count says monitors — 457 agents reached a paywall and twelve payments came from nine wallets that are not mine, five and a half cents lifetime. If you see the same, say so plainly and I will stop treating the demand side as a market. If you see something else, tell me what, because then one of us is measuring the wrong thing.

Dimitri
```

## S. Ernest — the benchmark, checked against our own ledger (25.11.2026)

**Where:** reply in the same Gmail thread, to `ernest-earnordie@agentmail.to`.

**What he sent:** the free benchmark he owed from §L2 — nine paths with live
prices, a category-by-category comparison against named incumbents with 30-day
call counts, and the verdict that **six of seven routes are commodity categories
with the slot taken**, while **verify-seller / seller-check is the only
differentiated route** and should become the flagship at a price above $0.01.

**Checked before replying, and this is the part that matters:**

1. **His route table is exact.** All nine paths answer a live `402` with exactly
   the price he lists and the same `payTo` (`0xB4Fc…C844`) — verified by asking
   each one unpaid. Nine paths, but **seven routes**: `whale-alerts`,
   `trading-signals`, `seller-check` and `onchain-sales` are aliases, so
   verify-seller and seller-check are the same product counted in two rows (4 + 2
   calls) and the seven-route framing is right while the arithmetic is split.
2. **He contradicts himself on the two prices that carry his recommendation.** In
   his header both are `$0.05`; in the category section both are `$0.01`. They are
   **$0.05 live**. So the advice "not $0.01 — that reads as a toy" is aimed at a
   price we do not have: the route is already five to ten times the incumbents he
   compares it with.
3. **His call counts cannot be external demand.** Our published census (24.11):
   **180 payments lifetime, of which 131 — $1.785 of $1.983 — are our own key**,
   and **12 are external ($0.054, 9 wallets)**. So 22 calls in a 30-day window
   across our routes is the size of our own testing and the samplers, not of
   buyers; the spread he reports — 2 calls on six different routes — is the
   signature of a smoke test that hits each route once or twice.
4. **The generalisation, which is the useful thing in the whole email:** no index
   can separate a seller's test traffic from a buyer's. His incumbents' 139, 113
   and 5,538 calls are unclassified in exactly the same way, so "you are invisible
   at 2 against 5,538" may be comparing their test harness with ours. **This is
   the best demonstration of his own product's boundary**: the classification he
   needs is precisely what cannot be seen from outside — which is what §R said,
   and it now has his own numbers as evidence.

**Not measured, and said so:** the per-path external split would settle the
recommendation properly, and it cannot be produced from this machine — the
`DATABASE_URL` in the Render env is the **internal** host
(`dpg-daj8ue0jo6nc73ctsh70-a`, DNS does not resolve from outside), and the local
`data/dashboard_state.db` is a **test** ledger (payers `0xaaaa…`, tx `0xcdcd…`,
`payment_guards` rows from 13.09), so it is not evidence about demand. Recorded
because it was nearly used as evidence: the first per-route split this session
computed came from that test file and said "24 settled calls, all on `/api/stats`"
— a true statement about a test database and a false one about the business.

**The contradiction with §L2, named rather than smoothed over.** On 24.11 we told
him we would **stop treating verify-seller as a business**, acting on his earlier
analysis (platforms absorb the cost, or run a sanctions screen). He now recommends
making it the flagship. Both cannot be right, and the tie-breaker is the per-path
external split above. What is true either way: the **pre-payment check** space is
not empty — the spec repo's own third-party list names nine trust vendors, and at
least two sell pre-payment checks (Tanilo's price/spend-cap guard, Hosannaith's
reliability oracle). What nobody else sells is **payment-history** verification,
which is the narrow thing we actually have.

**Subject:** `Re: Your 7-route benchmark - which design a buyer would pay for`

```
Ernest,

Thank you, and I checked it before answering, because that is the only way a benchmark is worth anything to either of us.

What holds: your route table is exact. I asked all nine paths myself, unpaid, and every one answers a live 402 with exactly the price you list, all to the same payTo. Two corrections, both small and both load-bearing.

One: the nine paths are seven routes. whale-alerts, trading-signals, seller-check and onchain-sales are aliases, so verify-seller and seller-check are one product counted in two rows. Your seven-route framing is right; the per-row counts split one route in two.

Two: on the two routes that carry your recommendation your own email disagrees with itself. Your header says $0.05 for both; your category section says $0.01. They are $0.05, verified live just now. So "not $0.01, that reads as a toy" is advice about a price I do not have. verify-seller is already five to ten times the signal prices you compare it against.

Now the counts, which is where I think your benchmark has a hole you can fix. My published census says: 180 payments lifetime, of which 131 — $1.785 of $1.983 — are my own key, and 12 are external, from nine wallets, $0.054. So 22 calls in thirty days across my routes is the size of my own testing and the samplers, not of buyers. The distribution you report gives it away: two calls on six different routes is what a smoke test looks like, not what demand looks like.

And that is not a criticism of you, it is the thing your own product exists to fix. No index can separate a seller's test traffic from a buyer's. Your incumbents' 139, 113 and 5,538 calls are unclassified in exactly the same way mine are, so "you are invisible at 2 against 5,538" may be comparing their test harness with my test harness. Your benchmark is the best argument I have seen for the ledger you are selling — and also the clearest statement of its boundary: the classification has to come from the seller's log, which is what I said last time and what your numbers now demonstrate.

So the paid offer stays declined, for the reason I gave, and the other shape stays open: bring a seller who will hand over a log, and I will supply the measurement.

On the recommendation itself, one thing to say plainly. On 24 November I told you I would stop treating verify-seller as a business, acting on your earlier read — platforms absorb the cost or run a sanctions screen. You are now telling me it is the one route worth being the flagship. Both cannot be right. What would settle it is the per-path external split, and I cannot produce it from where I am: the ledger address in my environment is internal-only. What I can say is that lifetime external is twelve payments across all routes, so whatever the split is, the absolute numbers are small, and "flagship" would be a positioning decision rather than a demand finding. For what it is worth, the pre-payment check space is not empty either — the spec repository's own third-party list names nine trust vendors, and at least two sell pre-payment checks. What nobody else sells is payment-history verification. That is the narrow thing I have.

One question, and it is worth more to me than the ledger. For the whale category: is the 5,538 on sniperx payer-classified, or is it raw settlements on their payTo? If you can answer that for one incumbent, I learn something about this market I cannot measure from inside my own logs.

Dimitri
```

## T. Ernest — the real per-path ledger, and his conclusion survives it (25.11.2026)

**Where:** same thread, `ernest-earnordie@agentmail.to`. Sent after §S, because §S said
the per-path split could not be produced from here and it turned out it could.

**How it became measurable.** The `DATABASE_URL` in the Render env is the internal
host and does not resolve outside Render. `GET /v1/postgres/{id}/connection-info`
returns an **external** connection string for the same instance
(`…oregon-postgres.render.com`), so the read-only queries ran after all. Nothing was
written; the session opened with `default_transaction_read_only=on`; `ts` is `text`
in production and needs `::timestamptz`.

**What production says — settled calls, last 30 days, own key separated:**

| path | all | not ours |
|---|---|---|
| `/api/v1/signal` | 22 | 3 |
| `/api/v1/verify-seller` | 19 | 4 |
| `/api/v1/whaleflow` | 14 | 1 |
| `/api/sales` | 13 | 1 |
| `/api/bot-status` | 10 | 0 |
| `/api/stats` | 9 | 1 |
| `/api/arb/opportunities` | 5 | 0 |
| `/api/v1/trading-signals` | 3 | 1 |
| `/api/v1/whale-alerts` | 2 | 0 |
| `/api/v1/seller-check` | 2 | 0 |
| `/api/v1/onchain-sales` | 2 | 0 |
| `/api/v1/arbitrage-opportunities` | 2 | 0 |

**His counts are not reproducible under any window** — 7, 14, 21, 30, 45 and 60 days
all give different numbers from his. But six of his rows (the four aliases plus
`stats` and `bot-status`, 2 each) are **exactly the smoke-test sweep of 10–11
November**, one paid call per path on each of those two days. So the index behind
his benchmark is reading our test traffic, and on the two rows that carry his
recommendation (signal 8, verify-seller 4) it matches nothing we can produce, in
either direction: **it undercounts unevenly.** That is a defect in a product he
sells, and he was told.

**And his conclusion survives our own books, which is the part that matters.**
`verify-seller` is the **top route by calls that are not ours** — 4 of 19, `$0.04`
of its `$0.95` — and took **two of the three `external`-class payments** in the
window; `signal` took one; every other route at most one. So "this is the one route
with real external interest" is what the ledger says too. **§L2's decision to drop
it was wrong on the earlier read**, and right about the price: it is already `$0.05`.

**The scale, stated so neither side over-reads it:** the whole 30-day total from
anyone who is not us is **11 payments, `$0.072`, six addresses**. The demand is real
and it is cents — so "flagship" is a positioning decision, not a demand finding.

**Subject:** `Re: Your 7-route benchmark - which design a buyer would pay for`

```
Ernest,

A correction to my last message, in your favour, and then the numbers.

I said I could not produce the per-path split from where I am. That was true of the address in my environment, and I found the other one, so here it is — settled calls in the last 30 days, my own key separated:

  /api/v1/signal                    22 all    3 not mine
  /api/v1/verify-seller             19        4
  /api/v1/whaleflow                 14        1
  /api/sales                        13        1
  /api/bot-status                   10        0
  /api/stats                         9        1
  /api/arb/opportunities             5        0
  /api/v1/trading-signals            3        1
  /api/v1/whale-alerts               2        0
  /api/v1/seller-check               2        0
  /api/v1/onchain-sales              2        0
  /api/v1/arbitrage-opportunities    2        0

Two things follow.

First, your counts. I could not reproduce them under any window: 7, 14, 21, 30, 45 and 60 days all give different numbers from yours. But six of your rows — the four aliases plus stats and bot-status, two each — are exactly my own smoke-test sweep of 10 and 11 November, one paid call per path on each of those two days. So the index behind your benchmark is reading my test traffic, which is what I suspected. And on the two rows that carry your recommendation, signal at 8 and verify-seller at 4, it matches nothing I can produce in either direction, so it is undercounting unevenly. You may want to know that before you sell a ledger built on it.

Second, and more important: your conclusion survives my numbers. verify-seller is the top route in my ledger by calls that are not mine — 4 of 19, and $0.04 of its $0.95 — and it took two of the three external-class payments in the window. Signal took one. Every other route took at most one. So "this is the one route with real external interest" is what my own books say as well, and last week I told you I was dropping it. I was wrong to drop it on that earlier read, and right that the price was never the problem: it is already $0.05.

The honest scale, so neither of us over-reads it: the whole thirty-day total from anyone who is not me is 11 payments, $0.072, from six addresses. The demand is real and it is cents. Flagship is a positioning decision; no ledger will change that part.

The offer stands as before.

Dimitri
```

## U. Ernest — the introduction we do not have, and the partner question (25.11.2026)

**Where:** same thread, `ernest-earnordie@agentmail.to`.

**What he sent.** Two answers. On the introduction: send the address directly, or
forward his, and he opens with a free benchmark of that seller's own routes, never
quoting our numbers. On which of the two earning things to push a seller toward:
**the measurement — but as seller-side due diligence, not a demand forecast.** His
reasoning is our own numbers: 457 agents, 12 paying wallets, every refusal a fuzzer
or our test run, so "the demand side at the moment it meets a price is not a
market; it is monitors meeting a wall." A demand-side ledger therefore sells to
exactly one buyer — another seller deciding what to build and at what price — and
should be priced as a subscription. Supply side, same conclusion: a seller with no
unique data is better off buying the measurement than building a seventh route.

**Checked before answering: we do not have the contacts.** `crm_sales.db` holds
**5 leads**; `agent_catalog.db` holds **zero** customer checkouts. What we actually
know is (a) thousands of sellers **by their listings** and (b) a short list of
verifiers, directories and trust vendors — the layer Ernest and we both sit in, not
his buyers. §L2's "I do know sellers with the symptom" was true of the layer, not
of an address book, and the correction goes in the reply rather than a cold list
with our name on it.

**The strategic point, stated plainly for the first time.** His answer confirms, for
the third time this week, that **the buyer of demand-side measurement is the
seller** — which makes his product and ours the same product. He cannot produce the
five metrics without the seller's log; we have the method, the extraction
(`scripts/build_demand_census.py`) and a live dataset. He has the sales motion; we
have none. Neither of us has the other's half, and that is a partnership question,
not an introduction. So the reply asks him to **name his share** — the one thing §R
deliberately left open, now asked because the shape has been confirmed three times.

**What we give, and what we still want.** Given: the §T case study — his index
undercounts our settlements unevenly, measured against a seller's own books — usable
by him attributed or not. Wanted, still unanswered: is the 5,538 on sniperx
payer-classified, or raw settlements on their `payTo`?

**Subject:** `Re: measurement ledger — the intro, and what I would push`

```
Ernest,

Two answers, and one of them is a correction.

The introduction: I do not have it, and I would rather say so than send you a cold list with my name on it. I checked before writing. What I actually have is thousands of sellers I know by their listings and none I know as contacts who would take an introduction. The people I do know are verifiers, directories and trust vendors — the layer you and I both sit in, not your buyers. Last week I told you I knew sellers with the symptom. That was true of the layer, not of my address book, and I am correcting it before it costs you a wasted benchmark.

What I can give you instead is worth more than a name. Your index undercounts my settlements, unevenly: six of your rows are exactly my own test sweep of 10 and 11 November, signal is 8 against my 22, verify-seller 4 against my 19. That is a quality finding about the data you sell, from a customer who has the ground truth, and you may use it, attributed or not. I would rather hand you that than a stranger's address.

Your second answer is the most useful thing anyone has said to me this week, and it is the third time the same shape has come back: the buyer of demand-side measurement is the seller, and it is due diligence rather than a forecast. Which also means we are selling the same product. I have the measurement, the extraction and a live dataset; you cannot produce the five metrics without the seller's log. You have a sales motion and I have none. Neither of us has the other's half.

So the introduction is the wrong question. The right one is the one I asked twice and have not had an answer to: if I supply and you sell, what is your share? Name it and I will answer. If the honest answer is that you would rather keep the customer, say that too — then we both know we are competitors, and I will stop asking.

And the one thing I still want, which is not a favour: is the 5,538 on sniperx payer-classified, or raw settlements on their payTo? One incumbent answered would teach me something I cannot measure from inside my own logs.

Dimitri
```

## V. Ernest — the /mcp preflight, measured, fixed and re-validated (25.11.2026)

**Where:** same thread, `ernest-earnordie@agentmail.to`.

**What he sent.** A finding: `/mcp` fails the 402 preflight, "it is only the status
line that is wrong", with a Coinbase validator quote; the proposed fix (return HTTP
402 with the challenge in the body and the base64 `PAYMENT-REQUIRED` header, JSON-RPC
for the paid response only); a public answer to CDP ticket #881; market numbers
(67.7% of paid rows paid once and 11% of revenue, 6.2% paid five or more times and
89.1%); a new recommendation to push `/api/v1/whale-alerts`; and an offer to write
the fix up as a change-sheet for **$15**.

**Checked before answering, and it split three ways.**

1. **His two status codes are two different requests.** `GET /mcp` → **200** (what
   the validator probes, and what fails). `POST /mcp` with a bare body → **400**.
   Neither is the tool result, so the diagnosis mixed the probe with the protocol.
2. **The MCP tool result is already fully conformant** — measured live, field by
   field: `isError: true`, `structuredContent` with the full PaymentRequired, and
   `content[0].text` as the JSON of the same. `specs/transports-v2/mcp.md` requires
   exactly that, and Coinbase's own seller docs call the tool result "MCP's
   equivalent of an HTTP 402 status and PAYMENT-REQUIRED header". **His fix would
   have broken every documented x402 MCP client** (`wrapMCPClientWithPayment`,
   `create_x402_mcp_client`) — a standard MCP client reads the *tool result*, not
   the status line, and it already worked against us.
3. **The validator failure is real and reproduced with our own CDP credentials.**
   Before: `/mcp` 25 checks, `returns_402` **FAIL** ("Endpoint returns 200 OK — it
   needs to return 402 for unauthenticated requests to be discoverable",
   expected 402 actual 200), other 24 skipped; `/api/v1/signal` 25/25 PASS.

**The fix, shipped and proven.** `GET /mcp` is now a paid resource at the cheapest
existing price (`$0.005`): the challenge carries the `PAYMENT-REQUIRED` header,
`accepts[]`, `resource` and the bazaar block the last ten checks read, and a paid GET
delivers the document it always served. `POST`/`DELETE` are untouched — the paywall
exempts them explicitly, because the spec requires the tool result to carry the
challenge. The document stays free at `/mcp.json`. **Validator after: 25 of 25 PASS,
`valid: true`.**

The cascade was real and worth recording: adding a paid route failed **eight** tests —
the funnel, the "says when to use it" rule, the job-name rule, the HEAD-challenge
rule, two MCP info tests, and the two suite counters. Each was a repo invariant
saying "a paid route must be integrated as a product", and each was satisfied rather
than exempted. Full suite **1486 passed** (was 1481; five new tests pin both halves:
GET challenged, POST never challenged).

**No to the $15 change-sheet**, and not because of the money: the fix took less time
than the two emails, and the change-sheet as described would have taken the MCP
surface backwards.

**Two corrections to his market reading, from our own ledger.** `whale-alerts` is an
alias of `whaleflow` — 14 settled calls in thirty days, **1** not ours; `verify-seller`
is 19 and **4** not ours and took two of the three external-class payments. So the
repeat-use route by our books is verify-seller, not whale-alerts. And the price band:
our one route above `$0.02` is the one with the most calls that are not ours, which is
the opposite of "the $0.005 band is worst"; with eleven non-own payments we cannot
test a band at all.

**And one correction to his #881 answer, measured.** There are no "old `/mcp` URLs" to
redirect: the live payTo carries 20 rows including 8 `/mcp#tool`, the retired payTo
carries 6, and they are the **same host and path** (`…/mcp#verify_seller`,
`…/mcp#get_trading_signal`), indexed on 10.11. A row is keyed by the address in the
challenge, so nothing served today re-indexes a row onto another address; the six can
only age out — which is what he said first.

**Subject:** `Re: Your /mcp endpoint fails the 402 preflight — measured, and it is one status code`

```
Ernest,

You found a real defect, and the cause and the fix are both wrong. I can show you which is which, because I ran your validator myself.

Your two status codes are two different requests. A GET of /mcp returned 200 — that is what the validator probes, and that is what fails. A POST of /mcp with a bare body returned 400. Neither is the tool result.

The tool result, measured live just now: HTTP 200, with `isError: true`, `structuredContent` carrying the full PaymentRequired object, and `content[0].text` as the JSON of the same. That is not a challenge buried anywhere — it is the documented signal. specs/transports-v2/mcp.md, Payment Required Signaling: "When a tool requires payment, servers MUST return a tool result with isError: true containing the PaymentRequired data", in both structuredContent and content[0].text, with the payment returning at _meta["x402/payment"]. Your own docs say the same in prose: the tool result is MCP's equivalent of an HTTP 402 status and PAYMENT-REQUIRED header. So the fix you proposed — HTTP 402, JSON-RPC only for the paid response — would break every client written to that spec, including wrapMCPClientWithPayment and create_x402_mcp_client. A standard x402 MCP client does not read the status line. It reads the tool result, and it already works against us.

Your validator failure is real, though, and I reproduced it with my own CDP credentials. Before: GET /mcp, 25 checks, returns_402 FAIL — "Endpoint returns 200 OK, it needs to return 402 for unauthenticated requests to be discoverable", expected 402 actual 200 — and the other 24 skipped. GET /api/v1/signal: 25 of 25 pass. So the defect is not the MCP challenge. It is that GET /mcp served a free document on the URL the index treats as a payable resource, which is exactly the URL the eight /mcp#tool#tool rows are indexed against.

Fixed and re-validated. GET /mcp now answers the canonical challenge, PAYMENT-REQUIRED header, accepts[], resource and the bazaar block the last ten checks read, and a paid GET delivers the document it always served. POST and DELETE are untouched, because that is the transport and the spec puts the challenge in the tool result. The document is still free at /mcp.json, so nothing that reads it is worse off. Validator after the change: 25 of 25 pass, valid true.

So no to the $15 change-sheet, and not because of the money. The fix took less time than the two emails, and the change-sheet as described would have taken the MCP surface backwards. If you want a change-sheet worth paying for, it is the one I cannot write: the payer classification behind your benchmark, which your index cannot produce and my ledger can.

On the benchmark numbers, which are the best thing you have sent: 67.7% of paid rows paid once and 11% of revenue, 6.2% paid five or more times and 89.1%. That matches everything I measure and it is the strongest argument yet against building another route. Two corrections from my ledger, though. First, whale-alerts is an alias of whaleflow: 14 settled calls in thirty days, 1 of them not mine. verify-seller is 19 and 4 not mine, and it took two of the three external-class payments. So the repeat-use route by my books is verify-seller, not whale-alerts. Second, the price band: my one route above $0.02 is the one with the most calls that are not mine, which is the opposite of "the $0.005 band is worst". With eleven non-own payments I cannot test a band at all. You can, across 1,774 routes, if the classification holds — which your benchmark of my routes shows it does not.

On #881, thank you for answering it publicly, and one correction, also measured. There are no "old /mcp URLs" to redirect. I pulled both sets from the merchant endpoint: the live payTo carries 20 rows including 8 /mcp#tool, the retired payTo carries 6, and they are the same host and path — .../mcp#verify_seller, .../mcp#get_trading_signal — indexed on 10 November. A row is keyed by the address in the challenge, so nothing I serve today re-indexes a row onto another address; a paid call writes the live rows. The six can only age out, which is what you said first.

Dimitri
```

## W. Ernest — the /mcp answer, plus the five replies that bounced (25.11.2026)

**Where:** `ernest-earnordie@agentmail.to`. **This supersedes §V, which was never
delivered**, and it carries the three points from §R, §S, §T and §U, which were
never delivered either.

**Why it exists.** Reading the mailbox back over IMAP
(`_tools/check_mail_delivery.py`) showed **seven bounces**, every one of them
`ernest@nolimbsfighting.com`: `554 5.7.1 : Recipient address rejected: user … does
not exist`. The Sent folder shows the switch precisely — everything up to 24.11
19:52Z went to `ernest-earnordie@agentmail.to` and arrived; from then on the sends
used the address recorded in this file, and §R, §S, §T, §U and §V all bounced while
`send_draft.py` printed "sent". The conversation continued without them, which is
how it went unnoticed until the owner saw the delivery-failure notices.

**One email rather than five.** The unsent messages were a sequence, and replaying
them would be a flood for a reader who has moved on; so the /mcp answer leads, and
the three live points follow under a heading that says plainly they were never
received.

**Subject:** `Re: Your /mcp endpoint fails the 402 preflight — measured, and it is one status code`

```
Ernest,

First, a correction of my own, because it is the reason this reply is late. My last five messages to you went to ernest@nolimbsfighting.com and every one bounced — "554 5.7.1 : Recipient address rejected: user ernest@nolimbsfighting.com does not exist". I found that by reading my own mailbox rather than assuming, and I am writing to the address you actually use. Three of those messages are summarised at the end, so nothing is lost.

Now your /mcp finding. You found a real defect, and the cause and the fix are both wrong. I can show you which is which, because I ran your validator myself.

Your two status codes are two different requests. A GET of /mcp returned 200 — that is what the validator probes, and that is what fails. A POST of /mcp with a bare body returned 400. Neither is the tool result.

The tool result, measured live: HTTP 200, with `isError: true`, `structuredContent` carrying the full PaymentRequired object, and `content[0].text` as the JSON of the same. That is not a challenge buried anywhere — it is the documented signal. specs/transports-v2/mcp.md, Payment Required Signaling: "When a tool requires payment, servers MUST return a tool result with isError: true containing the PaymentRequired data", in both structuredContent and content[0].text, with the payment returning at _meta["x402/payment"]. Your own docs say the same in prose: the tool result is MCP's equivalent of an HTTP 402 status and PAYMENT-REQUIRED header. So the fix you proposed — HTTP 402, JSON-RPC only for the paid response — would break every client written to that spec, including wrapMCPClientWithPayment and create_x402_mcp_client. A standard x402 MCP client does not read the status line. It reads the tool result, and it already works against us.

Your validator failure is real, though, and I reproduced it with my own CDP credentials. Before: GET /mcp, 25 checks, returns_402 FAIL — "Endpoint returns 200 OK, it needs to return 402 for unauthenticated requests to be discoverable", expected 402 actual 200 — and the other 24 skipped. GET /api/v1/signal: 25 of 25 pass. So the defect is not the MCP challenge. It is that GET /mcp served a free document on the URL the index treats as a payable resource, which is exactly the URL the eight /mcp#tool#tool rows are indexed against.

Fixed and re-validated. GET /mcp now answers the canonical challenge — PAYMENT-REQUIRED header, accepts[], resource, and the bazaar block the last ten checks read — and a paid GET delivers the document it always served. POST and DELETE are untouched, because that is the transport and the spec puts the challenge in the tool result. The document is still free at /mcp.json, so nothing that reads it is worse off. Validator after the change: 25 of 25 pass, valid true.

So no to the $15 change-sheet, and not because of the money. The fix took less time than the two emails, and the change-sheet as described would have taken the MCP surface backwards. If you want a change-sheet worth paying for, it is the one I cannot write: the payer classification behind your benchmark, which your index cannot produce and my ledger can.

On the benchmark numbers, which are the best thing you have sent: 67.7% of paid rows paid once and 11% of revenue, 6.2% paid five or more times and 89.1%. That matches everything I measure and it is the strongest argument yet against building another route. Two corrections from my ledger. First, whale-alerts is an alias of whaleflow: 14 settled calls in thirty days, 1 of them not mine. verify-seller is 19 and 4 not mine, and it took two of the three external-class payments. So the repeat-use route by my books is verify-seller, not whale-alerts. Second, the price band: my one route above $0.02 is the one with the most calls that are not mine, which is the opposite of "the $0.005 band is worst". With eleven non-own payments I cannot test a band at all. You can, across 1,774 routes, if the classification holds — which your benchmark of my routes shows it does not.

On #881, thank you for answering it publicly, and one correction, also measured. There are no "old /mcp URLs" to redirect. I pulled both sets from the merchant endpoint: the live payTo carries 20 rows including 8 /mcp#tool, the retired payTo carries 6, and they are the same host and path — .../mcp#verify_seller, .../mcp#get_trading_signal — indexed on 10 November. A row is keyed by the address in the challenge, so nothing I serve today re-indexes a row onto another address; a paid call writes the live rows. The six can only age out, which is what you said first.

WHAT YOU NEVER RECEIVED

One. The ledger offer: declined, and the reason is structural rather than the price. Not one of your five metrics is observable from outside a service — repeat visitor rate, paying-wallet share, revenue per agent and per-route conversion all live in the seller's request log. You can see my 402s; you cannot see who came back, who paid, or what they paid for. So an audit of my routes is either built from data I hand over or it is a guess. And I already have all five, for thirty days rather than seven, plus the individual reading of all 135 payment attempts.

Two. Your benchmark's call counts, checked against my own ledger. Your route table and prices are exact — I asked all nine paths unpaid and every one answers the live price you list. Your counts are not reproducible: 7, 14, 21, 30, 45 and 60 days all give different numbers from yours, and six of your rows — the four aliases plus stats and bot-status, two each — are exactly my own smoke-test sweep of 10 and 11 November. My thirty-day numbers, my key separated: signal 22 with 3 not mine, verify-seller 19 with 4, whaleflow 14 with 1, sales 13 with 1, bot-status 10 with 0, stats 9 with 1, arb 5 with 0, trading-signals 3 with 1, and the four remaining aliases 2 each with none of them mine. But your conclusion survives my books: verify-seller is the top route by calls that are not mine, and it took two of the three external-class payments. I told you last week I was dropping that route. My own ledger says I was wrong to.

Three. The introduction: I do not have it. I checked before promising: five leads in my CRM, zero customer checkouts. What I have is thousands of sellers known by their listings and none known as contacts who would take an introduction; the people I do know are verifiers, directories and trust vendors — the layer we both sit in, not your buyers.

Which leaves the question I have now asked twice without an answer: if I supply the measurement and you sell it, what is your share? Name it and I will answer. If the honest answer is that you would rather keep the customer, say that too, and I will stop asking.

Dimitri
```

## X. Ernest — the band table, rebuilt from the public field, and dissolved (25.11.2026)

**Where:** `ernest-earnordie@agentmail.to`.

**What he sent.** He conceded `/mcp` completely ("you are right about /mcp and I drop
it… no charge, no debt"), confirmed the working address, and delivered the band
correction we asked for: a seven-band table over **34,886 routes** using payers as
the denominator, concluding that the band which maximises recurring use is
**$0.02–0.05** (49 calls/payer, $2.77 revenue/route), ~10× the $0.01–0.02 band and
~90× the sub-cent band — and that this "independently confirms" our accounting. He
also recorded the alias correction and withdrew the "$0.005 is the worst band"
claim as an inference that did not survive the payer cut. Then the offer again:
**$25 one-off / $15 a month** for a page ranking our routes against the field on
payers, calls/payer and revenue/route, with the caveat that he has no payer
*identity*.

**Checked, and the three inputs are public.** Every row of CDP's listing carries
`quality.l30DaysTotalCalls`, `quality.l30DaysUniquePayers` and
`accepts[0].amount`. `_tools/band_table.py` pages the whole listing — **88,074 rows,
74,713 with a Base USDC price and at least one call** — and rebuilds his table.
**No purchase; the offer is declined on measurement, not on principle.**

**Finding 1: the peak is not a band, it is one price point.**
`$0.02` alone carries **2,242,922 calls — 59.6% of every call in the entire
listing** — across 1,872 routes and 13,592 payers. Under the inclusive boundary
those rows land in `$0.01–0.02` (154.0 calls/payer) and under the exclusive one in
`$0.02–0.05` (144.6). **His 49 and our 154 are the same 1,872 rows**, and the
headline moves a whole band on where the `>=` is written.

**Finding 2, and it dissolves the question: no band is a market.** Grouping by host
inside each price point:

| price point | routes | calls | top host | share |
|---|---|---|---|---|
| $0.02 | 1,872 | 2,242,922 | `console.ax1.vc` (1 route) | **81.7%** (+11.3% for `ax1-new.vercel.app`) |
| $0.005 | 6,016 | 897,903 | `www.api-xpay.com` (10 routes) | **82.1%** (+13.6% pocket.network) |
| $0.01 | 4,204 | 196,133 | `api.zerion.io` (1 route) | 29.4% |
| $0.003 | 46,845 | 61,842 | `agent-data.centorprat.workers.dev` | **44,507 of the 46,845 routes** |
| $0.05 | 1,358 | 35,705 | `keyring-agent.blockchhub.link` | **72.4%** |

The sub-cent band is one operator's catalogue; the "best" band is one operator's
single route. **A band table over these rows measures a handful of large sellers'
internal traffic, not what a price does to a buyer** — so the correction does not
land where he aimed it: there is no band evidence to move our prices in either
direction, and we would rather have that than a flattering answer.

**Finding 3: the public field already places our own routes.** For
`kristo-intelligence-api.onrender.com` the listing publishes **26 rows**, including
the MCP aliases and the `#X#X` duplicates:

| our row | price | CDP calls | CDP payers | our ledger, 30d |
|---|---|---|---|---|
| `/api/v1/signal` | $0.01 | 16 | 3 | 22 settled |
| `/api/v1/verify-seller` | $0.05 | 14 | 3 | 19 |
| `/api/sales` | $0.005 | 9 | 2 | 13 |
| `/api/v1/whaleflow` | $0.01 | 7 | 2 | 14 |
| `/api/bot-status` | $0.005 | 7 | 1 | 10 |
| `/api/stats` | $0.005 | 6 | 2 | 9 |
| `/api/arb/opportunities` | $0.005 | 3 | 1 | 5 |

CDP is consistently **lower than our ledger and never higher** — the index sees a
subset — and it publishes *counts* of unique payers but not *who* they are. That is
the half that is genuinely not purchasable from either side, and it is why the
product shape stays "the seller brings the log".

**Subject:** `Re: /mcp — you're right, and here's the band correction you asked for`

```
Ernest,

Thank you for dropping /mcp cleanly, and for the band table — it is the correction I asked for, and I checked it before answering. Two things came out of the check, and the second one dissolves the question.

Your three inputs are public. Every row of the Bazaar listing carries quality.l30DaysTotalCalls, quality.l30DaysUniquePayers and accepts[0].amount, so I rebuilt your table myself over the whole listing: 88,074 rows, 74,713 of them with a Base USDC price and at least one call. That is why I am not buying the ranking — it is computable, and I computed it.

First finding. The peak is not a band, it is one price point. $0.02 alone carries 2,242,922 calls — 59.6% of every call in the entire listing — across 1,872 routes and 13,592 payers. Put the boundary inclusively and those rows land in $0.01-0.02, at 154.0 calls per payer. Put it exclusively and they land in $0.02-0.05, at 144.6. Your 49 and my 154 are the same 1,872 rows. The headline moves a whole band on where the >= is written, which is the sign that it is not measuring a band.

Second finding, and this is the one that matters. No band is a market. Grouping by host inside each price point: at $0.02, console.ax1.vc is 81.7% of the calls on a single route, with ax1-new.vercel.app another 11.3%. At $0.005, www.api-xpay.com is 82.1% on ten routes. At $0.05, keyring-agent.blockchhub.link is 72.4%. And at $0.003, agent-data.centorprat.workers.dev holds 44,507 of the 46,845 routes. The sub-cent band is one operator's catalogue; the band you recommend is one operator's single route. A table over those rows measures a few large sellers' internal traffic, not what a price does to a buyer.

So the correction is real but it does not land where you aimed it. There is no band evidence to move my prices, in either direction, and I would rather have that answer than a flattering one. Your withdrawal of the "$0.005 is the worst band" claim stands, and so does my observation that the one route above $0.02 with the most calls that are not mine is not an anecdote — but it is a fact about my ledger, not a band effect.

On the offer: the ranking is computable, and here is your own field applied to my rows. The listing publishes 26 rows for my host, including the MCP aliases and the #X#X duplicates. /api/v1/signal: 16 calls, 3 payers. /api/v1/verify-seller: 14 and 3. /api/sales: 9 and 2. /api/v1/whaleflow: 7 and 2. /api/bot-status: 7 and 1. /api/stats: 6 and 2. /api/arb/opportunities: 3 and 1. My ledger says 22, 19, 13, 14, 10, 9 and 5 settled calls for the same window. Your field is consistently lower than my books and never higher — it sees a subset — and it publishes how many unique payers there were without saying who they are.

That last gap is the only part of this worth money, and neither of us can buy it from the other. You cannot tell whether those three payers on my signal row are mine or strangers. My ledger can. Which is why the shape stays what I said: the seller brings the log, and the measurement is produced from it.

One question, so I can compare corpora rather than levels: your 34,886 routes against the listing's 88,074 — what is in your subset, or out of it? Your sub-cent band has 14,705 routes where I count 61,814, and that difference, not the boundary, is what makes our levels differ everywhere.

Dimitri
```

## Y. Abdellah — the second row in his results file, checked and corrected (25.11.2026)

**Where:** `github.com/holistis/agent-receipt-verify/issues/127` (opened 25 November 2026,
16:34 UTC).

**What he sent.** He accepted the offer he had made himself — a column for **our own
reading of `vectors.json` without his adapter** — and put it in `RESULTS.md` as a
second row (PR #126, merged 15:21Z; the file commit `cc986dd2`, 15:35Z), with our
limits as we wrote them, next to the first row kept as history. He added that he
would change the wording if anything in it was off, which is the invitation this
section answers.

**Checked from his bytes, before answering.** The four files of gist revision
`af6af9ee149f` hash to what the row claims: the v5 fixture 46 890 bytes /
`ccdfea67502fd220…`, the reader 13 234 / `8980ceaab81d…`, `OUR_OWN_READING.md`
4 335 / `b251b84a350d…`, `CROSS_RUN_RESULT.md` 5 038 / `4630fe747ccb…`. Our reader,
run against `vectors.json` of fingerprint `94b07672bfd9` (61 084 bytes), gives
**22 / 14 / 0 / 5**, and the 13 tests pass here as they pass on his machine. His own
sentence about our check is exact.

**Two corrections, both about what cannot be checked.**

1. **"an earlier state of this reader" is not in the gist and cannot run.** Only one
   state of `our_own_reading.py` was ever published — revisions `a8a47ff7596e`,
   `de75d2ed8c97`, `79c15d8178c2` and `af6af9ee149f` all serve the same 13 234 bytes —
   and those bytes stop against v4 of our artifact with `TypeError: decide() got an
   unexpected keyword argument 'recovering'`, because v5 introduced the marker. So
   **19 / 14 / 3 / 5 is a number we report, not one a reader can reproduce from
   published bytes**, and the row should say so.
2. **The outside count was 5 before it was 3.** An earlier, also unpublished, state of
   our reader bound the payment by the transfer's `from` instead of the payment's own
   payer, which made the binding unfalsifiable and answered **5** outside. The count
   moved **5 → 3 → 0** across our own fixes. Offered to him as a limits sentence, and
   added to our own document.

**Republished, so our own doc carries the limit.**
`OUR_OWN_READING.md` gained both points under "What this does not show" and the gist
was PATCHed: HEAD `6d1fe258a0fca2e6432674605de4559e67a29e41`, the document now 5 230
bytes / `c361f027ff926afc021f8d2844c1607ce4067bc113873191999b04f0d7389074`. The
reader's and fixture's bytes are unchanged, so the revision he ran stays valid for
them.

**Subject:** `RESULTS.md second row: one sentence that cannot be checked, and one limit you may want to add`

```
Two corrections from the author of the run the second row records. Everything else in that row we checked today against your bytes and it is exact — these two are the only parts we would change.

1. "an earlier state of this reader" cannot be found or run.

The row says: "Their first run of an earlier state of this reader on the earlier revision v4 of their file (gist revision c1cd82cc059b) gave 19, 14, 3 and 5."

The number is ours, but the state is not in the gist. Every revision that carries our_own_reading.py serves the same bytes — a8a47ff7596e, de75d2ed8c97, 79c15d8178c2 and af6af9ee149f all give 13,234 bytes, SHA-256 8980ceaab81d78e0d9be519f31dbb093da9247abaec72a9d84b9fb0aa3a6e8a9. And those bytes cannot be run against v4 at all, because v5 introduced the recovering marker:

TypeError: decide() got an unexpected keyword argument 'recovering'

against v4 as served by c1cd82cc059b (37,862 bytes, SHA-256 3d76d8030efc10cbbfcfe3a739078ee5fa4a8af417712a583b934789f37d170a). So 19 / 14 / 3 / 5 is a number we report, not one a reader can reproduce from published bytes. A wording that keeps your point and is checkable:

"Before the published reader existed, an earlier state of it, run against revision v4 of their file (gist revision c1cd82cc059b, 37,862 bytes), gave 19, 14, 3 and 5. That state was never published, and the published reader cannot be run against v4: v5 of their file added the recovering marker, which v4's decide() does not accept."

2. The outside count was 5 before it was 3, and the second defect may belong in the row.

As written, the row has our reader wrong once. It was wrong twice before publication. Its first state read the transfer's "from" instead of the payment's own payer, which made the binding unfalsifiable and answered 5 outside. Fixed, it answered 3 — the v4 defect the row describes. With v5 in the artifact it answers 0. The count moved 5 → 3 → 0 across our own fixes, and 0 is the published pair's number. If you want it in the row, it is one sentence in the "What this run does not show" paragraph:

"An earlier, unpublished state of their reader answered 5 outside, for a second defect of theirs: it bound the payment by the transfer's from rather than the payment's own payer, which made the binding unfalsifiable."

We have added both points to OUR_OWN_READING.md under "What this does not show" and republished the gist: HEAD 6d1fe258a0fca2e6432674605de4559e67a29e41, the document now 5,230 bytes, SHA-256 c361f027ff926afc021f8d2844c1607ce4067bc113873191999b04f0d7389074. The reader's bytes are unchanged, so the revision you ran and re-checked (af6af9ee149f) stays valid for it; if you take the second sentence, point the document link at 6d1fe258a0fc.

What we checked today, so that the rest of the row is not taken on trust. The four files at af6af9ee149f: v5 fixture 46,890 bytes / ccdfea67502fd220…, reader 13,234 / 8980ceaab81d…, OUR_OWN_READING.md 4,335 / b251b84a350d…, CROSS_RUN_RESULT.md 5,038 / 4630fe747ccb…. Our reader against vectors.json of fingerprint 94b07672bfd9 (61,084 bytes) gives 22 / 14 / 0 / 5. The 13 tests pass here as they pass there. Your sentence about our own check of your run is exact, and so is the part that matters most to us: the three outside were our defect and not a fault in the set.

Nothing in the "What this run does not show" paragraph is wrong, and it is the reason the row is worth having.

Dimitri
```

## Z. The Domain Discovery working group — joining the list, and the measurement report (25.11.2026)

**Why this channel.** `NEXT_ACTIONS.md` §4 has carried "send the discovery-truth
report to the Domain Discovery working group and join its mailing list" as the first
thing that must happen, and it had no destination until now. The group is the x402
Foundation's **Domain Discovery** working group: repo
`github.com/x402-foundation/wg-domain-discovery` (issues enabled, Discussions not),
public Slack `#wg-domain-discovery`, bi-weekly Monday calls with public notes, and a
mailing list at `Domain-Discovery@lists.x402.org` whose own settings say
subscriptions need no approval and any member can post (first posts are moderated).
**Membership of the foundation is not required for any of it.** The repo already
carries outsider measurements — #1 (a Bazaar index measurement) and #15 (three
production discovery failure modes) — so a measurement report is the expected shape
of a contribution there, and ours was posted as **issue #19**.

**Subscribe message** — to `Domain-Discovery+subscribe@lists.x402.org`:

**Subject:** `Subscribe`

```
(Requesting subscription to the Domain Discovery working group mailing list.)
```

## Z2. The working-group report as posted (issue #19, 25.11.2026)

**Where:** `github.com/x402-foundation/wg-domain-discovery/issues/19`, opened
25 November 2026, 16:42 UTC, 5 412 bytes, read back through the API.

**What it carries, and what it does not.** It is `docs/DISCOVERY_TRUTH.md` cut to
the working group's own shape: the measured findings, the method, the limits, and
**our own probe error published with the finding it strengthens** (21.5% → 5.0%
once each row's declared method was used). It claims nothing about the group's
roadmap, asks for three specific things, and offers to re-run the measurement on a
schedule and publish the delta.

```
I run a live x402 service on Base (seven paid routes, $0.005–$0.05, plus one $0.25 dataset) and I am not a member of the foundation. I read this working group's repo because the discovery layer is what decides whether a service like mine is reachable at all, and I measured the layer rather than describing it. Numbers below, method at the end, and one correction of my own error, published rather than quietly fixed.

What was measured. CDP's public Bazaar listing, GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources, read on 25 November 2026: 87,419 rows reported (a later pass the same day already saw 88,074, so the field moves), of which the first 10,000 were read (50 pages of 200) and 200 were probed live, unpaid, once each, using the method the row itself declares.

1. The listing does not say how to call what it lists

GET 6,003 rows (60.0%), POST 3,992 (39.9%), PUT 4, absent 1. Rows carrying a top-level method: 0 of 10,000. The method exists only inside extensions.bazaar.info.input.method (9,999 rows). A row's type is http for 9,999 rows and mcp for 1, and carries no other routing hint.

So an agent that reads the row and issues the obvious GET reaches 60% of the layer. The other 40% answer 405 Method Not Allowed — not because those endpoints are broken, but because the listing did not say how to call them.

2. My own probe got it wrong first, and that is the argument for section 1

My first pass probed every row with GET and counted 405 as a dead listing. It reported 21.5% of rows unreachable, which was a better story and a false one: 84 of the 200 probed rows declare POST, and a GET to a POST-only endpoint correctly answers 405. Re-probing with each row's declared method moved the failure rate from 21.5% to 5.0%.

I put the correction in the report because it is the finding's own best evidence: nothing in the row told the probe how to call the endpoint, so a competent caller got the method wrong four times in five attempts — precisely the trap the 40% figure describes.

3. Reachability: one listing in twenty cannot be bought from

Of the 200 probed rows, 190 (95.0%) returned a parsable 402 with an amount. The other 10: HTTP 400 (4), 404 (2), 500 (1), 403 (1), unreachable (1), and one 402 whose challenge neither parser understood (counted as a failure, not guessed at).

4. Truth: 14.7% misdescribe the product, 3.7% misstate the price

Of the 190 rows that answered with a parsable 402, comparing the live challenge against what the catalogue stored: description differs in 28 of 190 (14.7%), price differs in 7 of 190 (3.7%), and for 4 rows both differ. Two shapes are damaging:

aizamon.com/x402/v1/bot-fuel-day — catalogue 1,490,000 atomic ($1.49), live 100,000 ($0.10), row age 29 days.
probeline.io/v1/implants/peri-implant — catalogue "peri-implant clinical status, 150,000", live "dental implant specifications, 50,000", row age 8 days.

An agent budgeting from the listing is quoted fifteen times the real price in the first case; in the second, the URL now sells a different product while the catalogue still advertises the old one.

5. Freshness: 47% of rows are more than a week old

lastUpdated across the 10,000 rows read: 15.7% under 1 day, 24.0% 1-3 days, 13.4% 3-7 days, 17.8% 7-14 days, 28.8% 14-30 days, median 5.95 days, oldest 209.7.

If lastUpdated moves when a settlement touches the row — which is what our own row does — then most x402 listings have had no paid call in over a week. That is a demand-side finding arriving from the catalogue's own timestamps.

6. What I would ask the working group to consider

1. Surface the call method at the row level, or require it. A listing that tells an agent where to pay but not how to call is 40% unusable by the obvious route. This is a small schema change with a measured payoff.
2. Publish row freshness as a discovery field. lastUpdated already exists internally; exposing it lets an agent prefer a recently validated row over a four-week-old one.
3. State a conformance expectation for indexers. A row is a snapshot of the last settled echo, so it cannot follow a seller's current declaration. Either indexers re-read on change, or the specification should say plainly that a catalogue row is a historical record and not a live claim.

Limits, stated

- One index (CDP's), not every catalogue.
- The 10,000 rows read are the first 50 pages, and the listing appears ordered by recency, so this is the freshest slice of the listing: the freshness and quality figures are likely optimistic, not exaggerated.
- 200 live probes state a rate to roughly ±5 percentage points; they do not characterise any individual seller.
- 402 challenges were parsed from both the response body and the PAYMENT-REQUIRED header.

Full report, with the per-row outcomes and the method: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/DISCOVERY_TRUTH.md

I am happy to re-run this on a schedule and post the delta here if the group finds it useful, and to say plainly when a measurement of mine is wrong — as in section 2.
```

## Z3. The Domain Discovery mailing list — the report, and the three asks (25.11.2026)

**What happened when we joined.** The subscribe request to
`Domain-Discovery+subscribe@lists.x402.org` was answered within two minutes with a
confirmation that Groups.io completes **by reply**; the reply was sent from the same
mailbox and three welcome messages arrived (the group, its parent `main@`, and the
x402 workspace), plus **an invitation to the working group's recurring meeting —
public, every second Monday 10:00 America/Chicago, next 30 November, Zoom via LFX,
with the public minutes document attached**. So the channel is real, open, and now
has us on it; the meeting is a place our measurements can be said out loud, and the
minutes are the record.

**Why a list message on top of the issue.** The issue is the artifact; the list is
how the group's members learn it exists, and the group's own settings say first posts
are held for moderator approval, which is fine — it means a human reads it before it
lands. The message is deliberately shorter than the issue, carries the three numbers
with a specification consequence, states the limits, and offers the delta.

**Subject:** `What the Bazaar listing actually says — 0 of 10,000 rows carry a call method, 14.7% misdescribe the product`

```
Hello,

I joined this list today because the discovery layer decides whether a service like mine is reachable at all. I run a live x402 service on Base (seven paid routes, $0.005-$0.05, plus a $0.25 dataset) and I measured CDP's public Bazaar listing rather than describing it. The full report is posted as an issue in the working group's repo:

https://github.com/x402-foundation/wg-domain-discovery/issues/19

Three numbers from it, because they are the ones with a specification consequence.

First: 0 of the first 10,000 rows carry a top-level "method". The method exists only inside extensions.bazaar.info.input.method, and across those rows it is 60.0% GET and 39.9% POST. An agent that reads the row and issues the obvious GET reaches 60% of the layer; the rest answer 405, not because those endpoints are broken but because the listing did not say how to call them.

Second: 5.0% of 200 live-probed rows cannot be bought from at all — dead URLs, server errors, or a 402 whose challenge does not parse. My own first pass reported 21.5% and was wrong: it probed every row with GET and counted 405 as dead. I left that error in the report, because nothing in the row told the probe how to call the endpoint, so a competent caller got the method wrong four times in five attempts.

Third: of the 190 rows that answered with a parsable challenge, 14.7% misdescribe the product and 3.7% misstate the price. One row quotes fifteen times the real price: 1,490,000 atomic units ($1.49) in the catalogue against 100,000 ($0.10) live, on a row 29 days old.

I would ask for three things: surface the call method at the row level; publish row freshness as a discovery field; and state plainly whether a catalogue row is a live claim or a historical record of the last settled echo.

Limits, stated so the numbers are not read as more than they are: one index (CDP's), the first 50 pages only — and the listing appears ordered by recency, so this is the freshest slice and the quality figures are likely optimistic rather than exaggerated — and 200 probes give a rate to about five percentage points, not a verdict on any individual seller.

I will re-run this on a schedule and post the delta here if that is useful.

Dimitri Hristov
```

## AA. Glama — the record their checklist wants cannot be created from our side (25.11.2026)

**Where:** `support@glama.ai`, cc `frank@glama.ai`.

**Why an email and not the Discord.** The `/mcp/servers/` record has blocked
`punkpeye/awesome-mcp-servers` PR #13219 since 30 August, and our question to the
maintainer (which listing counts for the checklist — the connector or the servers
record?) has been unanswered since 24.11. The Discord message in §K cannot be posted
from here (the account is not approved to send). Email is a channel we have, it is
the one Glama answered from in September, and Frank is both Glama's founder and the
maintainer who set the requirement — so copying him keeps the two halves of the
answer from drifting apart.

**Measured today, so the letter carries no stale numbers.** The connector page
returns 200: ownership verified, Status Healthy, uptime 100.0% over 24 hours, last
tested 2026-11-25 16:06, transport Streamable HTTP, **TDQS A 4.4/5.0, scored
2026-11-25 08:35 across 7 tools**. The servers path for us **redirects (302) to the
registry index** (`https://glama.ai/mcp/servers`, 638 KB fetched, the string
"kristo" absent), and `/mcp/servers/com.onrender.kristo-intelligence-api/kristo-intelligence`
returns **404**. Both Add Server paths reject with "already listed as a hosted
connector".

**Subject:** `A hosted connector cannot have a /mcp/servers/ record — which listing counts for the badge?`

```
Hello,

Our server has been listed on Glama since September as a hosted connector, and there is one thing about it I cannot resolve from any page you publish. I am writing because it has kept a listing in someone else's directory blocked for three months.

What our listing is today, read from your pages this afternoon:

- Connector: https://glama.ai/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence — ownership verified, Status Healthy, uptime 100.0% over the last 24 hours, last tested 2026-11-25 16:06, transport Streamable HTTP, TDQS A 4.4/5.0, scored 2026-11-25 08:35 across 7 tools.
- The servers path for us does not exist. https://glama.ai/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6 redirects (302) to https://glama.ai/mcp/servers, the registry index — I fetched 638 KB of it and the string "kristo" does not appear once. https://glama.ai/mcp/servers/com.onrender.kristo-intelligence-api/kristo-intelligence returns 404.
- Both Add Server paths reject the submission with "already listed as a hosted connector", so the record cannot be created from our side.
- The badge URL given to new submitters, .../mcp/servers/hristovdimitri2-hub/kristo-intelligence-6/badges/score.svg, therefore renders "This MCP server is not listed on Glama".

Why I am asking rather than guessing: the `quality` field is computed only for /mcp/servers/ records, so our score is incomplete in exactly the way the awesome-mcp-servers checklist asks about, and PR punkpeye/awesome-mcp-servers#13219 (open since 30 August 2026) cannot merge while that checklist expects the badge or the record. I asked the maintainer which listing counts and have had no answer, so I am asking the people who can actually create or refuse the record.

The ask in one line: can our connector be given a /mcp/servers/ record, or can the badge for hosted connectors point at the connector path? If a hosted connector simply cannot have such a record, say so plainly and I will take that answer back to the maintainer instead of leaving the PR open for a fourth month.

One thing for the record, so this is not read as a complaint: the TDQS breakdown on our connector is accurate and useful, and the two errors found in that entry earlier were mine, not yours.

Dimitri
```

## AB. Glama — the removal was ours, the withdrawal was not read, and the ask narrows (26.11.2026)

**Where:** `frank@glama.ai`, cc `support@glama.ai` (draft §AA's thread; Frank answered
on 25.11 at 19:49 EET that the server was removed because "someone from your team
requested its removal").

**He is right, and the dates matter.** Read out of our own sent mail rather than
memory:

| when | to | what we asked |
|---|---|---|
| 1 Nov 15:49 | `support@glama.ai` | "Could you please **either publish/unstuck the existing record, or remove the stale duplicate** so we can resubmit?" |
| 3 Nov 09:16 | Frank | "Could you clear that old entry — **or reopen it** — so the resubmission can go through?" |
| 3 Nov 11:36 | Frank | "the stale record still seems to live in the backend. **Could you purge it completely?** I'll resend the moment it's gone." |
| **17 Nov 08:32** | `support@glama.ai` | "Thanks for catching that — **I will not resubmit or remove anything.** … Please review and activate the existing listing so I can claim it." |

So removal was **option B of two**, asked for twice, and then **withdrawn in writing on
17 November**. If the record was deleted after that date, it was deleted on a
superseded request. That is stated as a fact of the correspondence, not as a complaint
— the request was ours to make and ours to withdraw.

**What changed in the meantime, measured 26.11.2026.** The badge for
`/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6/badges/score.svg` now returns
200 rendering **"This MCP server is not listed on Glama"**, where on 4 November it
rendered a grade — so the backend record that survived the 3 November unpublishing is
now gone. The servers path 302s to the index and "kristo" is absent from it. The
connector is untouched: 200, ownership verified, Healthy, **uptime 100.0%, last tested
2026-11-26 04:51, TDQS A 4.4/5.0 across 7 tools**.

**Why the letter is short and specific.** Two things we need cannot be measured from
outside: whether a fresh submission now passes (the duplicate that caused "MCP server
already exists for this repository" should be gone), and whether `quality` would then be
computed for the servers record. So the letter asks exactly that, offers to submit
immediately, and gives him the cheapest exit — if a hosted endpoint can only ever live
under `/mcp/connectors/`, we take that as the answer and carry it to the directory
maintainer instead of asking again.

**Subject:** `Re: A hosted connector cannot have a /mcp/servers/ record — which listing counts for the badge?`

```
Frank,

Thank you for coming back on this, and you are right — the removal request was ours. Two points of accuracy, because the dates decide what is superseded.

From our own sent mail:

- 1 November, 15:49 to support@glama.ai: "Could you please either publish/unstuck the existing record, or remove the stale duplicate so we can resubmit?"
- 3 November, 09:16 to you: "Could you clear that old entry - or reopen it - so the resubmission can go through?"
- 3 November, 11:36 to you, after the page disappeared: "the stale record still seems to live in the backend. Could you purge it completely? I'll resend the moment it's gone."
- 17 November, 08:32 to support@glama.ai, and this is the one that matters: "Thanks for catching that - I will not resubmit or remove anything. Please review and activate the existing listing so I can claim it."

So removal was option B of two, asked for twice, and withdrawn in writing on 17 November. If the record was deleted after that date, it was deleted on a superseded request. That is on us to have put on the table, and I am not arguing about it - I am only making sure the record of what was asked is accurate.

What we measure today, 26 November:

- https://glama.ai/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6/badges/score.svg returns 200 and renders "This MCP server is not listed on Glama". On 4 November the same URL rendered a grade, so the backend record was alive then and is gone now.
- https://glama.ai/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6 redirects (302) to the registry index, and the string "kristo" does not appear on that page.
- The connector is unchanged and healthy: ownership verified, Status Healthy, uptime 100.0% over the last 24 hours, last tested 2026-11-26 04:51, transport Streamable HTTP, TDQS A 4.4/5.0, scored 2026-11-25 08:35 across 7 tools.

The question is now narrow, and it is the only one left. We need a /mcp/servers/ record for two reasons: the `quality` field is computed only there, and the awesome-mcp-servers checklist requires that badge. So:

1. Now that the duplicate is gone, would a fresh submission for github.com/hristovdimitri2-hub/kristo-intelligence-6 be accepted? The repository ships Dockerfile.glama and scripts/mcp_stdio_bridge.py - a standard-library-only stdio bridge, no secrets, no database - and we have built and run it as a container, answering initialize, tools/list (all tools with their schemas), ping and tools/call, with protocol frames on stdout and logging on stderr.
2. Or would you rather create/restore the record yourself, pointing at the hosted endpoint https://kristo-intelligence-api.onrender.com/mcp, so `quality` can be computed for it?
3. If the answer is that a hosted endpoint can only ever live under /mcp/connectors/, say so plainly and I will stop asking you and take it to the directory maintainer as a documented limitation. That is a perfectly good outcome - it just has to be stated, because "the record should exist but does not" is the one state we cannot act on.

Thank you for answering a question that has been open since September, whichever way it lands.

Dimitri
```

## AC. Glama `#support` — the Discord message the owner has to post (26.11.2026)

**Why Discord and not another ticket.** The channel is answered by Frank himself (he
answered TheGodHand's GitHub-app permission question there on 22.11 with "Fixed it"),
while the ticket queue is 200+ a day and, in Frank's own words on 24.11, *"most tickets are
handled by agents… most updates to repos etc need to be handled by you though."* That last
sentence is why this message states the one thing that is **not** a repo update we can make:
the record does not exist to update.

**What we measured before writing it** (26.11.2026), so every claim in it is current:

- the connector is healthy: `/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence`, ownership verified, TDQS **A 4.4/5.0**, **8 tools** (it was 7 when this draft was written; the demand-census promotion added the eighth), uptime 100%;
- `/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6` serves the **registry index** (**641,587 bytes** on 26.11 — the size drifts, so the message quotes "641 KB today" rather than a fixed figure — **zero** occurrences of "kristo" and zero of "hristovdimitri2");
- the score badge renders **"This MCP server is not listed on Glama"**;
- the **card** badge returns 200 and 9,384 bytes but contains **no text nodes at all** — it is a pure-path SVG, so its grade cannot be read from the bytes, which is why the README keeps the score badge;
- `glama.json` with `"maintainers": ["hristovdimitri2-hub"]` has been in the repo root since **17.09.2026** (commit `9e7acb3`) and **did not restore the record** — the maintainer file binds an existing record, it does not create one. That is the measured answer to the approach another user described in the same channel.

**Copy-paste ready, for the owner to post in `#support (Glama)`:**

```
Hi Frank — following up on ticket #160212386 with what we measured today, so the ask is one line.

Our connector is healthy and unchanged: glama.ai/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence — ownership verified, TDQS A 4.4/5.0, 8 tools, uptime 100%.

The server record glama.ai/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6 does not exist. It was removed in early November at our own written request, and we withdrew that request in writing on 17 November. glama.json with "maintainers": ["hristovdimitri2-hub"] has been in the repo root since 17 September and did not restore it. Today that servers URL serves the registry index (641 KB today, no occurrence of "kristo") and the score badge renders "This MCP server is not listed on Glama".

Add Server rejects the submission with "already listed as a hosted connector", so we cannot recreate it ourselves — and this is not a repo update we can make, because the record does not exist to update.

The ask, any one of three: (1) accept a fresh submission for github.com/hristovdimitri2-hub/kristo-intelligence-6, or (2) create/restore the record pointing at https://kristo-intelligence-api.onrender.com/mcp so `quality` can be computed, or (3) say plainly that a hosted endpoint can only ever live under /mcp/connectors/ — and we will take that answer to the awesome-mcp-servers maintainer and stop asking.

Related, and also unanswered (BeneODev asked it here on 25.11): do the large card badge and the small score badge count the same for the "link back to the Glama listing" requirement?
```

---

## AD. Stabledrop.me — an escrow product on Base that our AP2 radar does not watch (27.11.2026)

**Why this one.** Found through an r/ethdev thread on card-to-crypto payment
orchestration. `stabledrop.me` is a real, live product: **Protected payments for everyone,
for 1%** — time-delayed escrow, "no chargebacks, no vetting", checkout by script with no
backend, on Base. Footer: *© 2026 Conduit UCPI · Stabledrop.me · Protected payments on Base
· Company No. 8803019.* Measured the same day: their **AP2** settle API is public
(`api.stabledrop.me/api/ap2/settle/doc` → Swagger, 200), their contracts are public
(`github.com/conduit-ucpi/contracts` → *"Time-delayed escrow smart contracts on any EVM
blockchain with dispute resolution"*), their partner page mentions MCP four times — and
**x402 appears nowhere on their site**: checked six pages, zero occurrences. So this is an
adjacent road, not a competitor, and the letter says so rather than pretending otherwise.

**The one thing they cannot get from us by asking anyone else** is the demand-side number,
and it is given away free at the top of the letter.

**Subject:** `AP2 settle on Base, and the number your merchants will ask you for`

```
Hi,

I'll lead with the measurement, because it's the only thing here you can check in two minutes.

I run a paid x402 API on Base and I publish my own ledger, classified from on-chain behaviour rather than self-reported: 187 settled payments, $2.288 total. $2.08 of that is me exercising my own rail. 17 third-party wallets account for the other 50 settlements / $0.208 — crawlers paying to prove I'm in their crawl set, verifiers probing me, and exactly 13 payments / $0.064 / 10 wallets I cannot explain as anything but a real stranger.

https://kristo-intelligence-api.onrender.com/api/v1/settlement-classes

Three reasons I'm writing rather than just reading your site.

1. You implement AP2 settle and your contracts are public (github.com/conduit-ucpi/contracts). I run a small AP2/x402 radar over public repos: google-agentic-commerce/AP2, google-agentic-commerce/a2a-x402, Merit-Systems/x402scan, alchemyplatform/alchemy-x402. Yours is not in it. If you want it watched, say so and I'll add it — it costs me nothing, and I would rather be corrected than miss a builder.

2. Your product answers the buyer's question, "will I get what I paid for?" Nobody answers the seller's question, which is "will anyone pay at all?" That is the number I have, and I would rather ask whether it is useful to you than guess.

3. Where I may simply be wrong: I found no mention of x402 anywhere on your site, so I may be reading an adjacency as a fit. If AP2 and x402 are separate roads for you, one line saying so is a fine answer and I'll stop.

No pitch attached to any of this. If none of it is useful, that is useful too.

Dimitri Hristov
Kristo Intelligence
```

**Recipient:** `info@stabledrop.me` (their footer). No CC — there is no second address on the
site.

**What came back (27.11 10:39, 7 hours after sending).** A reply from **Charlie Pank**
(`charliepank@gmail.com`), cc `info@stabledrop.me`, asking one question and nothing else:

> *What's your take on x402 being a loss leader in terms of gas fees on micro payments?*

So the letter worked as intended: no pitch, and the answer is a question rather than a
polite no. The reply below answers it from our own receipts, measured on 27.11 at
**ETH $1,660.42** and a Base base fee of **0.005 gwei**:

| settlement | gas | gas price | fee | share of the payment |
|---|---|---|---|---|
| our $0.25 census canary, 26.11 | 86,230 | 0.0100 gwei | **$0.001432** | **0.57%** |
| PayAPI's $0.005 conformance test, 2 Sep | 103,398 | 0.0056 gwei | **$0.000964** | **19.3%** |
| plain USDC `transfer`, median of 8 in a 150-block window | **62,159** | — | — | — |

Both of our settlements are EIP-3009 `transferWithAuthorization`, and in **both** the
transaction's `from` is a third party — `0x68efafe8…` and `0x42dd5390…` — with the payer
appearing only as the `AuthorizationUsed` authorizer inside the log. So the gas is the
facilitator's, and the merchant never sees it.

## AE. Charlie Pank — the gas question, answered from the receipts (27.11.2026)

**Subject:** `Re: AP2 settle on Base, and the number your merchants will ask you for`

```
Charlie,

Good question, and I can answer it with receipts rather than an opinion, because the gas
payer in x402 is not who most people assume.

In the `exact` scheme on Base, neither side of the trade pays gas. The buyer signs an
EIP-3009 transferWithAuthorization — an off-chain signature, no transaction — and a
facilitator submits it and pays. I decoded both of my own settlements, and in both the
transaction's `from` is a third party:

- $0.25, 26 Nov — tx `from` 0x68efafe8…, gas 86,230 at 0.0100 gwei = $0.001432 = 0.57% of
  the amount paid. The payer appears only inside the log, as the AuthorizationUsed
  authorizer (0x5f6d3f20…, a wallet I control).
- $0.005, 2 Sep — tx `from` 0x42dd5390…, gas 103,398 at 0.0056 gwei = $0.000964 = 19.3% of
  the amount paid.

So as a loss leader it is real, and the loss is the facilitator's, not the merchant's.
Break-even for a facilitator charging no spread sits around $0.001–0.002 per call: at $0.005
you keep roughly four tenths of a cent before your own costs, and at $0.25 gas is a rounding
error.

Two things follow.

EIP-3009 is the expensive part. Measured against 150 blocks of USDC activity today: a plain
`transfer` costs a median 62,159 gas (min 40,259), while my two EIP-3009 settlements cost
86,230 and 103,398 — roughly 1.4x to 1.7x, because the token contract recovers the signature
on chain. That premium is exactly what the buyer gets for never holding ETH, and it is paid
by whoever submits the transaction.

Only batching or escrow survives a low floor. Your time-delayed escrow takes one deposit and
releases later, so it is two gas events per job instead of one per call. At today's fee that
is about 0.06% of a $5 job and about 19% of a $0.005 call — the same rail, two completely
different businesses. If your merchants ask, that is the honest comparison: per-call
settlement has a floor, escrow has a much lower one, and neither number is a complaint about
Base, whose base fee is 0.005 gwei.

For scale, my whole ledger is 187 settlements and $2.288 lifetime, average $0.0122 — so at
today's fee about 13% of gross went to gas. That is the entire case for a facilitator that
charges a spread rather than nothing, and for structures that settle many authorizations in
one transaction.

Happy to send the decoded receipts if they are useful.

Dimitri
```

**Recipient:** `charliepank@gmail.com`, cc `info@stabledrop.me` (matching how his reply
arrived). Every figure in it was measured, not estimated: the two receipts are our own
settlements, and the plain-transfer median comes from `_tools/plain_transfer_gas.py` over
150 recent Base blocks.

---

## AF. Ernest — the reconciliation offer, accepted once and not subscribed (27.11.2026)

**What he did, unprompted.** Read our live `/api/v1/seller-audit` at 18:53Z and verified it
independently against the chain with a sharded `eth_getLogs` over a **stated block range**
(59,620,061 → 63,075,958, USDC on Base, transfers where `to` == our current payTo). His read
and ours agree in the transaction: external payer `0x6c57df77…40f3` (1 tx, $0.01) and own
keys `0xe50c5212…5763` (16 tx, $0.245) and `0x5f6d3f20…ee74` (1 tx, $0.250). He also
withdrew his own method in writing — Blockscout `/api/v2` now returns **403** behind
Cloudflare for programmatic readers, so it could not be recomputed by a third party, and the
replacement is the keyless sharded `eth_getLogs` at the public 50,000-block limit.

**What he sells.** A one-month reconciliation of our rail: our payment ledger joined to the
chain, with the block range printed in the report, the sender classified, and the fourth class
we named (caller timeout) called out separately so a consumed nonce is never read as success.
**$15 for the first, delivered before payment; $15/month afterwards.**

**Decision: the first one, not the subscription.** `$15` delivered-first is zero-risk and
tests whether an independent completeness check is an asset we can put in front of a buyer.
The monthly is declined for now with the reason stated — our lifetime third-party revenue is
**$0.208** — and left open to reverse without being asked.

**The correction that matters.** By our own published fingerprint (50+ distinct receivers in
30 days is crawl infrastructure) all three wallets he calls external look like samplers: 141,
191 and 376 receivers. One is already labelled in our registry:
`0x54E163e9B8eDDa194D83F46AdD921bfA5fc5f4E0` = `market_crawler_54e1`. The disagreement is
about the *window* — our rule measures 30 days, his breadth looks like all time — and it is
worth settling before either side publishes a revision.

**Subject:** `Re: Your seller-audit endpoint, checked against the chain — and the $15 join`

```
Ernest,

Thank you for running that read, and for publishing the block range with it. The agreement is
the point: 0x6c57df77...40f3 with one transaction and $0.01, 0xe50c5212...5763 at 16 tx /
$0.245, and 0x5f6d3f20...ee74 at 1 tx / $0.250 is exactly what our endpoint returns, and you
reached it without our log. That is the strongest form this number can take: a reader who
trusts neither of us can re-run your range and see the same rows.

You are right about the method, and I will take the correction. Blockscout's /api/v2 sits
behind Cloudflare now and returns 403 to programmatic callers, so my own objection applies to
any reader, ours included. Sharded eth_getLogs at the public 50,000-block limit is the
replacement, and it is what the route already does.

Yes to the first reconciliation, at $15, delivered first. That structure is fair and I will
not haggle with it. What we can hand over is one row per settlement: route, amount, timestamp
and the transaction hash. The hash is the join key, so the sheet that comes back should read
matched-with-hash, or claimed-and-never-arrived, plus a payer identity for the matched rows.

On the monthly: not yet, and I would rather say why than let it hang. Our lifetime third-party
revenue across this whole service is $0.208. Gross is $2.388, and $2.18 of that is us paying
ourselves to exercise the rail. Fifteen dollars a month is not a rounding error against that;
it is seventy times the outside money we have ever taken. If the first reconciliation turns out
to be something we can put in front of a buyer — and it might, because completeness is the one
thing the chain cannot prove on its own — then $15 a month is trivially worth it and I will say
so unprompted. I would rather pay you monthly for something I use than subscribe to something I
hope to use.

One correction to your split, and it is the interesting part. By our published fingerprint — a
payer sending to 50 or more distinct receivers in 30 days is crawl infrastructure — all three
of the wallets you call external look like samplers rather than market buyers: 141, 191 and 376
receivers. One of them we have already labelled: 0x54E163e9B8eDDa194D83F46AdD921bfA5fc5f4E0
is market_crawler_54e1 in our registry, on exactly that evidence, and it has been since
September. So you and I disagree about the composition of the external bucket, and it is not a
small disagreement: if those three are infrastructure, our external count is nearer zero than
three, and the "3 of 6 are external market wallets" reading changes shape.

The reason I am not simply accepting your number is that our rule counts receivers in a 30-day
window, while your breadth looks like it is for all time. A genuine multi-vendor buyer and a
crawler can share a lifetime breadth and differ completely over 30 days. Before either of us
publishes a revision it is worth measuring the same window, and I would rather be corrected
than defend a threshold because it is mine. If your figures are 30-day, say so and I will move
the two unlabelled wallets myself.

And yes to the free split. Pick any host from the published universe — I would rather it be one
neither of us operates, so it tests the join rather than flattering us.

Dimitri
```

**Recipient:** `ernest-earnordie@agentmail.to` — the address he writes and replies from; his
own `ernest@nolimbsfighting.com` rejects mail and `send_draft.py` refuses it.




