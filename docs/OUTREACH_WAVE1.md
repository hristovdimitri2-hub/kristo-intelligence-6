# OUTREACH WAVE 1 — ЧЕРНОВИ (НЕ СЕ ИЗПРАЩАТ)

> ## ⛔ ИЗПРАЩАНЕ ЧАКА ДВЕ УСЛОВИЯ: (а) merge на #13219, (б) F1 гейт затворен.
> ## Без двете — не се праща.

**Статус към 25.09.2026 (проверено живо):**

| Условие | Състояние |
|---|---|
| (а) PR #13219 (punkpeye/awesome-mcp-servers) | ✗ **OPEN** — mergeable CLEAN, етикет `has-glama`, значката рендерира „rated A"; чака merge от Frank (последна активност 22.09) |
| (б) F1 гейт | ✗ **ОТВОРЕН (частично доказателство)** — **A1:** жив guard_events (PostgreSQL, 25.09 06:18 UTC): **никога** няма `c2_settlement_in_flight`/`c1_nonce_adopted` — пътят съществува в код+тестове, живо не е минаван. **A2:** частично доказан — 402 + retry механика живи отвън (`scripts/e2e_nopay_probe.py`: 6×402 идентични, синтетичен proof → 401 fail-closed). **ПЪЛНО доказателство (плащане → 425 → 200) ЧАКА WALLET** — зареждането е човешко действие, не решение. |

**Правила на пакета:** нищо от тук не е изпратено; всеки текст се изпраща ЕДИН път,
персонализиран; payTo/цените/стражите не се пипат. Всеки текст води с едно число
ИЛИ една методология — никога и с двете наведнъж.

**Проверени живи числа (25.09):** 6 платени маршрута от $0.003/call · challenge-и
общо ~27.6k (signal 12,351) · on-chain $0.043 / 13 tx / 2 external · Glama rated A ·
410/410 теста · C1 lock в PostgreSQL (durable, survive deploy) · C2 = 12 confirmations.

**Единственият curl, който трябва на всеки:**
`curl -i https://kristo-intelligence-api.onrender.com/api/v1/signal` → 402 с цялото
challenge тяло (amount, payTo, scheme) — нищо друго не се обяснява с думи.

---

## СЕГМЕНТ 1 — Coinbase AgentKit / CDP общности (4 бр.)

Кратки. ЕДНО число + един curl. Не разказваме история — показваме готова
интеграция, която техните агенти могат да платят още днес.

### 1.1 CDP Discord → #agentkit (или #build-on-base)

> Hey — built against AgentKit + the x402 facilitator: a live DeFi data API
> where the agent pays per call in USDC on Base, no API keys, no signup.
> The whole integration is one GET — the 402 body carries amount, payTo and
> scheme, so `pay()` + retry is the full surface:
> `curl -i https://kristo-intelligence-api.onrender.com/api/v1/signal`
> Routes from $0.003/call. Happy to share the server side if useful.

### 1.2 github.com/coinbase/agentkit → Discussions

**Тема:** `x402-paid data endpoint that AgentKit agents can call out of the box`

> We run an x402 v2 endpoint (canonical challenges, atomic units, eip155:8453)
> tuned for AgentKit-style agents: `GET /api/v1/signal` → 402 → settle via the
> Coinbase facilitator → retry with the proof header → 200 data.
> `curl -i https://kristo-intelligence-api.onrender.com/api/v1/signal`
> Nothing to register — if AgentKit ever gains a generic "pay and retry"
> action, this is the shape it would consume. Feedback welcome.

### 1.3 Base Discord → #developers

> x402 server on Base that any agent can pay for in one round trip — 402 body
> is self-contained (amount/payTo/scheme), settle, retry, data.
> `curl -i https://kristo-intelligence-api.onrender.com/api/v1/signal`
> 6 routes from $0.003, all on-chain settled. If anyone's building an
> agent-wallet loop, this is a cheap endpoint to test against.

### 1.4 Отговор в съществуващ x402/CDP thread (попълни линка)

> One more server for the list — DeFi signals on Base, x402 v2 canonical
> challenges, paid per call from $0.003:
> `curl -i https://kristo-intelligence-api.onrender.com/api/v1/signal`
> Every settlement is public, so the receipts speak for themselves.

---

## СЕГМЕНТ 2 — x402 продавачи (3 бр.)

Колегиален тон. Методологията се СПОДЕЛЯВА, не се продава — писали сме я, защото
самите ние се спънахме в нея четири пъти; ако им спести един бъг, печелят всички.
Нито един текст не иска нещо.

### 2.1 ParkerChet / PayAPI Market (познат канал)

