# SALE DIAGNOSIS — първото външно плащане (06.09)

## ВЕРДИКТ: **C — LAUNCH SIGNAL. Първи външен платец.** 🎉

Едно плащане от **0.003 USDC** (точната цена на signal маршрута ни) в
**06:41 UTC на 06.09.2026** — от wallet, който НЕ е нито Chet, нито
известният sampler/crawler.

## 1. Мониторът: `python scripts/listing_monitor.py` изписа:

```
*** LAUNCH SIGNAL: external human/unknown payer detected ***
    external payers: 1  | payments: 1  | total 0.003 USDC
    0x4dB7AAFbe797a39Cd6Cc4E7aa64d970F7F6E02B7  1 txs, 0.003 USDC (avg 0.003)
```

Класификацията работи точно както е проектирана: Chet канарките
(`chet_payapi_verification`) и известните sampler/crawler wallet-и са
изключени → всичко останало = launch сигнал.

## 2. Точната транзакция (on-chain, 48h scan)

| Поле | Стойност |
|---|---|
| Сума | **0.003 USDC** (= цената на GET /api/v1/signal) |
| От | wallet, започващ `0x4dB7AAFb…E02B7` |
| Tx hash | `0xb881f9dcdd0df72bf1853ebbf3328cf8d140ae8966871136b6cbe0cf852d5fc3` |
| Блок | 50943758 |
| Време | **2026-09-06 06:41:03 UTC** |

Не е Chet (`0x7E6b…`), не е sampler `0xC59E…`, не е crawler `0x6777…`.

## 3. Fingerprint на платеца (30-дневен изходящ USDC scan)

| Метрика | Стойност | Таксономия |
|---|---|---|
| Различни получатели | **100** | ~23/седмица → под crawler (50), над loop (≤10) |
| Общо tx-ове | 145 | moderate cadence |
| Обща сума | 1.67 USDC | микро-диапазон |
| ENS | няма | анонимен |
| **PayAPI house каса** | **18 tx, $0.06** | източникът му ВКЛЮЧВА PayAPI листинги |

**Профил: умерен multi-API оператор** — агент, който плаща на ~100 x402
endpoint-а месечно, включително на house листингите на PayAPI. НЕ е
crawler-ът (145 tx/30д срещу 150–390/седмица при sampler-ите). И днес
**включи нас** в цикъла си — първото ни плащане от екосистемата.

## 4. Нашите логове (dashboard-stats, read-only)

- Продажбата е **записана и потвърдена** в `history` (status: confirmed,
  block 50943758, tx hash съвпада) — два записа за същия tx = известният
  козметичен double-record (settle+monitor), не две плащания
- Търсеният endpoint: **$0.003 = GET /api/v1/signal** (само той струва толкова)
- Днес (06.09): **107 requests, 2 sales записа ($0.006)**; вчера: 152 requests
- User-Agent breakdown: НЕ се експонира публично в dashboard-stats —
  логва се вътрешно (`_live_request_log`), но изисква admin достъп за преглед

## 5. Band проверка: все още unscored
`/agent/get` → reliability: score=null, band=unscored, computed_at=null.
Compute-ът на Chet не е пуснат за нас (title също не е сменен). Плащането
от 0x4dB7 е независимо от това.

## Какво следва според вердикта
**„Число" имейл към Chet** (граматиката на нишката — една линия, нула въпроси):

> Subject: first external payer
>
> Hi Chet — first external payer landed on our listing: 0.003 USDC via x402,
> signal route, settled on-chain this morning. Since you asked to know when
> the route gets used — this is that number.
>
> — Dimitri

Плюс: **наблюдавай 0x4dB7** — ако се върне (2-ро плащане), това е оператор
→	operator deal разговор ($0.01–0.05/call tier според NEW_OPERATOR_ANALYSIS).
Мониторът вече го класифицира автоматично.