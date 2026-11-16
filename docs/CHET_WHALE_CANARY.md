# CHET WHALE CANARY — имейл за копи-пейст (09.09)

**Кога се праща:** след като лентата покаже първия реален whale запис
(проверка: `GET /api/v1/whaleflow` с платено извикване) ИЛИ веднага с
„populating now" реда, ако собственикът реши да не чака.
**Кой праща:** собственикът (Димитри). Агентът НЕ изпраща нищо.

---

Subject: new route to verify — whale flow

Hi Chet,

We've built a new paid route and would like it canary-verified the same
way you verified the first four: GET /api/v1/whaleflow — live USDC whale
transfers on Base, $0.003 per call.

Live whale line: populating now, live within hours.

Two small things:

1. If you can run the paid canary when convenient, it would close the
   loop on our side and the route goes into discovery right after.

2. Separately — could you drop ~$0.05 USDC (plus a little gas) to our
   test wallet? We run external self-paid tests and our hot wallet is empty.
   If that's not something you can do, no problem at all — we'll top it up
   ourselves.

> **НЕ ИЗПРАЩАЙ ТОЗИ ТЕКСТ КАТОТО Е (поправено 16.11.2026).** Тук стоеше
> `0x9c1eb97e121a6836200C539a1BF0ecdC37F750dd`, а това е газовият портфейл,
> чийто ключ е записан като **изгорен/публикуван** още на 27.08 FREEZE
> (`docs/PROJECT_CHRONOLOGY.md`, `docs/CONTEXT_AND_ROADMAP.md`). Да помолиш
> трета страна да прати пари там значи да я подканиш да ги подари на всеки,
> който е прочел ключа. Адресът е махнат. Преди изпращане сложи адрес, чийто
> ключ държим — газовият се извежда от `WALLET_PRIVATE_KEY` и се проверява с
> `_forensics/does_self_broadcast_have_gas.py`. За щастие имейлът така и не е
> бил пратен, а адресът никога не е получавал нищо (ETH 0, USDC 0, nonce 0).

— Dimitri

---

## Правила (същите като GLAMA_REPLY)
- Нула пълни клиентски/операторски wallet адреси в имейла (размер/токен/време — да).
- Нула оплаквания; молбата за $0.05 е с вграден изход („no problem at all").
- Изпраща се САМО след жива проверка на 402 (направена: amount 3000, v2,
  description присъства, payTo непокоснат — виж доклада от 11.09).

## Статус към 11.09
- Hot wallet: `0x9c1eb97e121a6836200C539a1BF0ecdC37F750dd` — ETH 0, USDC 0.
- Whale лента: **празна, catch-up тече** (watermark 51186249, drpc free pace).
  Прогноза: жива лента в рамките на часове до един ден.
- 402 пулс: ✅ верен challenge ($0.003, v2, selling description, payTo).