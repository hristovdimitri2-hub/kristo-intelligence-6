# Kristo Intelligence v6

**Automated trading agent for the Base DeFi ecosystem**

Kristo Intelligence combines precise fee calculation for the
Base network (Coinbase's L2), price data from CoinGecko, and DeFi signals for
informed trading decisions.

## Architecture

```
kristo-intelligence-v6/
├── blockchain/
│   ├── __init__.py
│   └── wallet.py          # Base wallet, USDC transfers, request fee
├── services/
│   ├── __init__.py
│   ├── coingecko.py       # CoinGecko API client (prices, Base44 proxy + fallback)
│   ├── defi_signals.py    # DeFi signals (Base44-guided, ETH/ONDO/KAITO/DEGEN)
│   └── trading_agent.py   # Orchestrator: analysis → decisions → risk management
├── lib/
│   └── agents/
│       └── market_evaluator.js  # Market Demand & Auto-Evolution Agent (independent)
├── main.py                # CLI entry point (argparse)
├── requirements.txt
├── .env.example
└── README.md
```

### 5. Market Demand & Auto-Evolution Agent (`lib/agents/market_evaluator.js`)

**Independent Node.js module** for scanning market demand for x402 micro-services.
It does not change the base structure or the existing 8 agents — it runs separately.

- Scans CoinGecko Trending, DeFiLlama protocols, and GitHub x402 repositories
- On a new trend, sends a Telegram notification with inline buttons
  (✅ Approve / ❌ Reject)
- After approval, writes the trend to `market_state.json` for submission to the
  main agent

```bash
# Single cycle
node lib/agents/market_evaluator.js --once

# Continuous mode
node lib/agents/market_evaluator.js --loop
```

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token for notifications |
| `TELEGRAM_CHAT_ID` | — | Chat ID of the operator |
| `MARKET_SCAN_INTERVAL` | `600` | Interval between scans (seconds) |
| `MARKET_STATE_FILE` | `./market_state.json` | Path to the state file |

## Components

### 1. Base wallet (`blockchain/wallet.py`)

Class **`Wallet`** — a lightweight wrapper around web3.py for USDC payments on Base:

- USDC transfers (ERC-20 `transfer`)
- Balance checks (ETH and USDC)
- Request fee: from 0.003 USDC per request (per route: 0.003 / 0.005) on Base mainnet
- Non-blocking execution with bounded receipt wait
- Support for web3.py v6+ and v7+

```python
from blockchain.wallet import Wallet

wallet = Wallet.from_env()  # Reads WALLET_PRIVATE_KEY from .env
if wallet:
    usdc_bal = wallet.get_usdc_balance()
    fee_ok = wallet.pay_request_fee()  # Pays the fee from config.BASE_FEE_AMOUNT_USDC
```

**Important:** `BASE_FEE_RECEIVER` in `.env` must be a real address (not the zero
address), otherwise `pay_request_fee()` will skip the payment.

### 2. CoinGecko client (`services/coingecko.py`)

Class **`CoinGeckoClient`** — a resilient client with Base44 proxy + public fallback:

- Real-time prices for: ETH, ONDO, KAITO, DEGEN
- Base44 proxy if an API key is available (for higher rate limits)
- Automatic fallback to the public CoinGecko API
- Optional CoinGecko Demo/Pro API key

```python
from services.coingecko import CoinGeckoClient

client = CoinGeckoClient(api_key="your_base44_key")
prices = client.get_prices(["eth", "ondo", "kaito", "degen"])
eth_price = client.get_price("eth")
```

### 3. DeFi signals (`services/defi_signals.py`)

Class **`DeFiSignalGenerator`** — generates signals for 4 tokens:

| Token | Bias | Confidence | Action |
|-------|------|------------|--------|
| ETH | BULLISH | 0.78 | accumulate_on_dips |
| ONDO | BULLISH | 0.72 | hold_or_add |
| KAITO | NEUTRAL-BULLISH | 0.61 | monitor |
| DEGEN | SPECULATIVE | 0.45 | small_allocation_only |

The signals can be enriched with live data from the Base44 API if a key is available.

```python
from services.defi_signals import DeFiSignalGenerator

generator = DeFiSignalGenerator(api_key="your_base44_key")
signals = generator.generate_signals()
for token, signal in signals.items():
    print(f"{signal['symbol']}: {signal['bias']} (conf={signal['confidence']})")
```

### 4. Trading agent (`services/trading_agent.py`)

Class **`TradingAgent`** — orchestrates all components with **risk management**:

1. **Collects data** — prices from CoinGecko, signals from DeFiSignalGenerator
2. **Analyzes** — applies risk management filters
3. **Decides** — generates an action: buy / hold / monitor / avoid / recommend_*
4. **Logs** — full history with risk flags and portfolio status

**Risk Management parameters (from .env):**

| Parameter | Default | Description |
|---|---|---|
| `AGENT_AUTO_EXECUTE` | `false` | Automatic execution of transactions |
| `AGENT_MAX_POSITION_USD` | `1000` | Maximum size of a single position |
| `AGENT_MAX_EXPOSURE_USD` | `5000` | Maximum total exposure |
| `AGENT_MIN_APY` | `20` | Minimum APY for entering a yield position |
| `AGENT_MAX_RISK` | `60` | Maximum risk score (0-100) |
| `AGENT_MAX_GAS_GWEI` | `0.5` | Maximum gas price in Gwei |
| `AGENT_POLL_INTERVAL` | `300` | Interval between cycles (seconds) |

```python
from services.trading_agent import TradingAgent

agent = TradingAgent(coingecko_client=client, signals=signals)
decisions = agent.evaluate()
for token, d in decisions.items():
    print(f"{d['symbol']}: {d['action']} (approved={d['approved']}, pos=${d['suggested_position_usd']})")
```

## Installation

```bash
cd kristo-intelligence-v6
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your own values
```

## Usage

```bash
# Wallet and network status
python main.py --status

# Transfer fee estimate
python main.py --fees 0xRecipientAddress 0.01

# DeFi signals for Base
python main.py --signals

# Base token prices
python main.py --prices

# Single agent cycle
python main.py

# Continuous mode (Ctrl+C to stop)
python main.py --loop
```

## Configuration

See `.env.example` for all options. Key ones:

| Variable | Default | Description |
|---|---|---|
| `BASE44_API_KEY` | — | Base44 API key for enriched signals |
| `WALLET_PRIVATE_KEY` | — | Private key of the wallet |
| `BASE_RPC_URL` | `https://mainnet.base.org` | Base RPC endpoint |
| `BASE_CHAIN_ID` | `8453` | Base mainnet (8453) or Sepolia (84532) |
| `BASE_USDC_CONTRACT` | `0x833589fCD6...` | USDC contract on Base |
| `BASE_FEE_AMOUNT_USDC` | `0.005` | Base request fee in USDC (single source of truth; per-route prices live in `X402_PRICE_MAP`) |
| `BASE_FEE_RECEIVER` | `0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844` | Fee recipient address (active; the old operator address `0xd4cdA980…` is burned and must NOT be used) |
| `AGENT_AUTO_EXECUTE` | `false` | Automatic execution of transactions |
| `AGENT_MAX_POSITION_USD` | `1000` | Maximum size of a single position |
| `AGENT_MAX_EXPOSURE_USD` | `5000` | Maximum total exposure |
| `AGENT_MIN_APY` | `20` | Minimum APY for entering |
| `AGENT_MAX_RISK` | `60` | Maximum risk score (0-100) |
| `AGENT_POLL_INTERVAL` | `300` | Interval between cycles (seconds) |
| `AGENT_MAX_GAS_GWEI` | `0.5` | Maximum gas price in Gwei |
| `COINGECKO_API_KEY` | — | Optional CoinGecko API key |
| `OPENROUTER_API_KEY` | — | OpenRouter key for AI market bulletins |
| `GLM_API_BASE` | `https://openrouter.ai/api/v1` | OpenAI-compatible AI endpoint |
| `GLM_MODEL` | `openai/gpt-4o-mini` | AI model identifier |
| `ADMIN_API_TOKEN` | — | Token required in `X-Admin-Token` for CRM/admin routes |

## 🌍 Distribution in the x402 ecosystem

Kristo Intelligence is live in the x402 marketplaces: **x402scan** (11 resources,
0 errors), **PayAPI Market** (under review — v2-ready, settlement-verified),
**nohumans.directory** (3× VERIFIED), BlockRun data-source request submitted. All 4
paid endpoints and the discovery links are verified live and pass the mystery-agent
audit 23/23.

Full status and history: **[docs/DISTRIBUTION_STATUS.md](docs/DISTRIBUTION_STATUS.md)**
· Outreach plan: **[docs/OUTREACH_KIT.md](docs/OUTREACH_KIT.md)**

## ⚠️ Warning

This software executes **real transactions** on the Base network if
`AGENT_AUTO_EXECUTE=true`. Always test on the Base Sepolia testnet first.

The authors are not liable for financial losses.

## License

MIT
