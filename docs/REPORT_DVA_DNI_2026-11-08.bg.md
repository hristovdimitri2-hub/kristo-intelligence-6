# Two days of work — what happened, what went wrong, where we stand

**Date:** 08.11.2026
**Build:** `2804857` · 1147 tests, all green

---

## 1. Briefly, for a person without technical knowledge

Over the past two days the system went through **four separate outages**. Not one
of them was in what we sell. All of them were in the **infrastructure around it**:
how the service deploys, how it reads its database, and how it writes its notes.

At one point the service **was answering requests and writing nothing** — for
hours. Externally it looked healthy. That was the most dangerous part.

Now:

| Check | Result |
|---|---|
| `/health` | **0.32–0.45 sec** (was 2.3–2.7) |
| The dashboard | **0.30 sec** (was hanging) |
| Requests recorded today | **979** (was frozen at 46) |
| Organism | **5 blocks `ok`, 1 `not_reached`** |
| Deploy | ~1 minute (was 15 and failing) |
| Tests | **1147 green** |

---

## 2. The warnings from Glama and mcptry — in plain words

Both directories said the same thing about our tools, and I did not explain it
well. Here is what they say **literally**:

**mcptry, under every tool:**
> "This tool **is not marked as self-reading**, so it may change something on
> the server or in an account you have connected. [I understand, run it anyway]"

**Glama, on the quality score:**
> "**No annotations submitted**, so the description carries the whole weight"

**What this means in human language.** The MCP protocol has a special field in
which the server declares in machine-readable form: "this only reads", "this
destroys nothing", "this can touch the outside world". We **had not filled in**
that field — we wrote it only in the text description, which a human reads but a
program does not.

That is why automated clients saw a tool with **unknown behaviour** and showed a
warning. And the warning stood **right before a paid call that only reads**.
Every agent deciding whether to pay saw "it may change something" — before it had
spent a cent.

**Fixed:** all 7 tools now declare in machine-readable form "only reads",
"destroys nothing", "is repeatable". Verified live — `7/7`.

**Separately, honestly:** our Glama score was 4/5 on exactly this indicator,
across all seven tools. Now there is a chance for it to become 5/5.

---

## 3. The four outages

### 3.1 Deploys were failing for 15 minutes

**Symptom:** every deploy sat for 15 minutes and failed with "no open ports".

**Real cause:** Render's health check. It received **HTTP 200 from `/health`**
hundreds of times — proven, 139 requests, all successful — and still refused the
deploy with "timed out".

**Fix:** I disabled the check. The deploy completed in **1.1 minutes**.

**My mistake, which should be known:** before I found the truth, I made two
fixes that **made things worse** — I raised the timeouts and turned a fast
failure into a **hang**, which wedged the service and broke the external
monitors. I reverted them and recorded in the commit why they are wrong, so they
are not repeated.

### 3.2 The dashboard was dying

**Symptom:** `/api/dashboard/data` returned an error for hours, while everything
else was healthy.

**Real cause:** the dashboard assembled its data over **the same single database
connection** that another 19 threads use. One slow panel made everyone wait;
whoever waited too long gave up. The dashboard could not assemble → the cache
stayed empty → every request failed again.

**Fix:** the dashboard got **its own connection**. Assembly dropped from a hang
to **40 milliseconds**.

### 3.3 The service was answering but writing nothing — the most insidious

**Symptom:** the service was responding, returning the correct 402s, `/health`
said `ok` — and **recorded not a single request for hours**. Externally there was
no way to tell.

**Real cause, a chain of three things:**
1. The database connection was dying over SSL (the server closes it on idle).
2. Its closing happened, **while the lock is held** — and on a dead socket that
   hangs. So the lock stayed locked forever.
3. Four background tasks held the same connection for minutes: the kit scanner
   (45 sec), the sentinel (289 sec), the dashboard scanner (200 sec).

