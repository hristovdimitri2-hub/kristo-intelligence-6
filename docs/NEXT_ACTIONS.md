# Next actions — consolidated

**Compiled 24.11.2026, 15:20 EET.** This supersedes `docs/ACTION_BOARD.md`
(03.11.2026), which is kept as history. One page, in the order to work through
it. Full text of every message is in `docs/OUTREACH_DRAFTS.md`.

---

## The one priority

**The catalogue work is done. The marketplace work has not started.**

Six catalogues and directories now list us — CDP Bazaar, MCP Registry, Glama,
x402-list, x402scan, the awesome-list PR. Six listings, zero external calls ever.
That is not a distribution failure; it is the wrong kind of channel. A catalogue
is where an agent looks when it already knows what it wants. A marketplace is
where an agent goes to hire. We have never been in a marketplace.

The measured market (§108) says the same thing from the other side: x402 money
goes to **high-ticket integrations** or **high-frequency embedded pipelines**.
Our product is neither — a $0.005 lookup that an agent finds in a catalogue has
no reason to be called twice. More listings cannot fix that. An integration can.

**Two places where a hire happens on Base:**
- **Virtuals ACP** — offerings with escrow, `Virtual-Protocol/acp-cli`.
- **Olas Mech** — 14 323 settlements measured, `t.me/olaschat`.

---

## 1. Sent — five of six, by the owner on 24.11.2026

| # | To | Where | State |
|---|---|---|---|
| 1 | Ernest | `ernest@nolimbsfighting.com` | sent |
| 2 | r/x402 | the fourfold thread, 23.11 | sent |
| 3 | Virtuals ACP | `Virtual-Protocol/acp-cli/issues/new` | sent |
| 4 | Olas | `t.me/olaschat` | **not sent** — the only one left |
| 5 | x402scan | `Merit-Systems/x402scan/issues/1270` | sent |
| 5b | x402scan | `Merit-Systems/x402scan/issues/1340` | sent |

### 1b. Ready to send — two from Ernest's reply of 24.11

| # | What | Where | Note |
|---|---|---|---|
| 6 | **The CDP ticket** | support, as a reply in the Ernest thread | Ernest wrote it; we re-measured every row and corrected one claim. Text in `OUTREACH_DRAFTS.md` §L. Add your name. |
| 7 | **Reply to Ernest** | the same Gmail thread | Accepts his free benchmark of the seven routes; asks how he wants a referral introduced. Text in `OUTREACH_DRAFTS.md` §L2. |

**Why the ticket changed.** Ernest's second request said all MCP descriptions were
stale. Seven of eight were refreshed on 24 November by paying through each tool;
only the duplicate is still stale. Sending the original would have asked CDP to
answer a question we no longer have.

---

## 1c. What Ernest measured, and what it means

He read the whole CDP Bazaar discovery dump: **34,893 rows, 30-day window**, calls
per row multiplied by that row's price.

| | |
|---|---|
| Top 10 rows | **92%** of all spend |
| Top 100 rows | **96.9%** |
| Median revenue per row | **$0.01 per 30 days** |
| Rows reaching $1/month | 1,161 of 34,893 — **3.3%** |
| Hosts reaching $100/month | **32** |
| Rows with exactly one call in 30 days | **18,885** — mostly the owner testing their own route |

The verification routes that do sell are all occupied, and all by whoever
registered the space first:

| route | calls / 30d | price |
|---|---|---|
| `api.agents-trust.com/recommend` | 14,621 | $0.01 |
| `agent.pocket.network/v1/sanctions-watchlist-screen` | 3,733 | $0.005 |
| `api.strale.io/x402/domain-age-check` | 454 | $0.032 |
| `api.strale.io/x402/domain-reputation` | 219 | $0.054 |
| `api.strale.io/x402/sanctions-check` | 122 | $0.216 |

**His straight answer, in his words:** pre-payment trust checks *are* bought, as
$0.005–$0.05 lookups in the thousands — but he sees **no provider paying for the
pattern we built**, a platform checking a stranger's receiving wallet before paying.
Platforms absorb that cost themselves or run a sanctions screen. Nobody is buying
it as a standalone operation right now, and refining the route does not change
that, **because a route is invisible to buyers until someone has paid through it
and written the catalogue row.**

**His advice:** stop treating per-call fees as revenue — they are negligible unless
a volume buyer has no alternative. Two things earn: **(a)** data a buyer cannot get
anywhere else, or **(b)** selling the measurement itself, which is what he does and
what we have now bought twice.

**The consequence for us.** `verify-seller-receiver` is not a business, and neither
is any other single route we could add. The top verification route in the entire
index earns about $146 a month. This is the same conclusion the ACP work reached
from the other side: a catalogue entry is found only after it has been paid, and a
marketplace is where you are hired instead. Two doors, and both point away from
"one more route".

---

## 2. The four decisions — all approved, three finished

| # | Decision | State |
|---|---|---|
| 1 | **Jamenbin** — tell him the fixture moved | **DONE.** Comment posted 24.11 at 16:46Z on `VibeMirror-coder/n8n-nodes-omnidome#3`, verified by reading the issue back. |
| 2 | **Free or pilot tier** | **Approved.** Marketplace conversations may promise a pilot. |
| 3 | **`X402LIST_VERIFICATION_TOKEN`** | **Prepared.** Token still present (`x402list-verify-rCh48s…`, 59 chars) and `/.well-known/x402list.txt` serves it (HTTP 200). It expires 26.11 15:06Z. `_tools/remove_x402list_token.py` does the whole job — dry-run verified, `--apply` deletes the variable with `DELETE /env-vars/{key}` (never a `PUT` of the collection), triggers the deploy, then polls until the path returns 404. Reminder set for 26.11 17:10 EET. |
| 4 | **PayAPI's `Price` field** | **Blocked on the owner's email.** See §2b. |

