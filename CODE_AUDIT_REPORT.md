# Kristo Intelligence v6 — Code Audit

**Audit date:** 2026-08-19  
**Repository:** `https://github.com/hristovdimitri2-hub/kristo-intelligence-6`  
**Scope:** Python Flask application, payment/CRM integrations, blockchain listener and wallet, Telegram/AI/market-data services, tests and deployment configuration.

## Executive summary

The repository is a feature-rich Flask service for Base/USDC market intelligence and sales operations. The code compiles, and the CRM data layer has a basic passing smoke check when exercised directly. However, it should **not be considered production-ready** until the payment and administrative security boundaries are fixed.

The most important issues are:

1. **Critical:** Stripe webhook requests are accepted without signature verification, so anyone can mark an existing lead as paid.
2. **Critical:** CRM/admin endpoints and the sales-admin page expose lead emails, payment status and pipeline data without authentication.
3. **High:** The x402 paywall can be bypassed by spoofing `Referer`, and payment is advertised as verified without a request-level payment proof/settlement mechanism.
4. **High:** The app starts three infinite background loops at import time. Under Gunicorn with multiple workers this creates duplicate monitors, duplicate API traffic and duplicate Telegram activity.
5. **High:** Runtime state (sales history, usage counters, VIP subscribers, stats) is in memory and disappears on restart; multiple workers do not share it.
6. **Medium:** The current Replit environment has no installed Python dependencies, so the Flask app and test suite could not be started here. `python -m compileall` passes.
7. **Medium:** OpenRouter is not integrated. The only LLM path is configured for GLM via `GLM_API_KEY`; `OPENROUTER_API_KEY` is currently ignored.

## Findings

### AUD-001 — Unauthenticated Stripe webhook (Critical)

**Evidence:** `main.py:971-986` parses arbitrary JSON and calls `crm_store.mark_paid(...)`. `StripeCheckoutService` reads `STRIPE_WEBHOOK_SECRET` at `integrations/stripe_checkout.py:17`, but the handler never uses it.

**Impact:** An attacker can POST a fabricated `checkout.session.completed` event for any email already in the CRM and set its payment status to `paid`, including an arbitrary amount and plan. This can unlock paid functionality or create false financial records.

**Recommendation:**

- Read the raw request body with `request.get_data()`.
- Require `Stripe-Signature`.
- Verify with `stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)`.
- Reject requests when the webhook secret is missing in production.
- Accept only the event types needed by the product.
- Validate the Stripe session ID, payment status, currency, amount and metadata against the locally created checkout session.
- Store processed event IDs with a unique constraint for idempotency.

### AUD-002 — Admin and CRM data exposed publicly (Critical)

**Evidence:** `main.py:919-942` exposes `GET /api/leads`; `main.py:1008-1017` exposes `/api/admin/leads`; `main.py:1020-1080` renders `/sales/admin`. There is no authentication or authorization middleware anywhere in the route path.

**Impact:** Anyone can enumerate customer email addresses, campaigns, plans, statuses and payment amounts. `POST /api/leads` and `POST /api/funnel/track` also allow unauthenticated data creation and overwrite by email.

**Recommendation:**

- Put admin routes behind a real identity provider or a server-side admin session.
- Require authentication and role checks for all CRM reads and writes.
- Do not use a static query parameter or client-provided header as the only admin control.
- Return only the minimum fields needed; mask email addresses in operational dashboards.
- Add rate limiting, audit logs and CSRF protection for browser-based admin mutations.

### AUD-003 — Spoofable dashboard paywall bypass (High)

**Evidence:** `main.py:677-685` treats any request whose `Referer` contains `/dashboard` as trusted; `main.py:709-713` then bypasses the paywall.

**Impact:** `Referer` is client-controlled and can be omitted or forged. A caller can send `Referer: https://host/dashboard` to access paid endpoints without payment. Even a browser loaded from the real dashboard receives an unlimited bypass rather than a controlled server-side entitlement.

**Recommendation:**

- Remove the Referer-based exemption.
- Use an authenticated dashboard session with server-side authorization, or make dashboard data explicitly public.
- Implement x402 using a verifiable payment proof/settlement flow tied to the request, wallet and endpoint.
- Do not use IP address as the identity for payment, quotas or discounts.

### AUD-004 — Payment protocol and implementation are inconsistent (High)

**Evidence:** The manifest says payments are verified on-chain (`main.py:1299-1302`), but the paywall only tracks `_free_tier_usage` and `_paid_calls_usage` in process memory (`main.py:580-587`). There is no request handler that consumes a transaction hash/payment proof to grant access. The blockchain monitor records transfers and generates VIP invites, but it does not associate a payment with an API request or customer entitlement.

