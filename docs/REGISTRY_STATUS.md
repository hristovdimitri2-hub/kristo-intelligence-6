# Measured-health registries: where we stand, measured 19.11.2026

The question came from `#tsc-public` on 19.11: the foundation's ecosystem page is
retired, PRs to listing pages close without merge (Roberto Martins' #356 has been
open since 27.09), and naxytra asked where a live x402 seller can be listed today.
Roberto's proposal was a registry indexed by **measured health** — uptime, lint
score, on-chain verified settlements — rather than by PR review.

**The answer is that it already exists, in pieces, and we are in most of them.**
What follows is what each one says about us *today*, read from their own public
APIs, plus the one artefact that is stale everywhere.

Everything marked *(read)* was fetched live on 19.11.2026. Everything marked
*(second-hand)* comes from web research and is cited with its source in the
research thread, not verified by me.

## What each index says about us today

| Index | How it fills | What it says about us *(read)* | What it reads |
|---|---|---|---|
| **Official MCP Registry** (registry.modelcontextprotocol.io) | self-publish via `mcp-publisher`; no review | 4 versions, status active; **latest is 6.2.0 from 04.11** | `server.json` + GitHub namespace proof |
| **Glama** | hourly auto-import from the official registry, no manual review *(second-hand)* | not checked directly | the registry entry |
| **x402register.com** | crawl of CDP Bazaar; hourly probes; free to be rated | grade **A**, score **90.7**, rank **2668**, availability 100 %, median 576 ms, 168 probes | Bazaar declaration; probes every hour |
| **x402lint.dev** | scan-only, no registration | grade **B**, score **89** — 17 pass, 4 warn, **2 fail**; last scanned **04.11** | 25 checks: 402 validity, HEAD-does-not-settle, OpenAPI x402 conventions, `.well-known`, llms.txt, agent-card, on-chain standing |
| **x402-list.com** | submit + Bazaar/x402scan import; 5–15 min uptime probes | `payment_ready: true`, `verified: false`, compliance **A 14/14**, uptime 100 %, **endpoint_count 6**, `price_max_usd 0.01` | live 402 handshake; on-chain volume attributed by facilitator settler |
| **Roundhouse** (roundhouseai.io) | no application — settlement to our `payTo` is indexed regardless | **10 rows**; `concentrated: true`, `top_payer_share_30d 0.9581` | on-chain settlements joined to the discovery catalogue |
| **x402-trust.com** | auto-discovery or free submit; claim 4/4 complete | **all seven paid routes are grade B now** (76.8–78.7), `/mcp` 65.4, `/api/v1/verify-seller` 69.4; **`/api/stats` carries an error flag → recommendation `avoid`**; free endpoints score 30.2 / grade `?` | probes + on-chain USDC settlements |
| **Lumière PayCheck** | grades from real paid test calls | we serve `/.well-known/paycheck.json` for it | `paycheck.json` `payTo[]`, then 30-min probes |
| **Akari / 402 Index / x402dash / PayAPI Market / Agentic.Market** | register, scan or first settlement | not checked | 402 quality, latency, `.well-known` presence |

## Finding 1 — every index carries our October numbers, because our October numbers were the last ones published

The clearest example:

* the **official MCP Registry** holds `6.2.0`, published 04.11, advertising
  **6 tools** and `min_usd 0.003 / max_usd 0.005` *(read)*;
* the **same version in our repo** carries **7 tools** and `$0.005–$0.050` — it was
  regenerated on 16.11 and never republished. `scripts/build_registry_server_json.py
  --check` says `OK server.json matches the price source` *(read)*.

Versions are immutable at the registry, so republishing needs a **new** version,
not an edit. Until then, Glama and API Tracker — which import from there — carry
the six-tool, $0.003 picture.

`x402-list` is the same story one step removed: `endpoint_count 6`,
`price_max_usd 0.01`, `distinct_price_count 2`, and its description text still
reads `$0.003-0.005 per call` — that is *our own October submission*, echoed back
*(read)*.

`Roundhouse` holds eight MCP rows under the **retired** wallet `0xd4cd…d08f` at
0.003/0.005/0.1, including one doubled-fragment row
`/mcp#get_whale_flow#get_whale_flow` *(read)*. Rows outlive wallets; this is the
same finding as #5 in `docs/INDEXING_WRITEUP.md`, now visible on someone else's
index.

**So the registries are not the problem.** They measured what we last told them.

## Finding 2 — a third party now publishes our concentration, and it is right to

Roundhouse reports `top_payer_share_30d: 0.9581` and `concentrated: true` on our
whale-flow row, with `verified_volume_usdc_30d: 1.719` — a figure that is almost
entirely our own key exercising the rail *(read)*. Their `verified_x402` grade is
about *who relayed the settlement*, not about who paid.

