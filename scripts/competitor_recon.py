"""
Competitive on-chain recon — read-only, public data only.

Given a receiver wallet address (ours or a competitor's `payTo`), pull every
incoming USDC transfer on Base directly from an RPC node (no explorer API
key needed) and aggregate WHO actually pays, HOW OFTEN, and HOW MUCH.

Why: x402 payments are public USDC transfers. Before spending an hour on
marketing, this tells you whether a competitor's "thousands of calls" is
real operator volume or noise — and lists the wallets that pay repeatedly
(the operators worth talking to).

Usage:
    python scripts/competitor_recon.py                          # our receiver, last 7 days
    python scripts/competitor_recon.py --address 0xabc... --days 30 --out report.json
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

BLOCK_TIME_SECONDS = 2.0  # Base mainnet ~2s blocks
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DEFAULT_RECEIVER = "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"
DEFAULT_RPC = "https://mainnet.base.org"
TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)
USDC_DECIMALS = 6

# Known non-customer payers: market reviewers running verification canaries.
# They are real on-chain settlements (kept in totals) but they are NOT
# operators — labelled so operator stats never overstate the customer base.
KNOWN_PAYERS = {
    "0x7e6b6556322c4e26c567a867964ac793f5ee2b1c": "chet_payapi_verification",
}

# Transfers above this are almost certainly not per-call x402 payments
# (settlements, treasury moves, exchange flows) — flagged as noise, not hidden.
LARGE_TX_NOISE_THRESHOLD_USDC = 1000.0


def _pad_topic(address: str) -> str:
    """Encode an address as a 32-byte log topic."""
    addr = address.lower().replace("0x", "")
    if len(addr) != 40:
        raise ValueError(f"bad address: {address}")
    return "0x" + "0" * 24 + addr


def _decode_amount(data) -> float:
    """Decode ERC-20 Transfer data (raw uint256) into USDC units."""
    if hasattr(data, "hex"):          # HexBytes (web3 v7)
        raw = bytes(data)
    else:
        raw = bytes.fromhex(str(data).replace("0x", "") or "00")
    return int.from_bytes(raw or b"\x00", "big") / (10 ** USDC_DECIMALS)


def fetch_incoming_transfers(
    rpc_url: str,
    receiver: str,
    usdc_contract: str = USDC_BASE,
    from_block: int = 0,
    to_block: Optional[int] = None,
    chunk_size: int = 5000,
    pause_seconds: float = 0.15,
) -> List[dict]:
    """Fetch incoming USDC transfers to `receiver` via eth_getLogs.

    Read-only and rate-friendly (chunked with pacing). Returns a list of
    {tx_hash, payer, amount_usdc, block_number}.
    """
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise ConnectionError(f"RPC not reachable: {rpc_url}")

    latest = w3.eth.block_number
    if to_block is None:
        to_block = latest
    if from_block <= 0 or from_block > to_block:
        from_block = max(1, to_block - int(7 * 86400 / BLOCK_TIME_SECONDS))

    padded = _pad_topic(receiver)
    transfers: List[dict] = []
    start = from_block
    while start <= to_block:
        end = min(start + chunk_size - 1, to_block)
        try:
            logs = w3.eth.get_logs({
                "fromBlock": start,
                "toBlock": end,
                "address": Web3.to_checksum_address(usdc_contract),
                "topics": [TRANSFER_TOPIC, None, padded],
            })
        except Exception as exc:
            print(f"[warn] get_logs {start}-{end} failed: {exc}")
            start = end + 1
            continue
        for lg in logs:
            try:
                sender = Web3.to_checksum_address(
                    "0x" + bytes(lg["topics"][1]).hex()[-40:]
                )
                transfers.append({
                    "tx_hash": Web3.to_hex(lg["transactionHash"]),
                    "payer": sender,
                    "amount_usdc": _decode_amount(lg["data"]),
                    "block_number": lg["blockNumber"],
                })
            except Exception:
                continue
        start = end + 1
        if start <= to_block:
            time.sleep(pause_seconds)
    return transfers


def classify_transfers(
    transfers: List[dict],
    *,
    large_threshold_usdc: float = LARGE_TX_NOISE_THRESHOLD_USDC,
    known_payers: Optional[Dict[str, str]] = None,
) -> dict:
    """Pure aggregation: who pays, how often, how much — with noise flags.

    Noise policy: transfers >= large_threshold_usdc are NOT per-call x402
    payments (treasury/exchange/settlement flows); they go into a separate
    bucket so headline operator stats stay honest.

    Known payers (market reviewers running verification canaries) are real
    settlements but NOT operators: they are split into their own bucket so
    external-customer stats never overstate the customer base.
    """
    known = {k.lower(): v for k, v in (known_payers if known_payers is not None else KNOWN_PAYERS).items()}
    if not transfers:
        return {
            "total_txs": 0, "total_usdc": 0.0, "unique_payers": 0,
            "external_unique_payers": 0, "known_verification_txs": 0,
            "avg_check_usdc": 0.0, "repeat_payers": [], "payers": [],
            "known_verifications": [],
            "noise": {"large_txs": [], "large_tx_count": 0},
        }

    by_payer: Dict[str, List[float]] = {}
    large: List[dict] = []
    for t in transfers:
        amount = float(t.get("amount_usdc") or 0.0)
        if amount >= large_threshold_usdc:
            large.append(t)
            continue
        by_payer.setdefault(t["payer"], []).append(amount)

    # Split known verifiers out of the operator bucket.
    known_txs = 0
    known_bucket = []
    operators: Dict[str, List[float]] = {}
    for payer, amounts in by_payer.items():
        if payer.lower() in known:
            known_txs += len(amounts)
            known_bucket.append({
                "payer": payer,
                "label": known[payer.lower()],
                "txs": len(amounts),
                "total_usdc": round(sum(amounts), 6),
            })
        else:
            operators[payer] = amounts

    payers = [
        {
            "payer": payer,
            "txs": len(amounts),
            "total_usdc": round(sum(amounts), 6),
            "avg_usdc": round(sum(amounts) / len(amounts), 6),
        }
        for payer, amounts in operators.items()
    ]
    payers.sort(key=lambda e: (-e["total_usdc"], -e["txs"]))

    paid_txs = len(transfers) - len(large) - known_txs
    total = sum(sum(v) for v in operators.values())
    return {
        "total_txs": paid_txs,
        "total_usdc": round(total, 6),
        "unique_payers": len(by_payer),
        "external_unique_payers": len(operators),
        "known_verification_txs": known_txs,
        "avg_check_usdc": round(total / paid_txs, 6) if paid_txs else 0.0,
        "repeat_payers": [e for e in payers if e["txs"] >= 2],
        "payers": payers,
        "known_verifications": known_bucket,
        "noise": {
            "large_txs": [
                {"tx_hash": t["tx_hash"], "payer": t["payer"],
                 "amount_usdc": round(t["amount_usdc"], 2)}
                for t in large
            ],
            "large_tx_count": len(large),
        },
    }


def _summary(report: dict, address: str, days: int) -> str:
    lines = [
        f"== On-chain recon: {address} (last {days}d) ==",
        f"Micro-payment txs: {report['total_txs']}  |  total {report['total_usdc']} USDC"
        f"  |  unique payers: {report['unique_payers']}"
        f"  |  avg check: {report['avg_check_usdc']} USDC",
    ]
    if report["repeat_payers"]:
        lines.append("Repeat payers (operators — talk to these):")
        for e in report["repeat_payers"][:10]:
            lines.append(f"  {e['payer']}  {e['txs']} txs, {e['total_usdc']} USDC total")
    else:
        lines.append("Repeat payers: none in window")
    if report.get("known_verification_txs"):
        for e in report.get("known_verifications", []):
            lines.append(f"Known verifications (excluded from operator stats): "
                         f"{e['label']}: {e['txs']} txs, {e['total_usdc']} USDC")
    if report["noise"]["large_tx_count"]:
        lines.append(
            f"Noise: {report['noise']['large_tx_count']} large transfer(s) "
            f"(>= {LARGE_TX_NOISE_THRESHOLD_USDC:g} USDC) excluded from stats"
        )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="On-chain USDC payment recon (read-only)")
    ap.add_argument("--address", default=DEFAULT_RECEIVER, help="receiver wallet to analyze")
    ap.add_argument("--days", type=int, default=7, help="lookback window in days")
    ap.add_argument("--rpc", default=os.getenv("BASE_RPC_URL", DEFAULT_RPC))
    ap.add_argument("--contract", default=USDC_BASE)
    ap.add_argument("--chunk", type=int, default=5000)
    ap.add_argument("--out", default="", help="write JSON report here")
    args = ap.parse_args(argv)

    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        print(f"RPC not reachable: {args.rpc}")
        return 2
    to_block = w3.eth.block_number
    from_block = max(1, to_block - int(args.days * 86400 / BLOCK_TIME_SECONDS))
    print(f"Scanning blocks {from_block}..{to_block} ({args.days}d)...")

    transfers = fetch_incoming_transfers(
        args.rpc, args.address, args.contract,
        from_block=from_block, to_block=to_block, chunk_size=args.chunk,
    )
    report = classify_transfers(transfers)
    report["address"] = args.address
    report["window_days"] = args.days
    report["from_block"] = from_block
    report["to_block"] = to_block
    report["generated_at"] = datetime.now(timezone.utc).isoformat()

    print(_summary(report, args.address, args.days))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"Report saved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())