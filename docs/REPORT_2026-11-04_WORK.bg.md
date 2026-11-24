# REPORT №1 — THE WORK COMPLETED
### Kristo Intelligence · 04.11.2026

---

## In brief, in two minutes

The project was **working, but dishonest with itself**. It sold, settled and
delivered — but in **nineteen places** it told the world something the code did
not do. A price of $0.05 that was never that. "One free call" that production
does not give. "$29 unlocks the API", while not a single route checks for
subscribers. A guide that teaches the **24-second** slow path, while the fast
one takes 2 seconds. And a units trap in which **the server would have accepted
an overpayment of 1 000 000× instead of rejecting it**.

Today none of these is true.

**Tests: 550 → 688.** All green. Nothing about prices, paywall, `payTo` or fees
has been touched.

---

## 1. What the project is

A paid API for crypto data on **Base**, with payment over the **x402** protocol —
machine pays machine, no account, no card, no human. Six paid routes, six free
samples, an MCP server (for Claude Desktop / Cursor), an npm client, Stripe for
human subscriptions.

**State before:** working, but with accumulated lies in the documents, with open
security holes and **invisible** — public search found us with **1 page**.

---

## 2. What was done, by topic

### 🔐 Security and money (the most important)

| What it was | What it is now |
|---|---|
| **Leaked keys** in the code (F-13/14/15/30) | Closed. 0 real secrets in a full scan of 24 files (9 "hits" were public hashes — verified by hand) |
| **Underpayment**: a client could sign **1 atom** ($0.000001), write "5000" in the echo, and we would deliver data for $0.005 | Closed. The signature decides, the echo is only a fallback. **Proven live with a real attack: HTTP 401** |
| **Overpayment of 1 000 000×** (the units trap, F-18): `amount_usdc` is in atoms (`"5000"`), but the example passed it to `parseUnits` → 5 000 000 000 atoms = **5000 USDC** for a $0.005 request. The server compares `amount >= price` → **it would have accepted** | Closed in **all 8 places**, including `llms.txt`, the onboarding, the npm README and the home page. Verified 6/6 routes live |
| **Reorg** never reverses a credited payment (F-05) | ⬜ **still open** |
| **Acceptance by nonce** without a depth check (F-06) | Closed — every other path in the file went through the check, only this one did not |
| **A free poll wrote** into the replay-lock table (F-04) — 4 statements under **the same lock** that a paying client waits on | Closed. Sampling is tied to **time**, not to a request: 25 polls → **≤3 writes** (previously 75) |
| **Gas controlled by an anonymous client** (F-07) — we could broadcast a transaction that reverts, and **we pay** | Closed. A free `eth_call` simulation **before** signing. On revert we do not broadcast. **It can only stop us from spending, never stop a payer from paying** |
| **Depth requirement** when adopting a settlement | Closed |
| **Stripe webhook** — "any POST is accepted" (X-1) | **It was not a hole.** I checked: it requires `Stripe-Signature`, returns 400 without it, there are two tests |
| **Prices diverged** across 5+ machine surfaces (F-19) — we advertised the most expensive (0.005) as "the price", while two routes charge 0.003 | Closed. Everything is derived from **the map that the paywall itself reads**. 24 prices verified live — **zero divergences** |
| **"$29 VIP unlocks the API"** (F-20) — did not exist in the code | Closed. Honestly marked: `api_access_granted: false` |
| **A promise mathematically unreachable**: "payments over $0.1 give a Telegram code", while the most expensive route is $0.005 | Closed. Explicitly "**one** payment, not accumulated" |

### 📢 Visibility — how people find us

