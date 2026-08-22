---
name: Anonymous trial identities
description: Privacy-preserving abuse controls for free catalog utility requests.
---

Bind each anonymous free utility request to a server-signed, HttpOnly browser identity and keep new identity issuance bounded per network. Store only a keyed digest of that random identity in the durable usage ledger.

**Why:** IP-only trials create false positives on shared networks and invite spoofing or privacy-heavy raw-address retention. Cookie-only trials are trivial to reset for unlimited free use.

**How to apply:** Verify the signature before accepting an existing identity; issue a new secure cookie only within the bounded network issuance window. A missing, tampered, or exhausted identity must not bypass the paid x402/Stripe path.