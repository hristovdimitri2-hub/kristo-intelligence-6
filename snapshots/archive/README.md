# Census snapshot archive

`snapshots/demand_census.json` is the file the paid route serves — always the
latest build. The dated copies here are the archive.

## Why the archive exists

The product worth selling is not one snapshot, it is the **change between
snapshots**: which agents are new, which came back, which stopped, what they paid.
That difference cannot be reconstructed after the fact, because the source table
`request_log` retains only 30 days. A month that is not snapshotted is a month that
is gone.

So the archive has to start before the product can exist. The first sellable
issue is therefore **December 2026 against November 2026**, not earlier.

## How to take a snapshot

```sh
python scripts/build_demand_census.py \
    --out snapshots/archive/demand_census_YYYY-MM-DD.json
python scripts/build_demand_census.py          # refresh the served copy too
```

Run it from a Render one-off job or anywhere with `DATABASE_URL` set; it reads the
production ledger read-only. `--dry-run` builds without writing.

## Rule

- Never edit a dated file after it is written. It is a measurement, not a draft.
- The date in the filename is the date the ledger was read, taken from the
  document's own `generated_at`, not from the machine's clock at rename time.
- One file per month is enough. More is harmless.
