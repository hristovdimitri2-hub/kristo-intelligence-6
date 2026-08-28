# Kristo Intelligence 6 — Deployment Guide

This guide walks you through deploying the application to a production-ready
cloud environment. The application is now 100% code-complete and ready for
deployment — what remains is platform configuration and secret management.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Option A: Render.com (recommended, easiest)](#option-a-rendercom-recommended-easiest)
4. [Option B: Docker (any VPS / cloud)](#option-b-docker-any-vps--cloud)
5. [Option C: Replit (legacy)](#option-c-replit-legacy)
6. [Required Environment Variables](#required-environment-variables)
7. [Post-deploy Verification](#post-deploy-verification)
8. [Accepting Real Payments](#accepting-real-payments)
9. [Marketing Your First Customers](#marketing-your-first-customers)
10. [Troubleshooting](#troubleshooting)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Production Architecture                       │
└─────────────────────────────────────────────────────────────────┘

   Internet (HTTPS)
        │
        ▼
   ┌─────────────────┐
   │   Render / VPS   │  ← TLS termination, custom domain
   │   Load balancer  │
   └────────┬────────┘
            │
   ┌────────┴────────┐
   │                  │
   ▼                  ▼
┌─────────────┐  ┌─────────────┐
│  web service│  │   worker    │  ← separate processes (item #10)
│  (gunicorn) │  │   (python)  │
│  HTTP only  │  │   BG only   │
│  port 10000 │  │             │
└──────┬──────┘  └──────┬──────┘
       │                 │
       └────────┬────────┘
                │
                ▼
        ┌──────────────┐
        │  PostgreSQL  │  ← Render managed DB or docker-compose
        │  (optional)  │
        └──────────────┘
                │
                ▼
        ┌──────────────┐
        │  Base RPC    │  ← https://mainnet.base.org
        │  CoinGecko   │  ← https://api.coingecko.com
        │  Stripe API  │  ← https://api.stripe.com
        │  Telegram    │  ← https://api.telegram.org
        └──────────────┘
```

---

## Prerequisites

Before deploying, you need:

1. **A GitHub account** with push access to `hristovdimitri2-hub/kristo-intelligence-6`
2. **A Base wallet** with:
   - Some ETH for gas (~0.01 ETH is enough; Base fees are ~$0.01/tx)
   - The wallet's **private key** (will be set as `WALLET_PRIVATE_KEY`)
3. **Stripe account** (free to create at stripe.com) — for VIP subscriptions
4. **Telegram bot token** (optional, for sales bulletins) — from @BotFather
5. **CoinGecko API key** (optional, Demo plan is free) — for higher rate limits
6. **OpenRouter API key** (optional) — for AI market bulletins via gpt-4o-mini
7. **Render.com account** (free tier works for the first 90 days)

---

## Option A: Render.com (recommended, easiest)

### Step 1: Create the web service

1. Go to https://render.com and sign in with GitHub
2. Click **New +** → **Web Service**
3. Connect your GitHub and select the repo: `kristo-intelligence-6`
4. Configure:
   - **Name:** `kristo-intelligence-v6`
   - **Region:** Frankfurt (closest to most users) or your region
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn --bind=0.0.0.0:$PORT --workers=1 --threads=8 --timeout=120 main:app`
   - **Instance Type:** Starter ($7/month, 512MB RAM — sufficient for MVP)

5. Under **Advanced**, set the following environment variables (see
   [Required Environment Variables](#required-environment-variables)):

   | Variable | Value |
   |---|---|
   | `ADMIN_API_TOKEN` | generate a 32-char random string |
   | `WALLET_PRIVATE_KEY` | your Base wallet private key |
   | `BASE_CHAIN_ID` | `8453` (Base mainnet) |
   | `AGENT_AUTO_EXECUTE` | `false` (keep disabled until tested) |
   | `KRISTO_DISABLE_BACKGROUND_THREADS` | `false` (single-process mode) |
   | `TELEGRAM_BOT_TOKEN` | from @BotFather (optional) |
   | `STRIPE_SECRET_KEY` | `sk_live_...` from Stripe dashboard |
   | `STRIPE_WEBHOOK_SECRET` | `whsec_...` from Stripe webhook endpoint |

6. Click **Create Web Service**. Render will build and deploy (~3 minutes).

### Step 2: Create a PostgreSQL database (optional but recommended)

1. Click **New +** → **PostgreSQL**
2. Name: `kristo-db`
3. Database: `kristo`
4. User: `kristo`
5. Region: same as web service
6. Plan: Free (90 days) or Starter ($7/month)
7. After creation, Render shows the **Internal Database URL** — copy it
8. Go back to your web service → **Environment** → add:
   - `DATABASE_URL` = (the internal URL from step 7)
9. Save changes — Render will auto-redeploy

### Step 3: Set up Stripe webhook

1. Go to https://dashboard.stripe.com/webhooks
2. Click **Add endpoint**
3. **Endpoint URL:** `https://YOUR-APP-NAME.onrender.com/api/webhooks/stripe`
4. **Events to send:**
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
   - `checkout.session.expired`
5. Click **Add endpoint**
6. Copy the **Signing secret** (`whsec_...`)
7. Add it to your Render web service as `STRIPE_WEBHOOK_SECRET`

### Step 4: Set up Telegram webhook (optional)

The app auto-registers its Telegram webhook on startup. Just make sure:
- `TELEGRAM_BOT_TOKEN` is set
- `WEBHOOK_PUBLIC_URL` = your Render URL (`https://YOUR-APP-NAME.onrender.com`)

### Step 5: Verify deployment

After ~3 minutes, visit `https://YOUR-APP-NAME.onrender.com`. You should see
the landing page. Then check:

- `https://YOUR-APP-NAME.onrender.com/health` → should return 200 OK
- `https://YOUR-APP-NAME.onrender.com/.well-known/x402.json` → should show
  the correct fee receiver address (`0xd4cdA900...08f`)
- `https://YOUR-APP-NAME.onrender.com/dashboard` → HTML dashboard

---

## Option B: Docker (any VPS / cloud)

### Step 1: Prepare the server

```bash
# On a fresh Ubuntu 22.04+ VPS:
sudo apt update && sudo apt install -y docker.io docker-compose
sudo systemctl enable --now docker
```

### Step 2: Clone the repo and configure

```bash
git clone https://github.com/hristovdimitri2-hub/kristo-intelligence-6.git
cd kristo-intelligence-6
cp .env.example .env
nano .env  # edit values
```

### Step 3: Start the stack

```bash
docker compose up -d --build
```

This starts three containers:
- `kristo-postgres` — PostgreSQL 16
- `kristo-web` — Flask app (gunicorn) on port 10000
- `kristo-worker` — Background worker (blockchain monitor, agent, etc.)

### Step 4: Set up reverse proxy (nginx + Let's Encrypt)

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo nano /etc/nginx/sites-available/kristo
```

```nginx
server {
    server_name your-domain.com;
    location / {
        proxy_pass http://localhost:10000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/kristo /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.com
```

---

## Option C: Replit (legacy)

Replit is supported via the existing `.replit` config (gitignored but
preserved on local disk). For new deployments, prefer Render (Option A).

---

## Required Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ADMIN_API_TOKEN` | ✅ Yes | — | 32+ char random string for admin auth |
| `WALLET_PRIVATE_KEY` | ✅ Yes | — | Base wallet private key (no 0x prefix) |
| `BASE_RPC_URL` | Optional | `https://mainnet.base.org` | Base RPC endpoint |
| `BASE_CHAIN_ID` | Optional | `8453` | Base mainnet (8453) or Sepolia (84532) |
| `BASE_FEE_AMOUNT_USDC` | Optional | `0.10` | Per-call fee in USDC |
| `AGENT_AUTO_EXECUTE` | Optional | `false` | Set `true` only after testing |
| `AGENT_MAX_POSITION_USD` | Optional | `1000` | Max single position |
| `AGENT_MAX_EXPOSURE_USD` | Optional | `5000` | Max total exposure |
| `DATABASE_URL` | Optional | (SQLite) | PostgreSQL URL for production |
| `STRIPE_SECRET_KEY` | Optional | — | `sk_live_...` for VIP subscriptions |
| `STRIPE_WEBHOOK_SECRET` | Optional | — | `whsec_...` from Stripe dashboard |
| `TELEGRAM_BOT_TOKEN` | Optional | — | From @BotFather |
| `TELEGRAM_VIP_CHAT_ID` | Optional | — | Chat ID for VIP bulletins |
| `COINGECKO_API_KEY` | Optional | — | Demo/Pro plan key |
| `OPENROUTER_API_KEY` | Optional | — | For AI market bulletins |
| `APP_PUBLIC_URL` | Optional | — | `https://your-domain.com` |
| `WEBHOOK_PUBLIC_URL` | Optional | — | Same as APP_PUBLIC_URL |
| `KRISTO_WORKER_MODE` | Optional | `false` | Set `true` only in worker process |

---

## Post-deploy Verification

After deployment, run these checks:

```bash
# 1. Health check
curl https://YOUR-APP-NAME.onrender.com/health
# Expected: {"ok": true, "status": "live", ...}

# 2. x402 discovery
curl https://YOUR-APP-NAME.onrender.com/.well-known/x402.json
# Expected: JSON with receiver_address: 0xd4cdA900...08f

# 3. OpenAPI spec
curl https://YOUR-APP-NAME.onrender.com/openapi.json | head

# 4. Dashboard (HTML)
open https://YOUR-APP-NAME.onrender.com/dashboard

# 5. Agent catalog
curl https://YOUR-APP-NAME.onrender.com/api/v1/agents

# 6. Admin auth (should fail without token)
curl https://YOUR-APP-NAME.onrender.com/api/admin/leads
# Expected: 401 {"ok": false, "error": "admin_auth_required"}

# 7. Admin auth (with token)
curl -H "X-Admin-Token: YOUR_TOKEN" https://YOUR-APP-NAME.onrender.com/api/admin/overview
# Expected: 200 with JSON dashboard data
```

---

## Accepting Real Payments

The app supports two payment channels:

### Channel 1: x402 micro-payments (0.10 USDC per API call)

**How it works:**
1. A client (AI agent or human) calls `/api/stats`, `/api/sales`, or `/api/bot-status`
2. First call is free (free tier = 1 call per IP)
3. Subsequent calls return HTTP 402 with payment instructions
4. Client sends 0.10 USDC on Base to `0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f`
5. After on-chain confirmation (~2 seconds on Base), client retries the endpoint
6. Access is granted automatically (verified via ERC-20 Transfer event logs)

**Your action:** Make sure your wallet (`WALLET_PRIVATE_KEY`) has the
matching public address that owns `0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f`,
OR monitor that address externally. The app currently monitors incoming
transfers and grants access automatically.

### Channel 2: Stripe VIP subscriptions ($29/month)

**How it works:**
1. Customer visits `/sales/checkout` and pays $29 via Stripe
2. Stripe webhook hits `/api/webhooks/stripe` with `checkout.session.completed`
3. App grants 30-day unlimited access + sends Telegram VIP invite

**Your action:**
1. Create Stripe products/prices in your Stripe dashboard
2. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` env vars
3. Configure the webhook endpoint as described in Step 3 above

---

## Marketing Your First Customers

To get real revenue, you need real customers. Suggested channels:

1. **Crypto Twitter/X** — post about x402 micropayments for AI agents
2. **Base ecosystem Discord/Telegram groups** — share the dashboard URL
3. **Hacker News** — write a "Show HN: AI agents pay-per-call with x402" post
4. **Reddit r/CryptoCurrency, r/BaseChain, r/defi** — educational posts
5. **AI agent communities** (AutoGPT, BabyAGI, LangChain) — offer the API
6. **Crypto newsletters** — pitch to Bankless, The Defiant, etc.

Realistic first-month target: 5-20 paying customers = $5-15 micro + $29-145 VIP.

---

## Troubleshooting

### Health check returns 503

- Check that `WALLET_PRIVATE_KEY` is set correctly
- Check that the wallet has ETH for gas (Base fees are ~$0.01/tx)
- View Render logs: `https://dashboard.render.com/web/YOUR-SERVICE/logs`

### x402 payment not detected

- Verify the receiver address matches `config.BOUND_BASE_FEE_RECEIVER`
- Check that the blockchain monitor thread is running (look for
  `blockchain-monitor` in logs)
- Make sure the wallet has USDC balance for the gas of the verification call

### Stripe webhook not arriving

- Verify `STRIPE_WEBHOOK_SECRET` matches the signing secret from Stripe dashboard
- Check that the webhook URL is `https://YOUR-DOMAIN/api/webhooks/stripe`
- Test with `stripe listen --forward-to localhost:10000/api/webhooks/stripe`

### Telegram bot not responding

- Verify `TELEGRAM_BOT_TOKEN` is correct (test with `curl https://api.telegram.org/bot<TOKEN>/getMe`)
- Check that `WEBHOOK_PUBLIC_URL` matches your domain
- View logs for `register_webhook` errors

### Database connection failed

- Verify `DATABASE_URL` is the **internal** Render URL (not external)
- For Docker: ensure the `postgres` container is healthy (`docker compose ps`)
- Test connection: `psql $DATABASE_URL -c "SELECT 1"`

---

## Support

- **GitHub Issues:** https://github.com/hristovdimitri2-hub/kristo-intelligence-6/issues
- **Audit report:** see `download/kristo-intelligence-6-audit-report.pdf`
- **Code documentation:** see `docs/ARCHITECTURE.md` and `docs/QUICK_START.md`

---

**Last updated:** 2026-08-24 (after audit items 1-11 completed)
