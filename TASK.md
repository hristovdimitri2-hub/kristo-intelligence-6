# TASK — Kristo Intelligence: entry briefing

> **Refreshed 11.11.2026.** This file is only an entry point, not a source of truth.
> The chronology is in `HANDOVER.md`, the measurements — in `docs/VISIBILITY_MEASURED.bg.md`,
> and the money — on chain.
>
> The previous version was a snapshot of 30.09.2026 (`3661419`) and claimed things that
> are no longer true: 6 paid routes, 423 tests, production on a werkzeug dev server.
> The numbers below were checked on 11.11.2026.

## What the project is

A paid DeFi / on-chain market-intelligence API for AI agents on **Base** (chain id 8453),
with payment via **x402** (402 → USDC by EIP-3009 → 200). No registration, no subscription,
no API keys.

- **Live:** https://kristo-intelligence-api.onrender.com
- **Repo:** `hristovdimitri2-hub/kristo-intelligence-6` · MIT license
- **Paid routes:** **12 HTTP** (7 canonical + 5 aliases with buyer names) plus
  **7 MCP tools**; prices **$0.003–$0.01** during the pilot (see below)
- **Price source:** `config.py` (`KRISTO_*_PRICE`, each reads `os.getenv`)
- **Key documents:** `HANDOVER.md`, `docs/VISIBILITY_MEASURED.bg.md`,
  `PROJECT_STATUS.md`, `docs/PROJECT_CHRONOLOGY.md`

## Status as of 11.11.2026

| | |
|---|---|
| Tests | **1316** (1314 passed, 1 skipped) |
| CDP catalog | 19 rows; the new `serviceName`, `tags` and descriptions are **published** |
| CDP search | finds us for **12 of 14** buyer queries, **5 of them in first place** |
| PayAI Bazaar | first places for `verify seller`, `onchain sales`, `trading signal`, `telegram bot status`, `arbitrage` |
| Price pilot | the two seller-audit routes at **$0.01** until 11.12.2026 (the revert is scheduled) |
| External payers | **none new**; historically 9 (see the dashboard). The last payment that is not ours is from a crawling bot (`0xa19f…`) on 11.11 02:47:06 UTC |

**Active reminders:** 14.11 19:45 — shortening of `X402_FACILITATOR_TIMEOUT` for
the CDP window; 15.11 04:05 — revert; 11.12 10:00 — price revert after the pilot.

## Open decisions (owner)

1. Do we count the bot's payment as the "first external payer" under the **literal** text of
   the goal, or not — in spirit (the same address pays 269 recipients in two days)?
2. Text for external sending to the catalog operators — yes or no.

## Known debt (non-blocking)

- memory leak; frozen heartbeat of the chain monitor; connection leak in
  `integrations/dashboard_store.py:822`; empty memory metrics from Render;
- the `server.json` icon is SVG — the format that CDP rejects (in 402 it is already PNG);
- 4 routes are not yet registered in x402dash (limit 5/hour, a batch is scheduled);
- the request to x402scan has been pending since 08.10 with no answer; in Glama we have no
  public listing.

## Rules that are not violated

- **Prices, `payTo`/recipient, commission, the format of the 402 wrapper, `secrets/`,
  `config.py`, `.env`** — not touched without an explicit owner decision.
- **Render env** is changed only one **single** key at a time. `PUT` on the
  `/env-vars` collection replaces all variables and is forbidden (on 07.11 it deleted the
  configuration).
- **Money:** first a wallet check, then payment; on timeout — first a measurement,
  never a blind retry.
- **Nothing external is published** without an explicit "yes".
- **Our own payments are not clients.** The demo key has its own class (`own_key`),
  so that it is not counted as a client on the dashboard.
