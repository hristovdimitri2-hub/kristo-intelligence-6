# Production Readiness Checklist

## v6 publish handoff
- [ ] Re-publish the verified v6 build; the currently active public deployment still identifies as the prior v5 release.
- [ ] Confirm the deployed primary URL in Publishing and keep `APP_PUBLIC_URL` / `WEBHOOK_PUBLIC_URL` aligned with that exact URL. Do not guess a v6 domain.
- [ ] Set `RESEARCH_INGEST_TOKEN` as a production secret before connecting Discord, RSS, or GitHub ingestion.
- [ ] Verify `/.well-known/x402.json` contains eight catalog agents and clearly reports `settlement_status: discovery_only`.
- [ ] Verify `/agents` allows one bounded free request per client-agent and returns an honest 402 upgrade payload afterward.
- [ ] Confirm the Stripe payment snapshot is fresh or explicitly stale in `/sales/admin`; an unavailable Stripe feed must fall back to settled CRM events.
- [ ] Apply the production PostgreSQL schema before relying on research workflow persistence.

## Technical readiness
- [ ] project runs in production mode
- [ ] `.env` is configured correctly
- [ ] Telegram bot token and chat IDs are set
- [ ] webhook URL is valid for production
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
- [ ] payment flow is tested

## Launch gate
Only after all items above are complete should the project be considered ready for live sales.
