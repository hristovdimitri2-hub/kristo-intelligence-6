# CHET DATA PACKAGE — extracted 04.09 (second check), read-only

Source: `GET /agent/get?id=kristo-intelligence-defi-signals-api` +
`/agent/search?q=<term>` ×8. Diff against `docs/monitor_state.json`
(baseline, recorded at the first run of the monitor the same day).

## A) STATUS table

| Field | Baseline (04.09 morning) | Now (04.09, second check) | Change |
|---|---|---|---|
| **Reliability band** | unscored (score=null, computed_at=null) | **unscored** (score=null, computed_at=null) | — |
| **Title** | Kristo Intelligence — DeFi Signals API | Kristo Intelligence — DeFi Signals API | same |
| q=defi | #1 (of 3) | #1 (of 3) | = |
| q=whale | #1 (of 1) | #1 (of 1) | = |
| q=signals | #3 (of 7) | #3 (of 7) | = |
| q=rug | #2 (of 2) | #2 (of 2) | = |
| q=eth | ABSENT (2) | ABSENT (2) | = |
| q=ondo | ABSENT (1) | ABSENT (1) | = |
| q=kaito | ABSENT (0) | ABSENT (0) | = |
| q=degen | ABSENT (0) | ABSENT (0) | = |

Format check: the responses are in the expected format (reliability object + lists
with results); no need for a raw dump.

## B) VERDICT

**NOTHING TO SEND — band still unscored, title not changed.**

The thread's grammar holds: without a receipt, data, or a number — nothing is sent.
The next valid move: repeat `python scripts/listing_monitor.py` after
a signal from Chet (or at the earliest next week — he said that the compute
is manual, "when a new verified listing needs a band").

## C) FINAL EMAIL — ready for copy-paste (04.09, evening)

Status: the article is public (the repo is already public — verified, the link returns
HTTP 200 without authentication). Band still unscored, the title unchanged — but
the two lines are sufficient on their own: we deliver the ordered document.

**EMAIL FOR COPY-PASTE (the entire email content):**

```
Subject: the write-up, as promised

Hi Chet — the write-up, as promised:
https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/MARKET_WRITEUP.md

— Dimitri
```

*(When sending: if in the meantime the band has landed — see the STATUS
table above or run `python scripts/listing_monitor.py` — add one line
"reliability band: [score/band, computed_at]". As of the moment of writing:
band=unscored, the title is the same, the ranks identical to baseline.)*

## D) Special check (defi): not executable at the moment
The title is NOT changed → "defi" still comes from the name (#1) and the description
("DeFi signals" + substring matcher: proven to index the description — whale #1
without "whale" in the name; CMS "de**fi**ciencies" is #2 for q=defi). The condition for
the D-line (new title live + defi ABSENT) has not occurred. The fallback line is
recorded in RECON_FINDINGS.md and activates automatically from the next monitoring.
