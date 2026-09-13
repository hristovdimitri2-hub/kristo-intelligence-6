# Field notes from operating a 402 endpoint in production

**Status:** field notes, not a specification. They are derived from four
independent audit cycles against one live x402 endpoint that has been taking
real payments, and from the failures those audits actually found. Nothing here
is theoretical: every principle below exists because its absence produced a
wrong number, a lost payment, or a customer who was told something untrue.

**Scope:** the seller's side of the handshake — the part that answers
"was I really paid, and can I prove it?". Corrections welcome.

---

## 1. The problem: the seller cannot tell whether the money is real

A 402 endpoint returns data in exchange for a payment that settles on a
different system entirely. Between those two facts sits an assumption the seller
usually never tests: *that a presented proof of payment corresponds to money
that has actually arrived, exactly once, for exactly this request.* In practice
that assumption failed in four independent ways.

**a. A proof can be spent twice.** A settlement transaction hash is a bearer
token: whoever presents it first gets served. The common guard is an in-process
set of "hashes I have already accepted". It works until the process restarts —
and a deploy restarts it. After a deploy, every previously consumed proof is
live again, and the same payment can unlock a second call. The failure is
invisible in normal operation and appears exactly when a customer is least
likely to be honest about it.

**b. A proof is not bound to anything.** The same payment that buys a cheap
endpoint buys an expensive one, because verification only asks "is this a valid
payment to me, of at least this amount?" rather than "is this a valid payment
*for this route*?". The seller finds out by noticing that revenue does not match
usage.

**c. The receipt is checked, but not its depth.** A transaction at the chain tip
has one confirmation and can still be reorganised away. Serving on it means
serving on a payment that may cease to exist — while the returned data cannot be
un-returned. The fix is not "check the receipt" (everyone does) but "check how
deep it is buried, and refuse if you cannot tell".

**d. The dashboard counts memory, not the chain.** The till is usually an
in-memory list appended by a background scanner. It says what this process has
seen since it started, not what the chain contains. A deploy therefore zeroes
revenue, and the seller cannot distinguish "nobody paid" from "I forgot". This
is the most dangerous of the four, because it corrupts the *decision*: it is
impossible to run a business on a number that silently resets.

### The second failure is not a bug: honest emptiness versus invented completeness

Every 402 product makes a freshness claim — implicitly or explicitly — and the
claim is usually written by a human optimist while the data is supplied by an
infrastructure pessimist. A feed described as "refreshed every 60 seconds" on a
free-tier RPC that refuses any window wider than a single block is not
approximately right; it is a promise the seller cannot keep, sold to a customer
who pays for the promise and receives the reality.

The same pattern appears in the display layer: an empty result is rendered as a
confident zero, a broken scanner is rendered as "no activity", and a stale
number keeps its usual reassuring shape. **A seller who cannot display "I do not
know" will eventually display something false.**

---

## 2. Four principles that survived production

Each one is enforced by code, not by policy. If it is not enforced by code, it
is not a principle — it is a hope.

### C1 — Durable replay lock: consume once, before answering

The proof is claimed **exactly once, atomically, and before the paid response is
produced**, and the claim is written to a **durable store** (a database row, not
a set in memory). The claim and the check are the same operation — a single
insert whose uniqueness constraint is the lock — so two concurrent requests
carrying the same proof cannot both win.

Two details matter more than the mechanism:

* **Durability is the whole point.** A lock that does not survive a restart is
  not a lock; it is a rate limiter with a misleading name.
* **The claim precedes the response.** If the order is reversed, a crash between
  serving and recording leaves the proof unspent and the call free.

### C2 — Fail-closed confirmation depth

A settlement is trusted only when it is buried at least **N confirmations** deep
(12 on Base is roughly 24 seconds). The important half of this rule is the
failure path: **if the depth cannot be determined — RPC error, unknown block,
receipt not found — the payment is refused.** A verification that passes when it
cannot run is not a verification.

This has an honest cost, which the seller should state rather than hide: a
strict depth requirement slows down synchronous settlement rails, and a customer
whose authorisation is already spent on-chain cannot simply "retry later" — the
funds moved. Rail-specific depth policies are therefore legitimate, but the
*default* must be to refuse.

### H2 — Endpoint binding

A proof scoped to one route must not unlock another. The check happens **before
any chain call and before any consumption**: reject the mismatch first, and the
expensive work never happens for a request that was never going to be served.

