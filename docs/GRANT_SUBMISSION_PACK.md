# Sentient Foundation — the actual form, screen by screen

**SUBMITTED 2026-11-20 18:06.** Grant track, ask 25k, `docs/GRANT_ONE_PAGER.pdf`
attached. Kept as the record of what was sent, field by field.

**Form:** https://form.typeform.com/to/IRj7WaKH
**Written:** 2026-11-20, after decoding the form's own branching logic.

---

## What the form really asks (this is the important part)

The form has **two branches**, and the branch is chosen by the track question. I decoded the
jump logic from the form definition itself:

- **Grant branch: 7 screens, then straight to the thank-you page.** The form jumps to the
  end right after the supporting-documents upload. It never asks about the team, traction,
  revenue, the round, or a founder video.
- **Investment branch:** the long version — team, founder, traction, round, video, terms.

So the grant application is **short**. Everything a reviewer would want to know about the
team and the numbers has to travel in the **uploaded document**, because the form does not
ask for it on this branch. That is why the supporting document matters more than any single
answer field.

> **Every field on the grant branch is required.** There are no optional ones until the
> thank-you page. The one-line answer is capped at **80 characters**.

---

## Before you start — three things to have ready

1. **Your LinkedIn URL.** It is a required field and it is validated as a URL. Copy it from
   your browser address bar, not from the app's share sheet.
2. **The supporting document as a PDF.** Open `docs/GRANT_ONE_PAGER.html` in a browser →
   Ctrl+P → "Save as PDF" → A4, margins default. That gives you a 2-page PDF. If the upload
   refuses it, print to PDF with "Background graphics" on.
3. **The five numbers**, so you do not have to look them up mid-form: 171 settlements,
   $1.883 gross, 122 of them your own key ($1.685), 12 external payments ($0.054), 8 external
   buyers.

---

## Screen 1 — welcome

Click **Apply Now**. Nothing to fill. The page states the two tracks and that the grant form
is short.

## Screen 2 — *Who are you?* (4 fields, all required)

| field | what to type |
|---|---|
| Your email address | `[YOU]` — the address you actually read. This is where the decision goes. |
| Share your LinkedIn | `[YOU]` — full `https://www.linkedin.com/in/...` URL |
| What best describes your primary role? | **Founder** |
| Where are you currently based? | `[YOU]` — City, Country |

## Screen 3 — *What are you building?* (6 fields, all required)

### 3a. What problem are you solving, and why now?

> We sell paid HTTP endpoints to AI agents. The agents pay on-chain, and both ends of that
> payment report success to the wrong party. Two failures, measured on our own live endpoint.
>
> First: settlement is non-terminal. The x402 spec names `settlement_pending` — the transfer
> was broadcast but confirmation could not be established. It is not a failure, and the
> response carries the hash so the seller can reconcile. We were reading "success: false" as
> "the payment failed", so we refused settlements that had already gone through and the paying
> caller lost the call it had paid for. A facilitator operator in the working group measured
> about 19 settle failures across 11.7k settlements; 9 of those had in fact settled.
>
> Second: the offer that gets published is not the offer that was signed. The catalogue
> transforms what the seller declares, invisibly. It appends `#toolName` to a resource path, so
> declaring `/mcp#get_whale_flow` stores `/mcp#get_whale_flow#get_whale_flow`. An unknown key
> inside `accepts[0]` is accepted and silently voids the row — ours were two bookkeeping keys
> for our own signature pre-check. The facilitator settled, we got a hash, and eight
> settlements produced no listing. Removing the two keys: listed in 45 seconds.
>
> Why now: the spec is being amended right now in the working group's Signed Offers and
> Receipts thread, and the conformance cases do not exist yet. Whoever writes them decides what
> the next thousand sellers get to check.

### 3b. Who does this help?

> Sellers of paid endpoints, and the agents that buy from them. A seller loses a customer every
> time a settlement succeeds and the listing does not appear, or a payment lands and the code
> refuses to deliver. A buyer loses money every time it pays and gets nothing. Neither party
> can see the other's failure, because both are told "success". The conformance cases and the
> preview tool let each side check the leg it cannot see. The sellers are wherever x402 sellers
> are — the catalogue we are listed in carries 1,350 services — and the buyers are agents
> running on Base.

### 3c. In one line, what are you building? **(80 characters max)**

> Paid endpoints for AI agents that prove a payment actually happened.

*(68 characters. Fits with room to spare.)*

### 3d. Who is building this, and why are you the right one?

