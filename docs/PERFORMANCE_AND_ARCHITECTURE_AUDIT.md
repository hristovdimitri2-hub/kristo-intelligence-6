# PERFORMANCE & ARCHITECTURE AUDIT — kristo-intelligence-6

**Date:** 2026-11-03 · **Branch:** `main` · **HEAD during the audit:** `66a0ce4` (2026-11-02, "step2: echo extensions + resource in x402 payment payload")
**Local root:** `<repo>` (the path is removed — the repo is public)
**Remote:** `https://github.com/hristovdimitri2-hub/kristo-intelligence-6` (origin, main)
**Scope:** 345 `.py` files (excluding `venv/`), 5859 lines of `main.py`, 44 `@app.route` + 26 blueprint routes, 89 files in `docs/`, 55 files in `tests/`.

> **What was NOT touched:** the audit is **read-only**. Not a single file of code, the x402 headers, pricing, `payTo`/the commission or the protected configurations was changed. `secrets\` and `.env` were **not opened** (only `.env.example`). There is no `git add/commit/push`. The only file written is this report.
> **Why this matters:** `main` → auto-deploy to Render. Every recommendation below is a **proposal**, not a change already made; it is applied through a separate gate.

---

## 0. Index of findings (by priority)

| ID | Sev. | Finding | Evidence |
|---|---|---|---|
| **F-01** | 🔴 Critical | Paid products are handed out for free through `/api/dashboard-stats` and `/api/dashboard/data` | `main.py:142-157, 3427-3428, 3986-3989, 5573-5582` |
| **F-02** | 🔴 Critical | `accepted.amount` (from the client) replaces the signed `authorization.value` → underpayment | `services/connectors.py:195-200` |
| **F-03** | 🔴 Critical | When the receipt is unreadable, the paid call is delivered (fail-open) | `main.py:3082-3110, 3132, 3158-3159` |
| **F-04** | 🔴 Critical | A free GET performs 4 WRITES in the replay-lock table (`payment_guards`) | `integrations/dashboard_store.py:1542-1555` |
| **F-05** | 🟠 High | A reorg never reverses a credited payment | `main.py:2631-2690` |
| **F-06** | 🟠 High | Settlement is accepted by nonce **without** a depth check | `main.py:2321-2435` |
| **F-07** | 🟠 High | Zero rate limit on the payment path; gas spend controlled by an anonymous client | `main.py:1406-1416, 3431-3523` |
| **F-08** | 🟠 High | A single RPC provider, with no fallback and no cooldown on 429 | `config.py:57` |
| **F-09** | 🟠 High | One shared DB connection under a global lock, opened without `connect_timeout` | `integrations/dashboard_store.py:307, 334-340, 342-372` |
| **F-10** | 🟠 High | `/health` depends on the DB and returns 503 → restart of the only worker → loop | `app/blueprints/discovery.py:32-76` |
| **F-11** | 🟠 High | `/mcp/sse` (free, unlimited) pins 1 of 8 threads for ≥15 s → full DoS | `app/blueprints/discovery.py:665-717` |
| **F-12** | 🟠 High | Unbounded thread-per-payment reorg watch + unchunked `eth_getLogs(5000 blocks)` | `main.py:3217, 2321-2435, 2621-2628` |
| **F-13** | 🟠 High | The raw RPC text (`rpc_error`) is published on a free route | `main.py:643 → 3792 → 3986` |
| **F-14** | 🟠 High | The Telegram bot token can leak into the logs through `requests` exceptions | `services/telegram_sales.py:72, 80-81, 198-212` |
| **F-15** | 🟠 High | `secrets/` is baked into the Docker image (`.dockerignore` has no entry) | `Dockerfile:29`, `.dockerignore:47-50` |
| **F-16** | 🟡 Medium | X-Payment-Proof is a replayable bearer token over publicly published data | `main.py:2879-2900` |
| **F-17** | 🟡 Medium | A single payment can deliver twice under concurrency | `main.py:2438-2470` |
| **F-18** | 🟡 Medium | `payment.amount_usdc` returns atomic units under a USDC name (5000 instead of 0.005) | `main.py:1723-1733` |
| **F-19** | 🟡 Medium | The advertised prices drift from the 402 challenge across 5+ surfaces | `discovery.py:866-892, 1057, 1276, 1454, 1528` |
| **F-20** | 🟡 Medium | "$29 VIP — unlimited access" is not implemented anywhere | `discovery.py:873-881` |
| **F-21** | 🟡 Medium | `FREE_TIER_LIMIT` defaults to 1; production relies on env | `main.py:129-134` |
| **F-22** | 🟡 Medium | The statistics aggregate: 12 queries, 5 full scans, ~528 ms locally / ~41 s in production, with no cache on 2 of 3 routes | `main.py:3944-3945, 4067-4071, 5573-5582` |
| **F-23** | 🟡 Medium | Blocking budgets on the paid path > gunicorn `--timeout 120` (a single worker!) | `main.py:2596-2598, 3082-3096`, `connectors.py:390-410` |
| **F-24** | 🟡 Medium | Stripe SDK without a timeout: 80 s × 3 attempts ≈ 4 min on the checkout path + unbounded pagination | `stripe/_http_client.py:512`, `stripe/__init__.py:39` |
| **F-25** | 🟡 Medium | `_stripe_payment_snapshot_loop` is the only loop without `try/except` → it dies silently | `main.py:1113-1121` |
| **F-26** | 🟡 Medium | `/api/launch/health` without auth: lead count, paying customers, Stripe mode | `main.py:5198-5216` |
| **F-27** | 🟡 Medium | `/api/connectors` exposes the hot wallet and the internal settlement route | `services/connectors.py:944-947, 988` |
| **F-28** | 🟡 Medium | The Render configuration is not versioned (there is no `render.yaml`); the worker count is security-relevant | `Procfile:1`, `Dockerfile:46` |
| **F-29** | 🟡 Medium | The admin token falls back to `SESSION_SECRET` (no key separation) | `main.py:178, 1802-1813` |
| **F-30** | 🟡 Medium | `_t2_render_env_check.py` prints live env values (RPC key, ADMIN token) | `scripts/_t2_render_env_check.py:30-45` |
| **F-31** | 🟡 Medium | Unbounded in-RAM maps + no indexes on `user_agent`/`source`/`funnel` | `main.py:1319, 1345, 2260`, `dashboard_store.py:659-733` |
| **F-32** | 🟢 Low/Med | A manually maintained guard list with no coverage test | `main.py:137-139` |
| **F-33** | 🟢 Low | `/validation` publishes live paid addresses and a stale "550/550" | `discovery.py:179-203` |
| **F-34** | 🟢 Low | Dead/stale prices: `KRISTO_WHALE_PRICE=0.01`, `KRISTO_RUG_PRICE` outside the map | `config.py:78-79` |
| **F-35** | 🟢 Low | `requirements.lock` does not reproduce `requirements.txt` (`cryptography` is missing, no `--hash`) | `requirements.txt:33`, `requirements.lock` |
| **F-36** | 🟢 Low | `docker-compose.yml` publishes Postgres with a default password | `docker-compose.yml:27, 31-32` |
| **F-37** | 🟢 Low | The volume discount is a no-op (a hardcoded price in the monolith) | `main.py:83, 1476-1478` |
| **F-38** | 🟢 Low | Time zone: the Sentinel weekly report uses local time, everything else is UTC | `services/sentinel.py:464-467` |
| **F-39** | 🟢 Low | The block monitor does not persist its cursor → it misses transfers on restart | `main.py:714-716, 774` |
| **F-40** | 🟢 Low | A duplicate of the whole repo in `.kilo/worktrees/believed-dancer` (~2× disk, risk of "editing the wrong file") | `.git/info/exclude:9` |

---

## 1. Correction of the input premises (important for every subsequent assistant)

The technical description with which the audit was requested **does not match the actual repo**. This is the
first and most important finding, because every instruction based on the description will look for
nonexistent files:

| Claim in the assignment | Reality (verified) |
|---|---|
| `app.py` (FastAPI) | **Missing.** The application is `main.py` — **Flask 3.1.3 + gunicorn 26.1.0** (`requirements.txt:11-12`, `main.py:41, 166`). There is no `fastapi`/`uvicorn` anywhere. |
| `mcp_server.py` (FastAPIMCP wrapper) | **Missing.** The MCP server is embedded in `app/blueprints/discovery.py` (routes `/mcp/sse`:670, `/mcp/message`:720, `/mcp` POST/DELETE:742, `/mcp` GET:766, `/mcp.json`:1026, `/api/mcp/manifest`:835). |
| `auth.py`, `guard.py` | **Missing.** The paywall is `@app.before_request def _x402_paywall()` — `main.py:3396`. The guard logic is in `main.py` + `integrations/dashboard_store.py` (the `payment_guards` table). |
| `gas.py`, `wallet.py`, `facilitator.py`, `rpc.py` | **Missing.** There is only `blockchain/wallet.py` (8594 B). Gas/settlement/facilitator are in `services/connectors.py` (46329 B); the RPC logic is in `integrations/dashboard_store.py` + `main.py`. |
| `render.yaml` (auto-deploy from main) | **Missing and it has never been in git.** `git log --all -- render.yaml` → empty; `git grep "render.ya?ml"` → 0 hits in tracked files. There is `Procfile:1`, which Render does **not** consume. |
| "35 scanning routes" | **No such claim exists in the repo.** In reality: **6 paid** x402 routes (`main.py:89-100, 2071-2134`), 27 free in the allow-list, 44 `@app.route` in `main.py` + 26 blueprint routes. |
| "550+ tests pass" | ✅ **Confirmed initially:** `550 passed, 1 warning in 180.46s` (full run, Python 3.12.10, pytest 9.1.1). |
| "x402 headers, pricing, security — untouched" | ✅ Observed: **nothing was changed.** |
| Glama "A4.7 / 100% uptime / 47 days" | 4.7 appears as TDQS, but the same repo says **"A 3.6/5.0"** (`PROJECT_STATUS.md:1199,1204`; `PROJECT_CHRONOLOGY.md:128`). The strings "100% uptime" and "47 days" **do not exist** in the repo. |
| README: "zero payment incidents" | ❌ **False.** `PROJECT_STATUS.md:34-45` documents INCIDENT 14.09: an external payer paid $0.003 to `/api/v1/signal` (tx `0x06b4c8f2…58ce7`, block 51313253) and received **HTTP 401**, with no claim and no delivery. |

**Conclusion:** the description in the assignment appears to be from an earlier/different version of the
product. All references to `app.py`, `mcp_server.py`, `auth.py`, `guard.py`, `gas.py`, `facilitator.py`,
`rpc.py`, `render.yaml` must be treated as invalid. The documentation in the repo does **not** refer to
these files (verified with a full search) — the discrepancy is only in the assignment.

---

## 2. Actual architecture

### 2.1 Code map (without `venv/`, `.git/`, `.kilo/`)

| File | Size | Role |
|---|---|---|
| `main.py` | 272 244 B / **5859 lines** | Monolith: Flask app, x402 paywall, 44 routes, wallet state, background threads, 140 top-level functions |
| `app/blueprints/discovery.py` | 74 072 B | Discovery + **MCP server** + OpenAPI/llms.txt/robots/sitemap/glama.json, `/health`, `/validation`, 6 `/sample` routes |
| `integrations/dashboard_store.py` | 124 935 B | Durable store (SQLite **or** Postgres): sales, requests, payment_guards, whaleflow, meta watermarks |
| `integrations/stripe_checkout.py` | 20 057 B | Human subscriptions (the second, off-chain rail) |
| `integrations/catalog_store.py`, `crm_store.py`, `research_store.py`, `verified_sales.py` | 46 370 / 30 029 / 12 197 / 5 827 B | Catalog of agents, CRM/leads, research, seeded verified sales |
| `services/connectors.py` | 46 329 B | x402 facilitator chain (self-broadcast → CDP → PayAI), EIP-712 precheck, broadcast |
| `services/telegram_sales.py`, `sentinel.py`, `market_data.py`, `verifier.py`, `arb_radar.py`, `signal_track_record.py`, `trading_agent.py`, `coingecko.py`, `defi_signals.py`, `base_listener.py`, `ai_engine.py` | 45 158 … 3 470 B | Sales via Telegram, Sentinel monitoring/reports, CoinGecko/DEXScreener, signal verification, arbitrage, track record |
| `blockchain/wallet.py` | 8 594 B | Base wallet, USDC transfers, `pay_request_fee()` (**dead code**, no callers) |
| `src/nexus/*` | 7 files | The NEXUS "intelligent" layer (`mount_nexus_engine`) |
| `config.py` | 4 819 B | Single source of prices/addresses (`KRISTO_*_PRICE`, `BOUND_BASE_FEE_RECEIVER`) |
| `tests/` | 55 files | 550 tests |
| `docs/` | 89 files / 0.57 MB | 46 `.md` + 26 probe `.py` + JSON/PNG/PDF |

### 2.2 Execution topology

```
Render / Docker → gunicorn --workers=1 --threads=8 --timeout=120 main:app   (gthread, 1 process)
   ├── 8 threads = the ENTIRE HTTP capacity (every blocking call = −12.5% capacity)
   ├── 11 background threads in the SAME process (monitor, dashboard scan, whale scan, agent,
   │    catalog, stripe snapshot, arbitrage, sentinel, keep-alive, reorg-watch-per-call …)
   └── in-RAM state: free-tier counters, `_verified_payments`, caches, `_lock`
```

- `Procfile:1`, `Dockerfile:46`, `DEPLOYMENT.md:96`, `DEPLOYMENT_CHECKLIST.md:37` are consistent on **1 worker / 8 threads**.
- `PROJECT_STATUS.md:107` claims that production actually runs on `python main.py` (Werkzeug), `numInstances=1` — a **discrepancy** that needs to be verified.
- The only safeguard against thread duplication is `KRISTO_BG_THREADS_STARTED` (`main.py:5734`) — a **process-local env variable**. With `--workers 2+` or a second instance, all 11 loops and all in-RAM guards double **silently** (`tests/test_background_thread_guard.py` tests only the single-process case).
- `--timeout 120` with `--workers 1` means: **one excessively slow request kills the entire service** (8 threads + 11 loops + all caches).

### 2.3 Request lifecycle (the paid path)

```
HTTP → @app.before_request _x402_paywall()            main.py:3396
        ├─ parked demo surface? → 404                 3417
        ├─ path ∈ X402_FREE_ENDPOINTS (27 entries) → free   3427
        ├─ path ∈ X402_PAID_ENDPOINTS (6 entries, EXACT match) → 3431
        │    ├─ free tier (per-IP, in-RAM) → skip   3433-3442
        │    ├─ Rail 1: PAYMENT-SIGNATURE / X-PAYMENT (EIP-3009)   3450-3488
        │    │     ├─ 402→401 on invalid; 425 on "settled, but the node has not caught up"
        │    │     └─ _try_consume_standard_payment → connectors.verify/settle
        │    └─ Rail 2: X-Payment-Proof (legacy, base64 JSON)      3490-3518
        └─ everything else → NOT checked (deny-by-default is missing)   3525-3526
      → handler (route)
      → @app.after_request _capture_live_request → INSERT into request_log for EVERY response   2185-2216
```

**Key architectural fact:** the protection is an **allow-list by exact `request.path`**, not deny-by-default
and not a per-route decorator. Everything that is not listed in the two sets (`main.py:137-157`) passes
**for free and without any check** — including `/api/launch/health` (F-26) and, more importantly, the mirrored
dashboard routes (F-01).

### 2.4 Data and indexes (measured locally)

`data/dashboard_state.db` — **41 398 272 B**; tables `dashboard_meta, guard_events, meta, onchain_sales, payapi_state, payment_guards, pr_watch_state, request_log, signal_history, vip_invites, whaleflow_events`.
Indexes: `idx_guard_events_ts, idx_onchain_sales_ts, idx_request_log_path, idx_request_log_ts, idx_signal_history_issued, idx_vip_invites_wallet, idx_whaleflow_ts` (+PK).
Rows: `request_log` **46 301**, `onchain_sales` 10, `payment_guards` 3, `guard_events` 128, `whaleflow_events` 0.
**Missing indexes** on `request_log.user_agent` (the `LIKE 'Render/%'` filter), `source`, `funnel`, as well as on `payment_guards.consumed_at`.

---

## 3. The x402 payment rail

### 3.1 What is correct (verified — not touched)

1. **402 envelope parity.** `PAYMENT-REQUIRED` and the body (`accepts`, `accepts[]`, `x402_accepts`, `resource`, `extensions`) are identical **including the key order**, because the body is returned as a raw `Response(json.dumps(body), status=402)`, bypassing Flask's sorting (`main.py:1750-1763, 1791-1793`; test `tests/test_envelope_body_mirror.py:48-62`).
2. **Versioning.** v2 outward (`x402Version: 2`, CAIP-2 `eip155:8453`, atomic strings, `payTo`, `asset`, `extra: {USD Coin, 2}`, `maxTimeoutSeconds: 60` — `main.py:1577-1589`); inward it accepts `PAYMENT-SIGNATURE` (v2) and `X-PAYMENT` (v1), with v2 taking precedence (`main.py:2970-2981`); only the `exact` scheme is advertised.
3. **402 hygiene.** `Cache-Control: no-store` + CORS `Expose-Headers` **only** on status 402 (`main.py:3386-3393`). The six `/sample` routes are static with honest disclaimers — they do not leak live paid data.
4. **Local cryptographic verification.** There is no call to a facilitator on verify (`connectors.py:672-727`); EIP-712 recovery must match `authorization.from`; `auth.to` must be the server's `payTo` (a client cannot redirect the funds to itself); `asset` = the server's USDC; the authorization window is bounded to ≤60 s server-side (`connectors.py:203-225`).
5. **Replay locking.** `payment_guards.tx_hash` PRIMARY KEY + `INSERT … ON CONFLICT DO NOTHING` with rowcount — atomic across threads/processes, the DB is the truth, the RAM cache can only refuse, explicitly fail-closed on a store error (`dashboard_store.py:1313-1370, 439-448`). One tx buys exactly one call and cannot be redirected to another endpoint (the H2 binding), including across equally-priced neighbouring routes.
6. **Delivery accountability.** `delivered_at` is set only on 2xx/3xx (`main.py:3309-3316`), so a paid call whose handler died is recoverable exactly once and then permanently refused; the slot is released on error so that a payment is not lost.
7. **Rail 2 (legacy) amount integrity.** `amount_usdc` from the proof is decoded but **not** trusted (`main.py:2744-2750`); the amount comes from the receipt/the recorded sale; underpayment, wrong payer, unknown tx and endpoint mismatch → 401. Here C2 requires **12** confirmations (`main.py:2487-2493, 2775-2799`) versus 1 on the synchronous rail.
8. **No access caching and no session bypass.** Grants are per-call; `_verified_payments` is only a block-list; nothing is written to the Flask session; `_is_dashboard_request()` has been reduced to `return False` (`main.py:1797-1799`); MCP `tools/call` returns **only payment instructions**, it does not proxy paid data (`discovery.py:635-657`).
9. **Origin of the price in the challenge.** `_x402_challenge_core` derives `payTo`, `asset`, network and atomic amount from `config` (`main.py:74-100, 1577-1588`); the conversion is correct (0.005 → `"5000"`); `X-Payment-Amount-USDC`, `WWW-Authenticate`, `x402_amount` and `accepts[0].amount` match numerically (`main.py:1688, 1705, 1766, 1774`).
10. **Webhooks are fail-closed.** Stripe: `Stripe-Signature` → `Webhook.construct_event(payload, sig, secret)` over the **raw** body bytes; with a missing secret/library → **503**, never a grant (`main.py:4714-4723`, `stripe_checkout.py:313-322`). Telegram: `X-Telegram-Bot-Api-Secret-Token` through `hmac.compare_digest`, a missing secret by itself refuses with 401 (`main.py:4108-4117`).
11. **All admin routes have a guard**, not one of them is accessible without auth (verified individually); all shared secrets are compared with `hmac.compare_digest` (`main.py:1835, 1852, 1859, 4113, 5151, 5177, 2019`); the cookie is `HttpOnly + Secure + SameSite=Lax`, `session.clear()` before login (anti-fixation); `ProxyFix(x_for=0)` deliberately does **not** rewrite `remote_addr` from a header (`main.py:174`); the error handler does not leak a traceback (`main.py:218-236`); SQL is parameterized (the two interpolations are over constants); `MAX_CONTENT_LENGTH` 512 KB is enforced before the handlers.

### 3.2 Findings on the payment rail

#### 🔴 F-01 — Paid products are handed out for free (a broken business model)
`main.py:142-157` contains in the **free** allow-list the two dashboard JSON routes; the paywall lets them
through at `main.py:3427-3428`:

```python
X402_FREE_ENDPOINTS = { ..., "/api/dashboard-stats", "/api/dashboard/data", ... }
if path in X402_FREE_ENDPOINTS:
    return None
```

- `/api/dashboard-stats` (`main.py:3986-3989`) → `_cached_statistics_payload()` → `_statistics_payload(include_recent_requests=False)`; the **only** difference from the paid `/api/stats` (`main.py:4067-4071`) is:
  `if include_recent_requests: payload["recent_requests"] = recent_requests[-50:]` (`main.py:3818-3819`).
  Everything else a client pays for is in the free body: `"history"` (≤100 durable rows), `total_volume_usd`, `total_sales`, `by_token`, `market_data`, `products`, `wallet` (`main.py:3792, 3797-3800`).
- The rows come from `dashboard_store.py:1240-1244` — `SELECT tx_hash, block_number, ts, sender, amount_usdc, payer_class, payer_label, source` — i.e. **the tx hash + the payer + the amount + the internal operator classification of the payer** are public (`main.py:5259-5263`).
- `/api/dashboard/data` (`main.py:5573-5582`) is even worse: `"history": sales["history"][:100]` (`main.py:5452`) and `"whales": whales["whales"]` (`main.py:5503`) — the latter **is** the product that `/api/v1/whaleflow` charges $0.003 for (`main.py:5625-5634`), and with more fields at that. The entire body of `/api/sales` (`main.py:3630-3639`) is a subset of `sections.onchain`.

**Why it is serious:** `X402_PRICE_MAP` is practically unenforceable — a rational buyer compares one free URL
against six 402 responses. Moreover, publishing `(tx_hash, sender)` makes F-16 exploitable. This is a product
decision, not a bug in the code: the paywall cannot be "fixed" while a free mirror exists.

#### 🔴 F-02 — `accepted.amount` replaces the signed value; the actually paid amount is not checked
`services/connectors.py:195-200`:

```python
want_amount = str(requirements.get("amount", ""))
got_amount = str(accepted.get("amount") or auth.get("value") or "")
if want_amount and got_amount.isdigit() and int(got_amount) < int(want_amount):
```

The client-side `accepted.amount` takes precedence over the signed `authorization.value` and the two are
never compared. Proven with the real function (`precheck_payment_payload`, read-only):

```
A  accepted.amount=5000, signed value=1  -> []                                  (passes!)
B  without accepted.amount, signed value=1   -> ['amount below price: 1 < 5000 …']  (caught)
C  non-numeric amount "1_000"                  -> []                                  (the check is skipped)
```

Settlement then broadcasts exactly the signed amount (`connectors.py:360-368`, `abi_encode(... int(auth["value"]) ...)`), and on success `main.py:3182-3213` claims and delivers **without** reading the amount of the Transfer (only `status`, `blockNumber`, `blockHash` are read — `main.py:3076-3120`), recording the sale at the server price (`main.py:3210-3213`). In addition, `_merged_requirements` (`connectors.py:287-294`) passes the **client's** amount on to the facilitator as well.

**Why it is serious:** direct underpayment; every sale through the standard rail may be below the recorded
value. It is reliably exploitable along the self-broadcast path (`WALLET_PRIVATE_KEY` + gas are needed); with
PayAI/CDP it depends on whether their facilitator compares the signed value — protection by accident, not by
design.

#### 🔴 F-03 — When the receipt is unreadable, the paid call is delivered (fail-open)
`main.py:3082-3110` deliberately overrides a failed receipt check:

```python
log.warning("c2_receipt_status_override_delivered: tx=%s receipt status=%s after ~8s poll — fail-open, delivering", ...)
```

When the RPC is down, every `get_transaction_receipt` throws an exception, `receipt` stays `None` through
the 4 attempts and the request continues to the C1 claim and delivery on the facilitator's word alone. The
depth check is skipped as well (`if receipt is not None …`, `main.py:3132`). The whole check is wrapped in a
swallowing block that on an exception **grants** access (`main.py:3158-3159`), so `read_head()` under RPC
trouble also leads to a grant. The legacy rail wraps the **same** helper and sets `deep_enough = False`
(`main.py:2790-2793`) — the asymmetry looks accidental.

#### 🔴 F-04 — A free GET performs 4 WRITES in the replay-lock table
`/api/dashboard/data` (free, `main.py:142-157`) → `_canonical_dashboard_payload` (`main.py:5400`) → `dashboard_db.guard_stats()` → `integrations/dashboard_store.py:1542-1555`:

```
DELETE FROM payment_guards WHERE tx_hash = ?
INSERT INTO payment_guards (tx_hash, endpoint, payer, amount_usdc, consumed_at) VALUES (?,?,?,?,?)
SELECT COUNT(*) … WHERE tx_hash = ?
DELETE … WHERE tx_hash = ?
```

All of them through `_run`, which takes `_pg_lock` (`dashboard_store.py:307, 353` — "one shared, serialised
link") and commits. `templates/dashboard.html:763` calls it with `cache:'no-store'`, and `:800` repeats it
every 45 s on an open tab.

**Why it is serious:** this is **the same lock that `claim_payment_tx` uses for the C1 replay protection**,
on **the same table**. An anonymous poll can delay the replay claim of a paying client; the endpoint can be
spun in a loop for unbounded INSERT/DELETE/WAL; and the code itself documents (`dashboard_store.py:1532-1537`)
that a failed probe is the fail-closed condition under which payments start being refused. **Writing on a
read path is the single most dangerous pattern in the code.**

#### 🟠 F-05 — A reorg never reverses a credited payment
`main.py:2631-2690` re-reads the anchor heights and records `c2_reorg_detected` — **nothing else**. The row
in `onchain_sales` (`dashboard_store.py:812-845`), the claim in `payment_guards` (`:1313-1370`) and the VIP
invite (`main.py:882-898`) survive. The depth of the standard rail is **1** (`main.py:2484`), i.e. the window
is one Base block (~2 s). `tests/test_reorg_watch.py:100-118` explicitly pins down that detection is **not** a
refusal and does not move `blocked_total`.

#### 🟠 F-06 — Settlement is accepted by nonce without a depth check
`main.py:2321-2435` (`_find_settlement_by_nonce`) accepts any `AuthorizationUsed` log from the last 5000
blocks whose receipt contains the matching `Transfer`, checking **only** `receipt.status == 1` — without
`_confirmations_ok` and without comparison with the chain head. It is called from `main.py:3021` before every
settlement: a settlement at the very tip (or one that will be reorged) is accepted and then delivered along
the same path as F-03.

#### 🟠 F-07 — Zero rate limit on the payment path; the gas spend is under an anonymous client's control
`main.py:1406-1416` defines 9 rate-limit scopes; **not one of them covers the paywall**, and `_x402_paywall`
(`main.py:3431-3523`) never calls `_check_rate_limit`. Every request with a validly signed, fresh
authorization leads to: `eth_getLogs` over 5000 blocks (`main.py:3020-3021` → `:2364-2374`), then settlement.
If `WALLET_PRIVATE_KEY` is available, `_self_broadcast_settlement` broadcasts **our** transaction for a buyer
who can deliberately make it revert (zero USDC balance or a bombastic EIP-712 domain — F-16/F-33 context),
i.e. we pay the gas, and it holds the thread for up to 24 s (`connectors.py:390-410`: `deadline = time.time() + 24`, `time.sleep(2)`).

#### 🟠 F-12 — Unbounded reorg watch per payment thread + unchunked `getLogs`
`main.py:3217` starts `threading.Thread(target=_detect_reorgs, …)` from `_try_consume_standard_payment`
(fire-and-forget, with no throttle and no single-flight), while `_read_block_hash` (`main.py:2621-2628`) builds
a **new** `Web3(HTTPProvider(…, timeout=20))` on every call, up to 25 calls inside `_detect_reorgs` → up to 25
new providers and 25 RPC calls per paid call. In parallel, `_find_settlement_by_nonce` does a `get_logs` over
5000 blocks **in one line**, whereas `services/market_data.py:194+` has `_adaptive_get_logs` with window
reduction, which this path does not use. A 5000-block `getLogs` is a classic trigger for 429/timeout, and a
429 exactly there turns "paid and patient" into "paid and failed".

#### 🟡 F-16 — X-Payment-Proof is a replayable bearer token over publicly published data
The fast path (`main.py:2879-2900`) accepts a proof for any tx that is already in `_sales_history`, if the
claimed payer matches the recorded sender:

```python
if recorded_sender != proof["payer"]:
    ... return False
amount = float(s.get("amount_usd", 0.0))
```

The proof itself is unauthenticated base64 JSON (`main.py:2729-2752`: `{payer, transaction_hash, amount_usdc}`),
and **both** halves of the check are published for free by F-01 (the tx hash **and** the sender in ≤100 rows
of history). The test in the repo itself describes the threat model (`tests/test_payment_guards.py:396-429`).
Window: any transfer detected by the monitor but not yet having a row in `payment_guards` (e.g. the 9 seeded
hashes in `integrations/verified_sales.py:58-122`).

#### 🟡 F-17 — A single payment can deliver twice under concurrency
The durable claim is correct, but the recovery slot re-admits a sibling that is still in flight
(`main.py:2438-2470`): the losing `claim_payment_tx` gets False, but `delivered_at` is still NULL (the winner
has not emitted the response yet), so the loser takes the retry slot and delivers as well. Limited to 2
deliveries.

#### 🟡 F-18 — `payment.amount_usdc` returns atomic units under a USDC name
`main.py:1723-1733`: `"amount_usdc": int(atomic_amount),` → for a $0.005 route the body says `5000`, while the
header says `X-Payment-Amount-USDC: 0.005` (`main.py:1766`), and the message says "Send 0.005 USDC"
(`main.py:1719-1722`). `x402_amount` is documented as atomic (`main.py:1705`), but this field is not, and the
body exists precisely so that an agent can construct the payment without documentation (`main.py:1698-1700`).
`tests/test_402_response_headers.py:81` pins down the wrong unit. **An agent that reads only the JSON is
instructed to authorize 5000 USDC for a $0.005 call.**

#### 🟡 F-19 — The advertised prices drift from the challenge
- `discovery.py:866-867`: tier `price_usdc: MICRO_FEE_USDC` (=0.005) with the description "from {KRISTO_SIGNAL_PRICE}" (=0.003) — two different numbers in one object; `:887-892` prices `/api/stats`, `/api/sales`, `/api/bot-status` from `MICRO_FEE_USDC` instead of from the map.
- `discovery.py:1057, 1276, 1454, 1528`: `price_per_call_usdc: X402_FEE_USDC` (a flat 0.005), while `/api/v1/signal` and `/api/v1/whaleflow` charge 0.003.
- `discovery.py:440`: the whaleflow sample says "$0.005", while `KRISTO_WHALEFLOW_PRICE` is 0.003 (`config.py:83`); `:416/:462/:482/:504` are also hardcoded.
- The MCP tools (`discovery.py:535, 555, 576`) advertise `X402_FEE_USDC` for endpoints priced from the map.
- The correct pattern already exists: `discovery.py:950-956` derives from `X402_PRICE_MAP` — it simply has not been applied everywhere.

#### 🟡 F-20 — "$29 VIP — unlimited access" is not implemented
`discovery.py:873-881` sells it at `VIP_MONTHLY_USDC = 29.00` (`main.py:402`), but **not a single route
consults `_vip_subscribers`** (grep: only a write in `main.py:474`, dedup in `:887`, two counters
`:4949/:4980`); the paywall has no subscription branch. The only VIP trigger is a payment ≥
`VIP_THRESHOLD_USDC = KRISTO_VIP_ANALYSIS_PRICE` = **$0.10** (`main.py:406, 882-898`), which issues a Telegram
invite. That is, either a paid promise the API does not fulfil (risk of refund/dispute), or a $0.10 threshold
on a $29 benefit. The invite nav nav is also triggered by any unrelated transfer ≥$0.10 to the receiver.

#### 🟡 F-21 — `FREE_TIER_LIMIT` defaults to 1
`main.py:129-134`: `FREE_TIER_LIMIT = max(0, int(os.getenv("KRISTO_FREE_TIER_LIMIT", "1")))`. Only a comment
claims that production runs with 0. `.env.example` does **not** document this key, nor any x402 key. The
counter is in-RAM, per IP, without pruning (`main.py:1319`); with 1 worker it is consistent, but any scaling
multiplies the free calls. The 402 body publishes `"free_tier_limit": FREE_TIER_LIMIT` (`main.py:1735`).

#### 🟢 F-32 — A manually maintained guard list with no coverage test
`main.py:137-139` (six literals, exact match) is **the only thing** the paywall enforces, while the advertised
list is `REAL_X402_ROUTES` (`:2071-2134`), and the prices are `X402_PRICE_MAP` (`:89-100`). Adding to one list
without the other makes a route free or prices it with the `BASE_FEE_AMOUNT_USDC` fallback (`:1473`). There is
no test asserting `REAL_X402_ROUTES ⊆ X402_PAID_ENDPOINTS` (grep in `tests/` — 0 hits). Today there is no
second route to a paid resource, but the design allows it by construction.

#### 🟢 F-37 — The volume discount is a no-op and is a hardcoded price
`main.py:83` `X402_FEE_USDC_DISCOUNT = 0.01` in a file whose own docstring says "Nothing in this file may
hardcode a price" (`main.py:14-16`), applied as a **ceiling** (`:1476-1478`):
`return min(X402_FEE_USDC_DISCOUNT, base)`. All six prices are ≤ $0.01, so `min(0.01, base) == base` always —
the discount advertised after 10 paid calls never happens. The counter is per-process RAM per IP
(`:1345, 1475`).

---

## 4. Performance and bottlenecks

### 🟡 F-22 — The statistics aggregate: 12 queries, 5 full scans, no cache on 2 of 3 routes
Measured locally over **46 301** rows (`requests_summary`, `dashboard_store.py:659-733`), with `EXPLAIN QUERY PLAN`:

| Query | Time | Plan |
|---|---|---|
| `count_total` | 4.14 ms | covering index `idx_request_log_path` |
| `count_today` | 0.37 ms | index |
| **`noise_total`** | **159.49 ms** | **`SCAN request_log`** |
| `noise_today` | 0.10 ms | index |
| **`by_source`** | **60.76 ms** | `SCAN` + 2× temp B-tree |
| **`by_source_clean`** | **89.32 ms** | `SCAN` + 2× temp B-tree |
| **`by_channel`** | **15.82 ms** | `SCAN` + 2× temp B-tree |
| `by_path_top10` | 61.57 ms | covering index + temp B-tree |
| **`top_user_agents`** | **91.74 ms** | `SCAN` + 2× temp B-tree |
| `hourly_today` | 0.20 ms | index |
| `funnel_grouped` | 44.48 ms | `SEARCH idx_request_log_path` |
| `recent_25` | 0.20 ms | index |
| **TOTAL** | **528.22 ms** | **5 full table + 1 full index scan** |

- The reason: **there is no index on `request_log.user_agent`** (the `LIKE 'Render/%'` filter), nor on `source`/`funnel`.
- In production the scale is different: the code itself notes (`main.py:3944-3945`) "~783K rows, ~22 seq scans", "measured ~41 s live" — above the 30-second timeout of the Sentinel client.
- On Postgres `user_agent LIKE 'Render/%'` **cannot** use a btree → a guaranteed seq scan over 783K rows.
- The 60 s cache covers **only** `/api/dashboard-stats` (`main.py:3951-3955, 3966-3983`). `/api/stats` (`:4067-4071`) and `/api/dashboard/data` (`:5573-5582`) are **uncached**, and `_cached_statistics_payload` deliberately allows duplicate concurrent builds (`:3966-3983`): a TTL expiry + 8 simultaneous hits = 8 × ~41 s of DB work, serialized behind `_pg_lock`.
- In addition, `_sanitize_json` (`main.py:1482-1496`) recursively re-creates the whole tree of **every** response.
- **F-31:** `payment_guards` is pulled entirely into Python on every dashboard poll, **twice** (`dashboard_store.py:1615-1625` — `SELECT tx_hash, endpoint FROM payment_guards` without WHERE/LIMIT; called from `main.py:5400` and again in `clients_summary` `:1933-2002`), while `payment_guard_stats` (`:1479-1486`) adds `ORDER BY consumed_at DESC LIMIT 1` with no index on `consumed_at`.

### 🟠 F-09 — One shared DB connection under a global lock, without `connect_timeout`
`dashboard_store.py:307` (`_pg_lock`), `:334-340` (`_pg_connection()` — **without** `connect_timeout`),
`:342-372` (`_run` holds `_pg_lock` and on an exception closes the shared connection). The same file uses
`connect_timeout=5` for a side connection at `:624-625`. `integrations/crm_store.py:399-473` is also without
`connect_timeout`, and `:490-493` opens a **new** connection on every read.
**Effect:** psycopg does not pass a timeout → the libpq default of 0 = waits forever. A network blip or a
Postgres failover blocks the **first** request forever, holding `_pg_lock` → all 8 threads + all background
loops + `/health`. The SQLite path is no better: `_run` holds `self._lock` through connect+execute+commit,
while `DashboardStore._connect` (`:1659-1662`) opens a **new** `sqlite3.connect(..., timeout=30)` on every
call → one `/api/dashboard/data` opens ~35-40 connections.

### 🟠 F-10 — `/health` depends on the DB and can trigger a restart loop
`app/blueprints/discovery.py:32-76` calls `crm_store.is_healthy()` and returns **503** when the CRM store is
unhealthy (`:58, :76`); `crm_store.py:639-645 / 390-396` opens a connection on every call without
`connect_timeout`. Checkers: `Dockerfile:39` (`--interval=30s --timeout=10s --retries=3`), the platform check,
the keep-alive loop (`main.py:5681-5713`) and `sentinel.py:144-165`.
**Effect:** a transient DB delay → 503 → the orchestrator restarts the **only** worker → a cold start (see
F-04 from the perf analysis: ~1.3 s import + DB work + Telegram round trip) → more 503s. A self-sustaining
loop. Moreover, **an RPC disturbance alone does not flip `/health.status`**, so there is no Telegram alarm on
a full RPC failure.

### 🟠 F-11 — `/mcp/sse` pins 1 of 8 threads for ≥15 s, free and without a throttle
`discovery.py:665-667` (`_SSE_SESSIONS`, `_SSE_SESSIONS_LOCK`, `_SSE_IDLE_CLOSE_SECONDS = 15`), route
`:670-717`. It is missing from **both** `X402_FREE_ENDPOINTS` **and** `X402_PAID_ENDPOINTS` **and** the
rate-limit scopes (`main.py:1406-1448`; scopes are also missing for `/api/stats`, `/api/sales`,
`/api/v1/signal`, `/api/v1/whaleflow`, `/api/arb/opportunities`, `/dashboard`, `/api/dashboard/data`). 8
anonymous SSE connections = 8/8 threads occupied for ≥15 s → a full denial of service, including `/health`. A
single `curl` loop is enough.

### 🟡 F-23 — The blocking budgets on the paid path exceed `--timeout 120`
- `main.py:2596-2598` — `time.sleep(wait)` (C2 lag, `C2_LAG_WAIT_SECONDS_DEFAULT = 2.5` at `:2528`, up to 3 head re-reads).
- `main.py:3082-3096` — `time.sleep(2)` loop ≈ 8 s.
- `connectors.py:390-410` and `:656-667` — `deadline = time.time() + 24` + `time.sleep(2)` → up to **24 s** inside `_self_broadcast_settlement`/`_broadcast_client_transaction`.
- `connectors.py:100-136` — facilitator POST with `FACILITATOR_TIMEOUT=15` (`:47`), the PayAI→CDP chain (`:55-58`) in `settle_standard_payment` (`:799-899`) → up to ~2×15 s per provider set.
- `main.py:4389-4478` → `verifier.py:252` — **sequential** building of the DEXScreener map: up to 4 symbols × `SOURCE_TIMEOUT_SECONDS=5` = **+20 s** on a cold cache, ×8 concurrent = 32 upstream requests.
- **F-24:** Stripe SDK with no configured timeout — measured `_http_client.py:512` `timeout = 80`, `stripe/__init__.py:39` `max_network_retries = 2` → up to ~240 s in one checkout request (`stripe_checkout.py:290, 336, 361`; called from `main.py:4188, 4330, 4561, 4708`), plus `list_recent_completed_payments` (`:347-395`), which walks the **entire** checkout session history of the account until it finds 25 paid ones.

**Chain effect:** one paid call can chain the aggregate (41 s) + the C2 wait (2.5 s) + self-broadcast (≤24 s) +
the facilitator chain (≤30-60 s) > **120 s**. With 1 worker this is not "1 of N workers is stuck", it is **the
entire API dying and restarting in the middle of a payment**.

### 🟡 F-25 — A single loop without `try/except`
`main.py:1113-1121` (`_stripe_payment_snapshot_loop`) is the only background loop found whose body is not
protected: one unexpected exception kills it **forever** and the admin panel shows "stale" with nobody
notified.

### 🟢 F-39 — The block monitor's cursor is RAM-only
`main.py:714` sets `last_block = wallet.w3.eth.block_number` at startup; the loop scans
`last_block+1 … min(current, from_block+1000)` (`:749-750`). `_wallet_state["last_block_checked"]` is for
display only (`:716, 774`). A restart **misses** every transfer that went through during the downtime. The
dashboard path partially compensates with a durable watermark (`dashboard_store.py:2235-2247`), but the
monitor does not.

### 4.1 What is correct performance-wise (not touched)

- `/api/arb/opportunities` is genuinely cheap: `arb_radar.py:61-92` copies a list under a short lock; `data_age_blocks` from a wall clock — **zero RPC per call**.
- `/api/connectors` → `connectors.py:950-1034` is pure CPU; `_ACTIVITY` has 9 fixed keys (bounded).
- `market_data._CACHE` is correctly bounded (64 entries, TTL 900 s, stale 21600 s, `RLock`); `CoinGeckoClient._price_cache` — 32 entries (`coingecko.py:79-81`) with a 5 s timeout.
- `verifier.py` has a 60 s `_dex_cache` (`:44, 47, 70-71, 111-114`) — `/api/v1/signal` does **not** hit DEXScreener on every paid call.
- `main.py` has **140 top-level functions with not a single duplicated name** (AST check) — the hypothesis of "duplicated/dead helpers" is not confirmed.
- No test re-imports `main.py`; the thread guard works for the single-process case it was designed for.
- All `requests`/`urlopen`/`Web3` in `market_data.py`, `verifier.py`, `sentinel.py`, `telegram_sales.py`, `arb_radar.py`, `connectors.py` have an **explicit timeout** — the problems are in **budgets and serialization**, not in missing timeouts. The exceptions are the Stripe SDK (F-24) and the DB connect (F-09).
- `web3` (3.832 s cold import) is loaded **lazily**; the module import of `main.py` is 1.27-1.37 s and does not include web3/psycopg/stripe/telegram.

---

## 5. RPC, blockchain and external dependencies

### 5.1 Dependency table

| Dependency | Configuration | Timeout | Fallback | Behaviour on failure | Blast radius |
|---|---|---|---|---|---|
| **Base RPC** | `config.py:57` (`BASE_RPC_URL`, default `https://mainnet.base.org`; prod value `https://base.drpc.org` according to `scripts/_render_env_set.py:17` and `PROJECT_STATUS.md:2473`) | 15-30 s (varies by place) | **None**, no second provider | `_adaptive_get_logs` reduces the window and retries the **same** start block every 2 s (`dashboard_store.py:243-255`), **without** `Retry-After` | **Highest.** Both payment rails fail-closed (401) → nobody can pay; the scans stop; the price in the signal becomes `None` |
| **Postgres / `DATABASE_URL`** | `dashboard_store.py:300-371` | `connect_timeout=5` only on the request-log path (`:625`); elsewhere the default (infinite) | SQLite file when `DATABASE_URL` is missing — **not** a runtime failover | `claim_payment_tx` returns False → `C1 replay lock UNREACHABLE … refusing every payment` (`:1359-1364`) | **Critical:** an unreachable DB refuses every paid call, even though the money is on-chain |
| **CoinGecko** | `coingecko.py:32-33`, `market_data.py:31`; keys `COINGECKO_API_KEY`/`BASE44_API_KEY` | 5 s | Base44 proxy → public API (`coingecko.py:144-169`); stale cache up to 6 h | 2 attempts + exponential backoff; 429 → process-wide cooldown ≤120 s | Medium for money; **high for the paid signal** (price `None` → confidence ×0.8) |
| **DexScreener** | `verifier.py:39, 68`, `market_data.py:32` | 5 s / 10 s | `search` → `tokens` inside the verifier; no cross-provider | Returns `[]`/`"error"`; the verdict becomes `unverified` → **fail-open, the signal is delivered** | Medium: a paid signal is delivered unverified |
| **Telegram Bot API** | `main.py:536`, `sentinel.py:123`, `telegram_sales.py:74, 199` | 10-20 s | None | Logged, not fatal | Low: delayed alerts/VIP codes |
| **Stripe** | `stripe_checkout.py:85-133` | **None** → SDK default 80 s × 3 | None | `stripe_checkout_creation_failed`; the snapshot stays `stale` | Low for the x402 paywall (a human product) |
| **x402 facilitators** (PayAI, CDP) | `connectors.py:55-63`, chain `:86-97` | 15 s | Chain: self-broadcast → CDP → PayAI (`:860-899`) | HTTP/transport error → the next one; all fail → `settlement_failed` | Medium: **significant only if the hot wallet has no gas** |
| **GitHub API / DefiLlama / alternative.me** | `sentinel.py:248, 271, 362, 370`; `market_data.py:33, 494` | 25-30 s / 10 s | None | The field shows `n/a`; the baseline is preserved | Negligible |

### 5.2 Load arithmetic (derived from the code — **not** measured in production)

| Loop | Interval | RPC calls/loop | RPC/hour |
|---|---|---|---|
| `_blockchain_monitor_loop` (`main.py:679-780`) | 30 s | 1 `block_number` + 2 `balanceOf/decimals` + ~1 receiver balance + 1 `get_logs`(≤1000 blocks) | **~480** |
| `_dashboard_scan_loop` (`main.py:1151-1154`) | 60 s | 1 `block_number` + 1 `get_logs` + 1 `get_block` **per transfer** | ~60 + ~60·N |
| `_whaleflow_scan_loop` (`main.py:1229-1236`) | 60 s | 1 `block_number` + 1 `get_logs` + 1 `get_block` **per whale** | ~60 + ~60·M |
| `arb_radar` (`arb_radar.py:27`) | 60 s | 1 RPC + 8 sequential DEXScreener GETs | ~60 |
| **Total** | | | **~600-900/hour at low activity; ~2 700/hour at high activity** (the second estimate is from a separate analyzer and assumes 30+ transfers per loop — treat it as a pessimistic upper bound) |

> **Honesty note:** two independent analyzers gave 480/hour and ~2 700/hour. The difference is in the assumption
> about the number of transfers per loop (the local DB has only **10** `onchain_sales` in total). The numbers are
> **derived from the code**, not measured in production.
>
> **Boot backfill (once per deploy):** sales — 30 days × 86400 / 2 s = 1 296 000 blocks ÷ 5000 = **260 `getLogs`** + 1 `get_block` per transfer; whales — 24 h × 3600 / 2 = 43 200 blocks ÷ 100 = **432 `getLogs`** + 1 `get_block` per whale.

### 5.3 Additional findings

#### 🟠 F-08 — A single RPC provider, with no fallback and no cooldown
`config.py:57` defines a single `BASE_RPC_URL`; every consumer re-reads it with the same default
(`main.py:661, 2625, 3062`; `connectors.py:335, 646`; `dashboard_store.py:2125…2410`; `wallet.py:117`). There
is no second provider constant. `_block_timestamps` even hardcodes `mainnet.base.org`
(`dashboard_store.py:2078-2079`) — that is a **different** provider, not a fallback. The only "backoff" is
window reduction. `scan_window` even continues when `is_connected() == False`
(`dashboard_store.py:2137-2146`).

#### 🟠 F-40-related — Unserialized nonce management and gas without a ceiling
`connectors.py:319-417` (`_self_broadcast_settlement`) reads `get_transaction_count` at `:376` without a lock
and without tracking the pending nonce → two concurrent paid requests can build the same nonce, one reverts,
and the buyer's nonce is still consumed. `maxFeePerGas = gas_price * 2` **without a ceiling** (`:350`).
`connectors.py` does not import `threading` — there is not a single lock in the module.

#### 🟠 F-16-related — The service broadcasts a client raw transaction with almost no validation
`connectors.py:641-669` decodes and `send_raw_transaction`s whatever is in `payload.transaction`.
`_local_verify_transaction_payload` (`:561-634`) checks signer == `from`, chainId == 8453, `to` == USDC and
the calldata prefix `transfer(payTo, amount ≥ price)` — **but not** `gas`, `gasPrice`/`maxFeePerGas`, `nonce`
or `value`. A caller can make us broadcast a USDC transfer with an extreme gas price or a replayed nonce.

#### 🟡 H5 — The verifier's CoinGecko cache has a mismatched case
`coingecko.py:89` looks up `prices.get(s.lower(), prices.get(s))`, but the cached dictionary is built with the
caller's case (`:221-228`). The agent loop fills it with lowercase (`main.py:1067` → `trading_agent.py:76`),
while the verifier passes `[s.lower() for s in symbols]`, where `symbols` are uppercase
(`verifier.py:250-252, 237`). The key is normalized (`:179`), **the payload is not** → the verifier misses the
cache and makes a live CoinGecko call **on every paid `/api/v1/signal`**.

#### 🟡 M6 — The whales' 24-hour window can silently drop events
`dashboard_store.py:775-776` builds a cutoff from `datetime.now(utc) - 24h` and compares it with `ts` strings
recorded from **block** times (`:2316-2317`). On a failed block read the fallback is `datetime.now(utc)`
(`:2319`), which **inflates** the timestamp and can push real events outside the window; a stale watermark
also leaves the window empty. `all_time_count` uses different predicate logic (`:784-788`) → the two numbers
can diverge.

#### 🟡 M7 — A refused range can advance the watermark instead of retrying it
`dashboard_store.py:2423-2424` (`whaleflow_increment`) and `:2246-2247` (`scan_increment`) fall back to
`to_block` when `safe` is 0, i.e. when the **entire** window is refused; `whaleflow_backfill` does the same
(`:2401`). The rule "never skip a range", stated at `:2343-2345`, is not honoured on the totally-failed
branch.

#### 🟢 M3 — Every incoming USDC transfer is recorded as a sale, with no minimum
`main.py:764-765` → `_process_incoming_transfer` → `_record_real_sale` (`:815-822`) and
`dashboard_store.record_sale` (`:812-845`) accept **any** amount; `VIP_THRESHOLD_USDC` only gates the invite
(`:882`). A dust spammer can inflate `total_sales`, `total_volume_usd` and the 7-day line in the Sentinel
report (`sentinel.py:377-387`) and trigger `New payment received!` alarms (`sentinel.py:200-211`).

#### 🟢 F-38 — Time zone: only the Sentinel weekly report uses local time
`sentinel.py:464-467` uses `datetime.now()` and `local.weekday()/hour`. Everything else is UTC
(`sentinel.py:382, 405`; `main.py:3661, 3712`; `dashboard_store.py:1223`). On a non-UTC host the report
"Sunday 18:00" comes out on the wrong day or is skipped; `last_report_date` is a local string. The money
paths are UTC-consistent — the DST risk is only in this gate.

#### 🟢 L3 — `data_age_blocks` is derived from a wall clock
`arb_radar.py:75` divides elapsed seconds by a hardcoded 2 s block time — an estimate, not a measurement of
the chain, a misleading name.

---

## 6. Security and deployment configuration

### 🟠 F-13 — Raw RPC text is published on an anonymous free route
`main.py:643` — `_wallet_state["rpc_error"] = str(exc)` (raw). All other places in the same file
**deliberately** redact: `main.py:769, 778, 1141, 1158, 1228, 1235` use `redact_rpc(exc)`. The redactor itself
exists because RPC URLs carry keys (`dashboard_store.py:46-48`:
`(\/v[0-9]+\/|apikey=|api-key=|key=|token=)([A-Za-z0-9_\-]{6,})`). The raw value is served through
`main.py:3792` (`"wallet": wallet_info`) in `_statistics_payload`, reachable from `/api/dashboard-stats`
(`:3986-3989`) — **free** (`:147`). `_safe_jsonify` (`:1499-1501`) only removes NaN/Infinity, it does **not**
redact.
**Exploitation:** if `BASE_RPC_URL` is a provider with a key in the URL (Alchemy/DRPC/POKT are used in the
repo) and the monitor's Web3 init fails once, the exception (which usually contains the full URL with the
key) is returned to every anonymous `GET /api/dashboard-stats`.

### 🟠 F-14 — The Telegram bot token can leak into the logs
`telegram_sales.py:72` builds `url = TELEGRAM_API_BASE.format(token=token, method=method)` — the token is in
the URL path; `:80-81` logs `log.warning("Telegram API %s failed: %s", method, exc)`; the same at
`:198-199, 211-212` for `setWebhook`. `requests` exceptions stringify the **full** URL →
`.../bot<TOKEN>/sendMessage` ends up in the log line. `stripe_checkout.py:57-59` has a `redact()` helper, but
it is applied only on Stripe paths and its regex does not catch a Telegram token.
**Exploitation:** any transient network disturbance to `api.telegram.org` writes the live token into the
Render log stream → full takeover of the bot.

### 🟠 F-15 — `secrets/` is baked into the Docker image
`Dockerfile:29` — `COPY --chown=kristo:kristo . .` copies the entire build context. `.dockerignore:47-50`
excludes `.env`, `.env.local`, `.env.production`, but **there is no entry for `secrets/`**, whereas
`.gitignore:53` excludes it. `kristo_paid_demo_clip.mp4` (120 MB) and `kristo_paid_demo_clip_web.mp4` (20 MB)
are also missing.
**Exploitation:** a `docker build` from this tree produces an image with `secrets/cdp_api_key.json`,
`secrets/demo_private_key.txt`, `secrets/render_api_key.txt`; any push to a registry, layer inspection or
`docker save` hands over the CDP key pair, the demo wallet private key and the Render API key. (The files were
**not** opened — only their names were listed.)

### 🟡 F-26 — `/api/launch/health` without auth
`main.py:5198-5216` has no auth check in its body: `payment_provider` (Stripe or mock), `crm_backend`,
`lead_count`, `pipeline` (incl. the number of paying customers), `public_url`. It is in neither of the two
endpoint sets → `_x402_paywall` falls through to `:3526` without even a challenge.

### 🟡 F-27 — `/api/connectors` exposes the hot wallet and an internal route
`main.py:149` (free) + `:3992-4007` (without auth). `connectors.py:988` —
`"detail": f"payer wallet={wallet_addr}"` → the **payer-side hot wallet** (the side paired with
`WALLET_PRIVATE_KEY`), which the code explicitly distinguishes from the public fee receiver
(`main.py:3793-3796`). `connectors.py:944-947` via `:980` → `f"...(gas={gas}) → CDP ({cdp}) → payai"`, i.e.
whether `WALLET_PRIVATE_KEY` is loaded, the health of the CDP JWT/PEM and the internal settlement chain. It is
missing from `_RATE_LIMIT_DEFAULTS` (`main.py:1406-1416`) and makes an ES256 JWT on every request
(`connectors.py:941-943`).

### 🟡 F-28 — The Render configuration is not versioned
Verified, not assumed: `render.yaml` is missing; it is not in `git ls-files`; `git log --all -- render.yaml`
is empty; `git grep "render.ya?ml"` → 0 hits in tracked files. The only description is prose
(`DEPLOYMENT.md:95-96`, `DEPLOYMENT_CHECKLIST.md:36-37`), `Procfile:1` is not consumed by Render, and the
programmatic deploy is 3 imperative scripts that require `RENDER_API_KEY` from env or from the untracked
`secrets/render_api_key.txt`.
**Why it is security-significant:** the start command, the worker count, the health path and the region live
only in the dashboard. The code's invariants depend on them: `main.py:1404-1405` and `Dockerfile:45` assume
**one** worker (the in-RAM rate limiter, the free-tier counters, the `_verified_payments` replay set at
`main.py:2260`), and an edit in the dashboard leaves no trace for review.

### 🟡 F-29 — The admin token falls back to `SESSION_SECRET`
`main.py:1802-1813` returns `ADMIN_API_TOKEN`, otherwise `SESSION_SECRET`; `main.py:178` raises `SECRET_KEY`
from the same `SESSION_SECRET`. One secret simultaneously signs the session cookie and authenticates the
admin API. The correctness is fine (fail-closed if nothing is set — `:1835`), and the fallback is warned
about (`:1809-1812`), but it is not fatal.

### 🟡 F-30 — An operator script prints live env values
`scripts/_t2_render_env_check.py:30-31` defines `watch = ("RPC", "CHUNK", ..., "ADMIN")`; `:35-36` prints
`f"  {k} = {e.get('value')}"`; `:45` prints `startCommand`, `buildCommand`, `plan`, `region`,
`numInstances`, `healthCheckPath` from the live service. The list catches `BASE_RPC_URL` (a provider key) and
`ADMIN_API_TOKEN` (the shared admin password) by name, and the file is **tracked in git**.

### 🟡 F-31 / M6 — The admin brute-force limit and the XFF assumption
`main.py:1407` — `"admin_login": (20, 300)` (20 attempts/5 min per IP, no lockout, no global counter); the key
is `(scope, _get_client_ip())` (`:1434`). `main.py:174` — `ProxyFix(x_for=0)` → in production
`request.remote_addr` is **always** the private address of the Render proxy; therefore
`if fwd and _is_private_or_loopback(peer):` (`:1391`) is **always true** and the "anti-spoofing" branch
documented at `:1386-1387` is **unreachable** in production. The protection relies entirely on Render adding
the real client IP **last**. The regression test covers only the public peer branch
(`tests/test_v6_launch.py:170` passes a TEST-NET address). **This requires one live probe to close.**

### 🟢 F-33 — `/validation` publishes live paid addresses and a stale number
`discovery.py:186-203` serves a static `recent_payments` list with 4 real settlements with `payer`,
`amount_usdc` and the full `tx` — the data of the paid `/api/sales` — on a **permanently free** page;
`:179-183` publishes `"passed": 550, "total": 550` with `last_run: 2026-10-30`.

### 🟢 F-34 / F-35 / F-36 / L2 / L4 / L7 — Smaller items
- **F-34:** `config.py:79` `KRISTO_WHALE_PRICE = 0.01` and `:78` `KRISTO_RUG_PRICE = 0.003` are **not** in `X402_PRICE_MAP` — consumed only by the dead demo catalog. `docs/OUTREACH_KIT.md:20` still quotes Whale Flow at "$0.01/call".
- **F-35:** `requirements.txt:33` has `cryptography>=42.0.0` (a range in a file whose title claims "pinned"), and `cryptography` is **entirely missing** from `requirements.lock`; the lock has no `--hash`. Production installs `requirements.txt`, not the lock (`DEPLOYMENT.md:95`). `requirements.txt:32` pulls `pytest==9.1.1` into the production image (`Dockerfile:22-25`).
- **F-36:** `docker-compose.yml:27` — `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-kristo_dev}` with `:31-32` `ports: "5432:5432"` and `env_file: .env` (`:43, :64`). A copy-paste deploy on a non-localhost host exposes the CRM DB (emails, Stripe checkout ids, amounts) to `kristo:kristo_dev`.
- **L2:** `catalog_store.py:462-489` `grant_entitlement()` requires only a `checkout_id` and a valid product; `_checkout_matches` (`:400-417`) **never** checks `agent_checkouts.payment_status`. Today there is no live exploitation (the only caller is the signed webhook, behind a `payment_status != "paid"` gate), but any future caller could issue 30 days of access from an unpaid checkout id.
- **L4:** `main.py:1319` (`_free_tier_usage`) and `:1345` (`_paid_calls_usage`) are IP-keyed and **never** pruned (only `_rate_limit_hits` is cleaned at `:1443-1447`); `/api/leads` and `/api/funnel/track` accept an email of arbitrary length up to the 512 KB cap with no limit in `LeadRecord`.
- **L7:** `glama-connector-claim.json` is a committed and publicly served ownership token (`discovery.py:822-832`) — deliberate (an HTTP challenge), but subject to rotation after the claim window.
- **Test hygiene:** `tests/test_secret_hygiene.py:8-26` scans only 5 explicitly named files with 5 regexes; `ROOT` is computed at `:5`, but is never used for discovery — which is why it **cannot** catch F-13, F-14 or F-30.

---

## 7. Documentation, claims and repo hygiene

### 7.1 Inventory
`docs/` — **89 files / 597 925 B (0.57 MB)**: 46 `.md`, 26 probe `.py`, 7 `.json`, 3 `.png`, 2 `.pdf`, 2 `.static`, 1 `.prisma`, 1 `.txt`, 1 `.js`. **75 tracked, 14 untracked** (incl. `AP2_RADAR.md`, `BAZAAR_RESEARCH.md`, `GRANT_APPLICATION.md`, `HAIKU_AUDIT*.md`, `SCAN_LISTING_*.md`, `WATCH_LIST.md`, `monitor_state.json`, `glama_thumbnails/`). Remainder: `docs/evidence/pytest_cache/` — untracked, not gitignored, ACL-inaccessible.

### 7.2 Verification of the public claims

| Claim | Verdict |
|---|---|
| "550 tests" (`README.md:105,115`) | ✅ **Confirmed** — `550 passed in 180.46s` |
| MCP "3 tools" | ✅ **Confirmed** — `discovery.py:508` `_mcp_tools()`: `get_market_stats` (`:522`), `get_onchain_sales` (`:541`), `get_bot_status` (`:561`). **But:** the second catalog (`/api/mcp/manifest`, `discovery.py:1061-1110`) calls the same tool `get_sales_history` (`:1071`) — two catalog definitions with different names for one route |
| Prices "$0.003–$0.005" | ✅ **Confirmed** for the live map: values {0.003, 0.005} from `config.py:75-83` through `main.py:89-100`. ❌ False in `docs/PRODUCT_AUDIT.md:43` and `docs/MYSTERY_AGENT_REPORT.md:23,26` ($0.05) |
| "35 scanning routes" | ❌ **Does not exist anywhere in the repo.** In reality 6 paid |
| Glama "A4.7" | ⚠️ **Internally contradictory** — `PROJECT_CHRONOLOGY.md:196`, `PROJECT_STATUS.md:526`, `weekly/2026-09-29.md:39` = 4.7, but `PROJECT_STATUS.md:1199,1204` and `PROJECT_CHRONOLOGY.md:128` = **A 3.6/5.0**. The string `A4.7` occurs 0 times |
| "100% uptime (47 days)" | ❌ **Does not exist** in the repo (0 hits) |
| "11 resources on x402scan" (`README.md:112`) | ⚠️ **Not locally verifiable**; the code exposes **6** resources (`discovery.py:969-1007`) |
| …"zero payment incidents" (`README.md:111`) | ❌ **False** — `PROJECT_STATUS.md:34-45` documents INCIDENT 14.09 (paid $0.003 → 401, no delivery); `TASK.md:43-44` confirms it |
| agentic.market #66, MCPso #5200, awesome-x402 PR #1308 | ⚠️ **#66 and #5200 do not exist in the repo**; #1308 is documented as OPEN without review (`LISTING_CHANNELS_AUDIT.md:23,29,118`) |
| PulseMCP | ⚠️ `PULSEMCP_SUBMISSION_READY.md:9-17` — "**we are NOT there**", submissions are halted. Any claim of presence is false |

### 7.3 Contradictions between documents (specific pairs)
1. **Number of paid routes: 6 vs 5 vs 4 vs 3.** The truth = 6 (`main.py:89-100`; `tests/test_whaleflow.py:255`). `PROJECT_STATUS.md:27`/`TASK.md:19`/`weekly:38` = 6; `PRODUCT_AUDIT.md:9` = 5; `README.bg.md:206` = 4; `DISTRIBUTION_STATUS.md:11` = 3, while its own table `:20-27` lists 4; `MYSTERY_AGENT_REPORT.md:18,21` = 3.
2. **Price of `/api/sales`:** `config.py:76` = 0.005 vs `PRODUCT_AUDIT.md:43` and `MYSTERY_AGENT_REPORT.md:23,26` = 0.05.
3. **Whale threshold:** code = $5 000 000 (`dashboard_store.py:98`, `main.py:1514`) vs `WHALE_FLOW_SPEC.md:19` = $50 000.
4. **Whale flow price:** `config.py:83` = 0.003 vs `OUTREACH_KIT.md:20` = 0.01 (plus the orphaned `config.py:79`).
5. **Glama: 4.7 vs A 3.6/5.0** (see the table).
6. **PulseMCP path:** `DISTRIBUTION_STATUS.md:16` ("PayAPI publishes automatically") vs `PULSEMCP_SUBMISSION_READY.md:16-17` ("it still has not happened").
7. **Tests: 8/8 → 17 → 77 → 152 → 154 → 164 → 410 → 422 → 426 → 550** across nine different documents.
8. **"100% production-ready"** (`FINAL_STATUS.txt:5`, `PROJECT_COMPLETION_REPORT.md:4,11`, `TEST_REPORT_2026-08-17.md:5,100`) versus **its own** `CODE_AUDIT_REPORT.md:9-19` (Critical: unauthenticated Stripe webhook, unauthenticated admin endpoints, x402 bypass) and `PROJECT_STATUS_REPORT_2026-08-20.md:5` ("It is not correct to declare it '100% ready'").
9. **Stack/deploy:** `README.md:98`/`DEPLOYMENT.md:13` (Render, Flask) vs `ARCHITECTURE.md:1,20`/`QUICK_START.md:1-45`/`TEST_REPORT_2026-08-17.md:4` (**V5** sales engine) vs `PROJECT_STATUS_REPORT_2026-08-20.md:18` (Replit).
10. **`MYSTERY_AGENT_REPORT.md` is self-outdated:** `:18` "3 resources", `:23,26` $0.05 vs today's 6 resources and 0.005 — and `README.md:114` still quotes its "23/23".

### 7.4 Hygiene: what must not reach a client or a registry reviewer
**Tracked in git:**
- `CODE_AUDIT_REPORT.md` — the first five findings are Critical/High defects (incl. the unauthenticated Stripe webhook `:23-27` and the x402 bypass via `Referer` `:15`). Handing it to a reviewer is self-incriminating.
- `PROJECT_STATUS.md` (271 953 B) — financial internals, payer addresses, the 14.09 incident, secret rotation notes; `:20` discusses the compromised `WALLET_PRIVATE_KEY` address.
- `docs/_origin_data.json`, `docs/_operator_fingerprint.json`, `docs/_recon_currency_api_7d.json`, `docs/_cadence_*.json` — on-chain tracking of third parties (35 payTo addresses, per-wallet totals).
- `docs/DASHBOARD_AUDIT.md:13` — documents that `/nexus` shows **simulated random data as live activity**.
- `FINAL_STATUS.txt`, `PROJECT_COMPLETION_REPORT.md`, `docs/TEST_REPORT_2026-08-17.md` — "100% production-ready / 8-8 tests", refuted by the later audits.
- `docs/DISTRIBUTION_STATUS.md:66` — points the reader to `secrets/render_api_key.txt`.

**Untracked / on disk:**
- `kristo_paid_demo_clip.mp4` — **120 112 530 B (~114.5 MB)** + `_web.mp4` 19.9 MB + `preview.jpg` 583 KB (gitignored, but on disk in the project folder).
- `ops/kristo-intelligence-6-main.zip` — 885 327 B, a full source snapshot (verified: 272 entries, **without** `.env`/keys inside, but it contains `PROJECT_STATUS.md`, `CODE_AUDIT_REPORT.md`, `FINAL_STATUS.txt` and the whole `docs/`).
- `commit_54a7ba3_full.txt` / `_diff_only.txt` (38.5/38.2 KB), `main_py_diff.txt`, `main_py_full_diff.txt`, `temp_*.log`, `server_err.log`, `server_out.log`.
- **`.kilo/worktrees/believed-dancer/`** — a complete **second copy** of the repo (`main.py` 242 907 B, `dashboard_store.py` 118 472 B, …), detached HEAD `d08748f`. Ignored only via `.git/info/exclude:9` — **locally**, not in `.gitignore`; any disk scan yields doubled results (which is why the `.py` inventory is 345 and not ~176). Risk: editing the wrong copy.
- `docs/monitor_state.json` — untracked and **not** ignored → it goes in with `git add -A`.
- `kristo-intelligence/` (`.clinerules/`, `.specify/`, `specs/`) — an untracked speckit scaffold.

**Git state:** 29 entries in `git status --porcelain` (untracked `.mcp.json`, `TASK.md`, diff files, 10 `docs/` files, `scripts/_*.py`, `kristo-intelligence/`) — local work that has **not been committed**. 351 commits, the first on 2026-08-19, the last on 2026-11-02.

---

## 8. Prioritized action plan

> Everything below is a **proposal**. Nothing has been applied. Changes in production go through the
> "push = auto-deploy" gate.
> **Untouched invariants:** the x402 headers and envelope structure, `payTo`/`X402_RECEIVER_ADDRESS`, the
> prices in `config.py`, `/.well-known/x402-trust.txt`, `secrets/` and `.env`.

### P0 — blocking for the business model (without them, charging is decorative)
1. **F-01 — remove the mirror of the paid data.** Decide which field is actually sold and take it out of the public read model of `/api/dashboard-stats` and `/api/dashboard/data` (history with `tx_hash`+`sender`, `whales`, market snapshot). Alternative: the dashboard payload behind an admin/session scope. This is a product decision — the paywall cannot be "fixed" while a free copy exists.
2. **F-02 — verify the signed value.** Derive the amount **only** from `auth.value`; refuse on a mismatch with `accepted.amount`; refuse non-numeric amounts instead of skipping the check; re-read the `Transfer` amount from the receipt before the grant (the adoption path already does it correctly at `main.py:2419-2421`).
3. **F-03 — remove the fail-open on an unreadable receipt.** One explicit policy: fail-closed after the poll (401/425 with the tx hash, as the in-flight branch does at `main.py:3144-3157`), or an override only with independent confirmation. Never let an **exception** in the confirmation check lead to delivery.
4. **F-04 — remove the writes from the read path.** `guard_stats()` must not do INSERT/DELETE; move the liveness probe into the background loop, and let the route read the last result (and get a cached read model).
5. **F-05 + F-06 — decide the reorg semantics.** At minimum: mark the `onchain_sales` row as `reorged` and exclude it from the totals; add a depth check to the adoption path by nonce.
6. **F-07 — rate limit/budget on the payment path** (per IP and per signer), a pre-check of the buyer's USDC balance before broadcast, and move settlement out of the request thread.

### P1 — stability and information leakage
7. **F-22 + F-31** — one cached read model with single-flight for `/api/dashboard/data`, `/api/dashboard-stats` **and** the paid `/api/stats`; indexes on `request_log(user_agent)`, `(source)`, `(funnel)`; aggregate `payment_guards` in SQL and index `consumed_at`.
8. **F-09** — `psycopg_pool` + `connect_timeout` + `statement_timeout`; stop holding one global lock over one shared connection (`dashboard_store.py:624` already shows the correct pattern).
9. **F-10** — make `/health` pure liveness (no DB); readiness separately.
10. **F-11** — isolate and limit `/mcp/sse` (a cap on concurrent sessions + a rate limit).
11. **F-23 + F-24 + F-25** — bound every blocking budget on the paid path; set explicit timeouts on Stripe (and `max_network_retries=0` for the request path); wrap the body of `_stripe_payment_snapshot_loop` in `try/except`.
12. **F-08 + F-12** — a list of RPC providers with health rotation + a process-wide cooldown with `Retry-After`; one bounded reorg watcher with a queue instead of a thread per payment; chunk `getLogs` through the already existing `_adaptive_get_logs`.
13. **F-13 + F-14 + F-15 + F-30** — apply `redact_rpc()` at `main.py:643`; redact the Telegram token before logging; add `secrets/` and `*.mp4` to `.dockerignore`; mask the env values in `_t2_render_env_check.py`. Extend `tests/test_secret_hygiene.py` to **discover** files instead of checking 5 explicitly named ones.
14. **F-26 + F-27** — an admin guard for `/api/launch/health`; remove `payer wallet=`, `gas=` and the CDP detail from the public `/api/connectors`.
15. **F-28 + F-29** — commit `render.yaml` (or explicitly document the drift and pin `--workers=1`); require `ADMIN_API_TOKEN` in production instead of silently reusing `SESSION_SECRET`.
16. **F-21** — set and document `KRISTO_FREE_TIER_LIMIT=0` in `.env.example`; move the counters into the durable store.

### P2 — documentation and hygiene
17. **F-19 + F-20 + F-32 + F-34 + F-37** — a single accessor over `X402_PRICE_MAP`/`REAL_X402_ROUTES` for **all** advertising surfaces (the pattern of `discovery.py:950-956` is already correct); decide the fate of the $29 VIP (a Telegram product or an API entitlement); a test for `REAL_X402_ROUTES ⊆ X402_PAID_ENDPOINTS`; remove the dead prices; move the discount into `config.py` with an assert.
18. **F-33** — remove the raw payer addresses from `/validation` and pick one number for the tests.
19. **Documentation** — read `TASK.md` first (the only onboarding brief with correct operational facts; untracked, so `git add` + refresh it). Rewrite: `README.md` (remove "zero payment incidents"; fix "550 tests"; mark "11 resources" as an x402scan index, not a fact about the repo), `DISTRIBUTION_STATUS.md` (§1 vs §2 route count; PulseMCP), `MYSTERY_AGENT_REPORT.md` (date it or re-run it), `VISIBILITY_PLAN.md` (mojibake + the stale #12799), `OUTREACH_KIT.md:20`. Archive the V5 documents (`ARCHITECTURE.md`, `QUICK_START.md`, `TEST_REPORT_2026-08-17.md`, `DASHBOARD_AUDIT.md`, `PRODUCT_AUDIT.md`, `LISTING_CHANNELS_AUDIT.md`, `MCP_*`), as well as `docs/evidence/probes/`. Delete `FINAL_STATUS.txt`, `PROJECT_COMPLETION_REPORT.md`, the diff files, `temp_*.log`, `server_*.log`. Move outside the repo (unpublishable): `PROJECT_STATUS.md`, `CODE_AUDIT_REPORT.md`, `TASK*.md`, `docs/_*.json`, `docs/DASHBOARD_AUDIT.md`, `docs/DISTRIBUTION_STATUS.md`.
20. **Disk hygiene** — delete/remove `.kilo/worktrees/believed-dancer` (a second copy of the repo) or add it to `.gitignore`; gitignore `docs/monitor_state.json`; decide what to do with the ~134 MB of video artifacts.
21. **F-35 + F-36** — regenerate `requirements.lock` from `requirements.txt` with `--hash`, separate the dev/test dependencies, pin `cryptography`; bind the compose Postgres to `127.0.0.1` and remove the default password.

---

## 9. Methodology, limitations and what remains unverified

**How the audit was done:** an inventory through PowerShell (read-only), targeted `grep`/reading with line
numbers, an AST analysis of `main.py`, `EXPLAIN QUERY PLAN` + timings over the local SQLite DB (read-only,
`mode=ro&immutable=1`), isolated cold-import measurements, reading the installed Stripe SDK, a full test run.

**Measured initially:**
- ✅ `550 passed, 1 warning in 180.46s` (a full run in `venv`, Python 3.12.10, pytest 9.1.1).
- ✅ 46 301 `request_log` rows; 12 queries of `requests_summary` = **528.22 ms**, 5 full scans.
- ✅ Cold import: `web3` 3.832 s, `stripe` 0.963, `psycopg` 0.934, `telegram` 0.935, `flask` 0.655; the module set of `main.py` 1.27-1.37 s.
- ✅ `main.py` = 5859 lines (CRLF), 140 top-level functions, **0 duplicated names**.
- ✅ Stripe SDK: `timeout = 80`, `max_network_retries = 2`.
- ✅ The absence of `render.yaml`, `app.py`, `mcp_server.py`, `auth.py`, `guard.py`, `gas.py`, `facilitator.py`, `rpc.py` — confirmed by a search of the whole repo.

**Derived from the code (not measured in production):** the RPC/hour and backfill arithmetic, the
CoinGecko/DexScreener estimates, "~40 s worst case" for a paid signal, "~41 s / ~783K rows" (a quote from a
comment at `main.py:3944-3945`).

**Unverified / limitations:**
1. **`.env` and `secrets/` were not opened** (an explicit limitation). It is therefore unknown whether `KRISTO_FREE_TIER_LIMIT=0`, `WALLET_PRIVATE_KEY`, `DATABASE_URL`, `KRISTO_DISABLE_BACKGROUND_THREADS`, `FACILITATOR_CDP_*` are set in production. Some of the findings (F-02, F-07, F-15, F-21, F-28) depend on those values.
2. **There are no network checks** — Glama, x402scan, PayAPI, Smithery, PulseMCP, GitHub PRs remain UNVERIFIABLE; the behaviour of the live facilitators (whether they compare the signed value) is likewise unobserved.
3. **Render's X-Forwarded-For semantics** (F-31/M6) require one live probe to determine whether the admin limit and the free tier are bypassable.
4. **The production Postgres plan map** and the real row counts have not been reproduced — there is no access to the live DB.
5. `main.py` **was not executed** (importing it writes to `data/dashboard_state.db`), so the startup time and the seam between the `after_request` hooks are derived from the code, not measured end-to-end.
6. Two independent analyzers gave a different estimate of the RPC load (480/hour vs ~2 700/hour); both are presented with an explicit note.

---

## 10. Appendix A — Full inventory of the routes

### `main.py` (44 `@app.route`)
`/.well-known/x402-trust.txt`:2223 · `/f/<channel>`:2242 · `/api/arb/opportunities`:3549 · `/api/sales`:3582 · `/api/admin/seed-sales`:3823 · `/public/signals/history`:3912 · `/api/dashboard-stats`:3986 · `/api/connectors`:3992 · `/api/v1/quickstart`:4010 · `/api/stats`:4067 · `/api/bot-status`:4074 · `/api/telegram-webhook`:4089 · `/`:4152 · `/launch`:4182 · `/sales/checkout`:4188 · `/api/leads`:4299 · `/api/checkout`:4330 · `/api/v1/signal`:4389 · `/api/v1/agents`:4481 · `/api/v1/agents/<agent_id>`:4491 · `/api/v1/agents/<agent_id>/playground`:4500 · `/agents`:4537 · `/api/v1/agents/<agent_id>/click`:4543 · `/api/v1/agents/<agent_id>/checkout`:4561 · `/api/v1/agents/<agent_id>/access`:4624 · `/api/webhooks/stripe`:4708 · `/api/sales/summary`:4868 · `/api/admin/leads`:4890 · `/api/admin/overview`:5057 · `/api/admin/catalog-metrics`:5066 · `/api/v1/research/ingest`:5075 · `/api/admin/research-insights`:5102 · `/api/admin/research-insights/<insight_id>`:5118 · `/sales/admin/login`:5140 · `/admin/login`:5141 · `/sales/admin/logout`:5160 · `/sales/admin`:5166 · `/sales/admin/research`:5186 · `/api/launch/health`:5198 · `/api/funnel/track`:5219 · `/api/dashboard/data`:5573 · `/api/v1/whaleflow`:5585 · `/dashboard`:5642 · `/nexus`:5655

### `app/blueprints/discovery.py` (26 routes)
`/health`:32 · `/validation`:79 · `/api/v1/signal/sample`:356 · `/api/stats/sample`:399 · `/api/v1/whaleflow/sample`:420 · `/api/sales/sample`:444 · `/api/bot-status/sample`:466 · `/api/arb/opportunities/sample`:486 · `/mcp/sse`:670 · `/mcp/message`:720 · `/mcp` (POST/DELETE):742 · `/mcp` (GET):766 · `/glama.json`:804 · `/.well-known/glama.json`:822 · `/api/mcp/manifest`:835 · `/.well-known/x402.json`:914 · `/.well-known/x402`:922 · `/mcp.json`:1026 · `/openapi.json`:1127 · `/favicon.ico`:1358 · `/favicon.svg`:1359 · `/robots.txt`:1374 · `/sitemap.xml`:1387 · `/agents.json`:1416 · `/.well-known/ai-plugin.json`:1485 · `/llms.txt`:1536

### Paid allow-list (`main.py:137-139`) — 6 routes
`/api/sales` · `/api/stats` · `/api/bot-status` · `/api/arb/opportunities` · `/api/v1/signal` · `/api/v1/whaleflow`

### Significant constants
`FREE_TIER_LIMIT` = `KRISTO_FREE_TIER_LIMIT` (default **1**) `main.py:134` · `X402_PAID_ENDPOINTS` 6 · `X402_FREE_ENDPOINTS` 27 · `STATS_CACHE_TTL_SECONDS` 60 `main.py:3951` · `BLOCKCHAIN_POLL_INTERVAL` 30 `main.py:692` · `KRISTO_DASHBOARD_SCAN_INTERVAL` 60 `main.py:1133` · `WHALEFLOW_SCAN_INTERVAL` 60 `main.py:1219` · `AGENT_POLL_INTERVAL` 300 `main.py:1059` · `KEEPALIVE_INTERVAL_SECONDS` 600 `main.py:5681` · `SCAN_INTERVAL` (arb) 60 `arb_radar.py:27` · `SALES_CHUNK_BLOCKS` 5000 `dashboard_store.py:2117` · `WHALEFLOW_CHUNK_BLOCKS` 100 `:2276` · `WHALEFLOW_BACKFILL_HOURS` 24 `:106` · `WHALE_THRESHOLD_USDC` 5 000 000 `:98` · `C2_LAG_WAIT_SECONDS_DEFAULT` 2.5 `main.py:2528` · `FACILITATOR_TIMEOUT` 15 `connectors.py:47` · `BASE_RPC_URL` default `https://mainnet.base.org` `config.py:57`.

---

*The report was generated on 2026-11-03 at HEAD `66a0ce4`. All line numbers refer to that revision state.*
