# Bazaar / Discovery + Session Pricing — research (2026-10-07)

> Research only. No code, no public registration.
> Registration/listing in a public catalog = a public action → waits for an explicit "Yes".
> Sources: docs.x402.org, docs.payai.network, docs.cdp.coinbase.com,
> specs/ in `x402-foundation/x402`, npm `@x402/extensions@2.28.0`, GitHub code search.

---

## 1. What is supported

### 1.1 Bazaar / Discovery extension — YES, it is supported by everyone

| Who | Support | Evidence |
|---|---|---|
| **x402 specification** | ✅ official extension | `specs/extensions/bazaar.md` in `x402-foundation/x402`; docs: https://docs.x402.org/extensions/bazaar |
| **PayAI** (our facilitator) | ✅ full, automatic listing | https://docs.payai.network/x402/facilitators/bazaar.md |
| **Coinbase CDP** | ✅ in the SDK | `buildBazaarDeclaration(method, path)` in cdp-sdk (`server-extensions.ts:113`), constant `CDP_EXTENSION_BAZAAR` |

**How it works (the general scheme):**
1. The server declares it in the **402 body → `extensions.bazaar`** (exact JSON below).
2. The client **echoes** the declaration in the payment payload (mandatory behaviour in x402 v2 —
   "the client must include at least the extension info it received").
3. The facilitator indexes on `/verify` and `/settle` (PayAI: since 2026-07-29 the verify also
   records it, with no settlement needed).
4. The facilitator returns the **`EXTENSION-RESPONSES`** header after payment.

**`EXTENSION-RESPONSES` (HTTP header):**
- Value: base64 of JSON, key = the name of the extension.
- `bazaar.status` ∈ `"success"` | `"processing"` | `"rejected"` (+ `rejectedReason` on reject).
- Example: `EXTENSION-RESPONSES: eyJiYXphYXIiOnsic3RhdHVzIjoic3VjY2VzcyJ9fQ==` → `{"bazaar":{"status":"success"}}`.
- Its absence is **not** an error signal ("its absence carries no signal").

**`declareDiscoveryExtension`:**
- A helper in the **`@x402/extensions`** package (npm, latest **2.28.0**), quoted in the PayAI docs:
  "The `@x402/extensions` package builds a valid declaration for you (`declareDiscoveryExtension`), including the JSON schema the facilitator validates against."
- Equivalent in the CDP SDK: `buildBazaarDeclaration(method, path)` (the wire shape follows
  `go/extensions/bazaar`).
- Our implementation (Flask, pure Python) uses a **manually assembled declaration** — the valid
  wire shape is one and the same; the helpers are TS-only.

**Wire shape of the declaration (402 body):**
```json
{
  "x402Version": 2,
  "resource": { "url": "...", "description": "...", "mimeType": "application/json",
                "serviceName": "...", "tags": ["..."], "iconUrl": "..." },
  "accepts": [ ... ],
  "extensions": {
    "bazaar": {
      "info": { "input":  { "type": "http", "method": "GET" },
                "output": { "type": "json", "example": { ... } } },
      "schema": { "$schema": "https://json-schema.org/draft/2020-12/schema", ... }
    }
  }
}
```
- GET/HEAD/DELETE → `QueryInput` `{type, method}`; POST/PUT/PATCH → `BodyInput`
  `{type, method, bodyType:"json", body:{...}}` (`body` is mandatory for BodyDiscoveryInfo).
- **Optional service-level fields:** `serviceName`, `tags`, `iconUrl` on `resource`.
- Networks in the catalog: `eip155:8453` (Base), `eip155:84532`, Solana mainnet/devnet — USDC.

**Listing at PayAI:** automatic — "there is no registration form, account, or manual submission".
Catalog: `GET /discovery/resources` (+ `/discovery/listing-status?resource=…` for debugging).

### 1.2 Session pricing (`openSession` / `maxBudget`) — NO, it does not exist

Checked **everything**, 0 matches:
- `x402-foundation` org (all repos): `openSession` → **0**, `maxBudget` → **0**
- `coinbase` org: `openSession` → **0**, `maxBudget` → **0**
- `PayAINetwork` org: `openSession` → **0**, `maxBudget` → **0**
- `specs/x402-specification-v2.md`: there is no `openSession`/`maxBudget`; "session" only as an
  **application pattern**:
  - §12.2 "**Session-based access** (time-limited subscriptions)"
  - §12.6 "**Session management** for time-based access control"
  - explicitly: *"Implementation details … (budget management, … session handling) are available
    in application notes and implementation guides"* — i.e. **outside the protocol**.
