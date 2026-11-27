# -*- coding: utf-8 -*-
"""Recent USDC transfers into our receiver, from the chain, by block range.

Proves whether a paid call settled even when the client never saw a response.
"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ENDPOINTS = ["https://base-rpc.publicnode.com", "https://1rpc.io/base",
             "https://base.drpc.org", "https://mainnet.base.org"]
UA = "Mozilla/5.0 (compatible; kristo-measurement/1.0)"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
PAYTO = "0x000000000000000000000000" + "b4fcf8ef52b5dc275924aed2bae94fe6cb7fc844"


def rpc(method, params):
    for endpoint in ENDPOINTS:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params}).encode()
        request = urllib.request.Request(
            endpoint, data=body,
            headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return json.load(response)
        except Exception:                                     # noqa: BLE001
            continue
    raise SystemExit("no Base RPC answered")


head = int(rpc("eth_blockNumber", [])["result"], 16)
span = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
logs = rpc("eth_getLogs", [{
    "fromBlock": hex(head - span), "toBlock": "latest",
    "address": USDC, "topics": [TRANSFER, None, PAYTO]}]).get("result") or []
print(f"blocks {head - span}..{head}  ({span} blocks)")
print(f"USDC transfers into {PAYTO[-40:]}: {len(logs)}")
import datetime
for log in logs:
    amount = int(log["data"], 16) / 1e6
    when = rpc("eth_getBlockByNumber", [log["blockNumber"], False]).get("result") or {}
    ts = int(when.get("timestamp") or "0x0", 16)
    stamp = datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"  {stamp}  block {int(log['blockNumber'], 16)}  "
          f"${amount:.6f}  from {('0x' + log['topics'][1][-40:])}  "
          f"tx {log['transactionHash']}")
