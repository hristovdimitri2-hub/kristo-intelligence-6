---
name: x402 proof delivery fencing
description: Replay-safe delivery and hostile-input handling for x402 proof settlement.
---

Treat a paid x402 challenge as a one-time utility delivery right. A duplicate proof for an already settled challenge must never execute the paid utility again.

**Why:** Settlement idempotency protects revenue attribution, but allowing an accepted proof to reach the executor repeatedly gives a caller unpaid repeat execution and can trigger provider-side costs.

**How to apply:** Reject duplicate settlements before execution with a stable conflict response. Keep proof decoding and numeric-field parsing inside explicit client-error boundaries so hostile headers cannot become framework errors or leak internals.