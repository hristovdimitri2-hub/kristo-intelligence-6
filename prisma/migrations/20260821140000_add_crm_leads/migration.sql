-- Durable CRM lead persistence for production checkout and sales reporting.
-- Development applies this through scripts/post-merge.sh; production schema
-- changes are applied only by Publish.

CREATE TABLE IF NOT EXISTS public.leads (
    email TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'website',
    campaign TEXT NOT NULL DEFAULT 'launch',
    utm_source TEXT NOT NULL DEFAULT '',
    utm_medium TEXT NOT NULL DEFAULT '',
    utm_campaign TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    created_at TIMESTAMPTZ NOT NULL,
    plan TEXT NOT NULL DEFAULT '',
    telegram_chat_id TEXT NOT NULL DEFAULT '',
    amount_usd DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (amount_usd >= 0),
    payment_status TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_leads_created_at
ON public.leads (created_at ASC);

CREATE INDEX IF NOT EXISTS idx_leads_payment_status
ON public.leads (payment_status, created_at DESC);