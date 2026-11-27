# -*- coding: utf-8 -*-
"""Recomputable payer identity for a Base payTo, from a keyless public API.

Ernest proposed this measurement on x402-foundation/x402#4367 using Blockscout's
*v2* API, which is behind a Cloudflare challenge for programmatic callers (403
"Just a moment..."). The Etherscan-compatible endpoint on the same host is not,
so this uses that and prints everything a third reader needs to re-run it:

  * the FULL payTo, not a truncated one
  * every sender address, its transfer count and its USDC total
  * breadth: how many distinct USDC recipients that sender has ever paid on Base

    python scripts/payer_identity.py 0x<payTo>
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

API = "https://base.blockscout.com/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
SELF = {
    "0xb4fcf8ef52b5dc275924aed2bae94fe6cb7fc844": "our receiver (current payTo)",
    "0xd4cda900839c0fed4374ee37ea0dbe8e4c6fd08f": "our receiver (retired payTo)",
    "0x5f6d3f20282a8958c6607d7e17dc8c83b1f0ee74": "our gas wallet",
    "0xe50c5212e8211639c49276da190e248b83935763": "our demo payer",
}


def _get(params: dict):
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def token_transfers(address: str) -> list:
    out, page = [], 1
    while True:
        data = _get({"module": "account", "action": "tokentx",
                     "address": address, "contractaddress": USDC,
                     "page": page, "offset": 1000, "sort": "desc"})
        rows = data.get("result") or []
        if not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        if len(rows) < 1000:
            break
        page += 1
    return out


def main() -> int:
    payto = (sys.argv[1] if len(sys.argv) > 1
             else "0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844")
    rows = [r for r in token_transfers(payto)
            if (r.get("to") or "").lower() == payto.lower()]
    print(f"payTo (full)      : {payto}")
    print(f"USDC incoming     : {len(rows)}")
    print(f"total USDC        : "
          f"{sum(int(r['value']) for r in rows) / 1e6:.6f}")
    if rows:
        stamps = sorted(int(r["timeStamp"]) for r in rows)
        import datetime
        fmt = lambda s: datetime.datetime.utcfromtimestamp(s).strftime("%Y-%m-%d %H:%M:%SZ")
        print(f"window            : {fmt(stamps[0])} -> {fmt(stamps[-1])}")
        print(f"distinct senders  : {len({r['from'].lower() for r in rows})}\n")

    by_sender = defaultdict(list)
    for r in rows:
        by_sender[r["from"].lower()].append(r)

    print(f"{'sender':44s} {'n':>4} {'USDC':>9} {'share':>7}  breadth")
    breadth_cache = {}
    for sender, items in sorted(by_sender.items(), key=lambda kv: -len(kv[1])):
        usdc = sum(int(i["value"]) for i in items) / 1e6
        share = len(items) / len(rows) * 100
        if sender in SELF:
            print(f"{sender:44s} {len(items):>4} {usdc:>9.4f} {share:>6.1f}%  "
                  f"OURS: {SELF[sender]}")
            continue
        if sender not in breadth_cache:
            outgoing = [t for t in token_transfers(sender)
                        if (t.get("from") or "").lower() == sender]
            breadth_cache[sender] = (len({(t.get("to") or "").lower()
                                          for t in outgoing}), len(outgoing))
        distinct, paid = breadth_cache[sender]
        print(f"{sender:44s} {len(items):>4} {usdc:>9.4f} {share:>6.1f}%  "
              f"{distinct} distinct recipients over {paid} transfers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
