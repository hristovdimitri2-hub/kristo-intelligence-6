# TRAFFIC AUDIT — who is watching us (11.09, read-only)

Source: persistent request log (SQLite on Render) via `/api/dashboard/data`.
The day: 2026-09-11 · today: 13 792 requests (cumulative /health: 42 097 — the
noise is ours).

## Who is watching us — paths (aggregated from the log)

| Path | Count (log window) | Type |
|---|---|---|
| `/health` | 42 097 | ⚙️ our keep-alive (`Render/1.0`) + Render checks — self-noise |
| `/api/v1/signal` | 2 028 | agent/crawler probes of a paid route |
| `/.well-known/x402` | 570 | x402 indexers (discovery) |
| `/openapi.json` | 564 | indexers/catalogs |
| `/api/bot-status` | 451 | paid probes |
| `/api/sales` | 440 | paid probes |
| `/api/stats` | 438 | paid probes |
| `/robots.txt` | 392 | search engines/indexers |
| `/api/mcp/manifest` | 322 | MCP clients/catalogs |
| `/mcp` | 65 | MCP manual clients (Streamable HTTP) |

## Top User-Agents (full-day SQL aggregation — 11.09, log window)

| UA | Count | Type |
|---|---|---|
| `python-requests/2.34.2` | 4 | scripts/agents (undetermined type) |
| `ClaudeBot/1.0 (+claudebot@anthropic.com)` | 2 | 🟢 **Anthropic ClaudeBot — platform indexer** (first move by a big player!) |
| `Go-http-client/1.1` | 1 | indexer/agent (Go client) |
| `CarbonMonitor/0.1 healthcheck (+carbon-cashmere.de)` | 1 | monitor (dumb healthcheck on a paid route) |
| `Render/1.0` | 43 (separated) | ⚙️ internal noise |

*(the series covers the period since the last deploy — the ephemeral disk resets
the log; see the incident note in PROJECT_STATUS below. The top-UA table is
filled in automatically on every check.)*

## Funnel ("caught holding hands" — measured live, 11.09)

| Route | Today: 402 challenges → paid | Conversion |
|---|---|---|
| `/api/v1/signal` | **1 → 0** | 0% (the log is from the last deploy) |
| `/api/stats`, `/api/sales`, `/api/bot-status`, `/api/arb/*` | 0 → 0 | — |

## Hourly peaks (today)

| Hour (UTC) | Requests | of which noise |
|---|---|---|
| 14:xx | 51 | 43 (keep-alive) |
| clean | **8** | — |

## Cash desk (check)

- New payments from 0x4dB7 / 0xA19F today: **NONE** (external_unique_payers
  remains 2; the OPERATOR REPEAT detector did not light up — both are first-touch).
- On-chain cash desk: **$0.023 / 7 transfers** (2 external, 4 canary, 1 crawler).

## One sentence

**Today 100% of the traffic is indexers, monitors and our own keep-alive noise —
but ClaudeBot/1.0 (Anthropic) is already scanning the discovery, which is the
closest-to-a-buyer signal from the listings; the real buyers (0x4dB7, 0xA19F) are
from 06.09/09.09 and are waiting for a repeat (the OPERATOR REPEAT trigger is
armed).**

## Cash desk (check)

- New payments from 0x4dB7 / 0xA19F today: **NONE** (external_unique_payers
  remains 2; the OPERATOR REPEAT detector did not light up — both are first-touch).
- On-chain cash desk: **$0.023 / 7 transfers** (2 external, 4 canary, 1 crawler).

## One sentence

**Today 100% of the traffic is indexers, monitors and our own keep-alive noise —
nothing looks like a future buyer; the real buyers (0x4dB7, 0xA19F) are from
06.09/09.09 and are waiting for a repeat (the OPERATOR REPEAT trigger is
armed).**

## Missing depth (honestly)

Per-UA full-day breakdown (top 10 for the whole day) and hourly peaks require a
GROUP BY aggregation in the persistent log — it is part of "Caught Holding Hands"
(the funnel tool); after deploy the document is supplemented with the real top-10
UA table and the hourly peaks.
