"""Payer profile lookup: ENS/Basename resolution for recon payers.

Takes a recon JSON report (or raw addresses) and resolves reverse ENS
records so outreach can be personalized instead of wallet-to-wallet.
Free public resolver API (ensideas.com) — no key needed.

Usage:
    python scripts/payer_lookup.py docs/_recon_currency_api_7d.json
"""

from __future__ import annotations

import json
import sys
from typing import List

import requests

RESOLVER_API = "https://api.ensideas.com/ens/resolve/"


def resolve(address: str, timeout: int = 10) -> dict:
    """Best-effort reverse resolution: {address, ens, name, avatar}."""
    try:
        r = requests.get(RESOLVER_API + address.lower(), timeout=timeout)
        if r.ok:
            d = r.json()
            return {
                "address": address,
                "ens": d.get("ens") or "",
                "display": d.get("name") or d.get("ens") or "",
            }
    except Exception as exc:
        return {"address": address, "ens": "", "display": f"(lookup failed: {exc})"}
    return {"address": address, "ens": "", "display": ""}


def lookup_report(path: str, only_repeat: bool = False) -> List[dict]:
    """Resolve every payer (or only repeat payers) from a recon report."""
    report = json.load(open(path, encoding="utf-8"))
    payers = report.get("repeat_payers") if only_repeat else report.get("payers")
    if payers is None:
        raise SystemExit("not a recon report: no 'payers' array")
    out = []
    for p in payers:
        info = resolve(p["payer"])
        info.update({"txs": p["txs"], "total_usdc": p["total_usdc"]})
        out.append(info)
    return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("report", help="recon JSON report path")
    ap.add_argument("--repeat-only", action="store_true")
    args = ap.parse_args()
    rows = lookup_report(args.report, only_repeat=args.repeat_only)
    for r in rows:
        tag = r.get("display") or "(unnamed)"
        print(f"{r['address']}  {r['txs']:>4} txs  {r['total_usdc']:>10} USDC  {tag}  {r['ens']}")
    named = sum(1 for r in rows if r.get("ens"))
    print(f"\n{named}/{len(rows)} resolved to an ENS/basename")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())