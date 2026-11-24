# DISTRIBUTION STATUS — launching Kristo Intelligence into the x402 ecosystem

*Updated: 2026-09-30 (Smithery → PUBLISHED, slug -v4) · 2026-09-22 (listing
channels: Glama + PR #13219) · Server:
https://kristo-intelligence-api.onrender.com (Render, live)*

---

## 1. Directories and marketplaces

| Platform | Status | Details |
|---|---|---|
| **x402scan** | ✅ REGISTERED | 11 resources, 3 paid routes. Canonical x402 v2 challenge (CAIP-2 `eip155:8453`, atomic-unit amounts, bazaar schema) — validated against `@agentcash/discovery` 1.7.5. |
| **PayAPI Market** | ✅ LIVE + 2 VERIFIED ROUTES | 4 independent paid canaries settled on-chain (2× $0.005 /api/stats + 2× $0.003 /api/v1/signal; last: tx 0x0cc98ef9…). Signal verification row now notes price_usd + reasoning in paid body. Listed price correct. **Chet replied (03.09):** there is no paid featured slot/newsletter — distribution = live catalog + agent search + the listing page + occasional X posts from @ParkerChet when something new is verified ("because the route is useful, not because a slot was bought"). The invitation blurb on file → **SENT AND ACCEPTED (03.09, 19:29 UTC)**: "Blurb is on file. Listing stays. No extra fee and no promised post. If I mention the route on X it will use this copy." The thread is closed — no further emails to Chet (only a brief thanks). Blurb text: OUTREACH_KIT.md §6. |
| **nohumans.directory** | ✅ 3× VERIFIED | Listings active. |
| **BlockRun (data source)** | 🟡 NEGOTIATIONS (03.09) | The founder @1bcmax asked 2 due-diligence questions (consistency/quality + value against x402) — answered at 22:06 with the settlement-proofs + curated discovery reach arguments. Awaiting a listing decision; follow-up on Day 5 if he stays silent. |
| **Glama** | ✅ LIVE + CLAIMED (connectors **rated A**, servers **rated A**) | Two live listings: (1) `/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence` — Hosted, health-checked, rated **A**; (2) `/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6` — claimed (glama.json), **released**, badge **"MCP server rated A"**, 3 tools with prices + remotes (`/mcp`, `/mcp/sse`). 🎫 **Ticket #130688574** (initial) + 🎫 **Ticket #135407945** (22.09, Frank joined in on his own after the build errors): the server is registered under "Runs from source" by mistake; the correct type is **"Hosted endpoint"** (our `/mcp` on Render) → a type change/reset was requested, **awaiting a reply**. The badge/tools/release are not lost — the type change only stops the broken build path. |
| **MCP Registry / PulseMCP / mcp.so** | ⏳ VIA PayAPI | PayAPI automatically publishes approved listings to these channels. |
| **Smithery** | ✅ **PUBLISHED 2026-09-30** | https://smithery.ai/server/hristovdimitri2/kristo-intelligence-v4 — **score 76/100**, **3/3 tools detected**; slug "-v4" because the base "kristo-intelligence" was taken; description + homepage + GitHub link filled in; **Unlisted: no**. |
| **awesome-x402 (PR #1308) / awesome-mcp-servers (PR #13219)** | ⏳ Open PRs | **#13219 (21.09):** the badge was added in the format Frank requested (servers `OWNER/REPO`, right after the link) → the bot label `missing-glama` dropped off on its own, `has-glama` remains; awaiting a merge from Frank. #1308 (awesome-x402) — no review. Details: LISTING_CHANNELS_AUDIT.md |

## 2. Paid endpoints (all verified live on 2026-08-30)

| Endpoint | Price (USDC) | Atomic units | x402 v2 challenge |
|---|---|---|---|
| `GET /api/stats` | 0.005 | `5000` | ✅ 402, CAIP-2 `eip155:8453`, `extra.name = "USD Coin"` |
| `GET /api/bot-status` | 0.005 | `5000` | ✅ same |
| `GET /api/arb/opportunities` | 0.005 | `5000` | ✅ same |
| `GET /api/sales` | 0.005 | `5000` | ✅ same |

- **Receiver (Base USDC):** `0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844`
- **USDC contract:** `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- **Payment rails:** (1) **the standard x402** — a signed EIP-3009
  `transferWithAuthorization`, submitted in `PAYMENT-SIGNATURE` (v2; `X-PAYMENT` for
  v1 clients); verify + settle through the x402 facilitator
  (`services/connectors.py`), without waiting for blocks. Preferred. (2) **smart
  wallets and exchange withdrawals** —
  `X-Payment-Proof: base64url(JSON({payer, transaction_hash, amount_usdc}))`,
  self-describing, but requires **12 confirmations (≈24 s)** before the data.

## 3. Discovery links (all free, live)

| Link | Status |
|---|---|
| `/.well-known/x402` | ✅ 200 — version 1, resources, ownershipProofs |
| `/openapi.json` | ✅ 200 — OpenAPI 3.0.3, x-payment-info per operation, x-discovery.ownershipProofs |
| `/mcp/sse` | ✅ live — MCP SSE transport (Claude Desktop / Cursor) |
| `/api/mcp/manifest` | ✅ 200 — MCP/x402 manifest |
| `/api/v1/quickstart` | ✅ 200 — copy-paste first-call snippets (curl/Python/Node) |
| `/api/connectors` | ✅ 200 — connector registry (9 connectors, 8 active) |
| `/favicon.ico` | ✅ 200 — SVG icon |

## 4. Mystery Agent audit (23/23 PASS)

Independent adversarial buyer simulation (`scripts/mystery_agent.py`) against the
live server:
- Discovery from scratch: 6/6 ✅
- Challenge validation (agentcash/x402scan canon): 3/3 ✅
- Price sanity (atomic units, payTo ≠ burned address): 4/4 ✅
- Anti-fraud (synthetic proof → rejected 401): 2/2 ✅
- Standard-client compatibility probe: 2/2 ✅ (documented gap → unlocked in the
  EIP-3009 rail)
- Free tier: 6/6 ✅

Full report: [MYSTERY_AGENT_REPORT.md](MYSTERY_AGENT_REPORT.md)

## 5. Registration history in x402scan

1. `0 valid resources` — descriptive challenge format
2. `x402 v1 detected — migrate to v2` — canonical v1 → migration to v2
3. `No valid x402 response` — missing bazaar schema → added
4. ✅ **11 resources, 0 errors** (commits `ebb993d`…`d6eeb12`, 108/108 tests)

## 6. Open action items

- [x] Render API keys rotated (02.09): the old keys compromised in chat deleted, a
  new `rnd_VYr1…` stored locally in secrets/render_api_key.txt (gitignored) —
  verified via the API
- [x] BlockRun contact (02.09): founder @1bcmax on Telegram — endpoint + on-chain
  proof sent
- [x] Outreach Day 1 (02.09): GitHub Issue #1 in AnthonWinther/Trading_bot
  (template a)
- [ ] PayAPI approval → edit of the listing price $0.10 → $0.005
- [ ] BlockRun reply → integration agreement (data-tool contract / rev-share)
- [ ] MCP Registry submission (via PayAPI approval or directly)
- [ ] Outreach campaign: 1 personalized message/day (see
  [OUTREACH_KIT.md](OUTREACH_KIT.md)) — Day 2: Telegram crypto-dev channel
  (template b)
- [ ] CoinGecko demo key: a free key from coingecko.com → Render env
  `COINGECKO_API_KEY` — eliminates the 429s that are the root of the
  stale/bulletin warnings (the code already supports it: `x-cg-demo-api-key`
  header)
