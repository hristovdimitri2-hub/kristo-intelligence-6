-- Durable Stripe standard-checkout binding and Telegram VIP fulfillment.
-- Development applies this through scripts/post-merge.sh; production schema
-- changes are applied only by Replit Publish.

CREATE TABLE IF NOT EXISTS public.stripe_vip_checkouts (
    checkout_id TEXT PRIMARY KEY,
    customer_email TEXT NOT NULL,
    plan_key TEXT NOT NULL,
    expected_amount_cents INTEGER NOT NULL CHECK (expected_amount_cents > 0),
    currency TEXT NOT NULL CHECK (currency = lower(currency)),
    source TEXT NOT NULL,
    campaign TEXT NOT NULL,
    link_token TEXT NOT NULL UNIQUE,
    payment_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (payment_status IN ('pending', 'paid')),
    created_at TIMESTAMPTZ NOT NULL,
    paid_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_stripe_vip_checkouts_customer
ON public.stripe_vip_checkouts (customer_email, payment_status, created_at DESC);

CREATE TABLE IF NOT EXISTS public.stripe_webhook_events (
    event_id TEXT PRIMARY KEY,
    checkout_id TEXT NOT NULL
        REFERENCES public.stripe_vip_checkouts(checkout_id),
    event_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing', 'completed', 'failed')),
    processing_token TEXT,
    received_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_stripe_webhook_events_checkout
ON public.stripe_webhook_events (checkout_id, received_at DESC);

ALTER TABLE public.stripe_webhook_events
    ADD COLUMN IF NOT EXISTS processing_token TEXT;

CREATE TABLE IF NOT EXISTS public.stripe_vip_deliveries (
    checkout_id TEXT PRIMARY KEY
        REFERENCES public.stripe_vip_checkouts(checkout_id),
    telegram_chat_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending_link'
        CHECK (status IN (
            'pending_link', 'pending_payment', 'pending_delivery',
            'invite_created', 'invite_sent', 'invite_creation_failed',
            'invite_delivery_failed'
        )),
    invite_link TEXT NOT NULL DEFAULT '',
    invite_expires_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT NOT NULL DEFAULT '',
    delivery_lock_until TIMESTAMPTZ,
    delivery_lock_token TEXT,
    updated_at TIMESTAMPTZ NOT NULL
);

-- Keep the migration safe when a development workspace applied an earlier
-- fulfillment draft before invite expiration and delivery locking were added.
ALTER TABLE public.stripe_vip_deliveries
    ADD COLUMN IF NOT EXISTS invite_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS delivery_lock_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS delivery_lock_token TEXT;

CREATE INDEX IF NOT EXISTS idx_stripe_vip_deliveries_retry
ON public.stripe_vip_deliveries (status, updated_at);