# INDEX — where everything is

**Who this is for:** anyone who has to work on this project — a new agent, an
external auditor, or a person coming back after a month. Read this before you go
looking for files.

**Last change:** 16.11.2026.

---

## 0. Read this first if you are an external auditor

**Check that you are reading the LIVE copy before you judge anything.**

Three independent audits so far were performed against **stale copies** — one
GitLab mirror that stops at `HANDOVER.md` §39, and one file `HANDOVER.md.` (with a
dot) in the root that stops at §57. All three times more than half of the findings
described a repository that no longer exists.

The live copy:

```
https://github.com/hristovdimitri2-hub/kristo-intelligence-6     (public)
https://raw.githubusercontent.com/hristovdimitri2-hub/kristo-intelligence-6/main/HANDOVER.md
https://raw.githubusercontent.com/hristovdimitri2-hub/kristo-intelligence-6/main/docs/INDEX.md
```

**How to tell that a copy is stale:**
- `HANDOVER.md` must be **over 4 300 lines** and must reach **§66**.
- If it reaches §39 or §57 — the copy is stale, do not judge by it.
- If you see a file `HANDOVER.md.` (with a dot) — that is a manual copy through the
  web editor, it is not a version. The live repo does not contain it.

---

## 1. The live system

| | |
|---|---|
| **Production** | `https://kristo-intelligence-api.onrender.com` |
| **Repository** | `https://github.com/hristovdimitri2-hub/kristo-intelligence-6` (public) |
| **Hosting** | Render, one web service, **one worker** (`--workers=1 --threads=8`) |
| **Network** | Base mainnet (`eip155:8453`), USDC |
| **Protocol** | x402 v2 — `PAYMENT-REQUIRED` header + a copy in the body |
| **Recipient** | `0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844` (changed 16.11.2026) |
| **Gas wallet** | derived from `WALLET_PRIVATE_KEY`, not a constant in the code |

Paid routes (8): `/api/v1/signal`, `/api/v1/whaleflow`,
`/api/arb/opportunities`, `/api/bot-status`, `/api/sales`, `/api/stats`,
`/api/v1/verify-seller`, `/api/v1/seller-check`.

---

## 2. Where to start

| if you want | read |
|---|---|
| **what the project is** | `README.md` (English), `README.bg.md` (Bulgarian) |
| **the whole history and decisions** | **`HANDOVER.md`** — chronological record, 4300+ lines |
| **what is open RIGHT NOW** | **`HANDOVER.md` §62** — the only live list |
| **tasks for an external auditor** | `docs/AUDIT_BRIEF.md` |
| **how the payment gate works** | `docs/GUARD_METHODOLOGY.md` |
| **where we are listed** | `docs/DISTRIBUTION_STATUS.md` |
| **how deployment happens** | `DEPLOYMENT.md`, `DEPLOYMENT_CHECKLIST.md` |

---

## 3. The documentation by purpose

### The record (chronology and context)

| file | lines | what it is |
|---|---|---|
| `HANDOVER.md` | 4381 | **The main document.** Chronological record from 09.11 onward, §1–§66. Every section is dated and says whether it is a measurement or a conclusion |
| `docs/PROJECT_CHRONOLOGY.md` | 264 | Full chronology from the freeze on 27.08 |
| `docs/CONTEXT_AND_ROADMAP.md` | 488 | Context and the way forward |
| `docs/ACTION_BOARD.md` | 395 | Task board, including unaddressed ones (F-findings) |
| `docs/weekly/2026-09-29.md` | 71 | Weekly minutes |

### The open work

| file | lines | what it is |
|---|---|---|
| `HANDOVER.md` §62 | — | **The live list of what is open** — waiting on the owner / external / internal |
| `docs/AUDIT_BRIEF.md` | 350 | Brief with 26 tasks for an external auditor |
| `docs/MULTICHAIN_PLAN.md` | 150 | **Plan for a second chain** — measured cost, phases, and why the audit matters more than the payment |
| `TASK.md` | 63 | Entry briefing |
| `docs/WATCH_LIST.md` | 12 | Actively being watched |

### Audits (external and internal)