> Chet — sharing, not selling: we turned our 402-guard field notes into a short
> doc (https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md).
> Four principles that survived production — durable replay lock, fail-closed
> confirmation depth, endpoint binding, chain-truth revenue — each exists
> because its absence once cost us a wrong number or a lost sale. If any of it
> is useful for how PayAPI validates sellers, it's yours. No ask attached.

### 2.2 Втори x402 продавач (от x402scan/Bazaar — попълни името)

**Тема:** `402 guard field notes — yours if useful`

> Hi [NAME] — fellow x402 seller here ([едно изречение: какво продаваш]). We
> audited our own guard four times and wrote down what actually held up:
> consume the proof once in a durable store BEFORE serving, refuse when depth
> can't be determined, bind proof→endpoint→payer, read revenue from the chain
> only.
> https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md
> Curious whether your stack hit the same four failure modes — always keen to
> compare notes with another live seller.

### 2.3 Трети x402 продавач / инфраструктурен проект (facilitator или index)

**Тема:** `Replay + depth failures we hit in production — writeup`

> Hey — we operate a paid 402 endpoint and documented the failure modes that
> survived four audits (bearer-token replay across deploys, unbound proofs,
> depth-unchecked receipts, dashboards counting memory instead of chain).
> Full writeup, no product pitch:
> https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md
> If any of it matches what you see from other servers, we'd love the
> correction — the doc is field notes, not a spec.

---

## СЕГМЕНТ 3 — AI билдъри (3 бр.) — METHODOLOGY-LED

**Правило на сегмента:** „Какво научихме, докато строихме x402 payment guard".
Техническото съдържание води. **Числата остават в линка, не в съобщението** —
нито едно price/revenue число в телата по-долу.

### 3.1 Reddit r/AI_Agents

**Заглавие:** `We built an x402 payment guard for our API and audited it 4 times — here is what actually broke`

> Every "agent pays for data" demo assumes the seller can tell that the money
> is real, exactly once, for exactly this request. Ours couldn't, four
> different ways:
>
> 1. A settlement hash is a bearer token — and our in-process set of "seen
>    hashes" died with every deploy, re-opening every consumed proof.
> 2. A proof wasn't bound to anything — the same payment could unlock a
>    different, more expensive route.
> 3. We checked the receipt but not its depth — a payment at the chain tip
>    can be reorganised away after the data is already served.
> 4. The dashboard counted memory, not the chain — a deploy zeroed revenue
>    and we couldn't tell "nobody paid" from "I forgot".
>
> Each fix is enforced by code, not policy: one atomic durable insert before
> serving, refuse when depth is indeterminate, bind proof→endpoint→payer,
> read revenue from the chain only. Full field notes (corrections welcome):
> https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md

### 3.2 Hacker News — Show HN

**Заглавие:** `Show HN: Field notes from running a paid 402 endpoint in production`

> We've been selling API calls to AI agents and wrote down the seller-side
> half of the handshake — "was I really paid, and can I prove it?" — because
> that assumption failed on us four independent times.
>
> The principles that survived: consume the proof once, durably, *before*
> answering; fail closed when confirmation depth can't be determined; bind
> the proof to endpoint and payer; treat the chain as the only revenue
> source and everything else as a cache with a TTL. There's also a section
> on honest emptiness versus invented completeness — an empty result
> rendered as a confident zero is how a dashboard starts lying.
>
> It's field notes from four audit cycles against one live endpoint, not a
> spec: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md
> Curious what other people running pay-per-call endpoints got wrong that
> we haven't found yet.

### 3.3 Reddit r/AI_Agents (втори пост — по-тесен, deployment-фокус)

**Заглавие:** `A payment-replay lock that doesn't survive a deploy is a rate limiter with a misleading name`

> We kept a set of consumed payment hashes in process memory. It worked
> perfectly until the first deploy — after which every previously consumed
> proof was live again and the same payment could unlock a second call. The
> failure is invisible in normal operation and shows up exactly when a
> customer is least likely to be honest.
>
> Fix that held: the claim and the check are the same operation — a single
> insert whose uniqueness constraint is the lock — written to a durable
> store, before the paid response is produced. Details (plus the three
> failure modes we found next):
> https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/GUARD_METHODOLOGY.md

---

## Преди изпращане (чеклист — попълва се, когато гейтът е затворен)

- [ ] (а) #13219 е MERGED
- [ ] (б) F1 гейт: ПЪЛНО доказателство — реално плащане ($0.003) + уловен 425
      + 200, след което guard_events показва ново `c2_settlement_in_flight` /
      `c1_nonce_adopted`. Сега: A1 + A2 (no-pay) са готови, **последната стъпка
      чака funded wallet** (човешко зареждане — не „чака решение“)
- [ ] Всеки текст е персонализиран (име/проект на получателя)
- [ ] 1 съобщение/ден — сегментите не се пускат наведнъж
