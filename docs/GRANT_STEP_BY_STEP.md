# The Sentient Foundation Grant — step-by-step walkthrough

> **Submitted on 20.11.2026 at 18:06.** Grant track, ask 25k, attached
> `docs/GRANT_ONE_PAGER.pdf`. This walkthrough stays as a record of how the
> submission went — it is useful if we ever apply again, or if they come back
> with questions.

This is the walkthrough you keep open while you fill it in. Everything else —
`GRANT_SUBMISSION_PACK.md` (the exact text to copy), `GRANT_ONE_PAGER.html` (the
document to attach) and `GRANT_SENTIENT_APPLICATION.md` (why we are applying
exactly this way) — is detail hanging off it.

---

## First: what the form actually is (read this before you open the link)

The form has **two branches**, and the branch is chosen by the question about the
path. I checked the logic in the form itself:

- **If you pick "Grant" — the form is 7 screens and it ends.** After you attach
  the document it jumps straight to "thank you". It **does not ask** about team,
  traction, revenue, the round, video or terms.
- **If you pick "Investment" — the form is the long version** with team, founder,
  traction, round, video and terms.

That is: what the reviewer wants to know about the team and the numbers **has to
be in the attached document**, because the form does not ask for it. That is why
the PDF is more important than any individual answer.

**All fields in the "Grant" branch are required.** There is no option. The one-line
answer is limited to **80 characters**.

---

## Before you open the form — prepare three things

**1. The LinkedIn link.** A required field, validated as an address. Copy it from
the browser address bar, not from the app's "share" button. It must start with
`https://www.linkedin.com/in/...`.

**2. The PDF to attach.** Make it like this:
- Open the file `docs/GRANT_ONE_PAGER.html` in a browser (double-click the file).
- `Ctrl+P` → "Save as PDF" / "Save as PDF".
- Paper **A4**, default margins, **turn on "Background graphics"** (otherwise the
  grey bars disappear).
- You should get **2 pages**. If you get 3 — reduce the scale to 90% and try again.

**3. The five numbers**, so you do not have to hunt for them halfway through: 171
settlements, $1.883 gross, 122 of them are your own key ($1.685), 12 external
payments ($0.054), 8 external buyers.

---

## The link

**https://form.typeform.com/to/IRj7WaKH**

It opens in a browser. It does not ask for registration and does not ask you to
sign in — you just fill it in and press "Submit" at the end.

---

## Screen 1 — "Open Source AGI Grants & Investment Program"

This is the opening screen. It shows the two paths and that the grant is short.
Press **Apply Now**.

---

## Screen 2 — *Who are you?* (4 fields, all required)

| field | what you write |
|---|---|
| Your email address | your email — the one you read. The decision goes there. |
| Share your LinkedIn | the full address, copied from the browser |
| What best describes your primary role? | **Founder** |
| Where are you currently based? | City, Country |

---

## Screen 3 — *What are you building?* (6 fields, all required)

This is the longest screen. Six fields, each one asking for a different answer.
The exact text is in `GRANT_SUBMISSION_PACK.md`, section "Screen 3" — copy it field
by field. Here is what matters for each one:

**3a. What problem are you solving, and why now?** — The two failures:
`settlement_pending` (the settlement has been sent but is not confirmed, and
"success: false" lies) and the announcement that gets published is not the
announcement that was signed. It ends with "why now": the spec is changing right
now and the conformance cases do not exist yet.

**3b. Who does this help?** — The sellers of paid endpoints and the agents that
buy from them. Both sides lose when one sees "success" and the other does not.

**3c. In one line, what are you building?** — **Exactly this line, 68 characters:**

> Paid endpoints for AI agents that prove a payment actually happened.

Do not make it longer. The limit is 80 and the field may truncate or reject it.

**3d. Who is building this, and why are you the right one?** — Your name + one
sentence: you are the seller who lost the money and then measured why. That is
the qualification, not the team slide.

**3e. What's open about it, and what would get worse if it closed tomorrow?** —
MIT license, the whole repo. If it closed: the conformance cases, the preview
tool and the honest breakdown of the numbers. Also say for whom exactly — for
the next seller who will read "success: false" and decline a payment that has
already gone through.

**3f. Please provide demo or trial links** — Four addresses, one per line. The
first must be a bare address (the field is validated as a website):
```
https://kristo-intelligence-api.onrender.com
https://github.com/hristovdimitri2-hub/kristo-intelligence-6
https://kristo-intelligence-api.onrender.com/openapi.json
https://kristo-intelligence-api.onrender.com/.well-known/x402
```

---

## Screen 4 — *Are you interested in applying for the grant track or the investment track?*

Click **Grant**.

**Warning:** if you pick "Investment" by mistake, the form turns into the long
version and will ask you about the company valuation. If that happens — go back
and switch to Grant.

---

## Screen 5 — *How much grant funding are you asking for?*

Click **25k**.

The options are `10k` / `25k` / `50k` / `>50k`. There is no 3 000 and no 30 000.
25k is the closest to the scope; 10k is the fallback option if you decide to ask
for less.

---

## Screen 6 — *What would the grant unlock?*

Five things, in the order in which they come up: the conformance suite (month 2),
the preview tool (month 3), the `honest-revenue.json` schema (month 4), the live
endpoint (ongoing), the working-group record (month 6). End with what **cannot**
be done without the grant: the generalization. The cases now live in one Flask
app; making them run against someone else's server is weeks of work with no
commercial return.

---

## Screen 7 — *Please upload any supporting documents, decks, or research materials*

Attach the PDF from `GRANT_ONE_PAGER.html`. It carries what the form does not
ask: the team, the honest splitting of the revenue, the valuations from the
registries and the milestones.

**After this screen the form jumps to "thank you".** There is no team section, no
traction, no question about revenue, no video and no checkbox for terms. Do not
look for them.

---

## After you press Submit

The page says the decision comes by email. There is no application number — if
you want a record, take a screenshot of the "thank you" screen. Nothing else is
asked.

---

## The five things that most often get mixed up

1. **A one-line answer over 80 characters.** The field truncates or rejects. The
   version above is 68.
2. **LinkedIn as a handle** (`/in/name`) instead of a full address. The field
   validates for a website.
3. **Uploading a `.md` file.** A document is uploaded; make a PDF first.
4. **Looking for the team and traction questions.** They are not in the "Grant"
   branch. If you want that information in front of the reviewer, it has to be
   in the PDF.
5. **Picking "Investment" by mistake.** It flips the whole form into the long
   version and asks for a valuation. The right one is Grant.

---

## What remains yours alone

- The email address you read.
- The LinkedIn address.
- The city and the country.
- Your name in 3d and the sentence about what you did before.
- Turning the one-pager into a PDF.

---

## If something goes wrong halfway through

- **The form does not accept the LinkedIn address** → check that it starts with
  `https://` and has no space at the end.
- **The PDF is 3 pages** → reduce the scale to 90% when printing.
- **The upload rejects the PDF** → check the size; if it is over the limit, shrink
  it to 2 pages with a smaller font or upload only the first one.
- **If you close the form halfway through** → Typeform remembers the answers in
  the browser, but not always. Better to prepare the text in advance (it is in
  `GRANT_SUBMISSION_PACK.md`) and fill it in in one go — seven screens are 10–15
  minutes.
