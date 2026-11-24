# OUTREACH WAVE 1 — DRAFTS (DO NOT SEND)

> ## ⛔ SENDING WAITS FOR TWO CONDITIONS: (a) merge of #13219, (b) F1 gate closed.
> ## Without both — it does not go out.

**Status as of 25.09.2026 (verified live):**

| Condition | State |
|---|---|
| (a) PR #13219 (punkpeye/awesome-mcp-servers) | ✗ **OPEN** — mergeable CLEAN, label `has-glama`, badge renders "rated A"; awaiting merge from Frank (last activity 22.09) |
| (b) F1 gate | ✗ **OPEN (partial proof)** — **A1:** live guard_events (PostgreSQL, 25.09 06:18 UTC): **never** any `c2_settlement_in_flight`/`c1_nonce_adopted` — the path exists in code+tests, never traversed live. **A2:** partially proven — 402 + retry mechanics live from outside (`scripts/e2e_nopay_probe.py`: 6×402 identical, synthetic proof → 401 fail-closed). **FULL proof (payment → 425 → 200) WAITS FOR WALLET** — funding is a human action, not a decision. |

**Package rules:** nothing here has been sent; every text goes out ONCE, personalized;
payTo/prices/guards are not touched. Every text leads with one number OR one
methodology — never both at once.

**Verified live numbers (25.09):** 6 paid routes from $0.003/call · challenges total
~27.6k (signal 12,351) · on-chain $0.043 / 13 tx / 2 external · Glama rated A ·
410/410 tests · C1 lock in PostgreSQL (durable, survive deploy) · C2 = 12 confirmations.

**The only curl everyone needs:**
`curl -i https://kristo-intelligence-api.onrender.com/api/v1/signal` → 402 with the whole
challenge body (amount, payTo, scheme) — nothing else is explained in words.

---

## SEGMENT 1 — Coinbase AgentKit / CDP communities (4 pcs.)

Short. ONE number + one curl. We do not tell a story — we show a ready-made integration
that their agents can pay for today.

### 1.1 CDP Discord → #agentkit (or #build-on-base)

> Hey — built against AgentKit + the x402 facilitator: a live DeFi data API
> where the agent pays per call in USDC on Base, no API keys, no signup.
> The whole integration is one GET — the 402 body carries amount, payTo and
> scheme, so `pay()` + retry is the full surface:
> `curl -i https://kristo-intelligence-api.onrender.com/api/v1/signal`
> Routes from $0.003/call. Happy to share the server side if useful.

### 1.2 github.com/coinbase/agentkit → Discussions

**Topic:** `x402-paid data endpoint that AgentKit agents can call out of the box`

> We run an x402 v2 endpoint (canonical challenges, atomic units, eip155:8453)
> tuned for AgentKit-style agents: `GET /api/v1/signal` → 402 → settle via the
> Coinbase facilitator → retry with the proof header → 200 data.
> `curl -i https://kristo-intelligence-api.onrender.com/api/v1/signal`
> Nothing to register — if AgentKit ever gains a generic "pay and retry"
> action, this is the shape it would consume. Feedback welcome.

### 1.3 Base Discord → #developers

> x402 server on Base that any agent can pay for in one round trip — 402 body
> is self-contained (amount/payTo/scheme), settle, retry, data.
> `curl -i https://kristo-intelligence-api.onrender.com/api/v1/signal`
> 6 routes from $0.003, all on-chain settled. If anyone's building an
> agent-wallet loop, this is a cheap endpoint to test against.

### 1.4 Reply in an existing x402/CDP thread (fill in the link)

> One more server for the list — DeFi signals on Base, x402 v2 canonical
> challenges, paid per call from $0.003:
> `curl -i https://kristo-intelligence-api.onrender.com/api/v1/signal`
> Every settlement is public, so the receipts speak for themselves.

---

## SEGMENT 2 — x402 sellers (3 pcs.)

Collegial tone. The methodology is SHARED, not sold — we wrote it because we
tripped over it ourselves four times; if it saves them a single bug, everyone
wins. Not one text asks for anything.

### 2.1 ParkerChet / PayAPI Market (known channel)

> Chet — sharing, not selling: we turned our 402-guard field notes into a short
> doc (https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md).
> Four principles that survived production — durable replay lock, fail-closed
> confirmation depth, endpoint binding, chain-truth revenue — each exists
> because its absence once cost us a wrong number or a lost sale. If any of it
> is useful for how PayAPI validates sellers, it's yours. No ask attached.

