# The Organism — Alive in Production

**Date:** 08.11.2026
**Build:** `2f30a4e` · 1129 tests, all green
**Status:** all six steps are running live

---

## 1. In Brief

The organism from `STRATEGY_ORGANISM.md` is finished, tested and **working in
production**. Verified on the live address, not on my machine:

| Block | Verdict | Evidence |
|---|---|---|
| `chain_read` | **ok** | read the recipient's balance: 0.1640 USDC |
| `data_store` | **ok** | incremental scan passed |
| `discovery` | **ok** | GitHub reachable: 2 stars, 0 open |
| `alerting` | **ok** | `blockchain.ready=True` |
| `delivery` | **ok** | the dashboard is built |
| `payment_rail` | **not_reached** | there is no payment attempt yet — honestly |

The sixth block is `not_reached` and **that is the correct answer**. "We did not
look" is never shown as "nothing was found" — that is the rule the whole organism
is built on.

---

## 2. The Six Steps

1. **Conversion tool** — the funnel now records `authorised` and `abandoned`.
   Live numbers: 7 challenges today, 7 abandoned, 8,906 total.
2. **Six blocks** — each with its own heartbeat, a cheap self-check and a verdict
   from the `ok/degraded/failed/not_reached` vocabulary.
3. **Journal** — append-only, bounded, never throws an exception.
4. **Rules** — a deterministic table, **in self-observation mode** (confirmed:
   `observe_only: True`). It touches nothing.
5. **Executors** — five idempotent verbs behind a damage ceiling. **Disabled**
   (`KRISTO_ORGANISM_ACT` is not set), so the organism observes, decides and
   records — and undertakes nothing.
6. **Chaos tests** — 3 passed, 1 recovered on its own, 2 were correctly **not**
   attacked, 0 failed.

---

## 3. What Broke Today and Why

The day went by in three separate failures, each found with evidence, not a
guess.

### 3.1 Deploys Were Failing for 15 Minutes

**The cause was Render's health check, not our code.** Render received HTTP 200
from `/health` hundreds of times and still refused the deploy. The evidence:
139 requests, all 200, zero errors — and even so "timed out waiting for a
successful response code".

**The fix:** I disabled the health check. The deploy went through in **1.1
minutes** instead of 15.

*Two of my earlier fixes were wrong and made things worse:* raising the timeouts
turned a fast failure into a **hang**, which locked up the service and broke the
external monitors (mcptry, Glama). I reverted them. It is recorded in the
commits, so it does not happen again.

### 3.2 The Dashboard Was Dying with 500

**The cause:** the dashboard was assembling its data through **the same single
database connection** that another 19 threads use. One slow panel made everyone
wait; whoever waited too long gave up. The dashboard could not be assembled →
the cache stayed empty → every request failed again.

**The fix:** the dashboard now has **its own connection**. Assembly dropped from
a hang to **40 milliseconds**.

### 3.3 The Service Was Responding but Recording Nothing

**The most insidious one.** The service answered requests, returned the correct
402, and `/health` said `ok` — **and it recorded not a single request for
hours.**

The cause turned out to be a chain of three things:

1. **The connection was dying over SSL** (`unexpected eof while reading`) — the
   server closes it on idle, and nobody noticed.
2. **Its closing happened while the lock was held** — and on a dead socket
   `close()` hangs. That is why the lock stayed locked forever.
3. **The whale scanner** (`whaleflow-scan`) held the same connection **for 45
   seconds** continuously, while it was walking the chain.

The third thing was found only because I first made the failure **visible**.
Before that, the recording failed inside a bare `except Exception: pass` — with
not a single line in the log. The log finally said the name:

```
shared Postgres link busy for 2s; holder=whaleflow-scan held=45s
```

**The fix:** the whale scanner got its own connection; isolated connections no
longer repeat the database schema (it is only 0.1 CPU and three simultaneous DDL
passes block one another).

**Result:** `today` jumped from the frozen 46 to **235**.

---

## 4. The Rule That Saved the Day

Three separate times today the same rule found the cause:

> **"I could not look" is not the same as "I looked and there is nothing".**

It is at the foundation of the organism (the blocks), in the dashboard (the
panels), and it was **violated** exactly where it hurt the most: the recording of
requests was failing silently. That is why the fix was not "fix the recording"
but **"make the failure visible"** — and only then did the cause become obvious.

---

## 5. What Was NOT Touched

Prices, `payTo`, recipient address, commission, structure of 402 envelopes,
`secrets/`, `config.py`. Every upload was checked against this list.

## 6. Open

- `payment_rail` is `not_reached` until the first payment arrives.
- The executors are disabled by design — they are enabled with
  `KRISTO_ORGANISM_ACT`, after the rules table accumulates real observations.
- Dashboard latency is ~4 seconds on a cold cache; warm it is under a second.
