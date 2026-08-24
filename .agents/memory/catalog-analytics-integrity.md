---
name: Catalog analytics integrity
description: Rules for trustworthy catalog revenue, conversion, and popularity metrics.
---

Catalog revenue must be credited only after a signed Stripe event confirms a settled payment and the event matches a server-created checkout's SKU, buyer, and expected price. Treat completion and delayed-payment success consistently, and keep attribution idempotent. Agent purchases create agent-scoped, time-bounded entitlements rather than generic Telegram VIP membership.

**Why:** Client metadata, premature checkout events, and duplicate delivery can otherwise fabricate revenue, grant access incorrectly, and corrupt conversion/ranking data. An expiring sales claim must map to an expiring authorization rule, not only an expiring invite link.

**How to apply:** Preserve server-side checkout registration and payment-event idempotency when changing checkout or webhook flows. Check agent entitlements at the service access boundary and run expiry cleanup. Anonymous product clicks need bounded ingestion. Keep metrics that lack a real execution source (such as call counts before SKU endpoints exist) visible but excluded from popularity ranking.