### 2.2 Second x402 seller (from x402scan/Bazaar — fill in the name)

**Topic:** `402 guard field notes — yours if useful`

> Hi [NAME] — fellow x402 seller here ([one sentence: what you sell]). We
> audited our own guard four times and wrote down what actually held up:
> consume the proof once in a durable store BEFORE serving, refuse when depth
> can't be determined, bind proof→endpoint→payer, read revenue from the chain
> only.
> https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md
> Curious whether your stack hit the same four failure modes — always keen to
> compare notes with another live seller.

### 2.3 Third x402 seller / infrastructure project (facilitator or index)

**Topic:** `Replay + depth failures we hit in production — writeup`

> Hey — we operate a paid 402 endpoint and documented the failure modes that
> survived four audits (bearer-token replay across deploys, unbound proofs,
> depth-unchecked receipts, dashboards counting memory instead of chain).
> Full writeup, no product pitch:
> https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md
> If any of it matches what you see from other servers, we'd love the
> correction — the doc is field notes, not a spec.

---

## SEGMENT 3 — AI builders (3 pcs.) — METHODOLOGY-LED

**Segment rule:** "What we learned while building the x402 payment guard". The
technical content leads. **The numbers stay in the link, not in the message** —
not a single price/revenue number in the bodies below.

### 3.1 Reddit r/AI_Agents

**Title:** `We built an x402 payment guard for our API and audited it 4 times — here is what actually broke`

> Every "agent pays for data" demo assumes the seller can tell that the money
> is real, exactly once, for exactly this request. Ours couldn't, four
> different ways:
>
> 1. A settlement hash is a bearer token — and our in-process set of "seen
>    hashes" died with every deploy, re-opening every consumed proof.
> 2. A proof wasn't bound to anything — the same payment could unlock a
>    different, more expensive route.
> 3. We checked the receipt but not its depth — a payment at the chain tip
>    can be reorganised away after the data is already served.
> 4. The dashboard counted memory, not the chain — a deploy zeroed revenue
>    and we couldn't tell "nobody paid" from "I forgot".
>
> Each fix is enforced by code, not policy: one atomic durable insert before
> serving, refuse when depth is indeterminate, bind proof→endpoint→payer,
> read revenue from the chain only. Full field notes (corrections welcome):
> https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md

### 3.2 Hacker News — Show HN

**Title:** `Show HN: Field notes from running a paid 402 endpoint in production`

> We've been selling API calls to AI agents and wrote down the seller-side
> half of the handshake — "was I really paid, and can I prove it?" — because
> that assumption failed on us four independent times.
>
> The principles that survived: consume the proof once, durably, *before*
> answering; fail closed when confirmation depth can't be determined; bind
> the proof to endpoint and payer; treat the chain as the only revenue
> source and everything else as a cache with a TTL. There's also a section
> on honest emptiness versus invented completeness — an empty result
> rendered as a confident zero is how a dashboard starts lying.
>
> It's field notes from four audit cycles against one live endpoint, not a
> spec: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md
> Curious what other people running pay-per-call endpoints got wrong that
> we haven't found yet.

### 3.3 Reddit r/AI_Agents (second post — narrower, deployment-focused)

**Title:** `A payment-replay lock that doesn't survive a deploy is a rate limiter with a misleading name`

> We kept a set of consumed payment hashes in process memory. It worked
> perfectly until the first deploy — after which every previously consumed
> proof was live again and the same payment could unlock a second call. The
> failure is invisible in normal operation and shows up exactly when a
> customer is least likely to be honest.
>
> Fix that held: the claim and the check are the same operation — a single
> insert whose uniqueness constraint is the lock — written to a durable
> store, before the paid response is produced. Details (plus the three
> failure modes we found next):
> https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md

---

## Before sending (checklist — filled in once the gate is closed)

- [ ] (a) #13219 is MERGED
- [ ] (b) F1 gate: FULL proof — a real payment ($0.003) + captured 425
      + 200, after which guard_events shows a new `c2_settlement_in_flight` /
      `c1_nonce_adopted`. Right now: A1 + A2 (no-pay) are ready, **the last step
      waits for a funded wallet** (human funding — not "waiting for a decision")
- [ ] Every text is personalized (recipient's name/project)
- [ ] 1 message/day — the segments are not fired all at once
