# The Organism — how the platform watches itself

**Built:** 2026-11-07 · **Status:** sense layer and memory live; executors not built

---

## The problem this solves

Every defect this project has had was found by a human-run audit, diagnosed in a
human-run session, and fixed by a human-run commit. The system *watched* — the
sentinel sent Telegram on health, revenue and GitHub changes — but it carried no
model of its own health, so **each session re-discovered what the last one already
knew.** The owner's words: *"решаваме един проблем, излиза друг."*

The cost is not the fixing. It is the re-discovery.

---

## What is built

### Six blocks, one vocabulary

Each block owns a distinct failure domain, so one dying cannot make another look
dead — the property the dashboard already proves for its panels.

| Block | Owns | Heartbeat written by |
|---|---|---|
| `payment_rail` | settlement, guards, facilitator chain | a completed settlement, or a failed one |
| `chain_read` | RPC, receiver balance | the sentinel's revenue check |
| `data_store` | Postgres, retention, snapshot | the dashboard scan loop and snapshot warmer |
| `discovery` | public repo, registries | the sentinel's GitHub check |
| `alerting` | Telegram, VIP routing | the sentinel's health check |
| `delivery` | the board, deploy | the dashboard warmer, and boot |

Four verdicts, and the fourth is the point:

```
ok            the block reported, and it is well
degraded      working, but something is wrong
failed        the block reported a failure
not_reached   THE CHECK DID NOT RUN
```

**`not_reached` is counted as unhealthy.** "We did not look" is not the same as
"we looked and it was fine", and the single most dangerous thing this system could
do is report a confident `ok` produced by a check that never executed. That is the
defect class this codebase spent a week closing one surface at a time; the
organism holds it for the whole system at once.

A block that has never reported is `not_reached` — which is exactly why a fresh
deploy shows **six unhealthy blocks** rather than a clean sheet.

### The journal

An append-only, bounded, never-raising record of what the system noticed and did.

- **Append-only.** A journal that can be edited can be made to say anything.
- **Bounded on write** (`MAX_ENTRIES = 2000`), because a table with no retention
  is what took the service down on 07.11.
- **Never raises.** It is written next to payment handling; telemetry must not be
  able to fail the thing it describes.
- **`kind` is normalised** (`"Settle Failed"` → `settle_failed`) so the future
  rule table matches one token per signal.

Severities: `observe` · `info` · `warn` · `error`.

---

## Where to see it

`GET /api/dashboard/data` → `sections.organism` and `sections.journal`.

```json
"organism": {
  "blocks": [{"block": "payment_rail", "verdict": "ok", "age_seconds": 12.4, …}],
  "counts": {"ok": 2, "degraded": 1, "failed": 0, "not_reached": 3},
  "unhealthy": 4
}
```

`unhealthy` includes `not_reached`. If the organism itself cannot be read, the
payload says `available: false` — it does **not** render six healthy blocks.

---

## The honesty rules, held by construction

1. A self-check that raises returns `not_reached`, never `ok`.
2. A self-check returning the wrong type returns `not_reached`.
3. A block with no registered check returns `not_reached`.
4. A heartbeat older than 5 minutes that last said `ok` is reported as **failed** —
   a writer that stopped leaves behind a last word of "fine".
5. A missing heartbeat is `not_reached`, not healthy.
6. An empty journal and an unreadable journal are different answers.
7. A failed organism read is `available: false`, not a clean summary.

Each of these has a test in `tests/test_organism.py`.

---

## What is NOT built, and why

**The rule table and the executors.** The design calls for a deterministic table
mapping a signal to an action (`rpc_endpoint_refused` → `rotate_endpoint`), with
three guards: a blast-radius cap, per-action verification, and a journal entry for
every action.

It is deliberately not here yet, for one reason: **a rule you cannot see firing is
a rule you cannot trust.** The journal has to accumulate real signals first, so the
frequencies are known before anything is allowed to act on them. Building the
executors first would mean guessing which rules matter.

**Nothing in the plan moves money, changes a price, edits a receiver, touches
`secrets/`, or pushes to `main`.** Those stay escalated to the owner,
permanently.

---

## Honest limits

- **A rule table cannot fix a novel defect.** It closes the *known* failure modes
  permanently so human attention is spent only on the new.
- **Self-healing can mask rot.** A monitor that silently restarts forever looks
  identical to a healthy one. That is why a rising heal count in the journal is
  itself the signal the owner should watch.
- **`not_reached` on a fresh deploy is expected, not a defect.** It becomes a
  finding only if it persists.
