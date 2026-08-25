# Kristo Intelligence v6

**Автоматизиран trading агент за Base DeFi екосистема**

Kristo Intelligence комбинира точно изчисляване на такси за Base мрежата (L2 на Coinbase), ценови данни от CoinGecko и DeFi сигнали за вземане на информирани търговски решения.

## Архитектура

```
kristo-intelligence-v6/
├── blockchain/
│   ├── __init__.py
│   └── wallet.py          # Base портфейл, USDC трансфери, такса за заявка
├── services/
│   ├── __init__.py
│   ├── coingecko.py       # CoinGecko API клиент (цени, Base44 proxy + fallback)
│   ├── defi_signals.py    # DeFi сигнали (Base44-guided, ETH/ONDO/KAITO/DEGEN)
│   └── trading_agent.py   # Оркестратор: анализ → решения → risk management
├── lib/
│   └── agents/
│       └── market_evaluator.js  # Market Demand & Auto-Evolution Agent (независим)
├── main.py                # CLI entry point (argparse)
├── requirements.txt
├── .env.example
└── README.md
```

### 5. Market Demand & Auto-Evolution Agent (`lib/agents/market_evaluator.js`)

**Независим Node.js модул** за сканиране на пазарното търсене на x402 микро-услуги.
Не променя базовата структура нито съществуващите 8 агента — стартира се отделно.

- Сканира CoinGecko Trending, DeFiLlama протоколи и GitHub x402 репозитории
- При нов тренд изпраща Telegram известие с inline бутони (✅ Approve / ❌ Reject)
- След одобрение записва тренда в `market_state.json` за подаване към основния агент

```bash
# Единичен цикъл
node lib/agents/market_evaluator.js --once

# Непрекъснат режим
node lib/agents/market_evaluator.js --loop
```

| Променлива | По подразбиране | Описание |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token за известия |
| `TELEGRAM_CHAT_ID` | — | Chat ID на оператора |
| `MARKET_SCAN_INTERVAL` | `600` | Интервал между сканиранията (секунди) |
| `MARKET_STATE_FILE` | `./market_state.json` | Път до state файл |

## Компоненти

### 1. Base портфейл (`blockchain/wallet.py`)

Клас **`Wallet`** — лек wrapper около web3.py за USDC плащания на Base:

- USDC трансфери (ERC-20 `transfer`)
- Баланс проверки (ETH и USDC)
- Такса за заявка: 0.10 USDC на Base mainnet
- Non-blocking изпълнение с bounded receipt wait
- Поддръжка на web3.py v6+ и v7+

```python
from blockchain.wallet import Wallet

wallet = Wallet.from_env()  # Чете WALLET_PRIVATE_KEY от .env
if wallet:
    usdc_bal = wallet.get_usdc_balance()
    fee_ok = wallet.pay_request_fee()  # Плаща 0.10 USDC такса
```

**Важно:** `BASE_FEE_RECEIVER` в `.env` трябва да е реален адрес (не zero address),
иначе `pay_request_fee()` ще прескача плащането.

### 2. CoinGecko клиент (`services/coingecko.py`)

Клас **`CoinGeckoClient`** — resilient клиент с Base44 proxy + public fallback:

- Цени в реално време за: ETH, ONDO, KAITO, DEGEN
- Base44 proxy ако е наличен API key (за по-високи rate limits)
- Автоматичен fallback към публичния CoinGecko API
- Опционален CoinGecko Demo/Pro API key

```python
from services.coingecko import CoinGeckoClient

client = CoinGeckoClient(api_key="your_base44_key")
prices = client.get_prices(["eth", "ondo", "kaito", "degen"])
eth_price = client.get_price("eth")
```

### 3. DeFi сигнали (`services/defi_signals.py`)

Клас **`DeFiSignalGenerator`** — генерира сигнали за 4 токена:

| Токен | Bias | Confidence | Action |
|-------|------|------------|--------|
| ETH | BULLISH | 0.78 | accumulate_on_dips |
| ONDO | BULLISH | 0.72 | hold_or_add |
| KAITO | NEUTRAL-BULLISH | 0.61 | monitor |
| DEGEN | SPECULATIVE | 0.45 | small_allocation_only |

Сигналите могат да бъдат обогатени с live данни от Base44 API, ако е наличен ключ.

```python
from services.defi_signals import DeFiSignalGenerator

generator = DeFiSignalGenerator(api_key="your_base44_key")
signals = generator.generate_signals()
for token, signal in signals.items():
    print(f"{signal['symbol']}: {signal['bias']} (conf={signal['confidence']})")
```

