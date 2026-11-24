# ACP marketplace — the plan, and what it actually requires

**Written 24.11.2026, after reading the `acp-cli` README and installing the CLI.**
This is the answer to the question we sent to the ACP team, found in their own
documentation rather than waited for.

---

## What ACP offers, and what does not fit

The README describes three things an agent can publish. They are not the same,
and only one of them is a marketplace.

| Thing | What it is | Fits us? |
|---|---|---|
| **Resource** | "external data/service endpoints … discoverable but not transactional" | **No.** This is a catalogue entry — the same thing we already have in six places. |
| **Offering** | "the agent's offerings … buyers hire … USDC-escrowed jobs" | **Yes.** This is a hire. |
| **Subscription** | a recurring access window (15/30/60/90 days) | Maybe later. |

So the answer to our question is: **a hosted HTTP service cannot be an offering
directly. An offering belongs to an agent, and the agent must do the work.** The
way in is to wrap the HTTP API in a thin provider agent.

That is not a blocker — it is a small worker. But it is real work, and it is the
first thing in this whole project that would put us inside a hire rather than a
catalogue.

---

## The job lifecycle, from the README

1. A buyer finds the offering and creates a job. `acp browse <query>` →
   `acp client ... create-job --offering ...`
2. The buyer funds the job. The money sits in **escrow**, not with us.
3. The provider proposes a budget: `acp provider set-budget`.
4. The provider does the work and submits a deliverable:
   `acp provider submit --deliverable <url-or-payload>`.
5. The buyer accepts; escrow releases.

Events stream as NDJSON: `acp events stream`. The README calls this "suitable for
an agent interface".

**Key consequence:** we are paid when the buyer *accepts*, not when we answer.
A dispute means the money stays in escrow. That is a different commercial shape
from x402, where payment is immediate and final. It is worth knowing before we
commit.

---

## The auth flow — device-style, needs the owner once

`acp configure start` prints a URL and a requestId, then exits. The owner opens
the URL and signs in; then `acp configure complete --request-id <id>` exchanges
it for tokens. Same shape as the `mcp-publisher` device flow.

**Generated 24.11.2026 15:33 EET:**
`https://app.virtuals.io/acp/auth/v2?requestId=6cdc56bd37d2dfce6e77edcbacb1ccf9`

If that link has expired by the time it is used, run `acp configure start`
again — it costs nothing.

---

## The agent we would create

- **Name:** something that says what it sells, not what it is. The Glama lesson:
  the name is the first disambiguation signal.
- **Signer policy:** `restricted` (authorises ACP transactions only). `deny-all`
  would need a human approval per job; `unrestricted` is too much.
- **Offering:** `verify-seller-receiver` — the route that is hardest to
  commoditise and the only one a buyer needs *before* spending money.
  - **Requirements:** a receiving address on Base, and optionally the token and
    amount of the intended payment.
  - **Deliverable:** a verdict with the evidence (does the address match the
    claimed seller, is it a known contract, has it received payments before).
  - **Price:** to be decided. The x402 route is $0.05; an escrowed job has
    overhead, so a marketplace price should be higher, not lower.

---

## What has to be built

A small provider worker that:

1. listens to `acp events stream` for new jobs on our offering;
2. on a new job, calls our own `/api/v1/verify-seller` internally (no payment —
   we are the seller) and formats the verdict;
3. submits the deliverable with `acp provider submit`;
4. logs everything, so a dispute has a record.

That is a few hundred lines at most. It is also the first piece of our stack
that earns money without a human in the loop.

---

## Open questions to settle before building

1. **Is the escrow acceptable?** x402 pays instantly and finally; ACP holds the
   money until the buyer accepts. For a $0.05 check the escrow overhead may cost
   more than the sale. A higher price per job is the answer, or a subscription.
2. **Who is the buyer?** An ACP buyer is an agent with a funded wallet looking
   for a capability. That is a different buyer from an x402 caller, and we have
   no evidence yet that one exists for seller verification.
3. **Does the marketplace have demand?** `acp browse` needs an active agent, so
   we cannot inspect the listings until we register. The 3467-star client and
   the 37 open issues suggest an active project, not a populated marketplace.
   **We should look at the browse results before building the worker.**

The order that wastes the least: **authorise → create the agent → browse the
marketplace → only then decide whether the worker is worth writing.**
