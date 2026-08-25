# kristo-x402-client

Zero-dependency client for the [Kristo Intelligence API](https://kristo-intelligence-api.onrender.com) — handles **x402 paywalls automatically**: call an endpoint, the client pays the requested USDC on Base, retries with a cryptographic payment proof, and returns your data.

AI agents pay for DeFi market intelligence with **two lines of code**. No API keys. No signup.

## Install

```bash
npm install kristo-x402-client
```

## Quick start (with any signer)

The core has **zero dependencies** — bring your own wallet signer through the `pay` callback:

```js
import { KristoX402Client } from "kristo-x402-client";

const client = new KristoX402Client({
  // Your payer: receives { amount, recipient, tokenContract, chainId },
  // sends the USDC transfer on Base, and returns the tx hash.
  pay: async ({ amount, recipient, tokenContract, chainId }) => {
    // viem / ethers / web3.js — whatever you already use.
    const txHash = await myWallet.sendTransaction({ /* ERC-20 transfer */ });
    return { payer: myWallet.address, txHash };
  },
});

const result = await client.get("/api/stats");
console.log(result.data); // live market intelligence — paid & unlocked
```

### Example payer with viem

```js
import { createWalletClient, http, parseUnits } from "viem";
import { base } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

const account = privateKeyToAccount(process.env.WALLET_PRIVATE_KEY);
const wallet = createWalletClient({ account, chain: base, transport: http() });

const USDC_ABI = [
  "function transfer(address to, uint256 amount) returns (bool)",
];

const client = new KristoX402Client({
  pay: async ({ amount, recipient, tokenContract }) => {
    const txHash = await wallet.writeContract({
      address: tokenContract,
      abi: USDC_ABI,
      functionName: "transfer",
      args: [recipient, parseUnits(String(amount), 6)],
    });
    return { payer: account.address, txHash };
  },
});
```

## LangChain integration

```js
import { DynamicStructuredTool } from "@langchain/core/tools";
import { createKristoTool } from "kristo-x402-client/langchain";

const statsTool = new DynamicStructuredTool(
  createKristoTool({
    client,
    path: "/api/stats",
    name: "kristo_market_stats",
  })
);

// Register `statsTool` in your agent's tool list — it pays for itself.
```

## Dry-run mode (inspect the payment challenge without paying)

```js
const inspector = new KristoX402Client({ autoPay: false });

const { paymentRequired } = await inspector.get("/api/stats");
console.log(paymentRequired);
// { amount: 0.05, recipient: "0xd4cd...", tokenContract: "0x8335...", chainId: 8453, path: "/api/stats" }
```

## How it works

```
client.get("/api/stats")
  └─> GET /api/stats
        └─> HTTP 402 { x402_amount, x402_recipient, x402_token_contract, ... }
              └─> your `pay` callback sends USDC on Base (you hold the keys)
                    └─> retry with header X-Payment-Proof: base64url(JSON({payer, transaction_hash, amount_usdc}))
                          └─> server verifies the transfer ON-CHAIN
                                └─> HTTP 200 + your data
```

Payments are verified on-chain by the server (ERC-20 Transfer event decode) —
one payment unlocks exactly one call, and the proof cannot be replayed.

## API

### `new KristoX402Client(options)`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `baseUrl` | string | `https://kristo-intelligence-api.onrender.com` | API base URL |
| `pay` | function | — | Payer callback: `({amount, recipient, tokenContract, chainId, path}) => {payer, txHash}`. Required unless `autoPay: false` |
| `autoPay` | boolean | `true` | When `false`, 402 responses return as `{paymentRequired}` without paying |
| `maxPaymentRetries` | number | `3` | Payment rounds before giving up |

### `client.get(path)` / `client.post(path, json)`
Returns `{ok, status, data}` — or `{ok: false, status: 402, paymentRequired}` in dry-run mode.

### Helpers
- `buildPaymentProof({payer, transactionHash, amountUsdc})` — build the `X-Payment-Proof` header value yourself.
- `parsePaymentChallenge(body)` — parse a 402 body into `{amount, recipient, tokenContract, chainId}`.

## Pricing

- Free tier: 1 call per client, no signup
- Pay-per-call: **$0.05 USDC** (volume discount to $0.01 after 10 paid calls)
- Monthly VIP: **$29** — unlimited + Telegram group

## License

MIT
