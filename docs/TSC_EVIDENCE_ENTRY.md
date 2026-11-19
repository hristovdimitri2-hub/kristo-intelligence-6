<!-- Paste-ready draft for the REPLIES of Martin Sansone's "Evidence" thread in
     #tsc-public (x402 Foundation TSC; tsc#4 map of offer -> authorisation ->
     settlement -> delivery, and proof the service was received).
     Formatted for Slack: *bold*, bare URLs, no markdown link syntax, no
     headings. Nothing here is published by the agent. -->

Replying to the Evidence mapping thread (tsc#4), and to the question of a new
extension versus amendments to Signed Offers and Receipts #2811.

We run seven paid HTTP routes and seven MCP tools on Base
(https://kristo-intelligence-api.onrender.com), small enough that everything
below is first-hand. Two measurements, one at each end of the chain. Both are
reproducible from outside, with no access to us.

*Delivery end: settlement is non-terminal, and the boolean lies.*

The v2 spec names `settlement_pending`: the transaction was broadcast, but
confirmation could not be established, an RPC error or a receipt timeout. It is
*non-terminal*, and the response must carry the hash so the seller can reconcile
against the chain.

We were reading `success: false` as "this payment failed". So a settlement that
had already been broadcast was refused, and the paying caller lost the call it
had paid for. This is not a rare path: a facilitator operator in this group
measured ~19 settle failures across ~11.7k settlements, 9 of which had in fact
settled.

What I would put in guidance rather than leave to each seller:

1. Adopt the hash from a `settlement_pending` response instead of discarding it.
2. Verify it yourself before delivering: the transfer to your `payTo`, for at
   least the price you quoted. The relying party recomputes rather than trusts,
   which is the principle several proposals here already hold.
3. Match on the error *code*, never on `errorMessage`. The spec requires this
   because the message is free to change between releases.

Ours is `_adopt_settlement_pending` in services/connectors.py:
https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/services/connectors.py

A seller that trusts the boolean keeps the failures and loses the customers who
actually paid.

*Offer end: the offer that gets published is not the offer that was signed.*

`POST https://api.cdp.coinbase.com/platform/v2/x402/validate` takes no API key
and returns more than a validity verdict. It returns `bazaarExtension`, the
listing the catalogue intends to publish (`input.method`, `input.queryParams`,
`output.example`). The offer leg is produced by a transformation that is
invisible from the seller's side; this makes it visible. We wrapped it in a
preview that walks our paid routes, takes each 402, and diffs our declaration
against the intended listing:
https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/scripts/validate_preview.py

First run against the live server: 7/7, no differences.

Two cases where the published offer is not the offer that was sent:

- *The catalogue appends `#toolName` itself.* Declaring `/mcp#get_whale_flow`
  stores `/mcp#get_whale_flow#get_whale_flow`. The catalogued identity of your
  offer is not the string you signed.
- *An unknown key inside `accepts[0]` is accepted and silently voids the row.*
  Ours were `extra_name` / `extra_version`, bookkeeping for our own EIP-712
  pre-check, present in no facilitator schema. The facilitator settled, we got a
  hash, and eight settlements produced no listing. Removing the two keys: listed
  in 45 seconds.

Both ends have the same shape: everything reports success, and the party that
believes something happened is not the party that can check it.

One caveat we had to learn the same way: for *MCP* resources, `/validate` reports
`returns_402` failed and `bazaarExtension: null`, identically for MCP resources
that are listed. The endpoint is HTTP-shaped; failing it says nothing about MCP
eligibility.

*Our numbers, because evidence should be checkable.*

171 settlements, $1.883 total. Of that, *122 settlements and $1.685 are our own
key and canaries*. External customers: 12 payments, $0.054. The chain is not
verifiable if listing volume is self-dealing, so we publish the split rather
than the total. The full write-up, including the four mistakes we made getting
these numbers:
https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/INDEXING_WRITEUP.md

*On new extension versus amendment:* `settlement_pending` is already named in the
v2 spec, so what is missing there is guidance and a conformance case, not another
extension. I am happy to hand over the preview script and our `settlement_pending`
tests as a starting corpus for whoever is building that leg.
