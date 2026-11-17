# Getting an x402 endpoint indexed: measured field notes

*Written 17 November 2026 by the operator of a live x402 seller on Base
([kristo-intelligence-api.onrender.com](https://kristo-intelligence-api.onrender.com)).
Every claim below is a measurement with a number and a time attached, and the
three things we got wrong are recorded with the same care as the three we got
right. Nothing here is inferred from documentation; the documentation did not
say any of it.*

---

## Why this is worth writing down

An x402 seller can be fully correct — a valid 402, a signed payment, real USDC
settled on chain — and still be invisible. We know, because we spent a day being
exactly that: money moving, six routes settling, and **zero rows** in the
catalogue every agent reads.

There is no public account of how that catalogue decides what to list. This is
one, from the seller's side, with the queries to reproduce it.

---

## The method, so you can check any of this yourself

**Query by `payTo`, never by text.** The discovery endpoints are per-address:

```
GET https://facilitator.payai.network/discovery/resources?payTo=<your address>
GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?type=mcp
GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?type=http
```

A text query (`?query=…`) mixes addresses together, so it looks like you have
rows when the address you care about has none. Combining `query` and `payTo`
returns 400. We spent an hour misled by this, and a re-auditor we hired was
misled by it too — his list of "still stale" routes included six that no longer
existed under that address.

---

## Finding 1 — there are two catalogues, and they fill by different mechanisms

Both are described as "the Bazaar". They are not the same system.

| | CDP Bazaar | PayAI |
|---|---|---|
| how a row appears | **crawl** | **settlement** |
| proof | a real MCP call settled through CDP (`settled via cdp`, tx `0xb4acab73…`) wrote **nothing** across six checks over 4½ minutes | a settlement of `/api/v1/signal` produced a row in **45 seconds**, carrying the new receiver and the new price |

This matters more than it sounds. It means **paying your own endpoint does not
get you listed everywhere** — on one catalogue it does nothing at all, and no
amount of further paying changes that.

## Finding 2 — the shape of `resource` decides whether PayAI indexes you

The x402 spec's `PaymentRequirements.resource` is a string URI. We sent a string.
PayAI accepted the payment and **never listed it**. Eight settlements across two
rounds produced no rows.

The same route, settled with `resource` as the **object our own 402 publishes**
(`{url, description, mimeType, …}`), listed in 45 seconds.

We now send both forms and let the connector pick per facilitator: the string to
CDP, which is spec-strict and has settled for months; the object to the one that
keeps a catalogue. The helper is ~15 lines.

## Finding 3 — two keys of our own stopped the indexing dead

After fixing the resource shape, five more settlements still produced nothing.
The server was sending the same requirements plus four extra keys. Two of them
are legal `PaymentRequirements` fields (`description`, `mimeType`); two are ours,
added only so our own local pre-check could pin the EIP-712 domain:
`extra_name` and `extra_version`. They appear in no facilitator schema.

Isolated by settling the same route three ways:

| requirements sent | result |
|---|---|
| `accepts[0]` + resource object | listed in **45 s** |
| …plus `description` and `mimeType` | listed in **45 s** |
| …plus `extra_name` and `extra_version` | **never**, across eight settlements |

The failure is silent by construction: the facilitator settles, the client gets a
transaction hash, and the seller simply never appears.

## Finding 4 — the catalogue appends the tool name itself

CDP's MCP rows are shaped `<endpoint>#<toolName>`. We read that as the shape a
seller must *declare*, and declared it. CDP then appended the name again:

```
our declaration   https://…/mcp#get_whale_flow
CDP stored        https://…/mcp#get_whale_flow#get_whale_flow
```

The proof is a peer, listed next to us:

```
mcp.xrpl-utilities.io declares   "url": "https://mcp.xrpl-utilities.io/mcp"
CDP stores for it                "https://mcp.xrpl-utilities.io/mcp#xrpl_pulse_recent_events"
```

A bare endpoint in, one fragment out. And of CDP's 541 MCP rows, **534 carry
exactly one fragment** — ours was one of the few with two. Declare the bare
endpoint; the tool identity travels in `extensions.bazaar.info.input.toolName`,
which is where both catalogues read it from anyway.

## Finding 5 — a stale row is invisible from the seller's side

We rotated our receiving address. Every 402, every manifest and every live
challenge advertised the new one. The catalogue kept the old rows — thirteen of
them — and the only way we found out was by querying **by the retired address**,
where they were all still sitting.

The consequence is not cosmetic. A third-party trust-rating site republished our
stale prices from that source, including a route at a third of its live price and
several routes we had retired. An agent budgeting from that page budgets wrong.

**Check your own listing by old address, not just by new.** A row does not
disappear because you stopped using the wallet.

---

## Three things we got wrong, in the order we got them wrong

1. **"The catalogue is stale."** It was not stale — it was **empty**. Both the
   old and the new address returned zero rows. We had been reporting a listing
   problem that did not exist in the form we described.
2. **"The catalogue is one system."** It is two, with different fill mechanisms,
   and we had only ever checked one of them. The second one is where the stale
   data lived.
3. **"The doubled tool name must be our bug."** It was not. Two attempts to
   settle it from our own side — a real CDP settlement, and checking that our
   rows postdated our fix — both looked conclusive and both failed to distinguish
   the causes. One query against a **peer's** live challenge settled it in a
   minute.

The pattern in all three: we reasoned from our own side of the wire. The answers
were on the other side.

---

## What we would tell another seller

- **Settle one real call, then query the catalogue by your `payTo`.** Before
  that, you do not know whether you are listed, and no dashboard will tell you.
- **Query the other catalogue too.** There are at least two, they disagree, and
  a third party may be reading the one you never checked.
- **Compare your declared shape against a peer's live challenge.** If you are
  listed and a neighbour is not, the difference is in the bytes you send. One
  `curl` against a competitor answers in a minute what a day of reasoning did not.
- **Do not put your own bookkeeping keys in a payment requirements object.** A
  facilitator will accept them and a catalogue will silently refuse you.
- **Check by the address you retired.** Rows outlive wallets.

---

## Reproducing this

Every number above comes from one of these, all of which any seller can run:

- the live 402 of any endpoint (`curl` it; the challenge is free);
- `GET /discovery/resources?payTo=…` on both facilitators;
- one settled payment of your own, through each facilitator, then a re-query.

The seller this was written from is
[kristo-intelligence-api.onrender.com](https://kristo-intelligence-api.onrender.com) —
seven paid routes and seven MCP tools on Base, listed in both catalogues.
