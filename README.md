# Kristo Intelligence

Kristo Intelligence is an evidence-first agent utility marketplace. It provides small, machine-readable utilities with explicit source provenance, freshness labels and bounded payment access.

The application is designed to be honest about its state:

- A catalog utility is public only after an administrator activates a reviewed contract.
- A provider failure is returned as unavailable or partial data rather than hidden.
- A running preview is not presented as a commercially ready launch.
- Customer payments are fulfilled only through verified payment and entitlement flows.

## Public entry points

- `/agents` — public agent marketplace and bounded playground.
- `/developers` — integration guide.
- `/nexus` — separate Nexus premium signal product.
- `/openapi.json` — current runtime API specification.
- `/mcp.json` and `/api/mcp/manifest` — machine discovery.
- `/.well-known/x402.json` — runtime x402 discovery.
- `/api/launch/health` — public launch-readiness gate.
- `/sales/admin` — protected operational dashboard.

## Product access

Every active utility supports:

1. One bounded free playground request per client and utility.
2. Request-bound x402 payment on Base after the free request is consumed.
3. A 30-day Stripe entitlement with a short-lived access token.

The service does not execute trades, custody funds, make investment decisions or publish to external accounts.

## Launch policy

The application is ready for a commercial public launch only when `/api/launch/health` returns `200` with `launch_ready`.

That requires:

- managed PostgreSQL persistence and applied migrations;
- an active human-approved catalog contract;
- real Stripe checkout and signed webhook configuration;
- configured Base x402 settlement;
- Telegram VIP configuration and a real delivery test;
- dedicated production secrets; and
- real Stripe, Telegram and x402 smoke-test evidence after Publish.

Until then, the endpoint returns `503` with a non-sensitive list of blocked gates. This protects customers from seeing a preview or partial integration as a live commercial service.

## Local development

```bash
pip install -r requirements.txt
PORT=5000 python main.py
```

Use `.env.example` for variable names. Do not add secrets or production credentials to tracked files.

## Verification

```bash
pytest -q
python -m py_compile main.py
```

## License

MIT