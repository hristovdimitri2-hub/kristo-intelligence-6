# PULSEMCP — ready for submission (NOT submitted)

**Checked live:** 2026-09-17 · read-only, nothing was sent.

## Status (facts, not expectations)

| check | result |
|---|---|
| Search `pulsemcp.com/servers?q=kristo` | **We are NOT there** — 5 results, all foreign (`kjozsa-git`, `kjozsa-jenkins`, `krzko-google-cloud`, `kristofferstrube-blazor-webmcp`, `agentcrush`) |
| `pulsemcp.com/submit` | **"submissions and changes are temporarily paused"** · *Last updated: September 3, 2026* |
| Banner on `/servers` | "New server submissions and listing changes are **still paused** while we rework how we ingest and manage listings." |
| Their `/api` (sources of the directory) | Manual submissions · automated scraping · **"Integration with the Official MCP Registry"** |
| Our Registry record (the channel they read from) | **v6.0.0 · isLatest=True · active** · `/mcp` + `/mcp/sse` · repo `kristo-intelligence-6` · pricing 0.003–0.005 USDC |
| Their directory | 21 880 servers (Last Update on `/servers`) |

⇒ **Automatic pickup from the Registry has not happened yet** (we have been in the
Registry since 17.09). Their form is closed, so **nothing is being submitted** — the
ready-made request is waiting.

## What the owner does (by hand)

1. **Check the banner** on `pulsemcp.com/servers`: as soon as the text "still paused"
   disappears, the form is open. (If you have already received a message that they have
   opened it — that is a stronger signal than a cached page; then go straight to item 3.)
2. **Check the Registry too** (they take from there): if we have appeared in PulseMCP on
   our own after the return — **nothing is submitted**, you only verify the data (item 4).
3. **Open `pulsemcp.com/submit`** and fill it in from the block below (copy-paste; their
   fields may have different names — the text is the same).
4. **Data verification** (after we appear, automatically or manually):
   - URL = `https://kristo-intelligence-api.onrender.com/mcp` ✅
   - tools = `get_market_stats`, `get_onchain_sales`, `get_bot_status`,
     `get_trading_signal`, `get_whale_flow`, `get_arbitrage_opportunities` (6) ✅
     <br>If you see **3**, the listing has not reloaded yet after we opened all three
     new tools — it is not a data error, but a cache.
   - prices = **$0.003–$0.005** (`X402_PRICE_MAP`; zero "$0.05", zero "1 free call") ✅
   - repo = `hristovdimitri2-hub/kristo-intelligence-6` ✅

---

## Copy-paste block for the form

**Name**
```
Kristo Intelligence
```

**URL (remote MCP endpoint)**
```
https://kristo-intelligence-api.onrender.com/mcp
```

**Repository**
```
https://github.com/hristovdimitri2-hub/kristo-intelligence-6
```

**Short description** (from the ready-made listing, ≤160 characters)
```
DeFi market intelligence API for AI agents on Base. Six x402 endpoints, paid per call in USDC from $0.003: signals, whale flow, arbitrage, on-chain sales.
```

**Long description** (from the ready-made listing `kristo-agentic-market-final.md`)
```
Machine-readable DeFi intelligence for AI agents that trade autonomously. MCP server (Streamable HTTP + SSE on /mcp) exposing all six paid routes as tools — get_market_stats, get_onchain_sales, get_bot_status, get_trading_signal, get_whale_flow, get_arbitrage_opportunities — JSON only:

- /api/v1/signal — action, confidence, price, reasoning for ETH/ONDO/KAITO/DEGEN; 8-agent engine.
- /api/v1/whaleflow — USDC transfers >= $50k on Base with labeled counterparties and the scanned-block watermark.
- /api/stats — market snapshot (CoinGecko, DEXScreener, Fear & Greed) + daily aggregates.
- /api/sales — on-chain verified USDC sales history for this API (ERC-20 Transfer monitoring).
- /api/arb/opportunities — cross-DEX spreads on Base, 60s refresh.
- /api/bot-status — service and integration counters.

Payment is x402: no signup, no API keys. Unpaid calls return HTTP 402 with the exact USDC amount and receiver; the agent pays on Base (chain 8453) and retries. Prices: $0.003–$0.005 per call.

Chain-truth: sales figures come from the chain, not from RAM, and every number states the block it came from. If a scan has not run, the feed says so. No projections.
```

**Category**
```
Trading
```

**Transport / compatibility**
```
Streamable HTTP + SSE (MCP 2025-11-25)
```

**Tags**
```
defi, base, x402, usdc, market-data, payments, agents
```

**Contact**
```
<contact-email>
```

---

## Why this text (and why it is safe)

- The description is **the same** one that has already landed on Glama and Smithery — no new
  numbers.
- Prices come from `X402_PRICE_MAP` (single source): `/api/v1/signal` and
  `/api/v1/whaleflow` = $0.003; `/api/stats`, `/api/sales`, `/api/arb/opportunities`,
  `/api/bot-status` = $0.005. **Zero phantoms**: no "$0.05/call", no "1 free call"
  (production runs with `KRISTO_FREE_TIER_LIMIT=0` — every unpaid call returns 402).
- No wallet addresses, keys or internal details in the submission text.
- The sweep test (`tests/test_price_sweep.py`) guards these claims against regression.
