# Sentient Foundation — Open Source AGI Grant application

**Status:** draft, ready to paste. Written 2026-11-20.
**Form:** https://form.typeform.com/to/IRj7WaKH ("Sentient Foundation Open Source AGI Grant")
**Programme page:** https://sentient.foundation/grants — $42M committed, two tracks
(grant + investment), rolling review, no cohorts. Grant track: *"no equity, no claim
on your work."*

**Why this programme and not a generic one.** The call asks for two halves: products
for people, and *"the infrastructure that makes [them] trustworthy"* — naming, in
their own words, "identity and safe hands for the agents about to act on our behalf"
and "proof that a model is what it claims and did what it says". This project is the
second half, built and measured from the seller's side of a live payment wire.

**How to use this file.** Every answer below is written to be pasted into the matching
form field. Fields marked `[YOU]` need a fact only you hold. Nothing here is invented:
every number is either read from the repo or from a live endpoint, and each one is
cited so a reviewer can check it.

---

## 1. One line — what are you building

> A live, MIT-licensed x402 payment endpoint for AI agents, plus the public
> conformance evidence that makes agent-to-agent payments checkable: what the
> buyer was offered, what it actually paid, and what the seller actually delivered.

---

## 2. Who are you?

`[YOU]` — name, email, primary role (the form asks for role: founder / engineer /
researcher / other), and how you heard about the programme.

Suggested framing for "primary role": **independent builder / maintainer**.

---

## 3. What problem are you solving, and why now?

Agents are starting to pay each other, and the payment leg is the part nobody can
audit. Two failure modes are structural, not incidental, and both were measured on
this project's own live wire:

**a. Settlement is non-terminal, and the boolean lies.** The x402 v2 spec names
`settlement_pending`: the transaction was broadcast but confirmation could not be
established. It is non-terminal, and the response must carry the hash so the seller
can reconcile against the chain. We were reading `success: false` as "this payment
failed", so a settlement that had already been broadcast was refused and the paying
caller lost the call it had paid for. A facilitator operator in the x402 TSC group
measured ~19 settle failures across ~11.7k settlements, 9 of which had in fact
settled. A seller that trusts the boolean keeps the failures and loses the customers
who actually paid.

**b. The offer that gets published is not the offer that was signed.** The catalogue
transforms the declaration before listing it, and the transformation is invisible
from the seller's side. Two cases we hit: the catalogue appends `#toolName` itself
(declaring `/mcp#get_whale_flow` stores `/mcp#get_whale_flow#get_whale_flow`), and an
unknown key inside `accepts[0]` is accepted and silently voids the row — the
facilitator settled, we got a hash, and eight settlements produced no listing.