**Why it was invisible:** the write failed inside a bare `except Exception:
pass` — not one line in the log. The first fix was **to make the failure
visible**. Only then did the log say the names.

**Fixes:**
- Every background task got **its own connection**.
- `close()` now happens **after** the lock is released.
- Added TCP keepalives, so the dead socket is detected immediately.
- The lock became **fair (FIFO)** — a waiting thread can no longer lose the race
  while its timeout expires.

**Result:** `today` went from the frozen **46** to **979**.

### 3.4 (the same family) The isolated connections were re-running the database schema

**Symptom:** after I gave out their own connections, the dashboard stopped again.

**Cause:** every new connection ran **the whole schema (DDL)**. Our database is
**0.1 CPU** — the smallest plan — and three concurrent DDL passes block each
other.

**Fix:** isolated connections do not run the schema. Only the owner creates it.

### 3.5 I overdid the isolation itself — and that also broke the dashboard

**This is my mistake, and it deserves to be recorded.**

After I isolated every background task, each one got **its own database
connection**. But every connection is a **real connection**, and our plan is the
smallest (`0.1c-256mb`) with a **low limit**. Eight tasks × two processes ≈ **16
connections** — close enough to the ceiling that opening one more blocks.

Measured, and the contrast is the whole argument:

| | the dashboard |
|---|---|
| 4 pools | **0.30 seconds** |
| 8 pools | **hangs on the first step**, timings empty, 503 after 20s |

**Why it was hard to detect:** `/health` was 0.32–0.44s the whole time. So the
lock contention **really was solved** — the dashboard was failing for a
**completely different reason**, connection exhaustion.

**Fix:** a small number of **pools**, allocated by what the task actually costs,
not by the fact that we gave it a name:

| pool | who uses it | why |
|---|---|---|
| `dashboard-build` | the dashboard | this is the dashboard's read path |
| `snapshot` | the snapshot | eight full scans, minutes each |
| `background-heavy` | kit scanner, retention | network-bound and heavy |
| `background-light` | sentinel, scanner, reorg, telegram | the cheap scheduled ones |

An unknown task gets **its own** pool — so a new task never shares
**silently** with an already busy one.

**The lesson:** "isolate everything" is not the same as "isolate the right
thing". Every isolation costs a resource, and on a small database the resource
runs out.

---

## 4. The rule that ties everything together

One and the same rule found the cause in all four outages:

> **"I could not look" is not the same as "I looked and there is nothing".**

- The organism is built on it (`not_reached` is never shown as "nothing").
- The dashboard respects it (a panel that cannot be read is shown as
  unavailable).
- And it was **violated** exactly where it hurt most: request recording failed
  **silently**.

That is why the most important fix today was not "fix the recording", but **"make
the failure visible"**.

---

## 5. What I did NOT touch

Prices, `payTo`, recipient address, commission, the structure of 402 envelopes,
`secrets/`, `config.py`. Every deployment was checked against this list.

---

## 6. Where we stand right now

**The organism runs live.** Five blocks report `ok` with real evidence, the sixth
(`payment_rail`) is `not_reached` — because there is no payment yet, and that is
the correct answer.

**The conversion tool records** — `authorised` and `abandoned` are now visible.

**The executors remain disabled** (`KRISTO_ORGANISM_ACT` is not set). The organism
observes, decides and records — and takes no action. That is deliberate.

**The directories:** mcptry `Working · 97/100`, Glama `Healthy · 99.6% for 52
days`.

---

## 7. Open

- **`payment_rail` is `not_reached` until the first payment arrives.** It is the
  meter waiting for something to measure.
- **The organism recovered by itself from `failed` to `ok`** during today's
  deploys — proof that it works. But it also means that **frequent deploys cause
  real transient outages**. Fewer deploys = less noise.
- **The dashboard's cold-cache latency** is ~3 seconds; warm it is 0.3 sec.
- **I know nothing about the mentioned "Hristo with Oracle"** — I have no such
  information in this session and I will not invent a connection.
