"""Verified on-chain sales — DAY-OF-TRUTH recovery manifest.

Every row below was pulled DIRECTLY from the chain (Blockscout Base
`module=account&action=tokentx` for the fee receiver + `eth_getTransactionReceipt`
cross-check per hash), NOT reconstructed from memory. This file is the single
source of truth used by `DashboardStore.seed_verified_sales()` so the canonical
dashboard shows the real numbers even on an ephemeral filesystem that was wiped
by a deploy (priority-0 invariant: "deploy must not zero the counters").

Hard facts (chain, 100% reproducible):

  receiver  : 0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f
  token     : USDC 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 (Base, 6 decimals)
  transfers : 8 (ALL incoming, ALL USDC — the address has no other token flow)
  total     : 28000 atomic = $0.028

Truth vs earlier bookkeeping (see PROJECT_STATUS.md):
  * earlier notes said $0.026 / 3 external payers  → WRONG (priority-0 report)
  * chain says      $0.028 / 2 external payers
  * two transfers are $0.005 (0xb8a52dcd… and 0x98f63a29…), six are $0.003
  * 0xA19F (watchlist) and 0x5f64 NEVER sent USDC to the receiver — no tx exists

Payer classification is NOT hardcoded here: `record_sale()` re-derives
canary/sampler/external from KNOWN_PAYERS at insert time.
"""

from __future__ import annotations

from typing import Any, Dict, List

#: The fee receiver these transfers were verified against.
VERIFIED_RECEIVER = "0xd4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"

#: Base USDC contract.
VERIFIED_TOKEN = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"

#: Source query (reproduce the whole list in one request):
#:   https://base.blockscout.com/api?module=account&action=tokentx
#:     &address=0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f
#:     &contractaddress=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
#:     &sort=asc&page=1&offset=200
VERIFIED_SALES_SOURCE = (
    "https://base.blockscout.com/api?module=account&action=tokentx"
    f"&address={VERIFIED_RECEIVER}&contractaddress={VERIFIED_TOKEN}"
    "&sort=asc&page=1&offset=200"
)

VERIFIED_SALES: List[Dict[str, Any]] = [
    {
        "tx_hash": "0xb8a52dcd61962af4b2d15d6f166b6c5038bbe9c40c171b37508a199bd40a45e6",
        "amount_usdc": 0.005,
        "sender": "0x7e6b6556322c4e26c567a867964ac793f5ee2b1c",
        "block_number": 50783187,
        "ts_unix": 1788355721,
    },
    {
        "tx_hash": "0xf5cff040a181876efd3434f63c55cbafba970e3dd0860edd36c06c17e6993016",
        "amount_usdc": 0.003,
        "sender": "0x7e6b6556322c4e26c567a867964ac793f5ee2b1c",
        "block_number": 50787936,
        "ts_unix": 1788365219,
    },
    {
        "tx_hash": "0x1cf2a51caa352a19435c682ff88a8bf3f4121929d9d22101329db243fc91f971",
        "amount_usdc": 0.003,
        "sender": "0x7e6b6556322c4e26c567a867964ac793f5ee2b1c",
        "block_number": 50798541,
        "ts_unix": 1788386429,
    },
    {
        "tx_hash": "0x0cc98ef96e5e5d9a12f3021b77e2a67bba9439745b9eaf61efdb414491295a5f",
        "amount_usdc": 0.003,
        "sender": "0x7e6b6556322c4e26c567a867964ac793f5ee2b1c",
        "block_number": 50820464,
        "ts_unix": 1788430275,
    },
    {
        "tx_hash": "0xb881f9dcdd0df72bf1853ebbf3328cf8d140ae8966871136b6cbe0cf852d5fc3",
        "amount_usdc": 0.003,
        "sender": "0x4db7aafbe797a39cd6cc4e7aa64d970f7f6e02b7",
        "block_number": 50943758,
        "ts_unix": 1788676863,
    },
    {
        "tx_hash": "0x770d21789f4c5034bf923252fe97088b2c2475f856946e64e13dc36c271c0627",
        "amount_usdc": 0.003,
        "sender": "0x54e163e9b8edda194d83f46add921bfa5fc5f4e0",
        "block_number": 51033391,
        "ts_unix": 1788856129,
    },
    {
        "tx_hash": "0xc30268e387e84d449f433772ed11e9ab751394d80bfc310a9c7dbb5e604cce03",
        "amount_usdc": 0.003,
        "sender": "0x7e6b6556322c4e26c567a867964ac793f5ee2b1c",
        "block_number": 51200083,
        "ts_unix": 1789189513,
    },
    {
        "tx_hash": "0x98f63a29c54255003405c270763734da127c95b21fc533ff79564be1e9d55e2a",
        "amount_usdc": 0.005,
        "sender": "0x902dcf34e53695bdea2ffb354b1a2e58bd598256",
        "block_number": 51221690,
        "ts_unix": 1789232727,
    },
]

#: The three tx hashes that earlier notes stored as TRUNCATED reconstructions.
#: Kept for the audit trail so nobody re-invents them.
TRUNCATED_PLACEHOLDERS_RETIRED = (
    "0xc302… (Chet whale canary — real full hash: 0xc30268e3…4cce03)",
    "0x4dB7… (real full hash: 0xb881f9dc…2d5fc3)",
)


def expected_totals() -> Dict[str, Any]:
    """Deterministic expectations for the seeded manifest (used by tests)."""
    total = round(sum(r["amount_usdc"] for r in VERIFIED_SALES), 6)
    senders = {r["sender"] for r in VERIFIED_SALES}
    return {
        "total_usdc": total,
        "total_count": len(VERIFIED_SALES),
        "distinct_senders": len(senders),
    }
