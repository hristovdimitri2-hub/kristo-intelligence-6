# Sentient Foundation — submission pack (paste-ready)

**Form:** https://form.typeform.com/to/IRj7WaKH
**Companion:** `docs/GRANT_SENTIENT_APPLICATION.md` (the strategy and the evidence)
**Written:** 2026-11-20. Every answer below is ready to paste into the matching field.

---

## ⚠️ Two things the form forces, which the strategy doc did not know

**1. The grant amounts are fixed choices: `10k` / `25k` / `50k` / `>50k`.**
There is no $30,000 option and no $3,000 option. The honest fit is **25k**: it is the
closest selectable figure to the six-month scope, and it is the number a reviewer can
reconcile with the milestones. Do **not** pick `>50k` — the external revenue is $0.054
and a five-figure-plus ask would not survive the first question about traction.

**2. The "Round" block is investment-track shaped.** It asks "how much are you raising
for this round", "target valuation", "raised to date", "committed investors". On the
grant track those are not applicable; answer them plainly as "grant track — not a
priced round" rather than leaving them blank or inventing a valuation.

---

## Field 1 — *Who are you?*

| sub-field | answer |
|---|---|
| Your email address | `[YOU]` (the address you want the reply at) |
| Share your LinkedIn | `[YOU]` |
| What best describes your primary role? | **Founder** |
| Where are you currently based? | `[YOU]` — city, country |

---

## Field 2 — *What are you building?*

### 2a. What problem are you solving, and why now?

