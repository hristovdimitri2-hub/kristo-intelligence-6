# 1-minute founder video — script

> **Not asked on the Grant branch.** The form's Grant branch ends after the
> supporting-documents upload and never asks for a video — that field belongs to the
> investment branch. Keep this script for the case where you switch tracks or want the
> video for distribution; it is not needed to submit the grant application.

**What the form asks for:** "Share your 1-minute founder video." No production values
required — the brief is "rough and unscripted is fine, we want you, not a promo".

**What it must prove:** that you exist, that the thing is real, and that you will say the
uncomfortable number out loud. A reviewer who has read the application should recognise
the same person.

**Setup:** screen recording of a terminal, your face in a small corner camera. One take.
No music. No cuts except the two marked.

---

## 0:00–0:08 — who you are, what it is

> "I'm `[NAME]`. I built and run a paid API for AI agents — seven endpoints on Base that
> agents call and pay for in USDC, no keys, no signup."

*Show the repo page or the endpoint's landing page.*

## 0:08–0:28 — the thing that is actually real

> "Here's a paid call. I call the route without payment — it answers 402 with the price and
> the address. I pay, and the same call returns the data."

*Terminal: `curl` the route, show the 402 JSON; then the paid call returning data. If you
have a client script, run it. Keep it to one endpoint.*

## 0:28–0:45 — the finding, in one breath

> "The reason I'm applying is what happened next. Twice, the payment settled on-chain and
> our code read the response as a failure — so we refused a call the buyer had already paid
> for. The spec calls that state `settlement_pending`, and it is not terminal. That's the
> kind of thing the grant would let me write down properly, as a conformance test other
> sellers can run, instead of each of us losing a customer to it."

## 0:45–0:58 — the honest number, spoken

> "The project has 171 settlements and 1.88 dollars. Most of that is my own key — external
> customers are 12 payments, five cents. I'm telling you that because the whole point of
> this work is that a number should be checkable. The grant is for the checking, not for
> the revenue."

## 0:58–1:00 — close

> "The repo is MIT. Everything I just said is in it."

---

## Production notes

- **Say the five cents.** It is the single most credible thing in the video. A founder who
  quotes a small real number is more believable than one who rounds up.
- **Do not read the script.** Learn the four beats, then say them in your own words.
- **Do not show the private key.** If your client script prints it, cut that frame or use a
  burner.
- **Captions.** If you can, burn in subtitles — reviewers watch muted.
- **Length.** 55–60 seconds. The form says one minute; 1:20 is a fail, 0:45 is fine.
- **Where it goes.** Upload unlisted to YouTube or as an MP4 to the form's upload field.
  Check the field's size limit before recording at 4K — 1080p is plenty.

## If you would rather not be on camera

The form asks for a founder video, so a voice-over over the screen recording is the
minimum. What it cannot be is a produced promo with no person in it — the brief is
explicit that they want the founder, not the polish.
