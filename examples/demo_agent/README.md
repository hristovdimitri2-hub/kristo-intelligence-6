# Kristo Demo Agent — public reference x402 client

Демонстрира ПЪЛНИЯ път на платено извикване в 3 стъпки — това е цялата
интеграция: без signup, без API ключове, без библиотеки на нашата страна.

```
python examples/demo_agent/demo_agent.py                      # discovery + 402 challenge (safe, без wallet)
python examples/demo_agent/demo_agent.py --endpoint /api/v1/signal
python examples/demo_agent/demo_agent.py --pay                # РЕАЛНО плащане: DEMO_PRIVATE_KEY=funded test wallet
```

## Какво прави
1. **Discovery** — GET `/.well-known/x402` (free): всички платени ресурси
2. **Challenge** — GET платен endpoint → HTTP 402 с x402 v2 challenge
   (схема, мрежа, сума в атомни единици, payTo, описание)
3. **Pay & retry** — изпраща точната сума USDC на Base до `payTo`, чака
   майнингa, retry с `X-Payment-Proof: base64url(JSON({payer, transaction_hash, amount_usdc}))`
   → 200 с данните

## Защо е публичен
- **Доказателство:** всеки може да пусне клиента и да види работещо
  плащане от своя машина — trust през репродукция, не през обещания
- **E2E тест:** стъпка 3 с реален wallet е точно E2E self-paid тестът
- **Шаблон:** агент-билдъри копират `parse_challenge()` + proof header-а
  директно в своя код

⚠️ Никога не ползвай production private key. `--pay` е за funded test
wallet с микро-суми (0.003–0.01 USDC).

**Listing:** [Kristo Intelligence — DeFi Signals API on PayAPI Market](https://payapi.market/api/kristo-intelligence-defi-signals-api) — settlement-verified, $0.003/call, USDC on Base.
