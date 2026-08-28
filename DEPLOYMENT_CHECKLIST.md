# Deployment Checklist — Kristo Intelligence 6

Complete step-by-step guide to deploy the application to production and register it in x402scan + PayAPI.market marketplaces.

**Estimated time:** 30-45 minutes (15 min deploy + 15 min registrations + 15 min verification)

---

## Prerequisites

Before you start, gather these:

- [ ] GitHub account with push access to `hristovdimitri2-hub/kristo-intelligence-6`
- [ ] Render.com account (free to create at https://render.com)
- [ ] Base wallet with:
  - Wallet private key (will be set as `WALLET_PRIVATE_KEY`)
  - The wallet must own address `0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f` (the bound fee receiver)
  - At least 0.001 ETH for gas (~$3 at current prices)
- [ ] (Optional) Stripe account for VIP subscriptions
- [ ] (Optional) Telegram bot token from @BotFather
- [ ] (Optional) CoinGecko API key (Demo plan is free)

---

## Phase 1: Deploy to Render.com (15 minutes)

### Step 1.1 — Create the web service

1. Go to https://render.com and sign in with GitHub
2. Click **New +** → **Web Service**
3. Connect your GitHub account and select the repo: `kristo-intelligence-6`
4. Configure the service:
   - **Name:** `kristo-intelligence-v6`
   - **Region:** Frankfurt (or closest to your users)
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn --bind=0.0.0.0:$PORT --workers=1 --threads=8 --timeout=120 main:app`
   - **Instance Type:** Starter ($7/month — required for always-on, free tier sleeps)

### Step 1.2 — Set environment variables

In Render → your service → **Environment**, add these variables:

| Variable | Value | Required |
|---|---|---|
| `ADMIN_API_TOKEN` | Generate 32-char random string (e.g. `openssl rand -hex 32`) | ✅ |
| `WALLET_PRIVATE_KEY` | Your Base wallet private key (no 0x prefix) | ✅ |
| `BASE_CHAIN_ID` | `8453` (Base mainnet) | ✅ |
| `AGENT_AUTO_EXECUTE` | `false` (keep disabled until tested!) | ✅ |
| `KRISTO_DISABLE_BACKGROUND_THREADS` | `false` (single-process mode for Starter tier) | ✅ |
| `BASE_RPC_URL` | `https://mainnet.base.org` (default) | (optional) |
| `BASE_FEE_AMOUNT_USDC` | `0.05` (already set in code) | (optional) |
| `TELEGRAM_BOT_TOKEN` | From @BotFather | (optional) |
| `WEBHOOK_PUBLIC_URL` | `https://kristo-intelligence-v6.onrender.com` (your Render URL) | (optional) |
| `STRIPE_SECRET_KEY` | `sk_live_...` from Stripe dashboard | (optional) |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` from Stripe webhook endpoint | (optional) |

### Step 1.3 — Deploy

1. Click **Create Web Service**
2. Wait ~3 minutes for build and deploy
3. Note your app URL: `https://kristo-intelligence-v6.onrender.com`

### Step 1.4 — Verify deployment

Run these curl commands (replace `YOUR-APP` with your actual Render URL):

```bash
# 1. Health check
curl https://kristo-intelligence-v6.onrender.com/health
# Expected: {"status":"ok","database":{"backend":"sqlite","ready":true},"blockchain":{"ready":true,...}}

# 2. x402scan-compatible discovery (NO .json extension!)
curl https://kristo-intelligence-v6.onrender.com/.well-known/x402
# Expected: {"version":1,"resources":["https://.../api/stats",...],"ownershipProofs":["0xd4cdA900..."]}

# 3. OpenAPI spec with x-payment-info
curl https://kristo-intelligence-v6.onrender.com/openapi.json | python3 -m json.tool | head -30
# Expected: openapi 3.0.3, info.x402, x-discovery.ownershipProofs, paths./api/stats.get.x-payment-info

# 4. Free tier call (should return 200)
curl https://kristo-intelligence-v6.onrender.com/api/stats
# Expected: 200 OK with stats data

# 5. Paid call (should return 402 with payment headers)
curl -i https://kristo-intelligence-v6.onrender.com/api/stats
# Expected: 402 with X-Payment-Address and X-Payment-Amount-USDC headers

# 6. Dashboard
open https://kristo-intelligence-v6.onrender.com/dashboard
```

If all 6 checks pass — proceed to Phase 2.

---

## Phase 2: Register in x402scan (2 minutes)

x402scan (https://x402scan.com) is the main ecosystem explorer for x402 APIs. Registration is **free and automatic** if your discovery endpoints are valid.

### Step 2.1 — Submit your server URL

1. Go to: **https://www.x402scan.com/resources/register**
2. In the form, enter your app URL:
   ```
   https://kristo-intelligence-v6.onrender.com
   ```
3. Click **Submit** / **Add Server**

### Step 2.2 — How x402scan validates your server

x402scan will automatically:
1. Fetch `https://your-app.onrender.com/openapi.json` (OpenAPI-first discovery)
2. Parse `x-payment-info` per paid operation
3. Parse `x-discovery.ownershipProofs` for ownership verification
4. Probe each paid endpoint (`/api/stats`, `/api/sales`, `/api/bot-status`) with a test request
5. Verify the 402 challenge response is parseable
6. If all checks pass — register your server in the public directory

### Step 2.3 — Alternative: `/.well-known/x402` compatibility

If OpenAPI discovery fails for any reason, x402scan falls back to:
```
https://your-app.onrender.com/.well-known/x402
```
This returns:
```json
{
  "version": 1,
  "resources": [
    "https://your-app.onrender.com/api/stats",
    "https://your-app.onrender.com/api/sales",
    "https://your-app.onrender.com/api/bot-status"
  ],
  "ownershipProofs": ["0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"]
}
```

### Step 2.4 — Verify registration

After ~1-5 minutes, search for your API on https://x402scan.com:
1. Go to https://www.x402scan.com
2. Use the search bar to find "Kristo Intelligence"
3. Your API should appear in the listings with:
   - The 3 paid endpoints visible
   - "Verified" badge if x402scan's test payment succeeded
   - Transaction volume tracking (starts at 0)

If registration fails, check the common failure reasons in the [x402scan DISCOVERY.md](https://github.com/Merit-Systems/x402scan/blob/main/docs/DISCOVERY.md):
- `Expected 402, got 404/405/429` — endpoint URL wrong
- `parseResponse: Accepts must contain at least one valid payment requirement` — 402 challenge malformed
- `Missing input schema` — add request body schema to OpenAPI

---

## Phase 3: Register in PayAPI.market (5 minutes)

PayAPI.market (https://payapi.market) is another x402 marketplace with 89 live APIs and existing AI agent traffic.

### Step 3.1 — List your API

1. Go to: **https://payapi.market**
2. Click **"List your API (free)"** (top right)
3. Fill in the form:
   - **API Name:** Kristo Intelligence API
   - **Description:** AI-powered DeFi trading signals and crypto market intelligence on Base. Real-time prices for ETH, ONDO, KAITO, DEGEN, risk-managed portfolio recommendations, and on-chain sales history.
   - **Category:** Finance / Crypto / DeFi
   - **Base URL:** `https://kristo-intelligence-v6.onrender.com`
   - **Pricing:** $0.05 per request (or specify your own)
   - **Receiver wallet:** `0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f`
   - **Chain:** Base (chain_id 8453)
   - **USDC contract:** `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
4. Submit the form

### Step 3.2 — Verification

PayAPI.market will:
1. Make a test call to your endpoints
2. Pay 0.05 USDC from their own wallet to your receiver address
3. Verify the payment is detected on-chain
4. Retry the endpoint and verify access is granted
5. If successful — award the "x402 verified" badge

### Step 3.3 — Featured tier (optional, $49/month)

After basic registration, you can upgrade to Featured for:
- Gold badge on your listing
- Always-first ranking in search results
- Priority position in category filters
- Featured in MCP tool manifest

**Recommendation:** Start with Free tier. Upgrade to Featured only if you have <5 paid calls/day after 14 days.

---

## Phase 4: Set up Stripe webhook (5 minutes, optional)

Required only if you want to accept $29/month VIP subscriptions via Stripe.

### Step 4.1 — Create webhook endpoint

1. Go to https://dashboard.stripe.com/webhooks
2. Click **Add endpoint**
3. **Endpoint URL:** `https://kristo-intelligence-v6.onrender.com/api/webhooks/stripe`
4. **Events to send:**
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
   - `checkout.session.expired`
5. Click **Add endpoint**
6. Copy the **Signing secret** (`whsec_...`)

### Step 4.2 — Update Render environment

1. Go to Render → your service → **Environment**
2. Add: `STRIPE_WEBHOOK_SECRET` = `whsec_...` (from step 4.1)
3. Save changes (triggers auto-redeploy)

### Step 4.3 — Test webhook

```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe  # macOS
# or: https://github.com/stripe/stripe-cli/releases

# Forward test events to your local Render URL
stripe listen --forward-to https://kristo-intelligence-v6.onrender.com/api/webhooks/stripe

# In another terminal, trigger a test event
stripe trigger checkout.session.completed
```

---

## Phase 5: Post-deployment verification (5 minutes)

Run the full verification suite:

```bash
# 1. Health check
curl -s https://kristo-intelligence-v6.onrender.com/health | python3 -m json.tool

# 2. x402scan discovery (the critical one!)
curl -s https://kristo-intelligence-v6.onrender.com/.well-known/x402 | python3 -m json.tool

# 3. OpenAPI spec — verify x-payment-info is present
curl -s https://kristo-intelligence-v6.onrender.com/openapi.json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('x-discovery:', d.get('x-discovery')); print('stats x-payment-info:', d['paths']['/api/stats']['get'].get('x-payment-info'))"

# 4. Free tier call
curl -s https://kristo-intelligence-v6.onrender.com/api/stats | python3 -m json.tool | head -20

# 5. 402 challenge (after free tier exhausted)
curl -i -X GET https://kristo-intelligence-v6.onrender.com/api/stats

# 6. Check x402scan listing (after ~5 min)
# Open in browser: https://www.x402scan.com/?q=kristo

# 7. Check PayAPI.market listing (after ~24h)
# Open in browser: https://payapi.market/marketplace?q=kristo
```

---

## Phase 6: Marketing — get your first customers

After deployment, you need real customers to generate revenue. Suggested channels:

| Channel | Effort | Expected reach |
|---|---|---|
| **Crypto Twitter/X** — post about x402 micropayments for AI agents | 30 min | 100-500 views |
| **Base ecosystem Discord/Telegram** — share dashboard URL | 1 hour | 50-200 clicks |
| **Hacker News** — "Show HN: AI agents pay-per-call with x402 on Base" | 1 hour | 500-5000 views |
| **Reddit r/CryptoCurrency, r/BaseChain, r/defi** — educational posts | 2 hours | 200-1000 views |
| **AI agent communities** (AutoGPT, LangChain, Claude Desktop) | 2 hours | 100-500 clicks |
| **Crypto newsletters** (Bankless, The Defiant) — pitch | 2 hours | 1000-10000 views |

**Realistic first-month target:** 5-20 paying customers = $5-15 micro + $29-145 VIP = $34-160 total revenue.

---

## Troubleshooting

### x402scan registration failed

1. **Verify `/.well-known/x402` returns 200**:
   ```bash
   curl -i https://your-app.onrender.com/.well-known/x402
   ```
   Must return `200 OK` with JSON containing `version: 1` and `resources` array.

2. **Verify `/openapi.json` has `x-payment-info`**:
   ```bash
   curl -s https://your-app.onrender.com/openapi.json | \
     python3 -c "import json,sys; d=json.load(sys.stdin); print(d['paths']['/api/stats']['get'].get('x-payment-info'))"
   ```
   Must return a non-None dict with `protocols: ["x402"]` and `price.amount`.

3. **Verify paid endpoints return 402 after free tier**:
   ```bash
   # First call (free tier) — should be 200
   curl -o /dev/null -w "%{http_code}\n" https://your-app.onrender.com/api/stats
   # Second call (paid) — should be 402
   curl -o /dev/null -w "%{http_code}\n" https://your-app.onrender.com/api/stats
   ```

### Health check returns 503

- Check that `WALLET_PRIVATE_KEY` is set correctly (no 0x prefix, 64 hex chars)
- Check that the wallet owns the bound fee receiver address
- Check Render logs for blockchain connection errors

### x402 payment not detected

- Verify receiver address is `0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f` (commit dcebafd fix)
- Check that the blockchain monitor thread is running (look for `blockchain-monitor` in logs)
- Verify wallet has USDC balance for gas of verification calls

### Stripe webhook not arriving

- Verify `STRIPE_WEBHOOK_SECRET` matches the signing secret from Stripe dashboard
- Check that the webhook URL is `https://YOUR-DOMAIN/api/webhooks/stripe`
- Test with `stripe listen --forward-to localhost:10000/api/webhooks/stripe`

---

## Success criteria

After completing this checklist, you should have:

- ✅ App deployed at `https://kristo-intelligence-v6.onrender.com`
- ✅ `/health` returns 200 OK
- ✅ `/.well-known/x402` returns valid x402scan-compatible JSON
- ✅ `/openapi.json` includes `x-payment-info` and `x-discovery.ownershipProofs`
- ✅ Listed on x402scan.com (search "Kristo Intelligence")
- ✅ Listed on payapi.market (search "Kristo Intelligence")
- ✅ Stripe webhook receiving events (if VIP subscriptions enabled)
- ✅ First test payment of 0.05 USDC received from x402scan's verification bot

Once all boxes are checked — you're live and ready to accept real customers!

---

**Questions?** Open an issue at https://github.com/hristovdimitri2-hub/kristo-intelligence-6/issues
