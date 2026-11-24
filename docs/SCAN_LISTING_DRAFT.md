# SCAN_LISTING_DRAFT — listing application for x402scan (draft)

> LOCAL DRAFT — nothing has been published/submitted. Research + numbers + ready
> text. On submission the text is translated into EN and filed as an issue in
> `Merit-Systems/x402scan` with the title `[Listing Request] …`.
> Research date: 08.10.2026.

---

## 1. The format — what we found

### Where to submit
* **The practice (per the others):** GitHub issue in `Merit-Systems/x402scan` with
  the title `[Listing Request] <Name> — <brief>`. 44 open ones; current
  examples: **#1268** (Automaton-Sovereign), **#1249** (fitze-x402-seller),
  **#1244** (Livecheck).
* **The official path (README → "Add Resources"):**
  https://www.x402scan.com/resources/register — a URL is submitted; if it returns
  a valid x402 schema, the resource is added to the list automatically.
* **Validation before submission (per docs/DISCOVERY.md):**
  `npx -y @agentcash/discovery kristo-intelligence-api.onrender.com -v`

### Template / rules in the repo — **NONE**
* `.github/` contains **only** `workflows/` and `PULL_REQUEST_TEMPLATE.md` — and it
  is **only for new facilitators** ("DELETE THIS TEMPLATE IF YOU ARE NOT
  ADDING A NEW FACILITATOR!"). **There is no issue template for listing.**
* **There is no CONTRIBUTING.md.** The rules are in the README (section
  *Contributing*) and in `docs/DISCOVERY.md` ("x402scan Discovery & Registration
  Spec" — 180 lines).

### De facto format of a Listing Request (per #1244/#1249/#1268)
```
Title: [Listing Request] <Name> — <one sentence> (x402 v2, Base)
Origin:   <base URL>
Spec:     <openapi.json URL>
Network / asset: Base mainnet, USDC, x402 exact
Discovery: <URLs of the discovery documents>
What it does: 1–3 sentences
Route | Price   (table)
Ask: <what we want — e.g. "confirm that the paid routes are indexed")
```
Notes from the examples: #1268 explicitly says "No accounts, no API keys, no KYC"
and gives how to do a free test-probe; #1244 gives "Public stats at /stats".

### What they look at (docs/DISCOVERY.md — the indexing spec)
* **OpenAPI-first** (recommended): `/openapi.json` with `x-payment-info` on every
  paid operation (`protocols: ["x402"]`, `price` fixed/dynamic), 402 in
  `responses`, security schemes; optionally `x-discovery.ownershipProofs`.
* Fallback: `/.well-known/x402`; endpoint-only (402 + parseable `accepts`,
  non-empty, Bazaar input schema, **amount in token atomic units**).
* **Common reasons for rejection:** 404/405/429 instead of 402; empty `accepts[]`;
  missing input schema; amount in dollars instead of atomic units; request rejected
  by validation BEFORE the 402 challenge.

### Our discovery surface (verified live, 08.10)
| Path | Status |
|---|---|
| `/openapi.json` | 200 ✓ |
| `/.well-known/x402` | 200 ✓ |
| `/llms.txt` | 200 ✓ |
| `/api/mcp/manifest` | 200 ✓ (MCP: `POST /mcp`, `/mcp/sse`) |
| `/routes.md` | 404 — not cited |
| `/.well-known/agent-card.json` | 404 — not cited |

The 402 challenge is v2 (`Payment-Required` base64 header), `scheme: exact`,
`network: eip155:8453`, `amount: "3000"` (atomic units ✓), Bazaar declaration
in `extensions.bazaar` ✓.

---

## 2. Our numbers (30 days, from the `/api/dashboard/data` dashboard)

| Number | Value |
|---|---|
| **Paid calls** (payment accepted) | `/api/v1/signal` — **9** · `/api/v1/whaleflow` — **3** (12 total) |
| **Unique payers** | **5** wallets (2 with a repeat purchase — retention 2/5) |
| **Bazaar listings** | **2** |

* **Price:** 0.003 USDC/call for both endpoints
* **URLs:**
  * https://kristo-intelligence-api.onrender.com/api/v1/signal
  * https://kristo-intelligence-api.onrender.com/api/v1/whaleflow
* **payTo:** `0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f` (Base, USDC
  `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, scheme `exact`, x402 v2)

### How we count (for us only — not part of the text)
* "Paid calls" = rows in `payment_guards` (the payment unlocked
  delivery). 13 total, of which 1 is `/api/bot-status` (out of scope) → 12.
  All are in the last 30 days (the service has been live since 06.09, 32 days).
* 2 of the 12 (06:13, 08.10) have an empty delivery because of the delayed deploy —
  that is why we write "payment accepted", not "payment → delivery". The numbers
  9/3 are confirmed against the DB.
* "Unique payers" = `track_record.paying_strangers` from the dashboard (5). It
  includes the demo wallet `0xe50c…5763` (ours, `demo_sponsored_pay.py`) — if
  someone asks "how many are external", the honest answer is 4. The transactions
  are real USDC transfers on Base and are publicly verifiable, so "5 wallets
  paid" is true and verifiable.
* Payments from the known probing/review infrastructure are also real external
  payments (class `sampler`/`canary` in the dashboard) — they are counted above.

---

## 3. Ready text of the application (English)

**Title:**
`[Listing Request] Kristo Intelligence — live DeFi signals & whale-flow API (x402 v2, Base)`

**Body:**

> **Origin:** https://kristo-intelligence-api.onrender.com
> **Spec:** https://kristo-intelligence-api.onrender.com/openapi.json
> **Network / asset:** Base mainnet (eip155:8453), USDC
> `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, x402 v2 `exact`
> (payment-required base64 header, `x-402-version: 2`)
> **payTo:** 0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f
> **Discovery:** /openapi.json · /.well-known/x402 · /llms.txt ·
> /api/mcp/manifest (MCP transports: POST /mcp, /mcp/sse)
>
> **What it does:** Kristo Intelligence sells AI agents machine-readable
> crypto intelligence on demand: a live DeFi trading signal (action, confidence,
> one-line rationale for ETH/ONDO/KAITO/DEGEN), whale tracking
> (USDC transfers ≥ $5M on Base with labeled payers), cross-DEX arbitrage
> opportunities and rug checks. No accounts, no API keys, no KYC —
> pay per call in USDC on Base.
>
> **Routes and prices:**
>
> | Route | Price |
> |---|---|
> | GET /api/v1/signal — live DeFi signal | 0.003 USDC |
> | GET /api/v1/whaleflow — whale-flow feed (transfers ≥ $5M) | 0.003 USDC |
> | GET /api/arb/opportunities — cross-DEX arbitrage | 0.005 USDC |
> | GET /api/bot-status — bot health | 0.005 USDC |
> | GET /api/sales — sales statistics | 0.005 USDC |
> | GET /api/stats — API statistics | 0.005 USDC |
>
> **Activity (30 days, public dashboard at /dashboard):**
> * paid calls: `/api/v1/signal` — 9, `/api/v1/whaleflow` — 3
> * unique payers: 5 (4 external + 1 our demo)
> * Bazaar listings (PayAI): 2
>
> Payments are one-time per EIP-3009 nonce, payment verification is
> fail-closed (invalid proof → 401, never delivery), and every sale is
> verifiable against the chain's Transfer logs. 471 automated tests.
>
> **Ask:** please confirm that the paid routes are indexed correctly
> (OpenAPI-first discovery + 402 challenge are public on the origin), and say
> if there is an additional requirement for searchable/featured visibility — we
> will cover it.

**Before submitting (checklist):**
1. Translation of the text above into EN.
2. `npx -y @agentcash/discovery kristo-intelligence-api.onrender.com -v` —
   it should come out clean (OpenAPI-first).
3. Submission: issue in `Merit-Systems/x402scan` + (optionally) registration via
   https://www.x402scan.com/resources/register.
4. The registration/listing should be added to `docs/WATCH_LIST.md` for tracking.
