#!/usr/bin/env bash
set -euo pipefail

# This script runs only in the Replit development workspace after a task merge.
# Production schema changes are applied exclusively by the Publish flow.
if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not configured; skipping development migrations."
  exit 0
fi

for migration in \
  prisma/migrations/20260820150000_add_nexus_analytics_events/migration.sql \
  prisma/migrations/20260821110000_add_agent_marketplace_governance/migration.sql \
  prisma/migrations/20260821120000_add_runtime_persistence/migration.sql \
  prisma/migrations/20260821130000_add_stripe_vip_fulfillment/migration.sql \
  prisma/migrations/20260821140000_add_crm_leads/migration.sql
do
  echo "Applying development migration: $migration"
  psql "$DATABASE_URL" \
    --set=ON_ERROR_STOP=1 \
    --file="$migration"
done