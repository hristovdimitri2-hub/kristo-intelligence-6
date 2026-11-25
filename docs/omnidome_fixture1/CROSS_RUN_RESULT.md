# Cross-run, reproduced: the draft-3 vector set against fixture 1

**Run date:** 25 November 2026, 08:29 UTC.
**Vector set it ran against:** `94b07672bfd9be9335d52ac3bedd4f59bc663b30b2978d32f4bfcb1d83c1bbfe`
— 61 084 bytes, `vectors/settlement-pending/vectors.json` in
[`holistis/agent-receipt-verify`](https://github.com/holistis/agent-receipt-verify),
draft 3, 41 vectors of which 36 are asserted.
**Artifact that answered:** our
[gist revision `c1cd82cc059b`](https://gist.github.com/hristovdimitri2-hub/0d2f4436cc73a14d837c39f88168a5bf)
— 37 862 bytes, SHA-256
`3d76d8030efc10cbbfcfe3a739078ee5fa4a8af417712a583b934789f37d170a`, 11 tests.
**Adapter:** their `vectors/settlement-pending/cross-run/kruisrun.py`, unmodified,
SHA-256 `97d537f5124a75cbcca5a713fc3bc21f256bc047e1510762599bb6691236c86a`.

## The result

```
same answer as the reference:                          22
a different answer that the vector allows:             14
outside what the vector allows:                         0
of those, without an explanation in this adapter:       0
open vectors (nothing is asserted, shown anyway):       5
```

**This is the same tally their repository records** for the revision of
24 November: 22, 14, 0. The five open vectors come out the same way too — the
file denies a pending response without a hash, a malformed hash and a reverted
transaction at any depth; it holds a transfer whose nonce cannot be read; and it
delivers one vector whose payer cannot be read, which this file cannot express.

Nothing in the set is delivered that the vectors do not allow. The 14 differences
are all a hold where the reference refuses, or a refusal where the reference
leaves the case open — neither of which delivers.

## Why this run is worth recording at all

Not because it produced a new number, but because it is a **reproduction of a
third party's run from the third party's own frozen inputs**, and it says what a
reproduction should say:

- the set's fingerprint is what was asked for: `94b07672bfd9…`, draft 3, byte for
  byte;
- the adapter was run as published, with no edit and no shim;
- the file it answered with is the same 37 862 bytes, and the adapter was held to
  that hash (`--sha256`), so it could not have answered with anything else;
- our output is byte-identical to the output their repository recorded
  (`cross-run/uitvoer.txt`, SHA-256
  `83afce2f8f407a0db69a26f3d2cb7429d3a8c325a2e1a5b1301c44372d079dd2`) — with one
  exception, the second line, which echoes the filename it was handed on the
  command line. Every other byte, including all 19 divergent vectors and their
  reasons, matches.

The command, so that it can be repeated by anyone:

```
python -I kruisrun.py vectors.json test_settlement_pending_chain_before_delivery.py \
    --sha256 3d76d8030efc10cbbfcfe3a739078ee5fa4a8af417712a583b934789f37d170a
```

Python 3.12.10. No network call is made by the run itself; the two downloads are
the vector set and the gist file.

## What this does not show

- **It is not independent.** The vector set and the adapter are theirs; the file
  is ours; the run was ours on our own machine. It confirms a published run, it
  does not create a second opinion.
- **It is not a verification of our production code.** The file is a redacted
  extraction of a decision table with the transport removed. It says nothing
  about the facilitator, the RPC, on-chain settlement, or the idempotency of a
  write. Those are named as limits inside the file itself.
- **It is one dated revision.** The three earlier revisions of the file
  (`d76537a7…`, then the payer-binding and atomic-unit revision, then
  `558351e6…`) were answered by earlier runs of the same set and are recorded in
  the `REVISIONS` block inside the file, not re-run here.
- **The numbers rest on their script.** The adapter decides what "the reference
  answer" means. We ran it; we did not audit its reading of the 41 vectors
  beyond the fact that its output on the frozen pair is reproducible.
- **The 14 allowed differences are not a defect, but they are not nothing.** They
  are the places where the specification does not decide between refusing and
  holding, and where a hold is what a seller that cannot prove a payment should
  do. They are the natural candidates for a conformance case.

## This document did not touch the artifact

It was added to the gist as a second file. The bytes of
`test_settlement_pending_chain_before_delivery.py` are unchanged by it: the hash
above is still the hash of the file the gist serves, at the pinned revision
`c1cd82cc059b` and at every revision after this one.

## Credit

The `settlement_pending` cases, the two rails, the payer binding and the durable
one-hash-one-delivery claim came from `mitaka7210` (x402 community Slack),
published as a runnable gist owned by `hristovdimitri2-hub`
([the gist](https://gist.github.com/hristovdimitri2-hub/0d2f4436cc73a14d837c39f88168a5bf)).
The vector set, the adapter, the reference answers and the recorded output are
`github.com/holistis`.
