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
# Measured 17.09 on the public RPC (https://mainnet.base.org): a recipient-
# filtered eth_getLogs above ~1000 blocks answers **413 Payload Too Large**
# (5000-block chunks used to work — the endpoint tightened). Ranges are halved
# on refusal down to this floor; below it we stop and REPORT the gap, because
# an unscanned window must never be mistaken for "nobody paid".
MIN_CHUNK_BLOCKS = 100
DEFAULT_CHUNK_BLOCKS = 1000
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DEFAULT_RECEIVER = "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"
DEFAULT_RPC = "https://mainnet.base.org"
TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)
USDC_DECIMALS = 6

# ── Payer taxonomy (behavioral, automatic) ─────────────────────────────────
# A payer's *outgoing fan-out* tells us what it is:
#   crawler  — pays >= 50 distinct receivers/week (ecosystem probe/router)
#   loop     — <= 10 receivers, high cadence (benchmark bot / machine cycle)
#   human    — everything else (unknown until proven)
# The launch signal stays: external_unique_payers in the HUMAN bucket.
CRAWLER_MIN_RECEIVERS = 50
LOOP_MAX_RECEIVERS = 10
LOOP_MIN_TXS = 10

# Known non-customer payers: market reviewers running verification canaries.
# They are real on-chain settlements (kept in totals) but they are NOT
# operators — labelled so operator stats never overstate the customer base.
# Plus the market's known sampling infrastructure (fingerprinted 04.09 —
# see docs/RECON_FINDINGS.md): they pay EVERY endpoint continuously, so a
# payment from them is a HEARTBEAT (we're in the crawl set), never a
# launch signal.
KNOWN_PAYERS = {
    "0x7e6b6556322c4e26c567a867964ac793f5ee2b1c": "chet_payapi_verification",
    "0xc59e74ed6386b2a12d892fff2509a6965a0498dc": "market_sampler_c59e",
    "0x6777e11fb0a7917b8110b7dab9188aa3f6d23986": "market_crawler_6777",
    # Fingerprinted 08.09: 325 distinct receivers / 1281 tx / $11.32 (30d) —
    # paid our signal route once; same continuous-indexator class as 6777.
    # Its payment is a heartbeat ('in the crawl set'), never a launch signal.
    "0x54e163e9b8edda194d83f46add921bfa5fc5f4e0": "market_crawler_54e1",
}

# ── WATCHLIST: real-operator wallets we want to catch on a REPEAT payment ──
# NOT KNOWN_PAYERS — these are (probable) human operators, i.e. actual
# customers: they must stay counted as external. A second payment from a
# watchlisted wallet flips the trigger: "OPERATOR REPEAT" → operator-deal
# conversation (see NEW_OPERATOR_ANALYSIS).
WATCHLIST = {
    "0xa19f621581dbc851a21d6179868111709a52accc": "operator_watch_a19f",
    "0x4db7aafbe797a39cd6cc4e7aa64d970f7f6e02b7": "operator_watch_4db7",
}


def operator_repeats(transfers: list[dict],
                     watchlist: dict | None = None) -> list[dict]:
    """Watchlisted payers with >= 2 payments in the given transfer list.

    Pure function; returns [{'payer', 'label', 'txs', 'total_usdc'}] sorted
    by total desc. Empty list = no repeat yet (first-touch customers only).
    """
    watch = {k.lower(): v for k, v in (watchlist if watchlist is not None
                                       else WATCHLIST).items()}
    by_payer: dict[str, list[float]] = {}
    for t in transfers:
        payer = str(t.get("payer") or "").lower()
        if payer in watch:
            by_payer.setdefault(payer, []).append(
                float(t.get("amount_usdc") or 0.0))
    out = [
        {
            "payer": payer,
            "label": watch[payer],
            "txs": len(amounts),
            "total_usdc": round(sum(amounts), 6),
        }
        for payer, amounts in by_payer.items() if len(amounts) >= 2
    ]
    out.sort(key=lambda e: -e["total_usdc"])
    return out

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


def _get_logs_adaptive(
    w3,
    Web3,
    query: dict,
    chunk_size: int = DEFAULT_CHUNK_BLOCKS,
    min_chunk: int = MIN_CHUNK_BLOCKS,
    pause_seconds: float = 0.15,
    progress: bool = False,
) -> tuple:
    """Run a get_logs query over its whole range, halving refused chunks.

    The public Base RPC answers **413 Payload Too Large** for recipient-filtered
    ranges above ~1000 blocks (measured 17.09; 5000-block chunks worked in the
    past). The old code dropped such chunks and moved on — which is exactly how
    the weekly monitor came to report an EMPTY week: an unread window is not an
    empty one.

    Returns (logs, coverage) where coverage carries requested_blocks,
    scanned_blocks, failed_ranges, split_retries, chunks and `complete`.
    """
    from_block, to_block = query["fromBlock"], query["toBlock"]
    logs: List = []
    failed: List[list] = []
    retries = 0
    scanned = 0
    chunks = 0
    queue: List[tuple] = []
    start = from_block
    while start <= to_block:                       # start at the known-good width
        queue.append((start, min(start + chunk_size - 1, to_block)))
        start += chunk_size
    while queue:
        start, end = queue.pop(0)
        try:
            logs.extend(w3.eth.get_logs(dict(query, fromBlock=start, toBlock=end)))
        except Exception as exc:
            width = end - start + 1
            if width > min_chunk:
                mid = start + width // 2 - 1
                queue.insert(0, (mid + 1, end))    # the refused range is retried
                queue.insert(0, (start, mid))      # as two halves
                retries += 1
                continue
            print(f"[warn] get_logs {start}-{end} failed: {exc}")
            failed.append([start, end])
            continue
        scanned += end - start + 1
        chunks += 1
        if progress and chunks % 100 == 0:
            total = to_block - from_block + 1
            print(f"[..] scanned {100.0 * scanned / total:.0f}% (block {end}, "
                  f"{chunks} chunks, {len(logs)} txs)")
        if queue:
            time.sleep(pause_seconds)
    requested = to_block - from_block + 1
    return logs, {
        "requested_blocks": requested,
        "scanned_blocks": scanned,
        "failed_ranges": failed,
        "split_retries": retries,
        "chunks": chunks,
        "complete": not failed and scanned == requested,
    }


