# PayAPI Agent marketplace — готов листинг за `/api/v1/verify-seller`

**Защо точно този маршрут.** PayAPI има две места: **API каталог** (едно обаждане —
lookup, feed) и **Agent marketplace** (агент, който върши цяла работа, на цена за
работа). `/api/v1/verify-seller` е единственият ни маршрут, който е **задача**, не
данни: одитира продавач по веригата и връща присъда. Останалите ни маршрути вече
са в API каталога.

**Състояние (14.11.2026):** в API каталога сме с `endpoints_count: 11`,
`payment_verified: true`, 3 верифицирани маршрута. В Agent marketplace **още не
сме** — той иска вход с имейл, който агентът не може да осъществи (виж стъпките).

## Стъпките (само ти можеш)

1. Отвори <https://payapi.market/agent-marketplace/list>
2. Въведи `hristovdimitri2@gmail.com` — **същият имейл**, с който сме в API
   каталога (иначе се създава втори provider акаунт).
3. PayAPI праща **линк за вход** на този адрес. Отвори го.
4. В таблото добави агента с полетата по-долу. Един агент е включен в безплатния
   план.

## Полетата

```json
{
  "name": "Kristo Seller Audit — verify an x402 seller before you pay",
  "task": "Audit an x402 seller's on-chain payment history and return a verdict before an agent pays it.",
  "category": "Verification",
  "tags": ["x402", "seller audit", "trust", "on-chain", "base", "usdc", "payTo"],
  "description": "Give a Base receiver address and get an evidence-based verdict on whether it actually sells. The route reads incoming USDC transfers to that exact address on Base and returns distinct external payers, repeat payers, average check size, total volume, and how much of the volume is treasury/exchange flow rather than per-call payments. It separates known reviewer and verification addresses so they cannot inflate the customer count, and it reports coverage honestly: when the block scan is incomplete the verdict says the figures are a floor rather than a zero. It counts distinct paying addresses, and says so: one operator can pay from several wallets and several agents can share one. No signup, no API key, x402 on Base.",
  "paid_route_url": "https://kristo-intelligence-api.onrender.com/api/v1/verify-seller",
  "paid_route_method": "GET",
  "sample_url": "https://kristo-intelligence-api.onrender.com/api/v1/verify-seller/sample",
  "price_usdc": 0.01,
  "price_unit": "per_job",
  "networks": ["base"],
  "payment_flow": "authorization",
  "settles_before_running": true,
  "typical_latency_seconds": 3,
  "max_latency_seconds": 30,
  "underlying_model": null,
  "example_input": "receiver=0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f&days=7",
  "input_schema": {
    "type": "object",
    "required": ["receiver"],
    "properties": {
      "receiver": {
        "type": "string",
        "description": "Base address to audit (0x + 40 hex). Required.",
        "pattern": "^0x[0-9a-fA-F]{40}$"
      },
      "days": {
        "type": "integer",
        "minimum": 1,
        "maximum": 30,
        "default": 7,
        "description": "Window in days. Optional."
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "ok": {"type": "boolean"},
      "coverage": {
        "type": "object",
        "description": "complete=false means the figures are a floor, not a zero.",
        "properties": {
          "complete": {"type": "boolean"},
          "failed_ranges": {"type": "integer"},
          "lookback_days": {"type": "integer"},
          "scanned_blocks": {"type": "integer"},
          "split_retries": {"type": "integer"}
        }
      },
      "payer_analysis": {
        "type": "object",
        "properties": {
          "external_unique_payers": {"type": "integer"},
          "repeat_payers": {"type": "integer"},
          "total_txs": {"type": "integer"},
          "total_usd": {"type": "number"},
          "avg_check_usdc": {"type": "number"},
          "known_verification_txs": {"type": "integer"},
          "noise": {
            "type": "object",
            "properties": {
              "large_tx_count": {"type": "integer"},
              "large_txs": {"type": "number"}
            }
          }
        }
      },
      "notes": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

## Две неща, които да не се забравят

**Цената.** Полетата казват `0.01`, защото това е **пилотната** цена в момента.
На **11.12.2026** пилотът изтича и цената се връща на **0.10** (напомняне
`schedule-39d6abaf`). Ако листингът се направи след тази дата, `price_usdc` трябва
да е `0.10` — иначе листингът лъже за цената, което е точно дефектът, който
затваряхме при `config.py`.

**Верификацията.** `verification_state` се попълва от PayAPI, не от нас — те
верифицират, като платят маршрута. Не обещавай verified в описанието.

## Какво листването не прави (тяхното собствено предупреждение)

> It doesn't guarantee jobs. A listing is a place to be found, not demand.

Тоест това е разпространение, не търсене. Съответства на находката от
`df-data-agent`: ограничението ни е видимост, не цена.