**Impact:** A payment cannot reliably unlock the API call advertised by the 402 response. Conversely, transfer amounts are treated as sales solely by destination and amount, with no durable entitlement, replay protection or endpoint binding.

**Recommendation:**

- Define one payment flow and protocol contract.
- Verify chain ID, token contract, receiver, amount, sender, transaction receipt status and required confirmations.
- Persist transaction hashes and entitlement expiry in a shared database.
- Bind a verified payment to a wallet/request nonce and prevent replay.
- Document whether access is per-call, monthly or wallet-based, and make manifest prices match middleware constants. Current values conflict (`0.05`/`0.01` in middleware and `0.10` in the manifest/comments).

### AUD-005 — Duplicate background workers under production servers (High)

**Evidence:** `main.py:3231-3267` starts blockchain, trading-agent and Telegram threads when the module is imported. `Procfile` runs `python main.py`; deployment docs also recommend `gunicorn main:app`.

**Impact:** Every Gunicorn worker can start its own infinite loops. This multiplies RPC scans, third-party API calls, Telegram sends and AI calls. It can cause duplicate sales processing, rate-limit exhaustion and inconsistent in-memory state.

**Recommendation:**

- Run the HTTP app and workers as separate processes/services.
- Use a queue/scheduler with a single scheduler instance, or a distributed lock/leader election.
- Never start side-effecting threads at module import.
- Add graceful shutdown and health reporting for each worker.
- If keeping a development-only thread mode, gate it explicitly with an environment flag.

### AUD-006 — Runtime state is not durable or multi-worker safe (High)

**Evidence:** `_sales_history`, `_daily_stats`, `_product_stats`, `_free_tier_usage`, `_paid_calls_usage`, `_vip_subscribers` and `_vip_invites` are in-memory globals in `main.py:103-170` and `main.py:580-587`.

**Impact:** Restarting the process loses sales history, entitlements, quotas, invite state and stats. Separate workers have different views. A process crash during or after a blockchain scan can also cause gaps or duplicate side effects.

**Recommendation:**

- Persist transfers, processed block/log identifiers, payment entitlements, usage and stats in SQLite/PostgreSQL/Redis as appropriate.
- Add unique constraints on `(chain_id, tx_hash, log_index)` and webhook event IDs.
- Store a durable scan cursor and process reorgs with confirmation depth.
- Use database transactions for payment state changes.

### AUD-007 — Blockchain scan cursor can skip transfers (High)

**Evidence:** `main.py:367-390` scans at most 1000 blocks and advances `last_block` to `to_block` even when `get_logs` fails.

**Impact:** A transient RPC error logs a warning and then the cursor advances, permanently skipping payments in that range. The cursor also starts at the current block on each process start, so transfers while the app is down are never recovered.

**Recommendation:**

- Advance the cursor only after a successful scan and durable commit.
- Persist the cursor.
- Start from a configured deployment block or a bounded lookback window.
- Process only finalized blocks and handle chain reorgs.
- Record `transactionHash` plus `logIndex`, not only the transaction hash.

### AUD-008 — Client IP trust and unbounded quota memory (Medium)

**Evidence:** `main.py:589-594` trusts the first `X-Forwarded-For` value; usage dictionaries are never expired.

**Impact:** Clients can evade limits by supplying arbitrary forwarding headers or generate unbounded memory growth with many IP values. Shared NATs can also incorrectly combine unrelated users.

**Recommendation:**

- Configure proxy trust explicitly and use Werkzeug’s `ProxyFix` only for a known proxy count.
- Use authenticated wallet/API identities for quotas.
- Store quotas in Redis or a database with TTLs and atomic increments.
- Add request rate limiting and maximum request body sizes.

### AUD-009 — External data calls are synchronous in request paths (Medium)

**Evidence:** `/api/sales` and `/api/stats` call `get_market_snapshot()` (`main.py:1142-1153`, `main.py:1175-1198`), which makes several sequential upstream HTTP calls with 10-second timeouts (`services/market_data.py:79-109`, `120-144`, `153-174`, `190-229`, `268-288`).

**Impact:** One API request can block for roughly a minute when providers are slow, consuming web workers and causing cascading latency. The same upstream work is repeated by the agent and Telegram paths.

**Recommendation:**

- Refresh market data in a background job and serve the latest cached snapshot.
- Use a shared `requests.Session`, connection pooling and bounded retry/backoff.
- Add per-provider circuit breakers and stale-cache behavior.
- Emit latency, error-rate and cache-hit metrics.

### AUD-010 — Error responses leak internal exception text (Medium)

**Evidence:** `main.py:1240-1242` returns `str(exc)` from Telegram processing to the client. Similar broad exception handling appears throughout integrations.