That is the self-dealing problem, machine-readable, on an index we do not control.
Our answer already exists and is the right one: `/api/v1/settlement-classes`
publishes the split from on-chain behaviour (122 own-key / 17 verifier / 20 crawl /
12 external, $1.883 total, $0.054 external) *(read)*. It needs no counterpart in
the registry world — nothing consumes it — but it is what makes our numbers
checkable when theirs are unflattering.

## Finding 3 — three of our own files understated the catalogue (fixed today)

`/.well-known/x402.json` said `"These are the 6 live x402 endpoints"` above a list
of **seven**; `/validation` said `"six routes across two tiers"` beside a heading
that said `7 live x402 routes`; `llms.txt` pointed at `the same six paid routes`.
All three are now **derived** from the route table instead of typed, so they cannot
drift again.

## Finding 4 — x402-trust has downgraded us to B and flagged `/api/stats` "avoid", and our own page still advertises A

This is the finding that matters most, and it corrects an earlier reading of our
own page *(read live, 19.11)*:

| our route | x402-trust today |
|---|---|
| `/api/arb/opportunities`, `/api/sales`, `/api/bot-status` | **B** 78.7 |
| `/api/stats` | **B** 78.3 — **1 error flag, 1 warning → recommendation `avoid`** |
| `/api/v1/signal` | **B** 77.7 |
| `/api/v1/whaleflow` | **B** 76.8 |
| `/api/v1/verify-seller` | **B** 69.4 |
| `/mcp` | **B** 65.4 |
| free endpoints (`/health`, `/openapi.json`, `/.well-known/x402`, `llms.txt`, …) | 30.2 / grade `?` |

