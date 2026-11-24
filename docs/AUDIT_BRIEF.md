# External Auditor Brief — Kristo Intelligence

**Who should read it:** an external agent who has not seen the project and has none of
the conversations that created it.

**Report language:** Bulgarian or English, whichever is more convenient for you. The
owner reads both; Bulgarian is preferred for the summary.

**Brief date:** 15.11.2026.

---

## 1. What you are auditing

**Product:** Kristo Intelligence — an x402 API that sells DeFi signals, whale
flow, cross-DEX arbitrage and seller audit, paid per-call in USDC on Base.

**Live production:** `https://kristo-intelligence-api.onrender.com`

**Hosting:** Render, one web service, one worker (this matters — see task 14).

**Paid routes** (8 in total):

```
/api/v1/signal              $0.01
/api/v1/whaleflow           $0.01
/api/arb/opportunities      $0.005
/api/bot-status             $0.005
/api/sales                  $0.005
/api/stats                  $0.005
/api/v1/verify-seller       $0.05   <- the pilot ended on 16.11
/api/v1/seller-check        $0.05   <- the same
```

Aliases: `/api/v1/whale-alerts`, `/api/v1/trading-signals`,
`/api/v1/arbitrage-opportunities`, `/api/v1/seller-check`, `/api/v1/onchain-sales`.

---

## 2. Where everything is

> ### ⚠️ First: make sure you are reading the LIVE copy
>
> **Three audits so far were done on stale copies** — a GitLab mirror that stops at
> §39, and a file `HANDOVER.md.` (with a dot) in the root that stops at §57. All three
> times most of the findings described a repository that no longer exists. Do not
> repeat this.
>
> **10-second check:** `HANDOVER.md` must be **over 4,300 lines** and must reach
> **§66**. If it reaches §39 or §57 — the copy is stale.
>
> If you see `HANDOVER.md.` (with a dot) — that is a manual copy through the web
> editor, it is not a version. The live repo does not contain it.

**The whole map of the documentation is in `docs/INDEX.md`** — read it second, after
`HANDOVER.md`. It lists all 81 markdown files by purpose, the code map, what is **not**
in the repo (and why its absence is the correct state), and the four classes of defects
that have already cost us.

| what | where |
|---|---|
| **Repository** | `https://github.com/hristovdimitri2-hub/kristo-intelligence-6` — **it is public** |
| **Map of everything** | **`docs/INDEX.md`** |
| **The main document** | `HANDOVER.md` in the root. **4,381 lines, §1–§66. Read the whole of it before you touch anything** |
| **The most important section in it** | **§62 "Open tasks"** — the only living list of what is open. Everything in §1–§61 is a record; if it says "open" there, but it is not in §62, then it is closed |
| Code | `main.py` (~9,700 lines), `app/blueprints/`, `services/`, `integrations/` |
| Tests | `tests/` — **1,415 collected**; `python -m pytest tests -q` (~7 min) |
| CI | `.github/workflows/ci.yml` — `Test suite` + `Secret scan (gitleaks)` |

**If you do not have access to GitHub, say so explicitly** — do not judge by a copy you
have. Check it like this:

```bash
curl -s https://raw.githubusercontent.com/hristovdimitri2-hub/kristo-intelligence-6/main/HANDOVER.md | wc -l
# it must be over 4300; if it is ~2700, your copy is stale
curl -s https://raw.githubusercontent.com/hristovdimitri2-hub/kristo-intelligence-6/main/docs/INDEX.md | head -40
```
| Payment path | `services/connectors.py`, `main.py` around `_x402_paywall`, `_try_consume_*` |
| 402 envelope | `main.py`, search for `PAYMENT-REQUIRED` |

**Mandatory before anything else:** read `HANDOVER.md`. It was written precisely for you
— a new session without context. Every section is dated and says whether it is a
**measurement** or an **inference**. Where an early section contradicts a later one, the
later one wins.

---

## 3. The rules (do not break them)

