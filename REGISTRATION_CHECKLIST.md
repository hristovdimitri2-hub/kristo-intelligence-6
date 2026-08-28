# Registration Checklist — Kristo Intelligence 6

**Status:** Application is ALREADY LIVE on Render. This checklist covers ONLY the marketplace registrations (x402scan + PayAPI.market) — no deployment needed.

**Live URL:** `https://kristo-intelligence-api.onrender.com`

**Estimated time:** 10 minutes (2 min x402scan + 5 min PayAPI + 3 min verification)

---

## ✅ Pre-verified (already working)

These endpoints were tested on 2026-08-28 and are LIVE:

| Endpoint | Status | Notes |
|---|---|---|
| `https://kristo-intelligence-api.onrender.com/health` | ✅ 200 OK | `status: ok`, blockchain ready, chain_id 8453 |
| `https://kristo-intelligence-api.onrender.com/.well-known/x402` | ✅ 200 OK | x402scan-compatible format, dynamic pricing $0.005 |
| `https://kristo-intelligence-api.onrender.com/openapi.json` | ✅ 200 OK | Has x-payment-info, x-discovery.ownershipProofs |
| `https://kristo-intelligence-api.onrender.com/api/stats` | ✅ 402 (after free tier) | Returns payment headers |
| Fee receiver address | ✅ Correct | `0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f` |
| Price per call | ✅ Dynamic | $0.005 USDC (config-driven, not hardcoded) |

**No deployment action needed.** The app auto-deploys from GitHub `main` branch on every push.

---

## 📝 Registration 1: x402scan (2 minutes)

x402scan is the main ecosystem explorer for x402 APIs. Registration is **free and automatic**.

### Steps

1. Open: **https://www.x402scan.com/resources/register**
2. In the URL field, enter exactly:
   ```
   https://kristo-intelligence-api.onrender.com
   ```
3. Click **Submit** / **Add Server**

### What x402scan does next (automatic, 1-5 min)

1. Fetches `https://kristo-intelligence-api.onrender.com/openapi.json`
2. Parses `x-payment-info` per paid operation
3. Parses `x-discovery.ownershipProofs` for ownership verification
4. Probes each paid endpoint (`/api/stats`, `/api/sales`, `/api/bot-status`)
5. Verifies the 402 challenge response is parseable
6. Registers your server in the public directory

### Verify registration

After ~5 minutes, search for your API:
1. Go to https://www.x402scan.com
2. Search: `Kristo Intelligence`
3. Your API should appear with 3 paid endpoints

If it doesn't appear, the most common reasons are:
- `Expected 402, got 404/405` — endpoint URL wrong (yours are correct)
- `parseResponse: Accepts must contain at least one valid payment requirement` — 402 challenge malformed (yours is correct)
- Discovery fetch timeout — retry the submission

---

## 📝 Registration 2: PayAPI.market (5 minutes)

PayAPI.market has 89 live APIs and existing AI agent traffic.

### Steps

1. Open: **https://payapi.market**
2. Click **"List your API (free)"** (top right)
3. Fill in the form with these EXACT values:

| Field | Value |
|---|---|
| **API Name** | `Kristo Intelligence API` |
| **Description** | `AI-powered DeFi trading signals and crypto market intelligence on Base. Real-time prices for ETH, ONDO, KAITO, DEGEN, risk-managed portfolio recommendations, and on-chain sales history. Pay-per-call with USDC via x402 protocol.` |
| **Category** | `Finance` / `Crypto` / `DeFi` |
| **Base URL** | `https://kristo-intelligence-api.onrender.com` |
| **Pricing** | `$0.005 per request` |
| **Receiver wallet** | `0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f` |
| **Chain** | `Base (chain_id 8453)` |
| **USDC contract** | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| **MCP endpoint** | `https://kristo-intelligence-api.onrender.com/mcp/sse` (if asked) |

4. Submit the form

### What PayAPI.market does next (automatic, up to 24h)

1. Makes a test call to your endpoints
2. Pays 0.005 USDC from their own wallet to your receiver address
3. Verifies the payment is detected on-chain
4. Retries the endpoint and verifies access is granted
5. If successful — awards the "x402 verified" badge

### Featured tier (optional, $49/month)

After basic registration, you can upgrade to Featured for:
- Gold badge on your listing
- Always-first ranking in search results
- Priority inclusion in MCP tool manifest

**Recommendation:** Start with Free tier. Upgrade to Featured only if you have <5 paid calls/day after 14 days.

---

## ✅ Post-registration verification (3 minutes)

After completing both registrations, verify:

```bash
# 1. Health check (should be 200)
curl -s https://kristo-intelligence-api.onrender.com/health | python3 -m json.tool

# 2. x402scan discovery (should be 200 with version: 1)
curl -s https://kristo-intelligence-api.onrender.com/.well-known/x402 | python3 -m json.tool

# 3. OpenAPI spec (should have x-payment-info)
curl -s https://kristo-intelligence-api.onrender.com/openapi.json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('x-discovery:', d.get('x-discovery')); print('stats x-payment-info:', d['paths']['/api/stats']['get'].get('x-payment-info'))"

# 4. Free tier call (should be 200)
curl -s https://kristo-intelligence-api.onrender.com/api/stats | python3 -m json.tool | head -20

# 5. Paid call (should be 402 with payment headers)
curl -i -X GET https://kristo-intelligence-api.onrender.com/api/stats

# 6. Check x402scan listing (after ~5 min)
# Open in browser: https://www.x402scan.com/?q=kristo

# 7. Check PayAPI.market listing (after ~24h)
# Open in browser: https://payapi.market/marketplace?q=kristo
```

---

## ⚠️ CRITICAL: Revoke compromised GitHub token

The token `ghp_666tgT...` (used in earlier sessions) is compromised — it appeared in chat logs.

**Revoke it NOW:**

1. Go to: **https://github.com/settings/tokens**
2. Find the token in the list
3. Click **Delete** (or Revoke)
4. Confirm

After revoking, if you need continued assistance with the repo, create a new token and share it via a more secure channel (or run the commands yourself — I can provide exact commands for you to copy-paste).

---

## 📊 What happens after registration

Once both marketplaces list your API:

- **x402scan:** Your API appears in the public directory. AI agents searching for "DeFi", "Base", "trading signals" can discover it.
- **PayAPI.market:** Your API appears in the marketplace. Their existing AI agent customers (using Claude Desktop, Cursor) can find and pay for it.
- **Revenue:** Each paid call = 0.005 USDC to your wallet. Realistic first-month target: 5-20 paying customers = $0.025-0.10 from micro + $29-145 from VIP (if Stripe configured).

**The registrations are FREE distribution channels.** They cost you nothing but 10 minutes of your time, and they put your API in front of existing AI agent traffic that is already looking for x402-compatible APIs to pay for.

---

## ❌ What NOT to do

Based on lessons from earlier sessions:

- **Do NOT create a new Render web service.** The app is already live at `kristo-intelligence-api.onrender.com`. Creating a duplicate would cost $7/month for nothing.
- **Do NOT deploy from scratch.** Auto-deploy from GitHub `main` branch is already configured.
- **Do NOT build new products (Rug Score, Arb Radar, etc.) right now.** The priority is revenue from existing endpoints, not building more features. Free alternatives (GoPlus, TokenSniffer) make paid rug scores a hard sell.
- **Do NOT share GitHub tokens in chat.** Use GitHub's `repo` scope tokens only via secure channels, and revoke them immediately after use.

---

**Questions?** Open an issue at https://github.com/hristovdimitri2-hub/kristo-intelligence-6/issues
