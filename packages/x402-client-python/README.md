# kristo-x402-client (Python)

Zero-dependency x402 payment client for the **Kristo Intelligence** API. It
handles the whole 402 handshake for you: call the endpoint, read the payment
challenge, ask your signer for an authorization, retry with the credential, and
return the paid JSON.

```python
from kristo_x402_client import KristoX402Client

client = KristoX402Client(pay=my_signer)      # my_signer signs an EIP-3009 authorization
print(client.get("/api/v1/signal")["data"])   # paid, parsed, done
```

Three lines. No dependencies. The core uses only the standard library.

## Why it exists

A paid endpoint is useless if integrating it costs more than the data is worth.
This package removes the handshake from the developer's problem: you supply one
callback that signs, and everything else — the challenge, the two rails, the
retry on a still-settling payment, the at-most-once signing rule — is handled.

## Install

```bash
pip install git+https://github.com/hristovdimitri2-hub/kristo-intelligence-6.git#subdirectory=packages/x402-client-python
```

Not on PyPI yet. The JavaScript twin is published as `kristo-x402-client` on
npm and behaves identically.

## The signer callback

`pay` is called once per request with the challenge, and must return either:

**The standard rail (preferred).** An EIP-3009 authorization signed by the
payer. The server settles it through a facilitator in about two seconds and no
gas is spent by the buyer.

```python
def my_signer(challenge):
    # challenge["amount_atomic"]  -> "10000"  (0.01 USDC, 6 decimals)
    # challenge["recipient"]      -> "0xB4Fc..."
    # challenge["chain_id"]       -> 8453
    # challenge["accepted"]       -> the raw accept block to echo back
    signed = sign_eip3009(...)          # your wallet library
    return {"signature": signed.signature.hex(),
            "authorization": signed.authorization}
```

**The smart-wallet rail.** A plain USDC transfer you broadcast yourself. The
server waits for 12 confirmations, roughly 2.5 seconds on Base.

```python
def my_signer(challenge):
    tx = broadcast_usdc_transfer(challenge["recipient"],
                                 challenge["amount_atomic"])
    return {"payer": my_address, "txHash": tx}
```

## What it guarantees

- **Signs at most once per request.** If the server answers 402 again after a
  credential was already presented, the client returns
  `payment_outcome_unknown` rather than signing a second payment. A second
  signature is a second charge.
- **Re-sends, never re-signs, on 425.** A 425 means the settlement is still
  confirming. The client retries the *same* credential, because the nonce is
  one-time-use and a second signature would be rejected anyway.
- **Reads the v2 challenge first, falls back to the legacy body.** Both shapes
  are supported, so it works against older and newer servers.
- **Never guesses a price.** The amount is read from the live challenge. A
  decimal value is treated as USDC and a bare integer as atomic units; where the
  two readings could disagree, the smaller is chosen, so a mistake costs a
  rejected call rather than the buyer's balance.

## Free inspection

```python
client = KristoX402Client(auto_pay=False)
print(client.get("/api/v1/signal")["payment_required"])
```

`auto_pay=False` returns the parsed challenge and spends nothing — useful for
seeing the price before wiring a wallet.

## LangChain

```python
from kristo_x402_client import KristoX402Client
from kristo_x402_client.langchain import make_langchain_tools

client = KristoX402Client(pay=my_signer)
tools = make_langchain_tools(client)      # seven ready tools
```

`make_openai_tool(client, "get_trading_signal")` returns an OpenAI-style
function definition with a `call` dispatcher attached.

## Routes and prices

| Tool | Path | Price |
|---|---|---|
| `get_trading_signal` | `/api/v1/signal` | $0.01 |
| `get_whale_flow` | `/api/v1/whaleflow` | $0.01 |
| `get_arbitrage_opportunities` | `/api/arb/opportunities` | $0.005 |
| `get_market_stats` | `/api/stats` | $0.005 |
| `get_onchain_sales` | `/api/sales` | $0.005 |
| `get_bot_status` | `/api/bot-status` | $0.005 |
| `verify_seller_receiver` | `/api/v1/verify-seller` | $0.05 |

Prices are read from the live 402 challenge; the table is for planning only.

## License

MIT.
