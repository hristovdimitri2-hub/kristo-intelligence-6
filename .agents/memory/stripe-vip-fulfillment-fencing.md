---
name: Stripe VIP fulfillment fencing
description: Durable concurrency rules for recoverable Stripe webhook and Telegram VIP delivery work.
---

Stripe VIP fulfillment uses separate owner tokens for webhook processing and Telegram delivery. A time-based lease is only a recovery mechanism; every completion, failure, delivery-state update, and lock release must verify the token held by the worker that acquired the lease.

**Why:** After a stalled worker's lease expires, a new worker may safely reclaim the work. Without ownership fencing, the old worker can resume and overwrite the new worker's state, acknowledge a webhook prematurely, or cause duplicate invite delivery.

**How to apply:** Any future retry, reconciliation, or asynchronous fulfillment path must mint a new owner token on claim, require it for durable state transitions, renew it before bounded external calls, and treat a failed ownership check as a no-op/retryable outcome.