### 2b. PayAPI — the field cannot be fixed by API

Measured 24.11 through PayAPI's own discovery API, not from memory:

| | listing says | truth |
|---|---|---|
| price | `$0.003 – $0.005` | `$0.005 – $0.05` |
| endpoints | `3` | `7` |
| base_url | correct (the new host) | correct |

The listing is `kristo-intelligence-defi-signals-api`; the record is a leftover
from their September verification, when we really did have three routes at those
prices. **Submitting again will not fix it**: their OpenAPI documents that a URL
that already exists returns the existing fields rather than refreshing them, and
Chet has warned against creating a second card for one product.

**The fix is the provider dashboard**, which needs one click in the owner's inbox:

1. Open `https://payapi.market/agent-marketplace/list`
2. Enter `hristovdimitri2@gmail.com` (the address the listing is registered under)
3. Click the sign-in link PayAPI emails, then edit the DeFi Signals API listing:
   price `$0.005 – $0.05`, seven endpoints

The email to `hello@payapi.market` (`OUTREACH_DRAFTS.md` J1) stays as the
fallback if the dashboard has no price field.

---

## 3. Marketplace — the agent exists, the signer is one click away

Full detail in `docs/ACP_MARKETPLACE_PLAN.md`.

**Done 24.11.2026:**

| | |
|---|---|
| CLI authenticated | owner wallet `0x823750e5383008ba2c3f48523b6f723b268ea62d` |
| Agent created | `Kristo Intelligence`, id `01a20e70-5e40-75cc-b063-7e1915ab544c` |
| Agent EVM wallet | `0x3724b449603cb7faf70ea87f79c3733c6d9546e4` |
| Agent Solana wallet | `45ZEZR5WQY1YexW6YHiP4GYwbLho4BsKyeK3m1ob95u6` |
| Agent email | `kristo_intelligence@agents.world` |
| Offerings / resources | 0 / 0 — deliberately empty until the market is measured |

**Blocked on:** the signer approval link, which expires five minutes after it is
generated. `acp browse` refuses with `NO_SIGNER` until a signer exists, so the
marketplace cannot be measured without it. Policy chosen: **`deny-all`** — we are
only looking, so the agent should not be able to sign anything on its own. Switch
to `restricted` with `acp agent set-signer-policy` if we build the provider worker.

**A Windows trap worth keeping:** `acp-cli-signer-windows.exe` cannot write to
`%APPDATA%\acp-cli` — the sandbox gives spawned binaries read-only access outside
the workspace, so key generation dies with "Access is denied". Redirect **only**
`APPDATA` (to `_tools\home\AppData\Roaming`) and leave `USERPROFILE`/`HOME` alone:
the CLI keeps its token in `~/.config/acp`, and moving that loses the session.

**One thing to weigh before building anything:** ACP pays on buyer acceptance,
not on delivery. The money sits in escrow and a dispute leaves it there, while
x402 pays immediately and finally. For a $0.05 check the escrow overhead may cost
more than the sale — which argues for a higher price per job or a subscription.

---

## 4. Waiting on other people — no action from us

| # | Who | What |
|---|---|---|
| 1 | Abdellah | Re-running the 36-vector set against v4 (`3d76d803…`, 11 tests). Expected 22 + 14 + 0. |
| 2 | Ernest | Writing the CDP support request for the 7 duplicate rows. |
| 3 | x402-list | Manual review; the FORTE tier cannot be bought yet (§101). |
| 4 | Glama | The `/mcp/servers/` record — Discord message ready in `OUTREACH_DRAFTS.md` §K. |
| 5 | Glama | Tool Count 4/5 — decision taken: do not chase it. Removing response fields to buy 0.1 of a third-party score is not worth changing a paid endpoint. |
| 6 | Glama, the `/mcp/servers/` record | The connector is listed and rated A; the `/mcp/servers/` record does not exist and cannot be created from our side (both Add Server paths reject "already listed as a hosted connector"). `quality` is computed only for `/mcp/servers/`, so `awesome-mcp-servers` PR #13219 cannot merge. Discord message drafted in `OUTREACH_DRAFTS.md` §K; ticket #135407945 open since September. |

---

## 5. Technical — open, not urgent

| # | Item | State |
|---|---|---|
| 1 | Two-process deploy overlap | Render runs old and new instance together during a deploy, so log streams interleave. Harmless; makes "which process answered" non-deterministic from outside. |
| 2 | `autoDeploy` is on | Every push deploys production. Documentation commits carry `[skip render]`; verified to work. Build filters would be better but risk blocking real deploys. |

---

## 6. Done — so it is not reopened

| | |
|---|---|
| MCP Registry | `6.3.1` published, verified in the registry: 6 new descriptions, 0 old |
| CDP Bazaar | all 7 MCP rows carry the current descriptions |
| Two unbuyable routes | `/api/arb/opportunities` and `/api/v1/signal` refused every buyer because the serving process never started its producers; fixed, both now sell |
| Free samples | 7/7 return 200 |
| Documentation | 95/95 markdown files in English, zero Cyrillic |
| Suite | 1444 collected, 1443 passed, 1 skipped |
| Python client | `scripts/` + `docs/` — a paid call proven end to end |

---

## 6. Today's clock

**18:00 EET — x402 Identity Working Group.** Reminder set for 17:40. Public
meeting, listening only is enough. Three things we could raise: the two rails
(nonce vs proof), who the payer is under delegated payment, and the missing
ERC-8004 identity in our own announcements.
