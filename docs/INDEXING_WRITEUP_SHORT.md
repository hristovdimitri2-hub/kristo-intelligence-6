# Getting an x402 endpoint indexed — short version

The long version is `INDEXING_WRITEUP.md`. This is the version for a forum post:
five findings, our own numbers, and the mistakes we made getting them.

---

## The post

We run seven paid HTTP routes and seven MCP tools on Base
([kristo-intelligence-api.onrender.com](https://kristo-intelligence-api.onrender.com)).
Getting them listed took longer than building them, and the reasons were not the
ones we assumed. Five things we measured, all reproducible from a free `curl`:

1. **There are two catalogues, and they fill by different mechanisms.** PayAI
   and CDP's Bazaar disagree about what we are. Query both, by `payTo`.

2. **The shape of `resource` decides whether PayAI indexes you.** A string URI
   and an object (`resource.url`) are both legal; only one gets listed.

3. **Two keys of our own stopped indexing dead.** `extra_name` /
   `extra_version` in the requirements object — our bookkeeping — were accepted
   by the facilitator and silently refused by the catalogue. The settlement
   succeeded; the row never appeared.

4. **The catalogue appends the tool name itself.** Declaring `/mcp#tool` yields
   `/mcp#tool#tool`. Declare the bare URL; the identity belongs in
   `extensions.bazaar.info.input.toolName`.

5. **A stale row is invisible from the seller's side.** Rows outlive wallets.
   Check by the address you retired, not the one you use.

Two things we got wrong first: we called the catalogue *stale* when it was
empty, and we called it *one system* when it was two. Both times we reasoned
from our side of the wire; the answers were on the other side.

**Our numbers, so nobody has to guess our size.** 171 settlements, $1.883 total.
Of that, 122 settlements and $1.685 are our own key and canaries. External
customers: 12 payments, $0.054. That is the honest figure, and it is why we
write this down rather than quote the total.

If you are listed and a neighbour is not, the difference is in the bytes you
send. One request against a competitor's live challenge answers in a minute what
a day of reasoning did not.