| file | lines | what it is |
|---|---|---|
| `docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md` | 573 | The largest audit — performance and architecture |
| `docs/HAIKU_AUDIT.md`, `docs/HAIKU_AUDIT_DEEP.md` | 126, 113 | Two audits by an external model |
| `docs/PRODUCT_AUDIT.md` | 137 | Product and competitor |
| `docs/DASHBOARD_AUDIT.md` | 165 | The dashboard, sources, NEXUS |
| `docs/LISTING_CHANNELS_AUDIT.md` | 164 | Listing channels |
| `docs/TRAFFIC_AUDIT.md` | 80 | Who is watching us |
| `docs/MYSTERY_AGENT_REPORT.md` | 70 | Simulation of a hostile buyer (23/23) |

### The payment path

| file | lines | what it is |
|---|---|---|
| `docs/GUARD_METHODOLOGY.md` | 204 | **Field notes from working with 402 in production** — the C1/C2/H2 gates |
| `docs/VERIFIER_RESEARCH.md` | 110 | Research on the verifier layer |
| `docs/WHALE_FLOW_SPEC.md` | 92 | Specification of whale flow |
| `docs/SALE_DIAGNOSIS.md` | 76 | The first external payment |
| `docs/ORGANISM.md` | 164 | How the platform observes itself |

### Listings and distribution

| file | lines | what it is |
|---|---|---|
| `docs/DISTRIBUTION_STATUS.md` | 73 | Where we are listed and in what state |
| `docs/PAYAPI_AGENT_LISTING.md` | 116 | The listing in the PayAPI agent marketplace |
| `docs/MCP_REGISTRATION_PACKET.md` | 116 | Registration packet for MCP catalogs |
| `docs/MCP_ACCOUNTS_GUIDE.md` | 71 | Instructions for registrations (in Bulgarian, without jargon) |
| `docs/PULSEMCP_SUBMISSION_READY.md` | 107 | Ready for submission |
| `docs/SCAN_LISTING_DRAFT.md`, `docs/SCAN_LISTING_EN.md` | 156, 45 | Drafts for x402scan |
| `docs/BAZAAR_RESEARCH.md` | 126 | Research on Bazaar and discovery |
| `REGISTRATION_CHECKLIST.md` | 177 | Checklist for registrations |

### Architecture and deployment

| file | lines | what it is |
|---|---|---|
| `docs/ARCHITECTURE.md` | 552 | Production architecture (from v5) |
| `DEPLOYMENT.md` | 372 | Deployment guide |
| `DEPLOYMENT_CHECKLIST.md` | 343 | Checklist |
| `PRODUCTION_DEPLOYMENT_REPORT.md` | 143 | Report from the deployment |
| `ops/production_readiness_checklist.md` | 41 | Production readiness |
| `docs/QUICK_START.md` | 402 | Quick start (from v5) |
| `docs/TEST_REPORT_2026-08-17.md` | 241 | Test report (from v5) |

### Marketing and outreach

| file | lines | what it is |
|---|---|---|
| `docs/VISIBILITY_MEASURED.bg.md` | 1345 | **Measured visibility** — the most detailed marketing document |
| `docs/VISIBILITY_AND_TRAFFIC_STRATEGY.md` | 457 | Strategy |
| `docs/DISCOVERY_AND_TRAFFIC_PLAN.md` | 300 | Plan for discovery and traffic |
| `docs/OUTREACH_KIT.md` | 165 | Tools for contacting the ecosystem |
| `docs/OUTREACH_WAVE1.md` | 185 | **Drafts — DO NOT SEND** |
| `docs/CHET_WHALE_CANARY.md` | 54 | Draft to Chet (PayAPI) — **do not send as is, see the note inside** |
| `docs/CHET_DATA_PACKAGE.md` | 61 | Data sent to Chet |
| `docs/GLAMA_REPLY.md`, `docs/LOOPEMAIL_PACKAGE.md` | 51, 72 | Replies to reviewers |
| `docs/MARKET_WRITEUP.md` | 140 | Public market analysis |
| `docs/MARKETING_KIT.md`, `docs/CONTENT_PACK_1.md` | 139, 180 | Marketing materials |
| `marketing/offer-and-ad-strategy.md`, `launch/` | — | Offer and launch plan |
| `docs/blog/2026-10-23-x401-x402-one-gate.md` | 79 | Public post |