> Agents are starting to pay for things, and the payment is the part nobody can check.
> Two failures are live on the wire right now, and both were measured on our own
> endpoint, not in a lab.
>
> **One: settlement is non-terminal, and the boolean lies.** The x402 v2 spec names
> `settlement_pending` — the transaction was broadcast but confirmation could not be
> established. It is non-terminal, and the response must carry the hash so the seller can
> reconcile. We were reading `success: false` as "this payment failed", so we refused
> settlements that had already gone through and the paying caller lost the call it had
> paid for. A facilitator operator in the x402 TSC measured ~19 settle failures across
> ~11.7k settlements, 9 of which had in fact settled. A seller that trusts the boolean
> keeps the failures and loses the customers who actually paid.
>
> **Two: the offer that gets published is not the offer that was signed.** The catalogue
> transforms the declaration before listing it. Declaring `/mcp#get_whale_flow` stores
> `/mcp#get_whale_flow#get_whale_flow`. An unknown key inside `accepts[0]` is accepted and
> silently voids the row: ours were `extra_name` / `extra_version`, the facilitator
> settled, we got a hash, and eight settlements produced no listing. Removing the two
> keys: listed in 45 seconds.
>
> Both ends have the same shape: everything reports success, and the party that believes
> something happened is not the party that can check it. Why now: the spec is being
> amended right now (Signed Offers and Receipts #2811) and the conformance cases do not
> exist yet. Whoever writes them decides what "correct" means for the next thousand
> sellers.

### 2b. Who does this help?

> Three groups, in this order.
>
> **Sellers of paid endpoints** — the people who lose money when a settlement is refused
> after it already landed, and when a listing silently does not appear. That is not a
> hypothetical: it happened to us eight times before we found the cause.
>
> **Buyers — the agents and the developers running them** — who pay for a call and do not
> get it, or get a listing that promised something the endpoint does not deliver. The
> relying party should be able to recompute rather than trust.
>
> **The standard itself** — the working group amending #2811 needs conformance cases, not
> just prose. A spec clause with no test is a suggestion.
>
> Geographically this is not concentrated: the sellers and buyers are wherever agents run.
> The two failures we hit are protocol-level, so the fix travels without a localisation.

### 2c. In one line, what are you building? (≤ 80 characters)

> We sell small data calls to AI agents and prove each payment actually landed.

*(77 characters. Plain language, no protocol jargon — "x402" and "settlement" do not
survive the 12-year-old test.)*

### 2d. Who is building this, and why is your team the right one to do it?

> `[YOU]` — name. The reason: I built and operate the endpoint these failures were found
> on. I am not writing about x402 from the outside; I am the seller who lost eight
> settlements to a bug the spec does not warn about, and who had to read the facilitator's
> response to find out why. That is the qualification: the failures are first-hand, and
> the fixes are already running on a live mainnet endpoint.

### 2e. What's open about it, and what would get worse if it closed tomorrow, and for whom?

> **Open:** MIT licence. The endpoint, the 1,446-test suite, the conformance examples and
> every measurement write-up are in the public repository. Nothing about the business
> depends on the code being closed — the money is per call, not per licence.
>
> **What would get worse if it closed tomorrow:**
>
> 1. **The `settlement_pending` conformance examples** — the only tests we know of that
>    exercise the non-terminal path. Without them, the next seller reads the spec clause,
>    reads `success: false`, and refuses a payment that already settled. The people who
>    lose are the buyers who paid and did not get served, and the sellers who never learn
>    why their conversion is low.
> 2. **The preview script** that shows the listed offer before anyone pays for it. Closed,
>    it becomes a product; open, it becomes a habit.
> 3. **The honest split** — 171 settlements, $1.883, of which 122 settlements and $1.685
>    are our own key and canaries. A closed seller publishes the total. The split is what
>    makes the total mean anything, and it is the number a buyer needs to judge whether a
>    listing's volume is real.
> 4. **The registry mechanics write-up** — why a PR to the ecosystem page does not get
>    merged, what a "measured health" registry actually measures, and which of the two
>    catalogues indexes you by `payTo`. For the sellers who are stuck at "submitted and
>    never listed", this is the only document that explains the pipeline from the inside.

### 2f. Please provide demo or trial links

> - Live endpoint (mainnet, real 402s): https://kristo-intelligence-api.onrender.com
> - Source, MIT: https://github.com/hristovdimitri2-hub/kristo-intelligence-6
> - The offer preview that diffs our declaration against the published listing:
>   `scripts/validate_preview.py` in that repo
> - The honest revenue split: `docs/HONEST_REVENUE.md`
> - The signal's own track record, free: `/public/signals/history`
> - OpenAPI: `https://kristo-intelligence-api.onrender.com/openapi.json`
> - x402lint's last scan of us (B, three mechanical FAILs since fixed):
>   `docs/x402lint_scan_2026-11-19.json`

---

## Field 3 — Track

> **Grant**

---

## Field 5 — How much grant funding are you asking for?

> **25k**

---

## Field 6 — What would the grant unlock?

> Five things, in order of what cannot happen without it.
>
> **1. A published conformance suite for the seller side of x402** (month 2). Today the
> examples live inside one Flask application's test suite. The grant pays to extract them
> into a framework-neutral corpus with a runner: point it at any endpoint, it checks the
> `settlement_pending` handling, the hash adoption, the error-code matching (never
> `errorMessage`), and the offer/listing drift. That is the piece with the highest ratio
> of public good to cost, and it is the one I would fund first.
>
> **2. The preview tool, generalised and documented** (month 3). Right now it walks our
> seven routes. Anyone should be able to run it against their own endpoint and get a
> report of what the catalogue will publish versus what they signed.
>
> **3. An honest-revenue well-known document** (month 4). A `/.well-known/honest-revenue`
> schema so a seller can publish the split between own-key volume and external volume as a
> machine-readable field, instead of a paragraph nobody checks. This is the one that makes
> "self-dealing" measurable rather than accusatory.
>
> **4. Keeping the reference endpoint alive and current** (continuous). Seven paid routes,
> seven MCP tools, all registry entries current. A conformance corpus needs a reference
> implementation that is actually running.
>
> **5. Written up and handed to the working group** (month 5–6). The two measurements as
> amendment material for #2811, plus the corpus. The thread is already open; the Evidence
> entry is already posted.
>
> **What cannot happen without the grant:** generalisation. The corpus exists in one
> codebase's tests; turning it into something another seller can run is weeks of work that
> produces no revenue. That is exactly the kind of work a grant is for and a business
> cannot justify.

---

## Field 7 — Supporting documents

Upload: a 2-page PDF built from `docs/GRANT_SENTIENT_APPLICATION.md` (sections 3, 5, 8,
10), plus `docs/HONEST_REVENUE.md` as the second page. If the form takes links instead,
point at the repo paths.

`[YOU]` — the PDF conversion is yours to make; the markdown is ready.

---

## Field 8 — How did you hear about this program?

> `[YOU]` — pick from: Conference / X / Github-HuggingFace / Word of Mouth / Sentient Team
> Member / Others. Answer honestly; "Others" plus one line is fine.

---

## Field 10 — *ABOUT THE TEAM*

| sub-field | answer |
|---|---|
| How many people on the team, and how many full-time? | `[YOU]` — one person, and say how much of the time is full-time. Do not inflate it. |
| How long have the founders known each other and worked together? | `[YOU]` — for a one-person project, "solo, no co-founder" is the honest answer. |
| Who writes the code and builds the core? | `[YOU]` — you. |
| What key role are you missing, and what's the plan to fill it? | Suggested: **"A second engineer for the conformance work — the corpus needs someone who can write tests against a spec they did not write. Plan: contract or part-time hire funded by the grant, not a co-founder."** |
| Why is this the team that wins, what do you have that others building this don't? | Suggested: **"The failures are first-hand and already fixed in production. Most people writing about x402 conformance have not lost a settlement to it. I have, eight times, and I have the hashes and the listings to prove what happened."** |

---

## Field 11 — *FOUNDER & KEY TEAM MEMBERS*

| sub-field | answer |
|---|---|
| Founder / Key Member Name | `[YOU]` |
| Role | Founder / Engineer |
| Founder / Key Member Email | `[YOU]` |
| Founder / Key Member's Github | https://github.com/hristovdimitri2-hub |
| What have you built or shipped before? | `[YOU]` — one paragraph: what you shipped, where, and the one thing that is relevant here (running a live paid endpoint on mainnet with real settlements). |

---

## Field 12 — Team slide deck

`[YOU]` — not written. A one-page PDF is enough: who you are, what you shipped, why this
problem. Do not produce a promo.

---

## Field 13 — *TRACTION & PROOF*

### How do you (intend to) make money while staying open?

> Per call. Seven paid HTTP routes at $0.005–$0.050 in USDC on Base, plus seven MCP tools.
> No subscription, no API key, no signup: the payment is the identity. The code is MIT;
> the money is the running service, not the licence. That is the model that makes openness
> and revenue compatible instead of opposed — the moat is uptime and accuracy, not the
> source.
>
> The measured numbers, including the uncomfortable ones: 171 settlements, $1.883 total —
> and that is "since 9 November", because the ledger was rebuilt then. Of the 171, 122
> settlements and $1.685 are our own key paying our own routes, 17 are scheduled canaries and
> 20 are a market sampler. External customers: 12 payments, $0.054, from 9 addresses — one of
> which is the auditor we paid, so 8 real external payers and $0.041 once the auditor's own
> two payments are excluded. Those 8 addresses hold $131 between them. The chain is not
> verifiable if listing volume is self-dealing, so we publish the split rather than the total.

### How many users do you currently have?

> **8** — external paying addresses. (Total settlements are 171, but 122 are our own key
> and 9 are canaries; quoting 171 as "users" would be the exact dishonesty this project
> argues against.)

### How much revenue ($) do you currently have?

> **0.05** — external revenue in USD. The gross figure is $1.883, but $1.685 of it is our
> own key buying from ourselves. If the field rejects decimals, put **0** and say
> "$0.054 external, $1.883 gross including own-key volume" in the field below.

### Share your project's GitHub metrics

> 645 commits, ~98k lines of Python, 1,446 automated tests (1 skipped), 15 documented
> OpenAPI paths, MIT licence. 2 stars, 0 forks, 1 open issue — small, and stated as it is:
> the project is young and the repository is not yet the reason people find it.

---

## Field 14 — *THE ROUND*

Grant track: this block is investment-shaped. Answer plainly, do not invent a valuation.

| sub-field | answer |
|---|---|
| How much are you raising for this round? | **$25,000 — grant track, not a priced round.** |
| Target valuation (in $) | **n/a — grant track.** |
| Raised to date (in $) | **0** |
| Committed investors, if any. | **None. Grant track.** |
| Next 3–6 month milestones | see below |

> **Milestones, 3–6 months:**
> 1. Conformance suite published and runnable against any endpoint (month 2).
> 2. Preview tool generalised with a documented report format (month 3).
> 3. `/.well-known/honest-revenue` schema + reference implementation (month 4).
> 4. Two measurements submitted as amendment material for #2811 (month 5).
> 5. Reference endpoint alive and current across all registries (continuous).

---

## Field 15 — 1-minute founder video

`[YOU]` — not recorded. The brief on the form is explicit: rough and unscripted, you and
what you are building, not a produced promo. One take, one minute, the endpoint on screen.

---

## Field 16 — Is there anything else you want the Sentient Foundation team to know?

> Two things we would rather say ourselves than have found out.
>
> **The signal has no measured edge.** One of the seven endpoints sells a prediction. Its
> own free track record — 84 resolved calls — shows 52% hits, every call one-sided. We say
> so in public, in the repository, next to the endpoint. The other six endpoints sell
> facts that a buyer can check. If the programme's bar is "does this make open AGI more
> trustworthy", the answer is the six, not the seventh.
>
> **The revenue is mostly ours.** 89% of the dollar volume is our own key. The split is
> published next to the total. A reviewer who checks will find the numbers match what we
> say here, and that is the point: the whole application is built on claims a stranger can
> verify without asking us.
>
> What we are asking for is not a bet on the trading signal. It is a bet that the
> conformance work — the part that makes agent payments checkable — is worth funding
> before the market notices it is missing.

---

## Field 17 — Sentient employee or related?

> Skip. You are not an employee of Sentient Labs or the Foundation. If that changes, say so.

---

## Field 18 — Terms

> Check "I agree" and submit.

---

## Before you press submit — the five-minute checklist

1. **Amount: 25k.** Not 30k (not an option), not >50k (not survivable against $0.054).
2. **Track: Grant.** Not investment.
3. **One-liner is 77 characters** — the form caps at 80.
4. **Users: 8, revenue: 0.05.** Both are the external numbers, not the gross ones. If the
   number fields reject decimals, put 0 and explain in field 16.
5. **Field 14 is not a valuation.** "n/a — grant track" is a complete answer.

## `[YOU]` — what is still missing

- Email, LinkedIn, location, how you heard about the programme.
- Team answers (one person, how much full-time, what you shipped before).
- The two uploads: the 2-page PDF and the 1-minute video.
- The `LICENSE` fix: GitHub showed "Other" instead of MIT because an SPDX line sat between
  the title and the copyright. Removed in `cc88adf`'s follow-up commit; GitHub detects the
  licence only after the push, so check the repo badge after pushing.
