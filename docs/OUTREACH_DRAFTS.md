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