1. **Do not touch production.** No changes to Render, env variables, deploys, the
   database. Reading only.
2. **Do not touch `secrets/`, `.env`, `config.py`.** Do not print values from them.
3. **Nothing external is published** — not a comment, not an email, not a listing —
   without the owner's explicit "yes". This includes GitHub issues and Discord.
4. **Do not touch `payTo`, the prices and the 402 envelope.** They change only with
   explicit approval (see the section "Never touch without the owner's explicit
   approval" in `HANDOVER.md`).
5. **Do not trust the document.** Everything in it was written by an agent that made
   mistakes — see §53 and §55 for two cases where an inference was wrong and then
   corrected. If your measurement contradicts the text, **trust the measurement and
   say so**.
6. **The repo is public.** Do not add personal data, emails, local paths or
   infrastructure identifiers to anything you commit.

---

## 4. The tasks

Ordered by importance. Each one has **what to check** and **what "good" is**.

### A. The payment path — the most important

**1. Check that the 402 is correct on all 8 routes, from the outside.**
Call each route without payment and decode the `PAYMENT-REQUIRED` header
(base64 JSON). Check: `scheme=exact`, `network=eip155:8453`, `asset` = USDC on
Base, `payTo` = **a valid EIP-55 checksum**, `amount` in atomic units, `extra`
carries `name` and `version`, `maxTimeoutSeconds > 0`, and that `resource.url` points
to the requested URL.
*It looks good if:* all 8 respond 402, the address is the same everywhere and
is a valid checksum, and the amount matches the published price.

**2. Check that the body of the 402 and the header say the same thing.**
`accepts`, `accepts[]` and `x402_accepts` in the body must be byte-identical with
`accepts` in the header. A difference between them is what makes a client sign for
different terms.
*It looks good if:* there is no difference. If there is — that is a defect, report it
immediately.

**3. Trace how the server reconstructs `accepted`.**
In `services/connectors.py` there are `_with_accepted()` and `_merged_requirements()`.
They fill the `accepted` field that x402 v2 requires, from **the terms that the server
itself proposed** — not from what the client sent.
Check: can a client nudge the server into settling a payment to **another** address,
for **another** amount, or on **another** network, by sending a forged payload?
*It looks good if:* the server's terms always win and the client's can only
match or be rejected.

**4. Check that settlement is confirmed on-chain, not by `receipt.status`.**
A facilitator that settles a payment in **another token** also returns `status=1`.
See `_receipt_usdc_transfer()` — it must read the `Transfer` log and require
**the exact** amount and **our** address.
*It looks good if:* a payment that has not moved at least `price` USDC to our
`payTo` is rejected — and if an unreadable receipt does **not** let a payment through
(fail-open is deliberate; say whether you find it correct).

**5. Check the depth of confirmations against the real block time.**
Base produces a block every **~0.2 s**, not every 2 s. See §53. Check that
`PAYMENT_CONFIRMATIONS_DEFAULT` (12) and `STANDARD_PAYMENT_CONFIRMATIONS_DEFAULT` (5)
give a reasonable time and that no text of the 402 promises anything different.
*It looks good if:* the number is justified in time, not in blocks, and the text
matches the code.

**6. Check the nonce and the locking on self-broadcast.**
`_SELF_BROADCAST_LOCK` and `get_transaction_count(addr, "pending")`. Ask: can two
parallel settlements from one process get the same nonce?
*It looks good if:* the read and the send are in one critical section.

**7. Check `settlement_pending` against x402 v2 spec §9.**
The specification says: the code is **non-terminal**, the response **must** carry the
hash, and clients must match by **code, not by message text**.
See `_adopt_settlement_pending()` and `SETTLEMENT_PENDING_CODE`.
*It looks good if:* it matches by code, the hash is accepted only if it is valid, and
a client that rephrases `errorMessage` does not break the logic.

**8. Try to burn a payment.**
If you send a signature that is valid, but the request then fails (bad method,
bad body, an expired window) — has money been taken without a product?
*It looks good if:* nothing is settled before validation. This defect has already
existed (see §55, the "JarvisClaw" case) and is fixed — check that the fix genuinely
holds, and look for **another** path to the same outcome.

### B. The integrity of the data

**9. Check that every settled settlement leaves a trace that can be followed.**
`payment_guards` is the ledger: `tx_hash, endpoint, payer, amount_usdc, consumed_at,
delivered_at, retry_claimed_at`. Trace one record from the `tx_hash` on-chain to the
row in the database.
*It looks good if:* every settled tx has a row and `delivered_at` is written only
when the response has actually gone out.

**10. Check the classification of payers.**
`HANDOVER.md` claims that out of 116 settlements only **9 are from 7 external payers**,
and the rest are our own probes (`own_key`, `canary`, `sampler`).
Check the classifier (`classify_payer`). Is there a way for one of our own addresses to
be counted as an external client? Is there an external payer that hides as ours?
*It looks good if:* the classification is conservative — when in doubt it counts as
ours, not as a client. **The number on the search must be a lower bound, not an
upper bound.**

**11. Check the delivery claim (96.3%).**
`HANDOVER.md` §55 claims: 96.3% of settlements reach a real payer
(26/27 without our probes). Can you reproduce it independently?
*It looks good if:* the claim is verifiable from public data (the chain) or
explicitly says that it comes from our database, which an outsider cannot see.

### C. The public surface

**12. Check that the public surface leaks nothing private.**
Fetch `/api/dashboard/data`, `/.well-known/paycheck.json`, `/health` and every
public page. Look for: RPC keys in URLs, a DSN with a password, internal paths,
stack traces, names of env variables with values.
*It looks good if:* none of this is shown. If it is shown — report it
as **critical**, with the exact URL and the field.

**13. Check that `/health` tells the truth.**
The public health line for the gas wallet says `key-set, funds unprobed` — that is, it
admits that it has not checked the balance. Is there another line that claims more
than it knows? (The project has a whole class of defects exactly from this: "something
has not been looked at and is shown as looked at and empty".)
*It looks good if:* every statement is either measured, or explicitly marked
as unmeasured.

**14. Check the one-worker assumption.**
The rate limiter, the free-tier counters and the replay set live **in RAM**. If Render
starts a second worker, they split in two and the limits double.
Check the configuration and the code: is there a protection, or only an assumption?
*It looks good if:* there is an explicit check or a clear warning, not a silent
assumption.

### D. The claims the project makes about itself

**15. Check every number in `HANDOVER.md` against its source.**
The document makes many claims (prices, number of payers, ratio, market numbers).
The audit of 15.11 found eight errors that are already fixed (§54). Look for
**the remaining ones**.
*It looks good if:* every number is either verifiable, or explicitly marked as
unverifiable.

**16. Check whether we are where we claim to be.**
The document claims a presence in x402scan, CDP Bazaar, PayAPI Market, Bazaar and
others. Check each of them from the outside: does the entry exist, is it correct, how
many routes.
*It looks good if:* the claim matches the external entry. If not — say which
claim is stale.

### E. The code

**17. Review `main.py` for dead code and duplicated logic.**
The file is ~9,660 lines. Look for: functions that nobody calls; two implementations of
one and the same thing; import-time side effects; global state without locking.
*It looks good if:* you report concrete lines, not general impressions.

**18. Look for a place where an exception can become a public response.**
The project has already had such a defect (§38): the log went through `redact_rpc()`,
while the same exception was written **unredacted** into a state that comes out
publicly. Ten places were fixed. Look for **the eleventh**.
*It looks good if:* every exception that can reach a public
payload goes through redaction.

**19. Review the authentication.**
`ADMIN_API_TOKEN`, operator grants, Stripe webhook signature. Check: is there an
administrative route without a check; is the token compared in constant time;
can the webhook be forged.
*It looks good if:* every administrative route checks, and nothing
compares secrets with `==`.

### F. The operational side

**20. Check whether the service is stable under load.**
Respect production: do not hit it hard. A few sequential requests, not a parallel
attack. Watch for 5xx, for slow responses, for memory leaks.
*It looks good if:* there are no 5xx and the latency is stable.

**21. Check the CI.**
`.github/workflows/ci.yml` runs the tests and gitleaks. Run them locally if you
can. Check that the green status means something — that is, that the tests really
cover the payment path, not only the forms.
*It looks good if:* you can say which tests would fail on a real defect
in the payment path, and which would not.

### G. The gap hunt — look for MORE of the same kind

Four classes of defects repeat in this project and have cost us the most. Each one
is documented. **The task here is not to find them for the first time, but to find
their next manifestations** — because every time we fix one, others remain.

**22. The class "cannot be looked at, yet looks like zero".**
Something that has not been measured is shown as measured and empty: an empty panel
that looks like zero; a counter that looks like a fact. Example: `delivered_at
IS NULL` looked like "the buyer received nothing", while it meant "there was no
stamp yet" (§55). Look for every place where the absence of data is drawn as zero.
*It looks good if:* you can point out which statement on the dashboard is "unchecked",
and not "empty".

**23. The class "an exception reaches a public surface without redaction".**
Nine places in `services/connectors.py` were fixed on 16.11 (§66). Every
exception that can reach a public payload must go through
`redact_rpc()`. Look for the places that do **not** go through it — not only in
`connectors.py`, but in `main.py`, `integrations/`, `app/blueprints/`.
*It looks good if:* `grep -rn "{e}" --include=*.py` returns not a single line without
`redact_rpc` in the same expression.

**24. The class "a document is treated as a fact after it has gone stale".**
`docs/INDEX.md` lists 81 markdown files. Many of them describe a state that
has changed: prices, addresses, number of tests, host names, a "pending" action
that has happened. **Find claims in documents that are no longer true.**
An example from 16.11: `DEPLOYMENT_CHECKLIST.md` pointed to a host that returns 404.
*It looks good if:* you give a list "document:line → what it claims → what is
true now", with the command by which you established it.

**25. The class "a wait that refuses instead of waiting".**
The gate refused a payment for a wait that was almost over (§66).
Look for other places where the system refuses because something is not ready yet,
instead of waiting a little — in the gates, in the rate limit, in the check of
confirmations.
*It looks good if:* for each place found you can say how long the wait
that would have been enough is, and what the refusal costs.

**26. Check whether you are really reading the live copy.**
Before everything else: `HANDOVER.md` must be over 4,300 lines and must reach
§66. If it is not — say it in the **first sentence** of the report and stop, instead
of judging by a stale copy. Three audits have already failed on exactly this.
*It looks good if:* the report starts with the line count and the last section of
`HANDOVER.md` that you have read.

---

## 5. What we want back

A report that:

1. **Starts with a verdict** — "not everything is fine" or "it is fine" — and then
   justifies it. Do not bury the conclusion at the end.
2. **Separates the measured from the inferred.** Every claim says how it was checked.
3. **Also says what is fine.** A list of problems only does not allow one to judge
   whether the check was honest.
4. **Gives exact locations** — file and line, URL and field. Not "somewhere in the
   code".
5. **Says what you have NOT checked.** The limitations are part of the report.
6. **Fixes what it can fix itself**, in a separate branch, and leaves
   the decision to the owner for everything that touches production or money.

**Format of every finding:**

```
WHAT:           <one sentence>
WHERE:          <file:line or URL>
HOW I KNOW:     <the command or the observation>
WHY IT MATTERS: <what it breaks>
CONFIDENCE:     <measured | inferred | assumption>
```

---

## 6. One warning

The project has one recurring defect that has cost the most: **something cannot
be looked at and the surface shows it as looked at and empty.**
An empty panel that looks like zero. A counter that looks like a measurement.
`delivered_at IS NULL`, which looks like "the buyer received nothing", while in fact
it meant "there was no stamp yet" (§55).

If you find such a place, it is more important than any crash. A crash is visible.
This is counted as a fact.