Both ends have the same shape: *everything reports success, and the party that
believes something happened is not the party that can check it.* That is the exact
failure the programme's "infrastructure that makes it trustworthy" half is asking
for. It is why now: the spec is being amended right now (Signed Offers and Receipts
#2811), and the conformance cases do not exist yet. Whoever writes them first decides
what "correct" means for the next thousand sellers.

---

## 4. Who does this help?

- **Sellers** — every x402 seller who has ever had a settlement succeed and a listing
  not appear. The preview tool tells them before they pay.
- **Buyers/agents** — an agent that pays once and gets a refusal loses real money and
  has no way to tell "seller is broken" from "seller is honest and the chain was slow".
- **The standard itself** — the conformance corpus is the difference between a spec
  that says "should" and one that can be tested.

---

## 5. What's open about it, and what would get worse if it closed?

**Open:** MIT licence. The full API implementation, the 1,446-test suite, the
conformance cases, the preview script, and every measurement write-up are in the
public repo: https://github.com/hristovdimitri2-hub/kristo-intelligence-6
(~98k lines of Python, 645 commits, 15 OpenAPI paths).

**What would get worse if it closed, and for whom:**

1. **The `settlement_pending` conformance cases.** They are the only seller-side
   tests we know of that exercise the non-terminal path — the case where a payment
   is broadcast, not confirmed, and the correct behaviour is to adopt the hash and
   verify rather than refuse. If this repo closes, the tests close with it, and the
   next seller re-learns the lesson by losing a paying customer.
2. **The offer-preview tool** (`scripts/validate_preview.py`). It walks a seller's
   paid routes, takes each 402, and diffs the declaration against the listing the
   catalogue intends to publish. It answers in one request what took us a day of
   reasoning. Closed, it is a service; open, it is a habit.
3. **The honest-revenue split.** We publish 171 settlements / $1.883 *and* the split
   that shows 89.5% of that is our own key and canaries. A closed seller quotes the
   total. The split is the part that makes the total mean anything.
4. **The measurement method.** "Measure from the buyer's side, over a public RPC, one
   call per field, no payment" is a recipe anyone can repeat. It is written down.

---

## 6. Demo / trial links

- **Live API:** https://kristo-intelligence-api.onrender.com
- **Free discovery:** `GET /api/mcp/manifest`, `/.well-known/x402`, `/openapi.json`
- **The offer preview:** `scripts/validate_preview.py` in the repo — first run against
  the live server: 7/7 routes, no differences.
- **The honest split:** `GET /api/dashboard/data` → `sections.onchain.by_class`
- **The signal's own track record:** `GET /public/signals/history` (free, public)

`[YOU]` — the ≤2-minute demo clip (request → 402 → payment → HTTP 200) exists but is
kept out of the repo. Attach it to the form if the upload accepts video.

---

## 7. Track

**Open Source AGI Grant track.** Not investment: the deliverable is a public good
(conformance corpus + measurements + a live reference seller), and the grant track's
terms — no equity, no claim on the work — are the right shape for it. A closed round
would make the conformance cases less useful, not more.

**And the support beyond the money.** The programme offers four things next to the
grant — distribution, compute credits, engineering support from the team behind the
Sentient Stack (ROMA, Open Deep Search, EvoSkill), and the community. Those are worth
asking for explicitly, because each one removes a bottleneck the money does not:

| what the programme offers | what we would use it for | why the money alone does not solve it |
|---|---|---|
| **Distribution** | Put the conformance corpus and the reference seller in front of the people building open agents — the audience that has to implement the payment leg. | We can publish; we cannot reach. The programme already has the room. |
| **Compute credits** | A CI runner that runs the conformance suite against live servers on every change, plus a long-running probe for the honest-revenue measurement. | The suite's value is that it runs continuously. A one-off run is a screenshot. |
| **Engineering** | Review of the conformance-suite design by people who have shipped agent infrastructure; help making the corpus framework-agnostic and CI-friendly. | One person writing a standard is one person's blind spots. |
| **Community** | Peer review from open-source AI builders, which is what keeps conformance cases honest. | The cases are only as good as the sellers who try to pass them. |

There is a two-way piece here as well: if the Sentient Stack's own agents need an x402
payment leg, the `settlement_pending` handling and the offer/delivery diff in this repo
are directly reusable, and we would rather contribute them than have each team rediscover
them.

---

## 8. How much are you asking for, and what would it unlock?

**Ask: $30,000 over 6 months.**

The number is sized to one person working on this full-time for six months, plus
hosting and the paid probes the measurements require. It is not a valuation of the
product; it is the cost of finishing the public-good half.

| milestone | deliverable | when |
|---|---|---|
| 1 | **Published conformance suite for x402 v2 seller behaviour** — `settlement_pending` adoption, hash verification, error-code matching (never `errorMessage`), and the offer/delivery diff. Framework-agnostic, MIT, with a runner that takes any base URL. | month 2 |
| 2 | **`validate_preview.py` generalised** into a documented tool any seller can run against their own server, with a written report format. | month 3 |
| 3 | **Honest-revenue spec** — a `/.well-known/honest-revenue.json` schema and reference implementation, so "self-dealing" becomes a field a buyer can read instead of a suspicion. | month 4 |
| 4 | **The live reference seller kept running** — 7 paid routes, 7 MCP tools, all registries current, uptime published. | continuous |
| 5 | **Written up and handed to the TSC** — the two measurements as amendments/guidance in the #2811 thread, plus the corpus. | month 6 |

**What the grant unlocks that is not already happening:** the corpus and the tooling
are currently written for one server (ours) and one person's time. The grant buys the
generalisation — the part that only pays off for other people.

**If $30,000 is the wrong size for this round:** the honest fallback is a $3,000
micro-grant for milestone 1 alone (the conformance suite). That is the piece with the
highest ratio of public value to cost, and it is the piece we would fund first.

---

## 9. How do you make money while staying open?

Per-call micropayments: $0.005–$0.050 USDC per call on Base, no API keys, no accounts,
no prepaid credits. The code is MIT; the revenue is the running service, not the
source. Anyone can fork it and run it — and if they do, the conformance cases travel
with them, which is the point.

**The measured numbers, including the uncomfortable ones:**

| class | settlements | USDC | share |
|---|---:|---:|---:|
| own key | 122 | 1.685 | 89.5% |
| canaries | 17 | 0.067 | 3.6% |
| market sampler | 20 | 0.077 | 4.1% |
| **external customers** | **12** | **0.054** | **2.9%** |

171 settlements, $1.883 total — and 89.5% of the dollar volume is our own money. Twelve
settlements came from someone who is not us; after removing the auditor we paid, eight
real external buyers, ten payments, $0.041. Those eight wallets hold $131.13 between
them. They have money; they paid once and did not come back.

We publish the split because a number a buyer cannot check is marketing. The honest
figure is the reason the conformance work matters: the product did not survive a
second purchase, and the fix is not more discovery — it is a product a buyer can
verify for themselves.

---

## 10. Traction and proof

- **Live on Base mainnet** since 2026-09-02; 171 settlements, $1.883, split above.
- **Registry grades, read live on 2026-11-20:**
  - x402register.com — **A, 90.7**, availability 100%, median 576 ms
  - x402-list.com — compliance **A 14/14**, uptime 100%
  - x402lint.dev — **B, 84** (17 pass / 3 warn / 3 fail; the three fails are ours and
    mechanical, and are fixed in the current tree)
  - x402-trust.com — all 7 paid routes **B**; `/api/stats` graded **avoid**
- **Official MCP Registry** — 4 versions, `active`.
- **x402lint's three FAILs, fixed 2026-11-20:** `components.securitySchemes.x402` was
  missing; 7 paid operations carried a `402` but no `security`; one description was
  603 characters against a 500 cap. All three verified in the generated spec.
- **1,446 automated tests**, 1 skipped. The suite is not decoration: it is what makes
  the claims in this document checkable.
- **Independently re-checked by a third party, 18.11.2026.** The auditor who cleaned up
  our dead-host rows (x402scan issue #1340) re-ran the check and published the result:
  the dead host `kristo-intelligence.vercel.app` returns 404 `DEPLOYMENT_NOT_FOUND` and
  has **0 rows** left in the Bazaar catalogue dump and the CDP discovery index
  (`partialResults:false`, a complete list, not a truncated page); the live host has
  **19 catalogue rows, all active**, every one returning a correct 402 with our `payTo`,
  and the CDP index holds **20 rows, complete**, all on the live host. That is an
  outside party confirming the payment wire, not our own claim about it.
- **GitHub:** https://github.com/hristovdimitri2-hub/kristo-intelligence-6
  `[YOU]` — stars/forks if you want them quoted; the form asks for metrics.

**The honest risk, stated plainly.** This is a one-person project with $0.054 of
external revenue. The grant is not a bet on revenue; it is a bet that the measurement
and conformance work is worth more to the ecosystem than the product currently earns.
That is the argument, and a reviewer should weigh it as such.

---

## 11. Milestones for the next 3–6 months

1. **Ship the conformance suite** (month 2) — the deliverable that survives us.
2. **Generalise the preview tool** (month 3).
3. **Publish the honest-revenue spec** (month 4).
4. **Take the two measurements to the TSC** as guidance/amendment material for #2811
   (month 5) — the thread is already open; the Evidence entry is already posted.
5. **Keep the reference seller live and current** (continuous) — 7 routes, 7 MCP tools,
   all registries, honest uptime.

---

## 12. Anything else the reviewer should know

Two things we would rather say ourselves than have found out.

**The signal has no measured edge.** One of the seven endpoints sells a prediction.
Measured from its own public feed: 84 scored signals, 52.4% positive 24h moves, mean
move −0.56%, hit rate 1.2% at the published bar. The other six endpoints sell facts
that are either true or false and can be checked by the buyer. We say so in public
(`docs/SIGNAL_EDGE_FINDING.md`) because the alternative is selling the unproven one
first and making the whole API look untrustworthy.

**The revenue is mostly ours.** 89.5% of the dollar volume is our own key and
canaries. The split is published next to the total, in the same document.

If the programme's bar is "does this make open AGI more trustworthy", the answer is
the conformance corpus and the measurements — not the trading signal. We would rather
be funded for the first and say the second is unproven.

---

## Appendix — facts a reviewer can check without asking us

| claim | where to check |
|---|---|
| 7 paid routes, $0.005–$0.050 | `GET /openapi.json`, or any paid route's 402 |
| `securitySchemes.x402` present | `GET /openapi.json` → `components.securitySchemes` |
| 7 paid ops carry `security` | `GET /openapi.json` → each op with a `402` |
| no description over 500 chars | `GET /openapi.json` → `len(description)` |
| honest split | `GET /api/dashboard/data` → `sections.onchain.by_class` |
| signal track record | `GET /public/signals/history` |
| 1,446 tests | `pytest -q` in the repo |
| MIT licence | `LICENSE` in the repo |

---

## `[YOU]` — what only you can fill in

**Decided already (20.11):** grant track, not investment. Ask for the money *and* the
four supports next to it (distribution, compute credits, engineering, community). The
$30,000 ask stands, with the $3,000 micro-grant as the fallback only if the reviewer
prefers a smaller first round.

Still needed from you:

- Name, email, primary role, how you heard about the programme.
- Team size and how long the founders have known each other (this is a one-person
  project as far as the repo shows — say so plainly; it is not a weakness).
- Location / timezone.
- The demo video link, if the form accepts it.
- Whether to name the trading signal as unproven in the application itself. The
  recommendation is yes: it is the difference between a claim and a measurement, and
  it is the reason the conformance work is credible.
