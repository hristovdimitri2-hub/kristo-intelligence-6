# kristo-x402-client

Zero-dependency client for the [Kristo Intelligence API](https://kristo-intelligence-api.onrender.com) — it drives **our x402 paywall end to end**: call an endpoint, the client settles the requested USDC on Base, retries with the credential the server asked for, and returns your data.

It speaks **both** x402 rails and prefers the fast one:

| Rail | Credential | How it settles | Time to unlock |
|------|-----------|----------------|----------------|
| **Standard (x402 v2)** — preferred | `PAYMENT-SIGNATURE` | EIP-3009 `transferWithAuthorization`, settled through a facilitator. The payer signs; no gas, no broadcast. | **~2 seconds** |
| Legacy | `X-Payment-Proof` | A plain ERC-20 USDC transfer, verified on-chain | **~24 seconds** (12 confirmations) |

Both are accepted by the API. This package uses the standard rail whenever your
signer can produce an EIP-3009 signature, and the legacy rail otherwise — so
existing integrations keep working unchanged.

> **Version note — read this before installing.** The standard-rail support
> described above lands in **1.1.0**, which is **not published yet**. If
> `npm install kristo-x402-client` gives you the older **1.0.0**, that release
> speaks only the legacy rail: it still works and still pays the same price, but
> every call waits the full ~24 seconds, and the `PAYMENT-SIGNATURE` example
> below will not match it. Check what you got with
> `node -p "require('kristo-x402-client/package.json').version"`.

AI agents pay for DeFi market intelligence with **two lines of code**. No API keys. No signup.

## Install

```bash
npm install kristo-x402-client
```

## Quick start — the fast rail (recommended)

Sign an EIP-3009 authorization. The client reads the standard `PAYMENT-REQUIRED`
challenge the server sends and hands your signer everything it needs:

```js
import { KristoX402Client } from "kristo-x402-client";
import { createWalletClient, http } from "viem";
import { base } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

const account = privateKeyToAccount(process.env.WALLET_PRIVATE_KEY);

const client = new KristoX402Client({
  pay: async ({ amountAtomic, recipient, tokenContract, chainId, extra }) => {
    const now = Math.floor(Date.now() / 1000);
    const authorization = {
      from: account.address,
      to: recipient,
      value: amountAtomic,            // atomic units, as a string
      validAfter: String(now - 60),
      validBefore: String(now + 60),  // the challenge allows 60s
      nonce: "0x" + crypto.randomUUID().replace(/-/g, "").padEnd(64, "0"),
    };
    const signature = await account.signTypedData({
      domain: {
        name: extra.name,             // "USD Coin"
        version: extra.version,       // "2"
        chainId,
        verifyingContract: tokenContract,
      },
      types: {
        TransferWithAuthorization: [
          { name: "from", type: "address" },
          { name: "to", type: "address" },
          { name: "value", type: "uint256" },
          { name: "validAfter", type: "uint256" },
          { name: "validBefore", type: "uint256" },
          { name: "nonce", type: "bytes32" },
        ],
      },
      primaryType: "TransferWithAuthorization",
      message: authorization,
    });
    return { signature, authorization };   // <- the fast rail
  },
});

const result = await client.get("/api/v1/signal");
console.log(result.data); // signals, unlocked in about two seconds
```

## Legacy rail — a plain transfer (still supported)

If your signer can only broadcast a transfer, return `{ payer, txHash }` instead
and the client uses `X-Payment-Proof`. This costs no extra money but the server
waits for 12 confirmations, so expect roughly 24 seconds before the data unlocks.

```js
const client = new KristoX402Client({
  pay: async ({ amount, recipient, tokenContract }) => {
    const txHash = await wallet.writeContract({
      address: tokenContract,
      abi: ["function transfer(address to, uint256 amount) returns (bool)"],
      functionName: "transfer",
      args: [recipient, parseUnits(String(amount), 6)],
    });
    return { payer: account.address, txHash };   // <- the legacy rail
  },
});
```

The `pay` callback receives the same challenge object either way, so one signer
can branch on what it supports.

## LangChain integration

```js
import { DynamicStructuredTool } from "@langchain/core/tools";
import { createKristoTool } from "kristo-x402-client/langchain";

const signalTool = new DynamicStructuredTool(
  createKristoTool({
    client,
    path: "/api/v1/signal",
    name: "kristo_signals",
  })
);

// Register `signalTool` in your agent's tool list — it pays for itself.
```

## Dry-run mode (inspect the payment challenge without paying)

```js
const inspector = new KristoX402Client({ autoPay: false });

const { paymentRequired } = await inspector.get("/api/stats");
console.log(paymentRequired);
// { rail: "v2", amount: 0.005, amountAtomic: "5000", recipient: "0xd4cd...",
//   tokenContract: "0x8335...", chainId: 8453, network: "eip155:8453",
//   maxTimeoutSeconds: 60, extra: { name: "USD Coin", version: "2" }, path: "/api/stats" }
```

## How it works

```
client.get("/api/v1/signal")
  └─> GET /api/v1/signal
        └─> HTTP 402 + header PAYMENT-REQUIRED: base64url({ x402Version: 2, accepts: [...] })
              └─> your `pay` callback signs an EIP-3009 authorization (you hold the keys)
                    └─> retry with header PAYMENT-SIGNATURE: base64url({ x402Version, accepted, payload })
                          └─> server settles through the facilitator
                                └─> HTTP 200 + your data      (~2s)

        HTTP 425 with `settlement_in_flight`? The settlement is still confirming.
        The client re-sends the SAME credential — never a second payment, because
        the authorization nonce is one-time-use.
```

Payments are verified on-chain — one payment unlocks exactly one call, and the
credential cannot be replayed.

## API

### `new KristoX402Client(options)`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `baseUrl` | string | `https://kristo-intelligence-api.onrender.com` | API base URL |
| `pay` | function | — | Signer callback. Resolve with `{signature, authorization}` (fast rail) **or** `{payer, txHash}` (legacy). Required unless `autoPay: false` |
| `autoPay` | boolean | `true` | When `false`, 402 responses return as `{paymentRequired}` without paying |
| `maxPaymentRetries` | number | `3` | Payment rounds before giving up |
| `maxInFlightRetries` | number | `5` | Re-sends of the same credential while the server answers 425 |
| `inFlightDelayMs` | number | `1500` | Delay between those re-sends |

### `client.get(path)` / `client.post(path, json)`
Returns `{ok, status, data}` — or `{ok: false, status: 402, paymentRequired}` in dry-run mode.

### Helpers
- `parsePaymentRequiredHeader(headerValue)` — parse the standard x402 v2 `PAYMENT-REQUIRED` header into `{rail, amount, amountAtomic, recipient, tokenContract, chainId, network, extra, accepted, ...}`. Returns `null` when absent, so you can fall back.
- `buildPaymentSignatureHeader({signature, authorization, accepted})` — build the `PAYMENT-SIGNATURE` header value yourself.
- `parsePaymentChallenge(body)` — the legacy 402 body shape into `{amount, recipient, tokenContract, chainId}`.
- `buildPaymentProof({payer, transactionHash, amountUsdc})` — build the `X-Payment-Proof` header value yourself.

## Pricing

Prices come from the API's own price map, which is the same source the live HTTP
402 challenges use. There is **no volume discount**: the discounted constant in
the server (0.01) is higher than every real route price, so the "price drops
after 10 calls" behaviour can never trigger. It is not promised here.

- Free tier: **none** — production runs with a free-tier limit of 0, so every
  unpaid call returns HTTP 402. There is no free call and no signup.
- Pay per call, USDC on Base:
  - **0.003** for `GET /api/v1/signal` and `GET /api/v1/whaleflow`
  - **0.005** for `GET /api/stats`, `GET /api/sales`, `GET /api/bot-status` and
    `GET /api/arb/opportunities`
- Free samples of every one of those routes exist and cost nothing — e.g.
  `GET /api/v1/signal/sample`, `GET /api/stats/sample`. Use them to build a
  client before spending anything.

The monthly plans advertised on the landing page (`/launch`, paid through
Stripe) are a **separate human product** — market bulletin and Telegram access.
They do **not** unlock x402 API calls: no API route consults the subscriber
list. Paying $29 does not buy API credit.

## Tests

```bash
npm test
```

The suite runs offline against a mock `fetch`, including a check that a 425
settlement window re-sends the same credential rather than paying twice.

## License

MIT
