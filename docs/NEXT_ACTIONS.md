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

## 1. Send — five messages, ready, verified destinations

| # | To | Where | What |
|---|---|---|---|
| 1 | Ernest | `ernest@nolimbsfighting.com` | yes to the CDP support request; asks whether anyone buys pre-payment verification |
| 2 | r/x402 | the fourfold thread, 23.11 | comment on why the numbers move and what they do not show |
| 3 | Virtuals ACP | `Virtual-Protocol/acp-cli/issues/new` | can a hosted HTTP service be an offering? |
| 4 | Olas | `t.me/olaschat` | same question, their shape |
| 5 | x402scan | `Merit-Systems/x402scan/issues/1270` | update our listing: new host, 7 routes |
| 5b | x402scan | `Merit-Systems/x402scan/issues/1340` | confirm the vercel.app host is dead, remove the rows |

Order: **1, 2, 5b, 5, 3, 4.** Ernest first because he is already measuring us.
The two x402scan ones are housekeeping that costs nothing. ACP and Olas last
because they may need a follow-up conversation rather than a message.

---

## 2. Owner decisions — nothing moves without them

| # | Decision | Why it waits |
|---|---|---|
| 1 | **PayAPI's `Price` field** says "$0.003 to $0.005" and "3 endpoints"; the page text says seven routes at $0.005–0.050. Email Chet? | Under-prices us for a buyer who budgets from the structured field. No email sent. |
| 2 | **Remove `X402LIST_VERIFICATION_TOKEN`** after 26.11 15:06Z | The env var has no expiry check, so the well-known path keeps serving a stale proof. Removal plus a redeploy. |
| 3 | **Tell Jamenbin** the fixture moved from `d76537a7…` to `3d76d803…` | He verified v1 and was never told it changed. The `REVISIONS` block records it; he does not know. |
| 4 | **Free or pilot tier** — allowed or not? | Needed before any marketplace conversation can promise anything. |

**All four approved by the owner on 24.11.2026.** Actions:
`OUTREACH_DRAFTS.md` J1 (PayAPI, to `hello@payapi.market`), a reminder set for
26.11 17:10 EET for the token, `OUTREACH_DRAFTS.md` J2 (Jamenbin, at
`VibeMirror-coder/n8n-nodes-omnidome#3`), and the pilot tier is now allowed.

---

## 3. Marketplace — the priority, and where it stands

Full detail in `docs/ACP_MARKETPLACE_PLAN.md`.

**What the ACP documentation answers:** a hosted HTTP service cannot be an
offering directly — an offering belongs to an agent, and the agent does the work.
`acp browse` needs an active agent, so the marketplace cannot be inspected until
we register. The order is therefore: **authorise → create the agent → browse →
only then decide whether to build the provider worker.**

**The auth link, generated 24.11.2026 15:33 EET:**

`https://app.virtuals.io/acp/auth/v2?requestId=6cdc56bd37d2dfce6e77edcbacb1ccf9`

If it has expired, run `acp configure start` again — it costs nothing. The CLI is
installed at `_tools/acp/node_modules/.bin/acp.cmd` (v1.0.0, 400 packages).

**One thing to weigh before committing:** ACP pays on buyer acceptance, not on
delivery. The money sits in escrow and a dispute leaves it there. x402 pays
immediately and finally. For a $0.05 check the escrow overhead may cost more than
the sale — which argues for a higher price per job or a subscription.

---

## 4. Waiting on other people — no action from us

| # | Who | What |
|---|---|---|
| 1 | Abdellah | Re-running the 36-vector set against v4 (`3d76d803…`, 11 tests). Expected 22 + 14 + 0. |
| 2 | Ernest | Writing the CDP support request for the 7 duplicate rows. |
| 3 | x402-list | Manual review; the FORTE tier cannot be bought yet (§101). |
| 4 | Olas | The one message not sent. |
| 5 | Glama | Tool Count 4/5 — decision taken: do not chase it. Removing response fields to buy 0.1 of a third-party score is not worth changing a paid endpoint. |

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