- `@x402/extensions@2.28.0` tarball: 0 files with "session".

**What DOES exist as similar mechanisms:**

| Mechanism | What it gives | Where |
|---|---|---|
| **`upto` scheme** | "buyer authorizes a **maximum**, seller charges **actual usage**" — a per-request ceiling, not a session | docs.x402.org/schemes/upto |
| **`batch-settlement` scheme** | a reusable on-chain **channel** (one deposit, off-chain vouchers per request, cumulative ceiling = "charged so far + this request's maximum", claim/sweep/refund) — **the closest analogue of a session with a budget**; PayAI serves it on Base mainnet | docs.x402.org/schemes/batch-settlement; docs.payai.network/x402/servers/evm-batch-settlement |
| **`auth-capture` scheme** | escrow: hold → capture/void/refund after delivery of the resource | docs.x402.org/schemes/overview |

**Conclusion:** `openSession`/`maxBudget` **are not part of x402 v2** and neither PayAI nor CDP
documents it — probably an internal/draft term or a confusion with `upto`/`batch-settlement`.

---

## 2. What we need to change in the manifest / the 402 declaration

Our current state (`main.py`, `_x402_accepted_payment`, ~line 1528-1560) **is already a valid v2
Bazaar declaration**:
- ✅ `extensions.bazaar.info.input` = `{type:"http", method:"GET"}` (QueryInput — the correct shape
  for GET)
- ✅ `extensions.bazaar.schema` with `properties.input.queryParams` + `properties.output.example`
  (the requirement of the x402scan audit)
- ✅ `resource = {url, description, mimeType}` in the 402 body

**Missing / to be improved (in priority order):**

| # | Change | Mandatory? | Scope |
|---|---|---|---|
| 1 | `resource.serviceName` (`"Kristo Intelligence"`), `resource.tags` (e.g. `["signals","defi","base"]`), `resource.iconUrl` | No, but it enters the catalog more richly (PayAI: "Entry shows null for serviceName, tags, iconUrl… if the declaration omits them") | ~1 line in the builder |
| 2 | The client should echo `extensions` in the payment payload on `--send` (`scripts/demo_sponsored_pay.py`) — otherwise the facilitator **never sees** the declaration ("Step 2 is where most 'my resource never appears' reports come from") | **Yes** for listing via payment | ~15 lines in the client |
| 3 | Diagnostics: reading `EXTENSION-RESPONSES` after settlement + logging of `bazaar.status` | Desirable | small |
| 4 | Local validation of the declaration with the JSON schema from `@x402/extensions` (test/CI) — since we are on Python, the helper is not available | Desirable | 1 test |
| 5 | `resource.url` absolute public https URL | ✅ it already is (from `request.host_url`) | — |
| — | Changes to `GET /api/mcp/manifest` (the MCP manifest) | **No** — the Bazaar declaration lives in the 402 body, not in the MCP manifest | — |

**Session pricing:** nothing to change — it does not exist in the specification. If a
budget/monthly model is ever needed → `upto` (per-request ceiling) or `batch-settlement` (reusable
channel), not inventing an `openSession`.

---

## 3. How much work it is

| Step | Effort | Note |
|---|---|---|
| (1) `serviceName`/`tags`/`iconUrl` in the 402 builder | **~30 min** | pure addition, +1-2 tests |
| (2) Echo of `extensions` in `demo_sponsored_pay.py --send` | **~1–2 h** | tested against PayAI `/verify` (does not move money) |
| (3) Reading `EXTENSION-RESPONSES` in the client | **~1 h** | log + report |
| (4) Schema validation in a test | **~1–2 h** | schema JSON from `@x402/extensions` |
| **Total for the full Bazaar listing pathway** | **~½ day** | no public registration — the listing is automatic on the first payment/verify carrying a declaration |
| Session pricing | **0** | does not exist; if needed, a separate spike for `upto`/`batch-settlement` (~1–2 days) |

---

## 4. Risks / notes

- **Host policy (PayAI):** the first listing goes through a read-only probe (`HEAD`/`GET` → expects
  **402**); private/tunnel/preview hosts are refused. Our production URL
  (`kristo-intelligence-api.onrender.com`) is public https → ok.
- **Opt-out by default (v2):** if we remove `bazaar` from the 402 → nothing is indexed. The listing
  is "opt-in by declaration".
- **`processing` ≠ failure:** indexing is asynchronous; we do not conclude on absence immediately.
- None of the above has been published/registered — only read.

*Checked on 2026-10-07. For questions: @murrlincoln (x402) / PayAI Discord.*