The subtle half is identity, not routing. A payment hash is public the moment it
is shown on any surface — a dashboard, a block explorer, a support thread — so
"this is a hash I recognise" is not the same as "this is *your* hash". A proof
must be bound to the payer who actually sent it, either by the receipt itself or
by the recorded sender of the sale. Otherwise the seller is publishing free
passes and calling them transparency.

### Chain-truth: the chain is the only source of sales

Revenue is read from the chain (or from a durable projection of it), and every
other representation — a cache, a counter, a dashboard widget — is **explicitly
a cache with a TTL**, never the source. Two consequences follow:

* **Freshness is shown, not promised.** The response states the block it has
  scanned up to, so a buyer can verify the data's age instead of trusting a
  sentence about it. A claim in prose cannot be audited; a block number can.
* **A missing record must never render as a zero when the true state is
  "unknown".** Empty, scanning, stale and broken are four different states and
  deserve four different labels.

> The principles were derived on one rail (USDC on Base); none of them is
> rail-specific — they apply to any settlement rail.

---

## 3. What four audits taught us

These are the uncomfortable parts; they are the reason the note exists at all.

**Four independent audits found real problems every single time, and none of
them was redundant.** Each cycle went looking for the same class of thing — a
place where the system's claim and the system's behaviour could diverge — and
each cycle found one. The lesson is not "audit more"; it is that **a payment
path is never finished, only currently correct**, and that the honest output of
an audit is a list of things that were wrong, not a statement of confidence.

**Write the expected number down *before* you measure.** If the chain disagrees
with the notes, the notes are wrong — including when the notes are flattering.
In practice this rule caught: a total that had been remembered slightly wrong,
two transfers that were priced higher than assumed, and a "customer" who had
never paid at all. In each case the temptation was to adjust the measurement.
The correct action is always to correct the record and say so out loud.

**Publish full transaction hashes; truncated ones invent customers.** A hash
shown as `abc…123` is not evidence — it is a glyph that *looks* like evidence.
During reconstruction, truncated hashes had produced a payer who did not exist
and a payment count that was wrong by one. Once the full hashes were pulled from
the chain and cross-verified against independent receipts, the phantom payer
disappeared and the real customer count dropped. **A verification surface that
cannot be independently re-checked will slowly fill with things that never
happened.**

**A "truthful empty" beats an invented bar.** A feed with no data may be healthy
or broken, and those two states must never share a rendering. On a paid route,
"we are scanning and have found nothing above the threshold" is a legitimate
answer; "zero" is not, because it is indistinguishable from a dead pipeline, and
"checked" is worse, because it is genuinely false. The same applies to a lamp
that turns red when a scanner fails: **that is a feature, not a defect** — a
silent failure is the expensive kind.

**Count internal noise separately, and cite only the clean numbers outside.**
Self-generated traffic — health checks, keep-alive pings, monitoring probes —
inflates any naive total, and inflated totals destroy the credibility of the
real ones. Split them at the source, label them, and quote the clean figure in
public.

---

## 4. A five-minute self-check for any 402 seller

Five checks. Each one takes under a minute and each one has a binary outcome —
which is the point: a verification you cannot fail is not a verification.

| # | Do this | Pass condition |
|---|---|---|
| 1 | Replay an old, valid proof after a restart | It is **refused** (not merely slow) |
| 2 | Present a proof scoped to route A against route B | It is **refused**, before any chain call |
| 3 | Delete the in-memory state; read the till | The number is **unchanged** |
| 4 | Compare the price in the 402 challenge with the price on your own storefront | They are **identical** |
| 5 | Stop the RPC (or point it at a dead host) | The freshness lamp turns **red**; nothing goes silently stale |

Two notes on interpreting the results:

* **Checks 1–3 are about the seller's own honesty.** They fail silently in
  normal operation, which is why they need to be performed deliberately.
* **Checks 4–5 are about the seller's own claims.** They fail *visibly to the
  customer*, which is worse: a price that disagrees with your own listing means
  a paying agent overpaid by your own advertisement, and a freshness claim that
  outlives its provider is a promise sold and not delivered.

If any of the five fails, the fix is in the code, not in the wording — except
for check 4 and 5, where the honest short-term fix is often to change the
wording first and the infrastructure second.

---

*Field notes, published once, for the people who will operate these endpoints
after us.*


