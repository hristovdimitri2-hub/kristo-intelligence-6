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