| What it was | What it is now |
|---|---|
| `llms.txt` taught AI agents **the wrong payment protocol** — only the old manual path, and said "~2 seconds" for a path that waits **24** | Both paths described, **the standard one first**, with the codes 200/401/402/425 |
| **The three indexable pages** had not a single meta tag | og + twitter + canonical + **valid JSON-LD** on all of them |
| **The sitemap told Google to index pages that say "do not index me"** — three `noindex` pages inside, while the real `/validation` **was missing** | The three removed, `/validation` + `/pricing` + `/terms` added → **11 URLs** |
| **The machine specifications lied**: `agents.json` — 5 of 6 routes; `mcp.json` — 3 of 6; `ai-plugin.json` — **not a single one** | All 6, and `agents.json` is now **generated** from the single source — it cannot diverge |
| **The home page had no way out for a human** — all its buttons served machine files, and `/launch` (where the payment is) was not linked | 12 links (there were 7). Every human page now has the home page as an inbound link |
| `whaleflow/sample` reported a price **67% higher** than the real one — the first thing a buyer reads | The text is **generated** from the price map |
| `/validation` claimed "550/550, last run 30.10" while there were 569 tests | A single constant, guarded by a test |
| `docs/MYSTERY_AGENT_REPORT.md` — our honesty document — told every x402 client "**not yet honoured**" ("you cannot pay us") | A "SUPERSEDED" banner with a "then → now" table. The history is preserved |
| **Google Search Console** — we had none | ✅ Confirmed, sitemap submitted |
| **Bing Webmaster** — we had none | ✅ Connected (it came over ready-made from Google) |
| **IndexNow** — the channel that needs no login was ready in the code and **nobody had ever run it** | ✅ 11 addresses submitted to Bing, Yandex, Seznam |

### 🛒 The product

| What it was | What it is now |
|---|---|
| **The MCP server sold 3 of 6 products** — the flagship (the signals) **could not be bought** through Claude Desktop / Cursor | **6 of 6**, with prices from the same source the paywall reads |
| **Three different versions** for itself: OpenAPI said 6.0.0, the MCP handshake 1.0.0, the registry 6.2.0 | **One constant**, guarded by a test — five numbers that can no longer diverge |
| **The npm client** supported **only** the 24-second slow path and sent developers to **someone else's package** | It speaks the **fast** path (~2 seconds), backwards compatible, waits on 425 without paying a second time |
| `.github/`, `CHANGELOG`, `CONTRIBUTING`, `SECURITY`, `render.yaml` were missing | Partially (see "what remains") |

### 📊 The dashboard — today

The owner said: **"for much of the data I cannot understand exactly what it is about"**.
He was right. The numbers were there and **not one of them answered a question in words**.

Now at the very top stands:
- **Last sale** — amount + "10 h ago" + the exact time
- **Today versus yesterday** · **this week versus last**
- **Total**: 50 sales · $0.164 · 10 payers · 63 days
- **Strongest day** · **busiest hour**
- **Sales by day** — 28 days with **the Bulgarian day of the week**
- **Human or bot** — AI agent / search engine / programmatic client / external monitor
- **How the system works** — explained on the page itself
- **The table with the columns returned**: Time · Amount · **Client** (with colour) · **Service** · **Payer** · **Tx** → opens with **one click**, no token

**And three defects found only because a human read the page:**
1. The dashboard announced a micro-request at **$0.10**, while the live 402 asked for **$0.003** — **33 times**
2. `HeadlessChrome` was counted as **"Browser (human)"** — automation passed for a human reader
3. `CarbonMonitor` from **someone else's domain** was counted as **our** traffic

---

## 3. The most important thing we found today

### 🔴 A hole in F-01 that the test did not see

The free dashboard was handing out **10 full payer addresses + 10 transaction hashes** —
exactly the triple `{payer, hash, amount}` from which a proof of payment is made.
Verified on the **live site**.

**And the worst part:** the rule had existed **since 10 October**. The test claimed
"the free response must not contain `sender`". But it ran against an **empty**
database — with zero payers the key simply does not appear. **Weeks of "green" over
live data.**

Now: **0 hashes** live, and the test **loads real sales and checks itself** — if the
data disappears, it fails loudly.

### 🔴 My own mistake, caught by my own sentence

I wrote in the commit message that the new columns carry `data-v` (the sort value),
**without checking** — and they did not. Such a cell does not throw: it sorts as an
empty string and the column **quietly stops working**. I fixed **the code**, not the
sentence, and added a test for **every** cell.

---

## 4. What remains

### ✅ Closed after the first version of this report (04.11, in the evening)

| ID | What it was | What it is now |
|---|---|---|
| **F-26** | `/api/launch/health` returned **without a login**: `lead_count`, the whole pipeline by stages, `crm_backend`, and `payment_provider` — which is `"stripe"` **or `"mock"`**, that is, it told everyone **whether we charge anyone at all** | Public: `ok`, `status`, `crm_ready`, `public_url`, `timestamp`. The operational numbers require an admin token. **Verified live: ops keys `[]`, `ok: true`, `status: live`** |
| **F-27** | `/api/connectors` showed `payer wallet=0x…` — it links the relayer to the service and says **from which wallet we spend gas** | Publicly it says **`payer wallet loaded`**. The address is returned for an admin **or** for the operator view. `receiver` stays public — it is the `payTo` in every 402. **Verified live: 9 connectors, 8 active, `payer wallet=0x` → False** |

