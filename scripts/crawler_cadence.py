"""Crawler cadence analysis: WHEN does the ecosystem crawler sweep the market?

Two open questions (docs/RECON_FINDINGS.md, Wave 2):
  Q1. Sweeps or continuous discovery? Sweep model => predictable next-sweep
      DATE — the real indexing deadline, not "wait to day 30".
  Q2. False zero? All five sampled receivers showed "first payment 05.08" —
      extend the window back and see if the firsts move.

Usage:
    python scripts/crawler_cadence.py --wallet 0xC59E... --days 90
    python scripts/crawler_cadence.py --first-payment 0xd6b5... --days 60
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.competitor_recon import (
    BLOCK_TIME_SECONDS,
    DEFAULT_RPC,
    USDC_BASE,
    TRANSFER_TOPIC,
)

BURST_GAP_HOURS = 24.0  # payment gap larger than this starts a new burst


def collect_transfer_blocks(
    w3, usdc_contract: str, from_padded: Optional[str], to_padded: Optional[str],
    from_block: int, to_block: int, chunk_size: int = 5000, pause: float = 0.05,
) -> List[Tuple[int, str, str]]:
    """Matching USDC Transfers as (block, from, to), time-ordered."""
    topics = [TRANSFER_TOPIC]
    if from_padded:
        topics.append(from_padded)
    if to_padded:
        topics.append(to_padded)
    hits: List[Tuple[int, str, str]] = []
    start = from_block
    while start <= to_block:
        end = min(start + chunk_size - 1, to_block)
        try:
            logs = w3.eth.get_logs({
                "fromBlock": start, "toBlock": end,
                "address": usdc_contract, "topics": topics,
            })
            for lg in logs:
                frm = "0x" + bytes(lg["topics"][1]).hex()[-40:]
                to = "0x" + bytes(lg["topics"][2]).hex()[-40:]
                hits.append((lg["blockNumber"], frm, to))
        except Exception:
            pass
        start = end + 1
        if start <= to_block:
            time.sleep(pause)
    hits.sort()
    return hits


def pad(address: str) -> str:
    return "0x" + "0" * 24 + address.lower().replace("0x", "")


def cadence_report(
    w3, wallet: str, from_block: int, to_block: int, days: int,
    direction: str = "out",
) -> dict:
    """Histogram + burst analysis of a wallet's USDC payments (out) or
    incoming (in) activity over the window."""
    usdc = w3.to_checksum_address(USDC_BASE)
    if direction == "out":
        hits = collect_transfer_blocks(w3, usdc, pad(wallet), None, from_block, to_block)
    else:
        hits = collect_transfer_blocks(w3, usdc, None, pad(wallet), from_block, to_block)

    # Timestamps for distinct blocks only (bounded cache).
    ts_cache: Dict[int, int] = {}
    for blk, _, _ in hits:
        if blk not in ts_cache:
            try:
                ts_cache[blk] = w3.eth.get_block(blk).timestamp
            except Exception:
                ts_cache[blk] = 0
    stamps = sorted(ts_cache.get(b, 0) for b, _, _ in hits)
    days_hist = Counter(
        datetime.fromtimestamp(s, tz=timezone.utc).date().isoformat()
        for s in stamps
    )

    # Burst detection on sorted timestamps.
    bursts: List[List[int]] = []
    for s in stamps:
        if not bursts or (s - bursts[-1][-1]) > BURST_GAP_HOURS * 3600:
            bursts.append([s])
        else:
            bursts[-1].append(s)
    burst_info = [
        {
            "start": datetime.fromtimestamp(b[0], tz=timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(b[-1], tz=timezone.utc).isoformat(),
            "txs": len(b),
        }
        for b in bursts
    ]
    gaps_days = [
        round((bursts[i + 1][0] - bursts[i][-1]) / 86400, 1)
        for i in range(len(bursts) - 1)
    ]

    next_sweep = None
    meaningful = [b for b in burst_info if b["txs"] >= 20]
    if len(meaningful) >= 2:
        import statistics
        positive = [g for g in gaps_days if g > 0]
        if positive:
            med = statistics.median(positive)
            last = datetime.fromisoformat(meaningful[-1]["end"])
            from datetime import timedelta
            next_sweep = {
                "basis": f"median burst gap {med}d",
                "last_burst_end": meaningful[-1]["end"],
                "next_estimate": (last + timedelta(days=med)).date().isoformat(),
            }

    return {
        "wallet": wallet,
        "direction": direction,
        "window_days": days,
        "total_txs": len(hits),
        "distinct_counterparties": len({(f if direction == "out" else t) for _, f, t in hits}),
        "daily_histogram": dict(sorted(days_hist.items())),
        "burst_count": len(burst_info),
        "bursts": burst_info,
        "burst_gaps_days": gaps_days,
        "next_sweep_estimate": next_sweep,
        "window": {"from_block": from_block, "to_block": to_block},
    }


def first_payment_check(w3, receiver: str, days: int) -> dict:
    """Q2: extend the window back — does the receiver's first payment move?"""
    usdc = w3.to_checksum_address(USDC_BASE)
    to_block = w3.eth.block_number
    from_block = max(1, to_block - int(days * 86400 / BLOCK_TIME_SECONDS))
    hits = collect_transfer_blocks(w3, usdc, None, pad(receiver), from_block, to_block)
    if not hits:
        return {"receiver": receiver, "first_payment_in_window": None, "total_txs": 0}
    ts = w3.eth.get_block(hits[0][0]).timestamp
    return {
        "receiver": receiver,
        "window_days": days,
        "first_payment": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        "first_payment_block": hits[0][0],
        "total_txs": len(hits),
        "distinct_payers": len({f for _, f, _ in hits}),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Crawler cadence / first-payment analysis")
    ap.add_argument("--wallet", help="crawler wallet to analyze (outgoing)")
    ap.add_argument("--first-payment", dest="first_payment", help="receiver to test (incoming first payment)")
    ap.add_argument("--direction", choices=["out", "in"], default="out")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--rpc", default=os.getenv("BASE_RPC_URL", DEFAULT_RPC))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        print(f"RPC not reachable: {args.rpc}")
        return 2
    to_block = w3.eth.block_number
    from_block = max(1, to_block - int(args.days * 86400 / BLOCK_TIME_SECONDS))

    if args.wallet:
        print(f"Scanning {args.days}d of {'outgoing' if args.direction == 'out' else 'incoming'} txs for {args.wallet}...")
        report = cadence_report(w3, args.wallet, from_block, to_block, args.days, args.direction)
        print(f"total txs: {report['total_txs']}  |  counterparties: {report['distinct_counterparties']}")
        print(f"bursts: {report['burst_count']}  gaps: {report['burst_gaps_days']}")
        if report["next_sweep_estimate"]:
            print(f"NEXT SWEEP ESTIMATE: {report['next_sweep_estimate']['next_estimate']} "
                  f"({report['next_sweep_estimate']['basis']})")
        hist = report["daily_histogram"]
        print("daily histogram:")
        for d, n in hist.items():
            print(f"  {d}  {'#' * min(n, 60)} {n}")
    else:
        print(f"Checking true first payment for {args.first_payment} over {args.days}d...")
        report = first_payment_check(w3, args.first_payment, args.days)
        print(json.dumps(report, indent=1))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"saved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())