### Reports (dated, in Bulgarian)

`docs/REPORT_2026-11-04_WORK.bg.md` (214) · `docs/REPORT_2026-11-04_DISTRIBUTION.bg.md` (206) ·
`docs/REPORT_2026-11-07_ORGANISM.bg.md` (198) · `docs/REPORT_2026-11-08_ORGANISM_LIVE.bg.md` (127) ·
`docs/REPORT_DVA_DNI_2026-11-08.bg.md` (209)

### Radar and reconnaissance

`docs/AP2_RADAR.md` (366) · `docs/RECON_FINDINGS.md` (212) · `docs/PAYER_ORIGIN.md` (59) ·
`docs/NEW_PAYER_09b2.md` (85) · `docs/NEW_OPERATOR_ANALYSIS.md` (41)

---

## 4. Map of the code

| file | lines | what it is |
|---|---|---|
| `main.py` | ~9 700 | **The monolith.** Payment rail, the 402, the gates, organism, the dashboard |
| `config.py` | 171 | Single source for prices, recipient, network. Normalizes EIP-55 |
| `services/connectors.py` | ~1 550 | The facilitator chain, self-broadcast, CDP JWT |
| `services/verifier.py` | 312 | Cross-checking of prices (CoinGecko × DexScreener) |
| `integrations/dashboard_store.py` | ~4 400 | Postgres: ledger, gate events, sales |
| `app/blueprints/discovery.py` | ~4 050 | Public manifests: `/.well-known/x402`, OpenAPI, llms.txt |
| `redaction.py` | 74 | `redact_rpc` — masks keys and passwords in exceptions |
| `tests/` | 1 415 tests | `python -m pytest tests -q` (~7 min) |

**Redaction rule:** every exception that can reach a public surface goes through
`redact_rpc()`. Breaking this rule has been the most repeated defect in the
project.

---

## 5. What is NOT in the repository

| what | where it is | why |
|---|---|---|
| `secrets/` | on the owner's machine, gitignored | keys: `gas_wallet_key.txt`, `receiver_key.txt`, `demo_private_key.txt`, `render_api_key.txt`, `cdp_api_key.json` |
| `_forensics/` | `C:\Users\AlienWare\.dsh\state\superagent\_forensics\` | ~40 diagnostic scripts. **A new session cannot run them until it finds them there** |
| `.env` | the machine | real values; `.env.example` is in the repo |
| Render env | Render dashboard | 40 variables; visible with `secrets/render_api_key.txt` |

**Consequence for an auditor:** claims of the kind "this address is not in the
repo" prove nothing about production. The gas wallet, for example, **is not** a
constant in the code — it is derived from `WALLET_PRIVATE_KEY` at start. Its
absence from the repo is the correct state, not an omission.

---

## 6. The traps that have already cost us

Four classes of defects repeat. Each one is recorded in `HANDOVER.md` with a date.

1. **Something cannot be looked at and the surface shows it as looked at and
   empty.** An empty panel that looks like a zero. `delivered_at IS NULL`,
   which looked like "the buyer received nothing", but meant "there was not yet a
   stamp" (§55). If you find such a place — it matters more than any crash.
2. **A document is taken as fact after it has gone stale.** That is why every
   section in `HANDOVER.md` is dated and says measurement or conclusion.
3. **An exception reaches a public surface without redaction.** Nine places in
   `services/connectors.py`, fixed on 16.11 (§66).
4. **A wait that refuses instead of waiting.** The gate was refusing a payment for
   a wait that had almost already finished (§66).

---

## 7. If you are looking for something and cannot find it

Ask in this order:

1. `HANDOVER.md` §62 — whether it is in the list of what is open
2. `grep -rn "term" .` in the repo
3. `docs/ACTION_BOARD.md` — whether it is recorded as unaddressed
4. `_forensics/` on the owner's machine — that is where one-off diagnostics live
