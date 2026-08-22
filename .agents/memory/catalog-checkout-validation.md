---
name: Catalog checkout validation
description: Boundary validation rules for catalog Stripe checkout and entitlement access exchange.
---

Validate catalog checkout and access-exchange JSON at the HTTP boundary before writing a lead or invoking the payment provider. Accept only documented fields with bounded, typed values and structurally valid identifiers.

**Why:** Loose public payment input can create malformed CRM records, provider-side failures and unnecessary abuse work. A valid-looking but unknown checkout identifier is an authorization failure; a malformed identifier is a client input failure.

**How to apply:** Keep the checkout field allowlist explicit, normalize valid email input consistently, and reject unknown or oversized fields. Preserve the distinction between `400` malformed input and `403` valid request without an active entitlement.