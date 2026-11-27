"""What a settlement costs in gas, measured on chain rather than estimated.

Two questions this answers with numbers instead of opinion, both of which came up
when a payments company asked whether x402 is a loss leader on micro-payments:

1. Who pays the gas in the `exact` scheme? Not the buyer and not the seller: the
   buyer signs an EIP-3009 `transferWithAuthorization` off chain, and the
   facilitator submits the transaction. The receipt proves it — the transaction's
   `from` is a third party, and the payer appears only inside the log as the
   `AuthorizationUsed` authorizer.
2. What does EIP-3009 cost against a plain ERC-20 `transfer`? The premium is the
   signature recovery on chain, and it is about 1.4x to 1.7x.

Read-only, no API key, public Base RPC. Settlements are passed as arguments;
with none, it measures the plain-transfer baseline only.

    python scripts/measure_settlement_gas.py 0x<txhash> 0x<txhash>

Measured 27.11.2026, ETH $1,660.42, Base base fee 0.005 gwei:
    $0.25 settlement  86,230 gas at 0.0100 gwei = $0.001432 = 0.57% of the payment
    $0.005 settlement 103,398 gas at 0.0056 gwei = $0.000964 = 19.3% of the payment
    plain `transfer`  median 62,159 gas (min 40,259) over 8 calls in 150 blocks
"""
from __future__ import annotations

import json
import sys
import urllib.request

RPC_ENDPOINTS = (
    "https://mainnet.base.org",
    "https://base-rpc.publicnode.com",
    "https://1rpc.io/base",
    "https://base.drpc.org",
)
UA = "Mozilla/5.0 (compatible; kristo-measurement/1.0)"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
SELECTORS = {
    "0xa9059cbb": "transfer (plain ERC-20)",
    "0xe3ee160e": "transferWithAuthorization (EIP-3009)",
    "0x23b872dd": "transferFrom",
}
LOG_NAMES = {
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef": "Transfer",
    "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5": "AuthorizationUsed",
}
BLOCKS_TO_SCAN = 150


def rpc(method: str, params: list):
    """Call the first public endpoint that answers.

    Every public Base RPC rate-limits or refuses a burst after a handful of
    calls (measured: 403 from publicnode, 429 from mainnet.base.org), so a single
    hardcoded host makes the measurement fail halfway through a run.
    """
    last = None
    for endpoint in RPC_ENDPOINTS:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params}).encode()
        request = urllib.request.Request(
            endpoint, data=body,
            headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return json.load(response)
        except Exception as exc:                              # noqa: BLE001
            last = f"{endpoint}: {type(exc).__name__} {str(exc)[:60]}"
    raise SystemExit("every Base RPC refused the call — last was " + str(last))


def _addr(topic: str) -> str:
    return "0x" + topic[-40:]


def eth_usd() -> float:
    request = urllib.request.Request(
        "https://api.coinbase.com/v2/prices/ETH-USD/spot",
        headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=20) as response:
        return float(json.load(response)["data"]["amount"])


def describe(tx: str, price_usd: float) -> None:
    transaction = rpc("eth_getTransactionByHash", [tx]).get("result") or {}
    receipt = rpc("eth_getTransactionReceipt", [tx]).get("result") or {}
    if not receipt:
        print(f"  no receipt for {tx}")
        return
    gas = int(receipt["gasUsed"], 16)
    gas_price = int(receipt.get("effectiveGasPrice") or "0x0", 16)
    fee_eth = gas * gas_price / 1e18
    print(f"  submitter (paid the gas) : {transaction.get('from')}")
    print(f"  function                 : "
          f"{SELECTORS.get((transaction.get('input') or '0x')[:10], '?')}")
    print(f"  gasUsed                  : {gas:,}")
    print(f"  fee                      : {fee_eth:.10f} ETH "
          f"= ${fee_eth * price_usd:.6f}")
    for log in receipt.get("logs") or []:
        topics = log.get("topics") or []
        name = LOG_NAMES.get(topics[0] if topics else "", "?")
        detail = ""
        if name == "Transfer" and len(topics) >= 3:
            detail = f" from={_addr(topics[1])} to={_addr(topics[2])}"
        elif name == "AuthorizationUsed" and len(topics) >= 2:
            detail = f" authorizer={_addr(topics[1])}"
        print(f"  log                      : {name}{detail}")


def plain_baseline() -> list:
    head = int(rpc("eth_blockNumber", [])["result"], 16)
    logs = rpc("eth_getLogs", [{
        "fromBlock": hex(head - BLOCKS_TO_SCAN), "toBlock": "latest",
        "address": USDC, "topics": [TRANSFER_TOPIC]}]).get("result") or []
    hashes = []
    for log in logs:
        if log["transactionHash"] not in hashes:
            hashes.append(log["transactionHash"])
    samples = []
    for tx in hashes[:150]:
        transaction = rpc("eth_getTransactionByHash", [tx]).get("result") or {}
        if (transaction.get("input") or "0x")[:10] != "0xa9059cbb":
            continue
        receipt = rpc("eth_getTransactionReceipt", [tx]).get("result") or {}
        samples.append(int(receipt["gasUsed"], 16))
        if len(samples) >= 8:
            break
    return samples


def main() -> int:
    price = eth_usd()
    print(f"ETH/USD ${price:,.2f}\n")
    for tx in sys.argv[1:]:
        print(f"{tx}")
        describe(tx, price)
        print()
    samples = plain_baseline()
    if samples:
        samples.sort()
        print(f"plain `transfer` over {BLOCKS_TO_SCAN} blocks, {len(samples)} samples:")
        print(f"  min {samples[0]:,}  median {samples[len(samples) // 2]:,}  "
              f"max {samples[-1]:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