> `[YOU]`, one person. I wrote the endpoint, I run the seven paid routes, and both failures
> happened to me with real money attached — eight settlements that produced no listing, and a
> refused payment that had already gone through. The qualification is not a team slide; it is
> that I am the seller who lost the money and then measured why.

### 3e. What's open about it, and what would get worse if it closed tomorrow?

> MIT licence, the whole repository: the endpoint, 1,446 tests, and the findings. Nothing in
> the business depends on the code being closed — the money is per call, not per licence.
>
> What would get worse: the conformance cases. Ours are the only seller-side cases I know of
> that treat a broadcast-but-unconfirmed settlement as non-terminal. If the repository closes,
> the next seller reads "success: false", refuses a payment that already landed, and loses the
> customer — exactly as we did. The offer-preview tool goes with it: it diffs the declaration
> against the listing the catalogue will actually publish, and without it each seller has to
> discover the `#toolName` duplication and the voiding-key behaviour by losing listings. And
> the honest split goes with it: a closed project quotes its total volume and never says how
> much of it was its own key.

### 3f. Please provide demo or trial links

> https://kristo-intelligence-api.onrender.com
> https://github.com/hristovdimitri2-hub/kristo-intelligence-6
> OpenAPI: https://kristo-intelligence-api.onrender.com/openapi.json
> x402 discovery: https://kristo-intelligence-api.onrender.com/.well-known/x402

*(Four links, one per line. The field is validated as a website, so the first one is the one
that must be a bare URL.)*

## Screen 4 — *Are you interested in applying for the grant track or the investment track?*

> **Grant**

## Screen 5 — *How much grant funding are you asking for?*

> **25k**

*(The choices are 10k / 25k / 50k / >50k. There is no 3k and no 30k. 25k is the closest to
the scope; 10k is the fallback if you want to ask for less than you need.)*

## Screen 6 — *What would the grant unlock?*

> Five things, in order of when they land.
>
> One: a conformance suite for the seller side of x402, extracted from our own tests and made
> framework-neutral. It would ship as a runnable check against any paid endpoint: does it treat
> `settlement_pending` as non-terminal, does it adopt the hash, does it verify the transfer to
> its own `payTo` before delivering. That is month two, and it is the piece with the highest
> ratio of public good to cost.
>
> Two: the offer-preview tool, generalised. Today it walks our seven routes and diffs our
> declaration against the listing the catalogue publishes. Generalised, it runs against any
> seller's endpoint and reports where the published offer will differ from the signed one.
>
> Three: a `/.well-known/honest-revenue.json` schema. A seller publishes its split — own-key
> volume against external volume — as a machine-readable field, so a buyer can check whether a
> listing's volume is real demand or self-dealing. Ours would be the first implementation.
>
> Four: the reference endpoint kept running, all registries current, uptime published. A
> conformance corpus is only worth something if there is a live implementation it passes
> against.
>
> Five: the findings written up as amendment material for the working group's Signed Offers and
> Receipts thread.
>
> What cannot happen without the grant: the generalisation. The cases exist inside one Flask
> application; making them run against someone else's server is weeks of work with no
> commercial return. That is the part the grant buys.

## Screen 7 — *Please upload any supporting documents, decks, or research materials*

Upload the **2-page PDF** from `docs/GRANT_ONE_PAGER.html`. It carries what the form does not
ask: the team, the honest revenue split, the registry grades, and the milestones.

**After this screen the form jumps to the thank-you page.** There is no team section, no
traction section, no revenue question, no video, and no terms checkbox on the grant branch.
Do not go looking for them.

---

## After you press submit

The thank-you page says the decision arrives by email. There is no confirmation number on the
page — screenshot it if you want a record. Nothing else to do.

---

## The five things that most often go wrong

1. **The one-liner over 80 characters.** The field silently truncates or refuses. The version
   above is 68.
2. **LinkedIn pasted as a handle** (`/in/name`) instead of a full URL. The field validates as
   a website.
3. **Uploading a `.md` file.** The upload wants a document; convert the one-pager to PDF first.
4. **Looking for the team/traction questions.** They are not on the grant branch. If you want
   that information in front of the reviewer, it has to be in the PDF.
5. **Choosing "Investment" by accident.** It switches the whole form to the long version and
   asks for a valuation. Grant is the choice.

---

## `[YOU]` — what only you can supply

- Email address (the one you read).
- LinkedIn URL.
- City and country.
- Your name in 3d, and the sentence about what you shipped before.
- The PDF conversion of the one-pager.