Not one paid route is grade A any more. **`/api/stats` — our cheapest and most
probed route — is recommended `avoid`**, and the flag detail is behind a $0.005
paid report. Their published model
([leaderboard JSON](https://x402-trust.com/trust/leaderboard)) is
`0.45 × technical-reliability + 0.30 × spec-compliance + 0.25 × economic-reputation`,
with technical-reliability itself `0.45 × uptime + 0.40 × observed-age + 0.15 × latency`.

### We bought the report on 19.11 — and the `avoid` is our own receiver rotation

`_forensics/pay_x402trust_stats.py` (dry-run by default) paid the $0.005 and the
answer is unambiguous:

```
score 78.3   grade B   recommendation avoid   confidence 0.95
subscores  technical-reliability 91.2 · spec-compliance 98.3 · economic-reputation 31.2
breakdown  uptime 0.976 · compliance 0.976 · latency 0.674 · age 0.929
           · activity 0.417 · stability 1.000
flags      provider-verified (info)
           payto-changed-recently (ERROR)
           shared-payto-wallet (warn)
```

> `payTo changed 2 day(s) ago (0xd4cdA900… → 0xB4FcF8ef…) — possible endpoint
> hijack; verify before paying.`

**That is our own deliberate rotation of the receiver, read as a possible
hijack.** The change was ours, it was made on purpose, and we publish it in
`/.well-known/paycheck.json` — a file Lumière PayCheck reads and x402-trust does
not. The second flag says the wallet is "shared with 12 other endpoint(s)": those
twelve are our own routes behind the same receiver.

So `avoid` on our most-probed route is **not a product defect**. It is an
observed change with no declared intent, and it ages out on its own. The two
subscores that are genuinely ours are:

* **latency 0.674** — 969 ms average, measured from a single EU vantage point,
  which includes the network distance to Render's region. Structural, not a bug.
* **activity 0.417** — wallet-level settlement: $0.85 and 4 distinct payers over
  30 days, most of it our own key. That one is the real demand problem, and no
  registry flag will fix it.

The report also offers a better-scored alternative in our own category:
`x402stats.io/api/x402/stats`, grade A, 84.7.

**This is a standards gap worth raising, not a bug to fix:** a legitimate key
rotation is indistinguishable from a hijack to every index that does not read a
rotation declaration. We already serve one convention's file; no one reads it.

**Two things on our side are now wrong because of it:**

1. `/validation` still publishes a **dated 04.11 copy showing grade A** on six
   routes. The page does say the linked pages are authoritative, but the typed
   copy is the part people read, and it now flatters us.
2. Our `/validation` **misdescribes their methodology** — it prints "technical fit,
   transparency, ecosystem presence and operational confidence", a four-part model
   that appears nowhere on their site. We are quoting a third party's scoring model
   incorrectly on our own trust page.

Also still indexed under us by x402-trust: **four `kristo-intelligence.vercel.app`
rows, grade F, `delisted: false`** — the retired host is gone from CDP (§66) but not
from here, and it is the only F next to our name.

## Finding 5 — two more indexes we are probably absent from

`x402-list.com/best` (generation-3 scoring) and **Agent402** (`/api/index`,
`/api/leaderboard`, a health-aware router that ranks on match → health → distinct
payers → price) are independent coverage opportunities, not aggregators. We hold
`payment_ready` on x402-list but have never been `verified` there, because that
status requires them to have paid us and seen delivery *(second-hand)*.

## What NOT to build

The research checked whether any index reads a self-published scorecard or honesty
file. **None does** *(second-hand, but consistent across the surveyed indexes)*:

* `/scorecard.json` — nothing reads it;
* `/health` — only the indexes' *own* health endpoints are read, not ours;
* `/receipts` — nothing reads it;
* `/.well-known/honest-revenue.json` — the only reachable artefact of that name is
  `councilof.ai`'s own self-published file, and no registry consumes it.

So the "publish a scorecard so a registry indexes us" idea is dead on arrival. The
artefacts that *are* read are the ones we already serve: `/openapi.json`,
`/.well-known/x402`, the 402 itself with Bazaar metadata, `/.well-known/paycheck.json`,
`/.well-known/x402-trust.txt`, llms.txt, agent-card.

`/.well-known/honest-revenue.json` remains worth considering **only** as a
human-facing convention — it is Roberto's, the channel values it, and nobody
machine-reads it yet. That is a reason to raise it in a working group, not to
implement it today.

## What we should do, in order

1. **Done, 19.11 — the $0.005 x402-trust report for `/api/stats` is bought.** The
   `avoid` is our own receiver rotation read as a hijack (above). Nothing to fix in
   code; it decays. What it did buy us is a standards argument, see item 6.
2. **Fix `/validation`'s third-party block.** Two defects, both ours: a dated 04.11
   copy advertising grade A while the live grade is B/avoid, and a description of
   x402-trust's methodology that is not their methodology. The fix is to stop
   typing what somebody else measures.
3. **Republish `server.json` as 6.3.0.** Requires a fresh `mcp-publisher login
   github` (the stored token at `~/.config/mcp-publisher` is expired), then
   `publish`. This fixes Glama and API Tracker at once, and it is blocked on the
   owner's browser. The binary `_tools\mcp-publisher.exe` is gone and must be
   fetched again (~20 MB).
4. **Refresh the x402-list submission.** Their copy of us is our October text:
   `endpoint_count 6`, `price_max_usd 0.01`, "$0.003-0.005 per call".
5. **Buy the $0.05 x402lint rescan** to learn what the 2 fails and 4 warns are —
   the free cached report is older than 24 h and returns `no_fresh_report` *(read)*.
6. **Take two negative results to `#wg-domain-discovery`.** First: no index reads a
   self-published honesty file, so the artefact we already built
   (`/api/v1/settlement-classes`) is a worked example nobody can consume. Second,
   and sharper: **a legitimate `payTo` rotation is indistinguishable from a hijack**
   to any index that does not read a rotation declaration — we serve one
   convention's file and x402-trust, which flagged us `error` for exactly this,
   does not read it. Both are standards gaps, not code we should write.

## Registering on x402-list `/best` and Agent402?

**x402-list: we are already in it** — `status online`, `payment_ready: true`,
compliance A 14/14, uptime 100 % *(read)*. What we are not is **`verified`**, and
that status cannot be bought or submitted: it appears when *they* pay one of our
routes and it delivers. So the action there is not registration, it is fixing the
stale metadata in item 4 and then being worth probing.

**Agent402: yes, worth one free POST.** `POST https://agent402.tools/api/index/register`
with our origin *(second-hand)* — free, no review, and it is the only index found
that carries `supports_x402` as a first-class filter rather than a description
string. That is the closest thing to a *paid-API* directory, which is our actual
category.

Neither is urgent, and neither costs anything to try. The honest ordering is: fix
our own stale files first, because every index above is currently quoting them
back at us.

## What this does not change

We are already indexed and already graded: x402register A/90.7, x402-list
compliance A 14/14, the official MCP Registry active, x402-trust verified and
listed on 18 endpoints. The measured-health registry Roberto proposed is not
missing — it is eight of them, none of which requires a PR. Nothing here argues
for spending money on placement.

The one number worth carrying away: **x402-trust scores us B on every paid route
and `avoid` on `/api/stats`**, while the two indexes that read our own
declarations score us A. When a measured index disagrees with a declaration-based
one, the measured one is the one to believe.
