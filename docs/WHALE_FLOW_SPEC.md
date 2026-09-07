# WHALE FLOW — Спецификация-чернова (07.09, БЕЗ изпълнение)

Решение: **ОДОБРЕНО** от собственика (07.09) — записано в PROJECT_STATUS.md.
Този документ е черновата за преглед; строене започва само след изрично „давай".

## 1. Какво е

`GET /api/v1/whaleflow` — жива лента с големите USDC трансфери на Base
(китове), за агенти, които търгуват/следят потока на смарт-парите.
Терминът **whale е #1 от 1 в PayAPI** (празна ниша) — търсенето има, продукта
нямаше. Старият „WhaleFlow Radar" SKU беше демо витрина; това е реалната версия.

## 2. Източник (условие 1: съществуващата тръба, без нови системи)

- Сканер: **същият eth_getLogs механизмът от `competitor_recon` /
  dashboard_store.scan_window** — чете ERC-20 Transfer логове на USDC
  (0x8335…2913) на Base, **БЕЗ филтър по получател** (общ поток), chunked
  + paced, read-only публичен RPC.
- Филтър: `amount ≥ WHALEFLOW_MIN_USDC` (default **$50 000**, env-регулируем).
- Съхранение: **нова таблица в съществуващия `dashboard_state.db`**
  (`whaleflow_events`, dedup по tx+logIndex), синхронизирана от същия
  background scan цикъл (watermark модел — deploy-устойчив, като sales).
- Прозорец: rolling ~24–48 ч (env `WHALEFLOW_WINDOW_HOURS`), cap ~200 събития.

## 3. Формат на отговора (GET /api/v1/whaleflow)

```json
{
  "ok": true,
  "generated_at": "...",
  "window_hours": 24,
  "min_usdc": 50000,
  "events": [
    {
      "ts": "2026-09-07T14:03:11Z",
      "token": "USDC",
      "amount_usdc": 250000.0,
      "from": "0x…",
      "to": "0x…",
      "from_label": "exchange|wallet|unknown",   // виж §4
      "to_label": "wallet|unknown",
      "tx_hash": "0x…",
      "block_number": 51001234
    }
  ],
  "count": 42
}
```

## 4. Етикети (честни, без измислени данни)

- **known-set етикети:** известните ни адреси (chet_payapi_verification,
  market_sampler/crawler, нашия hot wallet/receiver) → „market_infra" /
  „kristo_internal".
- Всичко останало: **суров адрес, съкратен** (`0x1234…abcd`), label „unknown".
- ENS/Exchange tagging = БЪДЕЩА надградба (не в v1 — нулева измислица).

## 5. Цена

**$0.003** — като signal (нашата най-тествана цена; 5 успешни канарски
плащания на този tier). Алтернатива $0.005 (stats tier) — решава собственикът.
Препоръка: **$0.003**.

## 6. Какво му трябва за canary тест (условие 2)

1. Код: route + scan интеграция + таблица (1 сесия работа, ~30–60 мин).
2. `X402_PRICE_MAP["/api/v1/whaleflow"] = 0.003` (един ред) — чак тогава
   endpoint-ът става платим.
3. Тестове: формат/dedup/watermark/threshold (unit) + жив тест за свежест
   (най-новото събитие ≤ 15 мин стари).
4. Канарка: покана към Chet за paid canary (същият протокол като signal —
   той е платил 4 пъти досега; атрибутът „launch signal" се пази).
5. Едва СЛЕД успешна канарка → **чак тогава** влизане в x402 discovery /
   /api/v1/agents / dashboard „Реални маршрути" / манифест (условие 4).

## 7. Защити (непроменливи)

- payTo/съществуващите 5 маршрута — недокоснати.
- Без промяна по x402 логиката — новият route използва същия paywall.
- Не влиза в каталози/манифести преди canary-доказателство.
- Един нов продукт на вълна (условие 3) — след whale flow, следващ продукт
  чака ново решение.

## 8. Рискове / бележки

- Общ скан на USDC трансферите на Base е по-тежък от receiver-филтрирания —
  затова scan-ът е с watermark + cap и реже по threshold преди запис.
- RPC rate limits на public endpoint: същите chunk/pause настройки като
  competitor_recon (доказани в продукция).
- Ако eth_getLogs за общия поток се окаже прекалено тежък: fallback =
  по-кратък прозорец (6 ч) или по-висок праг ($100k) — решава се при строене,
  НЕ блокира дизайна.