**Impact:** Provider URLs, configuration details or implementation internals may be disclosed. Broad fallbacks can also hide operational failures and incorrectly report mock success.

**Recommendation:**

- Return stable generic error codes to clients.
- Log detailed exceptions server-side with correlation IDs.
- Distinguish unavailable, rejected and mock/development states in API responses.
- Avoid `except Exception` unless the boundary has explicit recovery behavior.

### AUD-011 — Mock checkout can be mistaken for a completed payment (Medium)

**Evidence:** `integrations/stripe_checkout.py:30-42` returns a successful-looking mock checkout payload when Stripe is unavailable; `main.py:944-968` returns `ok: true` regardless of provider.

**Impact:** Consumers may treat a mock checkout as a real payment path. There is no explicit environment guard preventing mock mode in production.

**Recommendation:**

- Make mock mode opt-in for development, never an automatic production fallback.
- Return `provider_status: unavailable` rather than a checkout that looks ready.
- Fail closed when payment is required and Stripe is not configured.
- Add an explicit environment banner and health check that prevents launch with mock payments.

### AUD-012 — Trading safety controls are recommendations, not execution controls (Medium)

**Evidence:** `services/trading_agent.py:122-130` calls gas checking a placeholder and reads `_CURRENT_GAS_GWEI` from an environment variable. `evaluate()` only returns decisions; execution safety is not enforced in this class.

**Impact:** If future code enables automatic execution, gas and exposure assumptions may be stale or bypassed. Numeric environment parsing can also crash startup/cycles on malformed values.

**Recommendation:**

- Fetch gas and wallet/exposure state from trusted live sources immediately before execution.
- Enforce limits in the transaction execution layer, not only in decision generation.
- Require explicit chain/environment allowlists and a dry-run approval gate.
- Validate all numeric configuration values at startup and fail closed.

### AUD-013 — OpenRouter secret is unused (Medium)

**Evidence:** `config.py:45-49` only reads `GLM_API_BASE`, `GLM_API_KEY` and `GLM_MODEL`; `services/ai_engine.py:23` imports those names. Repository search found no `OPENROUTER_API_KEY`.

**Impact:** Adding `OPENROUTER_API_KEY` to Replit Secrets does not enable AI calls. The service silently uses the offline bulletin unless `GLM_API_KEY` is set.

**Recommendation:**

- Either document GLM as the supported provider, or add explicit OpenRouter configuration:
  `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`, and a supported model.
- Keep provider selection explicit and report provider/model in health diagnostics without exposing secrets.
- Add mocked tests for timeout, malformed response and provider fallback behavior.

## Functional and performance observations

- `python -m compileall -q .` passed.
- `pytest` could not run because `pytest` is not installed.
- The Flask app could not be imported in the current environment because `flask`, `requests`, `python-dotenv`, `web3` and `python-telegram-bot` are not installed. `requirements.txt` declares them, but dependency installation/workflow setup is incomplete.
- `tests/test_sales_system.py` is a script-style test that mutates the repository database and does not assert response status codes or returned payload correctness. It also posts an unsigned Stripe webhook, which would validate the current vulnerability rather than the production contract.
- The repository contains a checked-in `data/crm_sales.db`; production data should not normally be committed or used as the default mutable database.
- The application embeds very large HTML documents in `main.py` through `render_template_string`, making the entry point difficult to test and maintain. Moving templates/static assets out of the entry point would improve maintainability, but should follow the existing stack rather than trigger a broad migration.

## Recommended remediation order

1. Add authentication/authorization to admin and CRM routes.
2. Implement strict Stripe signature verification, event idempotency and amount/metadata validation.
3. Replace Referer/IP-based authorization with server-side entitlements and a real x402 proof flow.
4. Move payment, transfer and entitlement state to a durable shared store; make blockchain scanning resumable and reorg-aware.
5. Split HTTP serving from background workers and eliminate import-time side effects.
6. Install dependencies, add a reproducible test command, and add security regression tests for all findings above.
7. Move market-data refreshes off request paths and add rate limiting, timeouts, metrics and circuit breakers.
8. Wire OpenRouter explicitly if that is the intended AI provider, then add provider contract tests.

## Suggested acceptance criteria before production

- Unauthenticated requests to `/api/leads`, `/api/admin/leads` and `/sales/admin` return 401/403.
- Invalid, missing, replayed and altered Stripe signatures are rejected.
- A payment cannot unlock an endpoint without a verifiable, non-replayed proof.
- Restarting a worker does not lose sales, entitlements or scan progress.
- Running two web workers does not create duplicate background loops.
- A failed RPC scan is retried without advancing the cursor.
- All declared tests run from a clean checkout with one documented command.
- Production health reports fail when payment is in mock mode or required secrets are absent.