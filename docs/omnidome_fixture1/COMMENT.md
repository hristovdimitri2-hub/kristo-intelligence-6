Fixture 1 is ready — `settlement_pending` acceptance + chain-before-delivery, as one runnable file.

**Gist:** https://gist.github.com/hristovdimitri2-hub/0d2f4436cc73a14d837c39f88168a5bf

Single file, standard library only. No network, no wallet, no keys. It exits 0 when every assertion holds and prints one line per assertion.

```
python3 test_settlement_pending_chain_before_delivery.py
# 7 passed, 0 failed
pytest -q test_settlement_pending_chain_before_delivery.py   # the same seven
```

**What it is, precisely.** A redacted extraction of the decision table our production code implements — not the production code. The transport (Flask, the facilitator HTTP call, the RPC client) is removed; the decisions are kept. Extracted from:

- commit `aa2600429bfbf215cc377350f98736e3ddc179db`
- `services/connectors.py` blob `ba69d51a84a05f5cd557e15c35904dbaf604daca` — `_adopt_settlement_pending` at line 1119, `_adopt_already_settled` at 1147
- `main.py` blob `fda47ea312c2bd6fc9ee917dd85eb9028a66d6ca` — `_receipt_usdc_transfer` at 4199, `_verify_payment_onchain` at 4243, `_admit_undelivered_payment` at 4162

Artifact SHA-256: `d76537a70102c6399deb9b8be9e8ceae3a90728e2e7d6004cef5840edc4b524e`

**The five assertions, and what each test does**

1. `test_pending_is_not_failure_not_completion_not_delivered` — a `settlement_pending` response with a hash is adopted, verdict `pending`, `delivered=False`. It is never `deny` and never `allow`.
2. `test_retry_with_the_original_operation_id_checks_the_chain` — the same hash against seven chain states: no receipt → hold; reverted → deny; too shallow → hold; wrong payTo → indeterminate; wrong token → indeterminate; underpaid → indeterminate; correct → allow. The presence of a hash decides nothing.
3. `test_confirmed_settles_once_and_a_lost_response_recovers` — the first confirmation produces one effect; a replay is denied; a lost response is recovered without a second effect or a second debit.
4. `test_unconfirmed_or_mismatched_is_held_never_allowed` — the held verdicts are explicit `pending`/`indeterminate`, never `allow`.
5. `test_matching_is_on_the_code_not_the_message` and `test_terminal_failure_is_never_adopted` — the code decides, not the message text; a terminal code carrying a hash is still a failure.

**Synthetic input and expected output** (the `--json` output, abbreviated here; full values in the gist):

```json
{
  "synthetic_input": {
    "settle_response": {
      "success": false,
      "errorReason": "settlement_pending",
      "errorMessage": "node returned 503 while waiting for the receipt",
      "transaction": "0xabab…ab",
      "network": "eip155:8453"
    },
    "chain": {
      "head": 997,
      "receipt": {
        "tx_hash": "0xabab…ab",
        "status": 1,
        "block_number": 995,
        "transfers": [
          {"token": "0x8335…2913", "to": "0x…00a1", "amount_usdc": 0.05}
        ]
      }
    },
    "price": 0.05,
    "pay_to": "0x…00a1",
    "required_confirmations": 3
  },
  "expected_output": {
    "verdict": "allow",
    "adopted": true,
    "tx_hash": "0xabab…ab",
    "delivered": true,
    "effect_count": 1
  }
}
```

**One caveat I want to state rather than hide.** In our production code, "adopt the hash" is not separable from "check the chain yourself": the settlement hash is only a claim, and the handler verifies a USDC Transfer to our own `payTo` for at least the price before delivering. A test that only asserts the hash was adopted would pass against an implementation that then delivers without checking — which is the regression this fixture exists to prevent.

**A second caveat, about the "one business-side effect" assertion.** Our production code guarantees one *debit* per settlement hash (the payment guard is keyed on the hash) and one recovery attempt. Our handlers are read-only, so a repeated handler call has no business side effect. Your workflows may write. The fixture therefore models the stronger property — one business-side effect, with the result cached for the recovery — and marks where production would need an idempotency key on the *write*, not only on the payment. If you would rather the fixture mirror our weaker guarantee, say so and I will change it; I did not want to present a stronger property than we ship without saying so.

**Limitations.** No facilitator, no RPC, no reorg simulation beyond the status/depth checks; the chain is a deterministic stub. The fixture pins the decision table, not the transport. If you want the next step, the `#toolName` catalogue case is the other one, and I can write it in the same format.
