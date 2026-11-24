# REPORT — THE ORGANISM
### Kristo Intelligence · 07.11.2026

---

## In brief, in two minutes

Until now every problem was found like this: **something breaks → you see it → you ask a
session → the session starts from zero → it fixes it → the next thing breaks.**

The expensive part is not the fixing. **The expensive part is the rediscovering.** Every
session starts from a blank page and nothing the system has learned about itself survives.

Today the system received **its own idea of its health**: six blocks, each with a
heartbeat; a journal that remembers; a table of rules that decides; five idempotent actions
that are **disabled by default**; and chaos tests that prove self-healing works before we
trust it.

**The tests: 1087.** All green.

---

## 1. The problem this solves

| Before | Now |
|---|---|
| Nobody knows whether the system is well, except by indirect signs | Six blocks answer with one of four words |
| The knowledge from one session dies with it | The journal remembers every event and action |
| Every defect is found by human audit | The table recognises the known ones, a human looks only at the new ones |
| "Healthy" is an opinion | "Healthy" is a verdict with evidence |
| Self-healing — none | There is, but **disabled** until proven |

---

## 2. The six steps

| # | Step | File | What it does |
|---|---|---|---|
| 1 | **Conversion** | `dashboard_store.py` | records who saw the price, who tried, who gave up |
| 2 | **Blocks** | `organism.py` | 6 blocks × heartbeat + self-check |
| 3 | **Journal** | `organism_journal.py` | append-only, bounded, never throws |
| 4 | **Rules** | `organism_rules.py` | 12 rules, observation-only mode |
| 5 | **Executors** | `organism_executors.py` | 5 idempotent actions, **disabled** |
| 6 | **Chaos** | `organism_chaos.py` | breaks things on purpose and checks recovery |

---

## 3. The six blocks and the four words

| Block | What it watches |
|---|---|
| `payment_rail` | payments and the protections against repetition |
| `chain_read` | reading the chain |
| `data_store` | the database, retention, the snapshot |
| `discovery` | the public repo and the registries |
| `alerting` | Telegram and the alerting |
| `delivery` | the dashboard and the deploy |

| Word | Means |
|---|---|
| `ok` | it works |
| `degraded` | it works, but something is wrong |
| `failed` | broken |
| **`not_reached`** | **we have not looked at it** |

### The rule that holds everything together

**`not_reached` is never shown as "nothing was found"** — and it never gives birth to an
action.

The first part is for the reader: "we have not looked" is not "everything is fine". The
second is for the healing itself: if `not_reached` gave birth to a restart, **every start
of the service would restart six healthy loops**, because on a fresh start all six blocks
are `not_reached`.

I checked it: I deliberately broke this one rule → **9 tests fell immediately**.

---

## 4. The table of rules — the whole policy on one screen

| Signal | Class | Action |
|---|---|---|
| RPC refused | self-healing | rotate to the next one |
| heartbeat stopped | self-healing | restart the loop |
| the cache is very old | self-healing | reload |
| the index is missing | self-healing | create it |
| retention lags behind | self-healing | purge |
| page returns 5xx | self-healing | check again |
| **the deploy failed** | **escalation** | **you** |
| **the environment changed** | **escalation** | **you** |
| **money was paid, not recorded** | **escalation** | **you** |
| **nobody is buying** | **escalation** | **you (business)** |
| **claim ≠ measured** | **escalation** | **you** |
| unknown signal | observation | it is recorded |

**Escalations never reach an executor** — even with actions enabled. This is checked by a
test.

### The boundary is in code, not in a comment

A rule **cannot** name `move_money`, `change_price`, `edit_receiver`, `touch_secrets` or
`push_to_main`. These actions are not merely absent from the table — they are
**unrepresentable** in it: the constructor throws an error.

---

## 5. The five executors — and why they are disabled

**ALL OF THEM ARE DISABLED.** The system observes, decides and records. It touches nothing
until a human sets `KRISTO_ORGANISM_ACT=1`.

| Action | Why it is safe twice | Verified |
|---|---|---|
| `rotate_endpoint` | a pure choice — the same input gives the same output | ✅ `b` → `b` |
| `restart_loop` | a live thread is not touched | ✅ live: 0 starts |
| `rebuild_cache` | the reload is the same every time | ✅ |
| `recreate_index` | `IF NOT EXISTS`; **the SQL is passed literally** | ✅ refused `DROP TABLE` |
| `purge_older_than` | what is deleted is not deleted again | ✅ 2 → 0 → 0 rows |

`recreate_index` deserves attention: **an executor that can assemble SQL is an executor
that can be made to assemble the wrong SQL.** That is why the query is passed literally
and it is checked that it starts with `CREATE INDEX`.

### The five guards, in this order

1. **The class must be "self-healing"** — escalations do not pass
2. **The action must exist** — `re_warm` is not ready and says so
3. **Actions must be allowed** — disabled by default
4. **The damage ceiling** — max 6 actions/hour per block
5. **A check after the action** — the signal must have **DISAPPEARED**

Point 5 is the important one: **an action is not finished when it is issued, but when the
symptom is gone.** If the symptom remains, the journal records it as an **error** —
because that is worse than inaction: it stops someone from looking.

---

## 6. The chaos tests — the proof

| Broken on purpose | Result |
|---|---|
| heartbeat stopped | **HEALED** |
| the block is unwell | sensed, decided |
| never reported | **CORRECTLY NO ACTION IS TAKEN** |
| the database is unreadable | **CORRECTLY NO ACTION IS TAKEN** |

**3 pass, 0 fail.**

`would_heal` is reported **separately** from `HEALED`, on purpose: a chaos test that never
checks recovery would pass forever and prove nothing.

---

## 7. What was NOT touched

Verified with `git diff`, not with a promise:

| Surface | Change |
|---|---|
| `X402_PRICE_MAP` | **no** |
| `payTo` / receiver / commission | **no** |
| `securitySchemes` | **no** |
| 402 envelope | **no** |
| `config.py` (the prices) | **untouched** |
| `secrets/` / `.env` | **no** |

---

## 8. Honest about the limitations

- **The table cannot fix an unknown defect.** It closes the known ones forever, so that
  human attention remains for the new.
- **Self-healing can hide rot.** A monitor that quietly restarts forever looks healthy.
  That is why every action is recorded and the growing number of healings is itself a
  signal.
- **A rule that has never fired is either rare or impossible** — and only counting tells
  them apart. That is exactly why the table observes first.

---

## 9. What remains

**One thing, and it is not code:** the deploy.

Five consecutive deploys failed because the new container does not open a port and the old
one holds the service. Render:

```
==> No open HTTP ports detected on 0.0.0.0, continuing to scan...
==> Port scan timeout reached, no open HTTP ports detected.
```

**The service works** — verified: `/health` responds, the database is ready, the chain
reads, the rail returns 402. Nothing is broken for clients.

A **manual restart** is needed from the Render dashboard: `kristo-intelligence-api` →
**Manual Deploy** → **Restart service**. That kills the stuck process.
