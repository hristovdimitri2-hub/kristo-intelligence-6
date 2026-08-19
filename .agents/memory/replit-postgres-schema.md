---
name: Replit Postgres schema setup
description: Reliable setup and verification rule for Replit managed PostgreSQL schemas.
---

Create development schema objects with explicit `public.` qualification, then verify the table through the application's `DATABASE_URL` connection before making the runtime select PostgreSQL.

**Why:** A schema command can report success while an unqualified follow-up lookup does not see the object consistently; the application's runtime connection is the authoritative readiness check.

**How to apply:** Use the managed development database for schema changes, qualify application tables as `public.<table>`, and verify runtime read access before Publish. Let Replit Publish apply the development-to-production schema diff; do not add startup-time or deploy-time DDL.