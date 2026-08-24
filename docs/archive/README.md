# Archived Files

This directory contains files preserved for historical reference but no longer
active in the codebase.

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
