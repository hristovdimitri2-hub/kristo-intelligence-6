### Endpoint URL

https://kristo-intelligence-api.onrender.com/api/v1/verify-seller

### Your relationship to this endpoint

I operate it

### What looks wrong?

The grade is C, and the reason on the page is the only one that matters here:
**"Test payments — Not yet paid-tested: in the test queue (C until then)."**
Nothing about uptime or failed checks — your page says every check in the last
7 days passed, and the score is 74/100.

What I would like is the paid test that clears it. The endpoint is $0.01, so it
is inside your free re-test band.

While filing this I also fixed the one real defect your check found, and I want
to record it here because your report is the only reason we found it:

> **Browser agents** — Can't pay it yet: CORS headers missing (server-side agents are fine)
>
> "The CORS preflight (OPTIONS) is refused with HTTP 402, so a browser can't send
> the paid retry. Fix: answer OPTIONS with 204 and the CORS headers."

You were right, and it was worse than a warning — **no in-page agent could reach
the paid retry at all.** Reproduced before changing anything: `OPTIONS` returned
the canonical `402` carrying `Access-Control-Allow-Origin` but **no**
`Access-Control-Allow-Methods` and **no** `Access-Control-Allow-Headers`.

Fixed. `OPTIONS` now answers `204` before the paywall can challenge it, with the
payment headers listed. Verified against the live host:

```
HTTP/1.1 204 No Content
access-control-allow-methods: GET, HEAD, POST, OPTIONS
access-control-allow-headers: Content-Type, Accept, Authorization,
  PAYMENT-SIGNATURE, payment-signature, X-PAYMENT, x-payment,
  PAYMENT-REQUIRED, payment-required, X-Payment-Proof, x-payment-proof, …
access-control-allow-origin: *
access-control-max-age: 600
```

Two related fixes in the same pass, both measured rather than guessed:

* a **wrong method** used to be settled and *then* refused with a `405`. A real
  buyer (`JarvisClaw-Federation/1.0`, 2026-10-21) paid $0.003 and got the 405.
  A method the route does not answer is now refused **before** any credential is
  read, and nothing settles;
* a request that cannot be answered (missing a required parameter) is likewise
  refused before settlement, so a `400` never costs the buyer anything.

One more thing that should make a re-test read better than the last one: our
listing had nothing to compare a response against. Our Bazaar output example
carried only `{type, description}` and no field list, so a delivery check could
only say `nothing_to_compare`. It now publishes the real response fields.

We also publish our payout wallet at
`https://kristo-intelligence-api.onrender.com/.well-known/paycheck.json` as
`{"payTo": ["0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f"]}` — the shape your
docs ask for, so a future rotation is a recognised event rather than an
unconfirmed change.

### Timestamps or evidence (optional)

- CORS fix verified live: `OPTIONS /api/v1/verify-seller` → `204` with
  `Access-Control-Allow-Methods` and `Access-Control-Allow-Headers`.
- `POST /api/v1/signal` → `405` with `payment_taken: false`.
- The scout receipt Settled holds for this service reads
  `checks.verdict: nothing_to_compare` with the note *"the listing has no sample
  response to compare against"* — the listing fix above is aimed at that.
- `/.well-known/paycheck.json` returns `200`.

### Before submitting

- [X] I looked at the endpoint's "Recent failed checks" section.
