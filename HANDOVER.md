# Handover — 09.11.2026, end of session

Written to be read by a fresh session that has none of this conversation's
context. Everything below was measured, not inferred. If something here
contradicts what you observe, trust the observation and say so.

## What works, verified live

| | state |
|---|---|
| Payments (HTTP) | settling, ~1.5s end to end, through the CDP-first chain |
| Payments (MCP) | **an agent can now buy a tool in-session** — was impossible until 09.11 |
| CDP Bazaar | **6 routes listed**, each with real `payers=1` |
| Test suite | **1218 green** |
| Board | `/health` 200, `/api/dashboard/data` 200, `degraded: []` |

## THE OPEN LEAD — why CDP does not index us as MCP

This is the one live thread. Everything else is closed.

**The gap, measured:** the catalog carries `type=mcp` with **515 resources**. Ours:
**0**. Our six HTTP routes are in it; no MCP tool is.

**What was already fixed** (all deployed, all tested):

1. Our MCP tools advertised `extensions.bazaar.info.input.type = "http"` because
   `_x402_challenge_core` is shared with the HTTP path. An MCP tool declaring
   itself HTTP is not an MCP resource. Now retyped to `type: "mcp"` with
   `toolName`, `transport`, `example`, `inputSchema` —
   `_retype_bazaar_for_mcp()` in `app/blueprints/discovery.py`.
2. The MCP tool could not be BOUGHT at all: `tools/call` returned the challenge
   and never accepted a payment. Now it forwards the caller's own header to the
   HTTP route and serves the route's payload — but only when a **settlement
   actually happened** (`_serve_paid_mcp_tool`).
3. `resource.url` for an MCP challenge was the HTTP route, so CDP filed the
   settlement under the endpoint. Rewritten to `<scheme>://<host>/mcp#<tool>`.

**The settlement is real and goes through CDP.** Logged, 09.11 14:14 UTC:

```
x402 settle phase cdp-jwt       0.00s  ok
x402 settle phase cdp-settle    0.68s  ok
standard x402 settled via cdp: tx=0x7bcde0d2...
```

**And the catalog still shows 0 MCP, with `/api/v1/whaleflow` gaining a second
call instead.** So the settlement was filed under the route again, one hour after
the identity fix was deployed and after a further paid MCP call at ~16:45.

### The next thing to check, specifically

**Does the CDP facilitator index from `paymentPayload.resource` or from
`paymentRequirements.resource`?**

- If the former, fix (3) should have worked and something else is wrong.
- If the latter, the identity must be set on the **requirements** too — that is
  what `_merged_requirements()` sends, and it currently carries the HTTP path's
  terms.

Where to look: `services/connectors.py`, the `body = {"x402Version": 2,
"paymentPayload": payload, "paymentRequirements": payment_requirements}` in
`settle_standard_payment`, around lines 984 and 1034.

**Read the facilitator's actual reply before changing anything.** That is how the
`accepted` bug was found after hours of guessing, and it is the cheapest step:

```python
connectors._facilitator_post(
    "https://facilitator.payai.network", "settle", body)
```

`_forensics/repro_400.py` does exactly this and prints the body.

## Hard-won facts — do not relearn these

- **`accepted` (singular, ONE OBJECT) must travel in the payment payload.** A
  spec-strict facilitator refuses without it:
  `"accepted: Invalid input: expected object, received undefined"`. This is why
  PayAI never settled for us and everything went through CDP. `echo_extensions`
  in `scripts/demo_sponsored_pay.py` now adds it. **Build payloads with that
  helper, never by hand** — hand-building is how `_forensics/pay_mcp_tool.py`
  missed the field for two rounds.
- **A 200 is not proof of payment.** The MCP forward arrives from `127.0.0.1` and
  the free tier grants on IP, so `PAYMENT-SIGNATURE: FAKE` returned real data
  until the settlement check was added.
- **Import `eth_account` and `web3` at boot.** Deferred, the first buyer's payment
  compiles 417 modules — ~20s on a 0.1-CPU instance, which is what made
  `_local_recover_signer` look like it hung.
- **The catalog fluctuates.** Measured 34,156 → 33,058 → 31,000-ish, and
  `nev3r` in the x402 WG tracks the same thing (28,221 ↔ 101,965). A scan that
  finds fewer of our resources than yesterday is probably this, not a regression.
- **Bound every step of the payment rail.** `X402_STEP_DEADLINE_SECONDS` (verify,
  20s), `X402_NONCE_SEARCH_SECONDS` (5s), `X402_SETTLE_DEADLINE_SECONDS` (50s —
  it MUST exceed the facilitator chain's own 15s × 2 budget, or the wrapper is the
  failure). Total 75s, under gunicorn's 120s, asserted by a test.
- **gunicorn `--timeout 120`.** A request that has not answered by then gets its
  worker KILLED, taking every other in-flight request with it. That is what the
  repeated `Background threads started` lines were.
- **Deploy via per-key `PUT /env-vars/{KEY}`.** `PUT /env-vars` REPLACES THE WHOLE
  SET and once destroyed all 33 production variables.

## Never touch

Prices we charge, `payTo`, the receiver (`X402_RECEIVER_ADDRESS`), the commission,
any 402 envelope, `secrets/`, `config.py`, `.env`. `payTo` is a platform invariant:
third-party reliability scoring checks it, and Чет Паркър (PayAPI Market) gave it
as a condition.

## The owner's own words worth keeping

- He could not tell where the money came from on the board. It was because
  `DEMO_PRIVATE_KEY` classified as `external` → "истински клиент", so nine
  self-payments read as nine customers. Fixed: class `own_key` →
  "нашият демо ключ — не е клиент". **A board that cannot separate a customer
  from a test cannot be steered by.**
- He is in the x402 `#wg-domain-discovery` Slack, where the standard is being
  written. `takeshi` (vet402.com) asked whether discovery should carry
  **delivery after settlement** — which our board already models, since it records
  `settled` before the delivery checks because a 425 is a buyer who paid.
  `nev3r` tracks the catalog fluctuation. Both are places our measurements are
  directly relevant. **Nothing external is posted without his explicit "Да".**
