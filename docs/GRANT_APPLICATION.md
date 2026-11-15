### **Project Overview**

**Kristo Intelligence** is a production, mainnet-live x402 paid API: an 8-agent crypto intelligence
engine (Coinbase + DeFiLlama + CoinGecko + DeFi signals + risk overlay) that sells machine-readable
signals to AI agents per HTTP call, settled in USDC on Base.

- **Live API:** https://kristo-intelligence-api.onrender.com
- **MCP transports:** `POST /mcp` (Streamable HTTP) and `/mcp/sse`
- **Paid discovery (free):** `GET /api/mcp/manifest`
- Status: live on Base mainnet, production DB, real paying buyers since 02.09.2026.
- **Requested grant amount:** $3,000 — for continued endpoint development, documentation,
  directory listings (awesome-mcp-servers PR #13219), and user support.

### **x402 Integration Details**

- **Network:** Base mainnet (`eip155:8453`, chainId 8453)
- **USDC contract (Base):** `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` *(6 decimals)*
- **Receiver (`payTo`):** `0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f`
- **Payment scheme:** `exact`, x402 v2 canonical 402 challenge, idempotent on retry
- **Two settlement rails:**
  1. **Rail 1 (STANDARD, gasless):** EIP-3009 `TransferWithAuthorization` — client signs
     `PAYMENT-SIGNATURE` (base64url JSON, `x402Version/scheme/network/payload{signature,authorization}`);
     settlement relayed by the x402 facilitator chain (PayAI default → Coinbase CDP fallback;
     `services/connectors.py`). Payer needs **0 ETH** — proven twice, payer holds 0 wei.
  2. **Rail 2 (direct ERC-20 transfer):** for standard clients without EIP-3009 support.
- **Paid endpoints & prices (USDC):** `/api/stats`, `/api/sales`, `/api/bot-status`,
  `/api/arb/opportunities` → **0.005**; `/api/v1/signal`, `/api/v1/whaleflow` → **0.003**;
  `/api/mcp/manifest`, `/dashboard` → **0.0 (free)**.
- **Client code (open in repo):** `scripts/demo_sponsored_pay.py` — dry-run + `--send` gasless
  client building the EIP-3009 signature against our own 402 challenge (commit `b5bc92e`).
- **Verified paid calls (both gasless, $0.003 each):**
  - #1 `0xdaf3dd0f0d16528136b7f04a68b88b5f3fe954a121f0336568b5a78333d75355` (block 52287422) — HTTP attempts 425 → 401 → **200**
  - #2 `0xcac187e8666039d09604cc15bc2114ce69782c639cc57c051af94bba562d4c1b` (block 52288216) — HTTP **200** first attempt

### **Impact & Innovation**

- **New supply:** raw, actionable trading intelligence other agents can automate against
  (signals, whaleflow, arb radar) — an x402-paid data source that did not exist before.
- **New demand:** per-call micropayments ($0.003–0.005) make agent-to-agent data buying
  practical with no API keys, no accounts, no prepaid credits.
- **Gasless pioneer:** our Rail 1 demonstrates the full sponsored flow — payer with **zero ETH**
  signs EIP-3009, facilitator settles, HTTP 200 delivers — the pattern x402 promotes for agentic
  commerce. On-chain verifiable: two settlement txs above.
- **Screen-recorded proof for the Micro-Grant:** ≤2-min demo clip of request → 402 → payment →
  HTTP 200 (`kristo_paid_demo_clip.mp4`, 95.5 s; sha256
  `74dae09ade32578987cb6b95adff90249017abd54068e7a0296546b931278698`;
  19 MB web version `kristo_paid_demo_clip_web.mp4` sha256
  `e0484f5824fb9c4237253703076d5510d52d1da7338546ef6625b8a08858a7de`;
  payment-moment preview frame `kristo_paid_demo_preview.jpg` sha256
  `2bb507d7a3de11fe265d519314b42b6ae9065e0006ee5a4f395fb3539699c260`) — available on request
  (kept out of the repo on purpose; media never committed).
- **Quality bar:** 426/426 automated tests green; fail-closed payment verification
  (401 on invalid proof), idempotent 402 retries, on-chain Transfer-log verification of every sale.

### **Team & Socials**

- **Twitter (Main Contact):** @Dimitri7210 — demo video post: https://x.com/Dimitri7210/status/2107801169925960035
- **GitHub:** https://github.com/hristovdimitri2-hub (repo: kristo-intelligence-6)
- **Facilitator:** registered via PayAI public facilitator (CDP-ready)
- **Live on mainnet since:** 2026-09-02 (first chain-verified sale, block 50783187)

cc @murrlincoln