def fetch_incoming_transfers(
    rpc_url: str,
    receiver: str,
    usdc_contract: str = USDC_BASE,
    from_block: int = 0,
    to_block: Optional[int] = None,
    chunk_size: int = DEFAULT_CHUNK_BLOCKS,
    pause_seconds: float = 0.15,
    stats: Optional[dict] = None,
) -> List[dict]:
    """Fetch incoming USDC transfers to `receiver` via eth_getLogs.

    Read-only and rate-friendly. Chunks are ADAPTIVE: when the node refuses a
    range (public Base RPC → 413 above ~1000 blocks), the range is halved and
    both halves are retried down to MIN_CHUNK_BLOCKS. A weekly 7-day window
    therefore gets scanned end to end instead of silently returning nothing.

    Pass `stats` (dict, filled in place) for the coverage report:
    rpc_url / from_block / to_block / requested_blocks / scanned_blocks /
    failed_ranges / split_retries / complete. `complete=False` means the window
    was NOT fully read — silence is not proof that nobody paid.

    Returns a list of {tx_hash, payer, amount_usdc, block_number}.
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
    logs, coverage = _get_logs_adaptive(
        w3, Web3,
        {
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": Web3.to_checksum_address(usdc_contract),
            "topics": [TRANSFER_TOPIC, None, padded],
        },
        chunk_size, pause_seconds=pause_seconds, progress=stats is not None,
    )
    transfers: List[dict] = []
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
    if stats is not None:
        stats.update({"rpc_url": rpc_url, "from_block": from_block,
                      "to_block": to_block})
        stats.update(coverage)
    return transfers


def fingerprint_payer(
    rpc_url: str,
    payer: str,
    usdc_contract: str = USDC_BASE,
    days: int = 7,
    chunk_size: int = 5000,
) -> dict:
    """Behavioral fingerprint: WHERE ELSE does this payer send USDC?

    Outgoing fan-out classifies the payer automatically:
      crawler (>= CRAWLER_MIN_RECEIVERS receivers) — ecosystem probe; pays
      every x402 service it indexes, arrives regardless of price (H2 refuted
      04.09: it pays across the whole price range).
      loop (<= LOOP_MAX_RECEIVERS, >= LOOP_MIN_TXS) — benchmark/machine cycle;
      the ONLY observed comparative shopping on the market.
      human — everything else; this bucket feeds external_unique_payers.
    """
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(
        os.getenv("BASE_RPC_URL", DEFAULT_RPC), request_kwargs={"timeout": 30}
    ))
    to_block = w3.eth.block_number
    from_block = max(1, to_block - int(days * 86400 / BLOCK_TIME_SECONDS))
    padded = "0x" + "0" * 24 + payer.lower().replace("0x", "")
    receivers: Dict[str, List[float]] = {}
    logs, coverage = _get_logs_adaptive(
        w3, Web3,
        {"fromBlock": from_block, "toBlock": to_block,
         "address": Web3.to_checksum_address(usdc_contract),
         "topics": [TRANSFER_TOPIC, padded, None]},
        chunk_size, pause_seconds=0.05)
    for lg in logs:
        recv = "0x" + bytes(lg.topics[2]).hex()[-40:]
        amt = _decode_amount(lg["data"])
        receivers.setdefault(recv, []).append(amt)

    n_recv = len(receivers)
    n_tx = sum(len(v) for v in receivers.values())
    if n_recv >= CRAWLER_MIN_RECEIVERS:
        kind = "crawler"
    elif n_recv <= LOOP_MAX_RECEIVERS and n_tx >= LOOP_MIN_TXS:
        kind = "loop"
    elif not coverage["complete"]:
        # A window we could NOT read must never be sold as a "human" payer —
        # that bucket is what feeds the launch signal (external_unique_payers).
        kind = "unknown"
    else:
        kind = "human"
    return {
        "payer": payer,
        "window_days": days,
        "distinct_receivers": n_recv,
        "total_txs": n_tx,
        "total_usdc": round(sum(sum(v) for v in receivers.values()), 6),
        "top_receivers": sorted(
            (
                {"receiver": r, "txs": len(v), "total_usdc": round(sum(v), 6)}
                for r, v in receivers.items()
            ),
            key=lambda e: (-e["txs"], -e["total_usdc"]),
        )[:10],
        "classification": kind,
        "scan_complete": coverage["complete"],
        "scan_failed_ranges": coverage["failed_ranges"],
        "scan_blocks": f"{coverage['scanned_blocks']}/{coverage['requested_blocks']}",
    }


def recv_addr(lg) -> str:  # pragma: no cover - helper
    return "0x" + bytes(lg.topics[2]).hex()[-40:]


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
    ap.add_argument("--chunk", type=int, default=DEFAULT_CHUNK_BLOCKS,
                    help="initial blocks per eth_getLogs call; ranges are halved "
                         "automatically when the node refuses them")
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