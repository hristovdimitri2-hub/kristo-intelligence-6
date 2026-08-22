# Production Readiness Checklist

## v6 publish handoff
- [ ] Publish the verified v6 build; the currently active public deployment identifies as the prior v5 release and is not approval for this catalog.
- [ ] Confirm the deployed primary URL in Publishing and keep `APP_PUBLIC_URL` / `WEBHOOK_PUBLIC_URL` aligned with that exact URL. Do not guess a v6 domain.
- [ ] After confirming that URL, set `TELEGRAM_WEBHOOK_AUTOREGISTER=true` only in production and restart once to register the signed Telegram webhook. Keep it unset in development so local restarts cannot overwrite production bot configuration.
- [ ] Set `RESEARCH_INGEST_TOKEN` as a production secret before connecting Discord, RSS, or GitHub ingestion.
- [ ] Set a dedicated `AGENT_ACCESS_TOKEN_SECRET` production secret; access tokens are signed checkout-bound bearer credentials.
- [ ] Keep `TRUST_PROXY_HEADERS` disabled until the exact immediate reverse-proxy addresses are confirmed, then set it with a matching `TRUSTED_PROXY_IPS` allowlist. Never trust arbitrary `X-Forwarded-For` headers.
- [ ] Confirm the PostgreSQL Publish schema diff includes Nexus, catalog-governance, runtime-persistence and Stripe/VIP fulfillment migrations. The application must not create any of these tables at startup.
- [ ] Before Publish, verify the development database has all catalog, entitlement, operational-audit, x402 and Stripe/VIP runtime tables; the protected dashboard persistence gate must show `schema verified`.
- [ ] After Publish, authenticate as an administrator and activate the reviewed v2.0 contract. Before that action, `/api/v1/agents`, `/.well-known/x402.json`, `/mcp.json`, `/api/mcp/manifest`, and `llms.txt` must safely expose no catalog utilities with `migration_required` or `approval_required`.
- [ ] After activation, verify all discovery surfaces expose the same eight agent IDs, prices and active contract version.
- [ ] Verify `settlement_status` is `full` only after a successful production challenge/proof/delivery smoke test. If settlement is disabled or unhealthy, keep the corresponding discovery status explicit; never claim a live paid flow by configuration alone.
- [ ] Verify `/agents` allows one bounded free request per client-agent and returns an honest 402 upgrade payload afterward only when an active contract exists.
- [ ] Confirm the Stripe payment snapshot is fresh or explicitly stale in `/sales/admin`; an unavailable Stripe feed must fall back to settled CRM events.
- [ ] Confirm the development merge setup applied Nexus, marketplace-governance, runtime-persistence and Stripe/VIP fulfillment migrations, then rely on Replit Publish to carry the managed schema change to production.

## Technical readiness
- [ ] project runs in production mode
- [ ] `.env` is configured correctly
- [ ] Telegram bot token, verified group/supergroup ID and administrator permission are confirmed; the bot must create and deliver a one-use invite in the target VIP group.
- [ ] The Stripe webhook uses the deployed production URL and signing secret; a real paid checkout must validate its server-bound plan, amount and currency before durable fulfillment.
- [ ] A paid Stripe customer completes `/start vip_<token>` from their own Telegram account, receives exactly one reusable invite link, and an intentionally failed delivery can be retried from the protected admin endpoint.
- [ ] wallet and USDC receiver are configured
- [ ] live data sources are verified
- [ ] AI fallback is tested
- [ ] health endpoint works

## Business readiness
- [ ] product offer is finalized
- [ ] landing page is live
- [ ] pricing is clear
- [ ] kickoff / welcome flow is configured
- [ ] support workflow exists
- [ ] refund flow exists

## Sales readiness
- [ ] ad campaigns are prepared
- [ ] analytics tracking is installed
- [ ] source tagging works
- [ ] conversion funnel is tested
- [ ] CRM is connected
- [ ] payment flow is tested with one real customer-safe payment and signed webhook delivery; do not treat a success redirect, Stripe configuration or test fixtures as fulfillment proof.

## Launch gate
Only after all items above are complete should the project be considered ready for a limited beta launch. Broad live sales require observed payment delivery, provider reliability and repeat-use evidence from the flagship utility review.