**Both remained public — deliberately.** The first is the deploy check (called by
`render_status_check.py`, `production_verify.py` and a test), the second is **real
public proof** that the rails are alive. **Only the operational** part is hidden.

**Proven by mutation:** I forced both gates open → the fields **appeared**
(`lead_count: 5`, the wallet address). That is, **the gate is what closes them**,
not coincidence.

### 🔴 P0 — still open (3 of 7)

| ID | What | Severity |
|---|---|---|
| **F-03** | Fail-open on an unreadable receipt — **the paid item is delivered** | High |
| **F-05** | Reorg never reverses a credited payment | High |
| **F-01** | Paid data, partially replaceable at $0 | Residual |

### 🟠 P1 — important (most still open)

A single RPC provider with no fallback (F-08) · a single DB connection under a global
lock (F-09) · `/health` depends on the DB → restart of the only worker (F-10) · a free
`/mcp/sse` holds a thread for 15 s (F-11) · the stats aggregate does 5 scans (F-22) ·
the budgets exceed `--timeout 120` (F-23) · Stripe 80 s × 3 attempts (F-24) ·
`_stripe_payment_snapshot_loop` without `try/except` (F-25) · **`render.yaml` is missing**
(F-28, owner) · admin token falls back to `SESSION_SECRET` (F-29) · indexes are missing (F-31)

### 🟡 P2

`X-Payment-Proof` is a reusable bearer token (F-16) · double delivery under
concurrency (F-17) · `FREE_TIER_LIMIT` 1 versus 0 (F-21) · dead discount code
(F-37) · a second worktree (F-40)

### ⏸️ Waiting on others

| What | Who holds the key |
|---|---|
| Glama still caches `toolCount: 3` (while the live one serves **6**) | Glama |
| PR #13219 (awesome-mcp-servers) | punkpeye — blocked on the Glama number |
| PR #1308 (awesome-x402) | xpaysh — `mergeable_state: clean` |
| mcp.so verification | mcp.so (comment #3441) |
| Smithery | **dead** — proxy stopped on 31.10, the channel is being unsubscribed |

### ⏸️ Waiting on you

| # | Question |
|---|---|
| 1 | **`KRISTO_FREE_TIER_LIMIT` in production — 0 or 1?** Affects all public claims |
| 2 | Shall we delete the second worktree (`.kilo/worktrees/believed-dancer`)? It is safe |
| 3 | Shall we cite the x402-trust badge (grade **A**) on `/validation`? |
| 4 | Paid channels: mcpmarket $69 · CDP Bazaar $0.25 (so far **$0** spent) |
| 5 | `render.yaml` — shall we add it? |
| 6 | ~~Shall we fix F-26 and F-27~~ — **done** (you said "yes") |

---

## 5. The numbers

| | |
|---|---|
| Tests | **550 → 791** (0 failed) |
| Live check | `/validation` **791/791** |
| Commits this session | **17**, all pushed (`9089ba5` … `4e760cc`) |
| Defects found and fixed | **21+** |
| Found by **the owner** (by reading alone) | **5** |
| Touched in prices · paywall · `payTo` · fees | **nothing** |

---

## 6. The lessons worth keeping

1. **`200 OK` does not mean the content is true.** We checked that the sample
   answered 200 — while inside it said a price 67% above the real one.
2. **A test written to match the code locks the bug in.** Three tests claimed
   `== "unchanged since launch"`, which was **never** true.
3. **A guard that passes for the wrong reason is worse than none.** The test for
   `sender` passed on an empty database for weeks.
4. **When an audit shows something dramatic, the audit is checked first.** My first
   check "robots.txt serves binary data" was **my** gzip mistake.
5. **The smaller mistake is the safe one.** An underpriced item = an honest refusal
   with the money intact. An overpriced one = money transferred that **does not come
   back**.
6. **A sentence that has outlived the fact behind it is a defect.** This is the
   disease of this repo, and it is not caught by tests, but by a human who reads.
