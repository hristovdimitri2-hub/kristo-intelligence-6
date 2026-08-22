from pathlib import Path


MIGRATION = Path("prisma/migrations/20260821120000_add_runtime_persistence/migration.sql")
CRM_MIGRATION = Path("prisma/migrations/20260821140000_add_crm_leads/migration.sql")


def test_runtime_persistence_migration_covers_every_postgres_runtime_table():
    sql = MIGRATION.read_text(encoding="utf-8")

    for table in (
        "agent_skus",
        "agent_events",
        "agent_playground_uses",
        "agent_checkouts",
        "agent_entitlements",
        "agent_metrics_24h",
        "x402_payment_challenges",
        "x402_settlements",
        "operational_events",
    ):
        assert f"public.{table}" in sql

    for invariant in (
        "PRIMARY KEY (agent_id, client_key_hash)",
        "transaction_hash TEXT UNIQUE",
        "challenge_id TEXT NOT NULL UNIQUE",
        "idx_agent_events_window",
        "idx_agent_entitlements_access",
        "idx_operational_events_recent",
    ):
        assert invariant in sql


def test_development_migration_runner_includes_runtime_persistence():
    script = Path("scripts/post-merge.sh").read_text(encoding="utf-8")

    assert "20260821120000_add_runtime_persistence/migration.sql" in script
    assert "Production schema changes are applied exclusively by the Publish flow." in script


def test_crm_leads_migration_covers_postgres_crm_store_and_runner():
    sql = CRM_MIGRATION.read_text(encoding="utf-8")
    script = Path("scripts/post-merge.sh").read_text(encoding="utf-8")
    schema = Path("prisma/schema.prisma").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS public.leads" in sql
    for column in (
        "email TEXT PRIMARY KEY",
        "created_at TIMESTAMPTZ NOT NULL",
        "telegram_chat_id TEXT NOT NULL",
        "payment_status TEXT NOT NULL",
    ):
        assert column in sql
    assert "20260821140000_add_crm_leads/migration.sql" in script
    assert "model Lead" in schema
    assert '@@map("leads")' in schema