# Archived Files

This directory contains files preserved for historical reference but no longer
active in the codebase.

## openapi.json.static / llms.txt.static

**Original location:** repo root (`openapi.json`, `llms.txt`)
**Archived:** 2026-08-24 (post-audit hardening)

These static discovery specs were the source of the original
wrong-receiver-address bug (2026-08-24 audit): the static files pointed to a
different wallet than the one the app actually monitors. Both endpoints
(`GET /openapi.json`, `GET /llms.txt`) are now served **dynamically** from
`app/blueprints/discovery.py`, built from `config.get_base_fee_receiver()` —
a single source of truth — so they can never drift from the configured
receiver again.

Do NOT restore these files to the repo root.

## prisma-schema-legacy.prisma

**Original location:** `prisma/schema.prisma`
**Archived:** 2026-08-24 (audit item #7)

This Prisma schema was defined but never wired into the Flask runtime — the
application uses `psycopg` directly via `integrations/catalog_store.py`
(`PostgresCatalogStore`) and `integrations/crm_store.py` (`PostgresCRMStore`).

It is preserved here as documentation of the original database design intent
(tables: `agent_skus`, `agent_events`, `agent_metrics_24h`, `agent_checkouts`,
`agent_entitlements`). If a future migration to Prisma is desired, this schema
can serve as a starting point.

To re-activate:
1. `mv docs/archive/prisma-schema-legacy.prisma prisma/schema.prisma`
2. Add `prisma` and `@prisma/client` to a new `package.json`
3. Run `npx prisma generate` and `npx prisma db push`
4. Replace `psycopg` calls in `integrations/*_store.py` with Prisma client calls