### 4. Trading агент (`services/trading_agent.py`)

Клас **`TradingAgent`** — оркестрира всички компоненти с **risk management**:

1. **Събира данни** — цени от CoinGecko, сигнали от DeFiSignalGenerator
2. **Анализира** — прилага risk management филтри
3. **Решава** — генерира action: buy / hold / monitor / avoid / recommend_*
4. **Логира** — пълна история с risk flags и portfolio статус

**Risk Management параметтери (от .env):**

| Параметър | По подразбиране | Описание |
|---|---|---|
| `AGENT_AUTO_EXECUTE` | `false` | Автоматично изпълнение на транзакции |
| `AGENT_MAX_POSITION_USD` | `1000` | Максимален размер на една позиция |
| `AGENT_MAX_EXPOSURE_USD` | `5000` | Максимална обща експозиция |
| `AGENT_MIN_APY` | `20` | Минимален APY за влизане в yield позиция |
| `AGENT_MAX_RISK` | `60` | Максимален риск score (0-100) |
| `AGENT_MAX_GAS_GWEI` | `0.5` | Максимален gas price в Gwei |
| `AGENT_POLL_INTERVAL` | `300` | Интервал между циклите (секунди) |

```python
from services.trading_agent import TradingAgent

agent = TradingAgent(coingecko_client=client, signals=signals)
decisions = agent.evaluate()
for token, d in decisions.items():
    print(f"{d['symbol']}: {d['action']} (approved={d['approved']}, pos=${d['suggested_position_usd']})")
```

## Инсталация

```bash
cd kristo-intelligence-v6
pip install -r requirements.txt
cp .env.example .env
# Редактирай .env с твоите стойности
```

## Използване

```bash
# Статус на портфейла и мрежата
python main.py --status

# Оценка на такси за трансфер
python main.py --fees 0xRecipientAddress 0.01

# DeFi сигнали за Base
python main.py --signals

# Цени на Base tokens
python main.py --prices

# Единичен цикъл на агента
python main.py

# Непрекъснат режим (Ctrl+C за спиране)
python main.py --loop
```

## Конфигурация

Виж `.env.example` за всички опции. Ключови:

| Променлива | По подразбиране | Описание |
|---|---|---|
| `BASE44_API_KEY` | — | Base44 API ключ за enriched сигнали |
| `WALLET_PRIVATE_KEY` | — | Private key на портфейла |
| `BASE_RPC_URL` | `https://mainnet.base.org` | Base RPC endpoint |
| `BASE_CHAIN_ID` | `8453` | Base mainnet (8453) или Sepolia (84532) |
| `BASE_USDC_CONTRACT` | `0x833589fCD6...` | USDC контракт на Base |
| `BASE_FEE_AMOUNT_USDC` | `0.10` | Такса за заявка в USDC |
| `BASE_FEE_RECEIVER` | `0xd4cdA980...` | Адрес на получател на таксата |
| `AGENT_AUTO_EXECUTE` | `false` | Автоматично изпълнение на транзакции |
| `AGENT_MAX_POSITION_USD` | `1000` | Максимален размер на една позиция |
| `AGENT_MAX_EXPOSURE_USD` | `5000` | Максимална обща експозиция |
| `AGENT_MIN_APY` | `20` | Минимален APY за влизане |
| `AGENT_MAX_RISK` | `60` | Максимален риск score (0-100) |
| `AGENT_POLL_INTERVAL` | `300` | Интервал между циклите (секунди) |
| `AGENT_MAX_GAS_GWEI` | `0.5` | Максимален gas price в Gwei |
| `COINGECKO_API_KEY` | — | Опционален CoinGecko API key |
| `OPENROUTER_API_KEY` | — | OpenRouter key for AI market bulletins |
| `GLM_API_BASE` | `https://openrouter.ai/api/v1` | OpenAI-compatible AI endpoint |
| `GLM_MODEL` | `openai/gpt-4o-mini` | AI model identifier |
| `ADMIN_API_TOKEN` | — | Token required in `X-Admin-Token` for CRM/admin routes |

## ⚠️ Предупреждение

Този софтуер изпълнява **реални транзакции** на Base мрежата, ако `AGENT_AUTO_EXECUTE=true`.
Винаги тествайте на Base Sepolia testnet първо.

Авторите не носят отговорност за финансови загуби.

## Лиценз

MIT