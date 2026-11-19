<!-- Paste-ready draft for the "Evidence" thread in #tsc-public (x402 Foundation
     TSC; Martin Sansone's offer -> authorization -> settlement -> delivery map).
     Formatted for Slack: *bold*, bare URLs, no markdown link syntax, no
     headings. Nothing here is published by the agent. -->

Two measurements on the offer-to-delivery chain, from a small seller.

We run seven paid HTTP routes and seven MCP tools on Base
(https://kristo-intelligence-api.onrender.com), which makes us small enough that
everything below is first-hand. Two findings, one at each end of the chain you
are mapping. Both are reproducible from outside, with no access to us.

*1. Delivery end: settlement is non-terminal, and the boolean lies.*

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
   least the price you quoted.
3. Match on the error *code*, never on `errorMessage`. The spec requires this
   because the message is free to change between releases.

Ours is `_adopt_settlement_pending` in services/connectors.py:
https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/services/connectors.py

A seller that trusts the boolean keeps the failures and loses the customers who
actually paid.

*2. Offer end: you can see the listed offer before anyone pays for it.*

`POST https://api.cdp.coinbase.com/platform/v2/x402/validate` takes no API key
and returns more than a validity verdict. It returns `bazaarExtension`, the
listing the catalogue intends to publish (`input.method`, `input.queryParams`,
`output.example`). The offer leg of your chain is produced by a transformation
that is invisible from the seller's side; this makes it visible. We wrapped it in
a preview that walks our paid routes, takes each 402, and diffs our declaration
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

One caveat we had to learn the same way: for *MCP* resources, `/validate` reports
`returns_402` failed and `bazaarExtension: null`, identically for MCP resources
that are listed. The endpoint is HTTP-shaped; failing it says nothing about MCP
eligibility.

*Our numbers, because evidence should be checkable.*

171 settlements, $1.883 total. Of that, *122 settlements and $1.685 are our own
key and canaries*. External customers: 12 payments, $0.054. The offer-to-delivery
chain is not verifiable if listing volume is self-dealing, so we publish the
split rather than the total. The full write-up, including the four mistakes we
made getting these numbers:
https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/INDEXING_WRITEUP.md

Happy to hand over the preview script or our conformance examples for
`settlement_pending` to anyone building the same leg.
