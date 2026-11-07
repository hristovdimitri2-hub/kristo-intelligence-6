# The Organism — how the platform watches itself

**Built:** 2026-11-07 · **Status:** all six steps implemented; actions OFF by default

---

## The problem this solves

Every defect this project has had was found by a human-run audit, diagnosed in a
human-run session, and fixed by a human-run commit. The system *watched* — the
sentinel sent Telegram on health, revenue and GitHub changes — but it carried no
model of its own health, so **each session re-discovered what the last one already
knew.** The owner's words: *"решаваме един проблем, излиза друг."*

The cost is not the fixing. It is the re-discovery.

---

## The six steps, and where each one lives

| # | Step | Module | State |
|---|---|---|---|
| 1 | Conversion funnel | `integrations/dashboard_store.py` | live |
| 2 | Block heartbeats + verdicts | `services/organism.py` | live |
| 3 | The journal | `services/organism_journal.py` | live |
| 4 | The rule table (observe-only) | `services/organism_rules.py` | live |
| 5 | Executors | `services/organism_executors.py` | **OFF by default** |
| 6 | Chaos drills | `services/organism_chaos.py` | live |

---

## The chain, end to end

```
a loop runs  ->  beat(block, ok|degraded|failed|not_reached)   [step 2]
                        |
                        v
              last_verdicts(store)  ->  the board             [step 2]
                        |
                        v
         signals_from_verdicts(store)                          [step 2→4]
                        |
                        v
              decide(signal)  ->  class + action + why         [step 4]
                        |
                        v
              execute(decision)  ->  Result(ok, verified)      [step 5]
                        |
                        v
              journal_result(...)                              [step 3]
                        |
                        v
              chaos drills prove the whole path                [step 6]
```

---

## Six blocks, one vocabulary

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

**`not_reached` is counted as unhealthy, and is NEVER converted into an action.**
"We did not look" is not "something is broken", and restarting a loop on it would
restart six healthy loops on every single deploy. A drill asserts this.

---

## The rule table

Twelve rules, three classes, and six verbs. Read the whole policy in one screen —
that is the point of a table over a model.

| Signal | Class | Action |
|---|---|---|
| `rpc_endpoint_refused` | self_heal | `rotate_endpoint` |
| `heartbeat_stale` | self_heal | `restart_loop` |
| `cache_violently_stale` | self_heal | `rebuild_cache` |
| `index_missing_or_invalid` | self_heal | `recreate_index` |
| `retention_backlog_over_horizon` | self_heal | `purge_older_than` |
| `surface_returns_5xx` | self_heal | `re_warm` |
| `deploy_failed` | escalate | — |
| `env_missing_or_drifted` | escalate | — |
| `payment_settles_but_not_recorded` | escalate | — |
| `conversion_below_floor` | escalate | — |
| `public_claim_contradicted` | escalate | — |
| `anything_unrecognised` | observe | — |

**A rule cannot name a forbidden effect.** `move_money`, `change_price`,
`edit_receiver`, `touch_secrets` and `push_to_main` are not merely absent from the
table — a `Rule` constructed with one raises. That is enforced by a test.

---

## The executors, and the guard order

`KRISTO_ORGANISM_ACT` is **unset by default**, so the organism ships observing.
The guards run in order, cheapest and safest first:

1. the class must be `self_heal` — escalate/observe never act, in any mode
2. the verb must be implemented — `re_warm` is not, and says so
3. actions must be ENABLED — off unless a human turns it on
4. the blast radius must allow it — at most 6 actions/hour/block
5. then the executor runs
6. and the result is **verified**: the signal must be GONE

A repair whose symptom survives is journalled as an **error**, because it is worse
than not acting — it stops anyone looking.

---

## The chaos drills

Four drills, each breaking one thing and requiring the organism to notice,
classify and (where a repair exists) heal it *and have the signal disappear*.

```
stale_heartbeat   -> HEALED
degraded_block    -> sensed, decided (would_heal in observe-only)
never_reported    -> CORRECTLY NOT ACTED ON (not_reached is not a fault)
unreadable_store  -> CORRECTLY NOT ACTED ON
```

`would_heal` is reported separately from `HEALED`, deliberately: a chaos suite
that never verifies recovery would pass forever and prove nothing.

---

## Where to see it

`GET /api/dashboard/data` → `sections.organism`, `.journal`, `.rules`, `.chaos`.

The organism sections are behind `KRISTO_ORGANISM_BOARD`, **off by default** while
the service is stabilised. The heartbeats and the journal run either way.

---

## Honest limits

- **A rule table cannot fix a novel defect.** It closes the *known* failure modes
  permanently so human attention is spent only on the new.
- **Self-healing can mask rot.** A monitor that silently restarts forever looks
  identical to a healthy one. That is why every action is journalled and the
  digest counts a rising heal rate as a signal in itself.
- **A rule that has never fired is either rare or impossible**, and only counting
  tells them apart — which is exactly why the table observes before it acts.
