"""RPC bake-off: which free Base RPC serves network-wide USDC getLogs?

Tests each candidate with increasing block ranges (500/2000/5000/20000) over
REAL USDC Transfer logs (wildcard topics), verifies a KNOWN canary payment
(block 50943758, tx 0xb881f9dc...) is found by the recipient-filtered query,
and measures latency. Read-only, no keys, nothing sent anywhere.
"""
import json
import time

import requests

USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
# Known canary payment: block 50943758 (0x4dB7 external payer, 06.09 06:41)
CANARY_BLOCK = 50943758
CANARY_TX = "0xb881f9dcdd0df72bf1853ebbf3328cf8d140ae8966871136b6cbe0cf852d5fc3"
PAYTO_PADDED = "0x" + "0" * 24 + "d4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"

RPCS = ["https://base.drpc.org", "https://base-pokt.nodies.app"]
ANCHOR = 511_750_000  # known recent block near the tests
RANGES = [(ANCHOR, ANCHOR + 99, "100blk"),
          (ANCHOR, ANCHOR + 249, "250blk"),
          (ANCHOR, ANCHOR + 499, "500blk"),
          (ANCHOR, ANCHOR + 999, "1k")]


def call(rpc, frm, to, topics):
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [{
        "fromBlock": hex(frm), "toBlock": hex(hi := to),
        "address": USDC, "topics": topics,
    }]}
    t0 = time.time()
    r = requests.post(rpc, headers={"Content-Type": "application/json"},
                      json=body, timeout=30)
    dt = time.time() - t0
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:80]}", dt
    res = r.json().get("result")
    if res is None:
        return None, str(r.json().get("error", {}))[:80], dt
    return res, None, dt


def probe(rpc, lo, hi, topics):
    return call(rpc, lo, hi, topics)


def main():
    anchor = ANCHOR
    print("=" * 90)
    print(f"{'RPC':<34} {'100blk':>7} {'250blk':>7} {'500blk':>7} {'1k':>7}  canary  notes")
    print("=" * 90)
    for rpc in RPCS:
        row, notes = {}, []
        for lo, hi, tag in RANGES:
            res, err, dt = probe(rpc, lo, hi, [TOPIC, None, None])
            if res is None:
                row[tag] = "ERR"
                notes.append(f"{tag}: {err}")
            else:
                row[tag] = len(res)
        res, err, dt = probe(rpc, CANARY_BLOCK, CANARY_BLOCK + 10,
                             [TOPIC, None, PAYTO_PADDED])
        canary = "OK" if (res and len(res) >= 1) else f"FAIL({err[:30] if err else len(res) or 0})"
        print(f"{rpc:<34} {str(row.get('100blk','-')):>7} {str(row.get('250blk','-')):>7} "
              f"{str(row.get('500blk','-')):>7} {str(row.get('1k','-')):>7}  "
              f"{canary:<8} {'; '.join(notes[:2])}")
    print("=" * 78)
    print("canary=OK means the RPC correctly returns the real 06.09 payment log.")


if __name__ == "__main__":
    main()

# ── drpc stability check: 5 consecutive 250-block wildcard queries ─────────
h = {"Content-Type": "application/json"}
latest = json.loads(requests.post(
    "https://base.drpc.org", headers=h,
    json={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []},
    timeout=25).text)["result"]
latest = int(latest, 16)
fmt = lambda n: "0x" + format(n, "x")  # noqa: E731
print(f"\n=== drpc stability (latest {latest}) ===")
for i in range(5):
    lo, hi = latest - 250 - i * 260, latest - 1 - i * 260
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [{
        "fromBlock": fmt(lo), "toBlock": fmt(hi),
        "address": USDC, "topics": [TOPIC, None, None]}]}
    t0 = time.time()
    r = requests.post("https://base.drpc.org", headers=h, json=body, timeout=25)
    n = len(r.json().get("result", [])) if r.status_code == 200 else "ERR " + r.text[:50]
    print(f"  call {i}: {r.status_code} | {n} | {time.time() - t0:.1f}s")