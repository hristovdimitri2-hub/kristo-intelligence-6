# INDEX — къде е всичко

**За кого е това:** за всеки, който трябва да работи по този проект — нов агент,
външен одитор, или човек, който се връща след месец. Прочети това, преди да
търсиш файлове.

**Последна промяна:** 16.11.2026.

---

## 0. Прочети това първо, ако си външен одитор

**Провери, че четеш ЖИВОТО копие, преди да съдиш каквото и да е.**

Три независими одита досега са били направени върху **остарели копия** — едно
GitLab огледало, което спира на `HANDOVER.md` §39, и един файл `HANDOVER.md.` (с
точка) в корена, който спира на §57. И трите пъти повече от половината находки
описваха репозитория, който вече не съществува.

Живото копие:

```
https://github.com/hristovdimitri2-hub/kristo-intelligence-6     (публично)
https://raw.githubusercontent.com/hristovdimitri2-hub/kristo-intelligence-6/main/HANDOVER.md
https://raw.githubusercontent.com/hristovdimitri2-hub/kristo-intelligence-6/main/docs/INDEX.md
```

**Как да разбереш, че копието е старо:**
- `HANDOVER.md` трябва да е **над 4 300 реда** и да стига до **§66**.
- Ако стига до §39 или §57 — копието е старо, недей да съдиш по него.
- Ако видиш файл `HANDOVER.md.` (с точка) — това е ръчно копие през уеб
  редактора, не е версия. Живото репо не го съдържа.

---

## 1. Живата система

| | |
|---|---|
| **Продукция** | `https://kristo-intelligence-api.onrender.com` |
| **Репозиторий** | `https://github.com/hristovdimitri2-hub/kristo-intelligence-6` (публичен) |
| **Хостинг** | Render, един web service, **един worker** (`--workers=1 --threads=8`) |
| **Мрежа** | Base mainnet (`eip155:8453`), USDC |
| **Протокол** | x402 v2 — `PAYMENT-REQUIRED` хедър + копие в тялото |
| **Получател** | `0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844` (сменен 16.11.2026) |
| **Газ портфейл** | извежда се от `WALLET_PRIVATE_KEY`, не е константа в кода |

Платени маршрути (8): `/api/v1/signal`, `/api/v1/whaleflow`,
`/api/arb/opportunities`, `/api/bot-status`, `/api/sales`, `/api/stats`,
`/api/v1/verify-seller`, `/api/v1/seller-check`.

---

## 2. Къде да започнеш

| ако искаш | чети |
|---|---|
| **какво е проектът** | `README.md` (английски), `README.bg.md` (български) |
| **цялата история и решения** | **`HANDOVER.md`** — хронологичен запис, 4300+ реда |
| **какво е отворено СЕГА** | **`HANDOVER.md` §62** — единственият жив списък |
| **задачи за външен одитор** | `docs/AUDIT_BRIEF.md` |
| **как работи платежният гейт** | `docs/GUARD_METHODOLOGY.md` |
| **къде сме листнати** | `docs/DISTRIBUTION_STATUS.md` |
| **как се разгръща** | `DEPLOYMENT.md`, `DEPLOYMENT_CHECKLIST.md` |

---

## 3. Документацията по предназначение

### Записът (хронология и контекст)

| файл | редове | какво е |
|---|---|---|
| `HANDOVER.md` | 4381 | **Основният документ.** Хронологичен запис от 09.11 насам, §1–§66. Всяка секция е датирана и казва дали е измерване или извод |
| `docs/PROJECT_CHRONOLOGY.md` | 264 | Пълна хронология от замразяването на 27.08 |
| `docs/CONTEXT_AND_ROADMAP.md` | 488 | Контекст и път напред |
| `docs/ACTION_BOARD.md` | 395 | Дъска със задачи, включително неадресирани (F-находки) |
| `docs/weekly/2026-09-29.md` | 71 | Седмичен протокол |

### Отворената работа

| файл | редове | какво е |
|---|---|---|
| `HANDOVER.md` §62 | — | **Живият списък с отвореното** — чака собственика / външни / вътрешни |
| `docs/AUDIT_BRIEF.md` | 277 | Бриф с 21 задачи за външен одитор |
| `TASK.md` | 63 | Входен брифинг |
| `docs/WATCH_LIST.md` | 12 | Активни за следене |

### Одити (външни и вътрешни)

| файл | редове | какво е |
|---|---|---|
| `docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md` | 573 | Най-големият одит — производителност и архитектура |
| `docs/HAIKU_AUDIT.md`, `docs/HAIKU_AUDIT_DEEP.md` | 126, 113 | Два одита от външен модел |
| `docs/PRODUCT_AUDIT.md` | 137 | Продукт и конкурент |
| `docs/DASHBOARD_AUDIT.md` | 165 | Таблото, източници, NEXUS |
| `docs/LISTING_CHANNELS_AUDIT.md` | 164 | Канали за листинг |
| `docs/TRAFFIC_AUDIT.md` | 80 | Кой ни гледа |
| `docs/MYSTERY_AGENT_REPORT.md` | 70 | Симулация на враждебен купувач (23/23) |

### Платежният път

| файл | редове | какво е |
|---|---|---|
| `docs/GUARD_METHODOLOGY.md` | 204 | **Полеви бележки от работа с 402 в продукция** — C1/C2/H2 гейтовете |
| `docs/VERIFIER_RESEARCH.md` | 110 | Проучване на проверяващия слой |
| `docs/WHALE_FLOW_SPEC.md` | 92 | Спецификация на whale flow |
| `docs/SALE_DIAGNOSIS.md` | 76 | Първото външно плащане |
| `docs/ORGANISM.md` | 164 | Как платформата се наблюдава сама |

### Листинги и разпространение

| файл | редове | какво е |
|---|---|---|
| `docs/DISTRIBUTION_STATUS.md` | 73 | Къде сме листнати и в какво състояние |
| `docs/PAYAPI_AGENT_LISTING.md` | 116 | Листингът в PayAPI agent marketplace |
| `docs/MCP_REGISTRATION_PACKET.md` | 116 | Регистрационен пакет за MCP каталози |
| `docs/MCP_ACCOUNTS_GUIDE.md` | 71 | Инструкция за регистрации (на български, без жаргон) |
| `docs/PULSEMCP_SUBMISSION_READY.md` | 107 | Готово за подаване |
| `docs/SCAN_LISTING_DRAFT.md`, `docs/SCAN_LISTING_EN.md` | 156, 45 | Чернови за x402scan |
| `docs/BAZAAR_RESEARCH.md` | 126 | Проучване на Bazaar и discovery |
| `REGISTRATION_CHECKLIST.md` | 177 | Чеклист за регистрации |

### Архитектура и разгръщане

| файл | редове | какво е |
|---|---|---|
| `docs/ARCHITECTURE.md` | 552 | Архитектура на продукцията (от v5) |
| `DEPLOYMENT.md` | 372 | Ръководство за разгръщане |
| `DEPLOYMENT_CHECKLIST.md` | 343 | Чеклист |
| `PRODUCTION_DEPLOYMENT_REPORT.md` | 143 | Отчет от разгръщането |
| `ops/production_readiness_checklist.md` | 41 | Готовност за продукция |
| `docs/QUICK_START.md` | 402 | Бърз старт (от v5) |
| `docs/TEST_REPORT_2026-08-17.md` | 241 | Тестов отчет (от v5) |

### Маркетинг и outreach

| файл | редове | какво е |
|---|---|---|
| `docs/VISIBILITY_MEASURED.bg.md` | 1345 | **Измерена видимост** — най-подробният маркетинг документ |
| `docs/VISIBILITY_AND_TRAFFIC_STRATEGY.md` | 457 | Стратегия |
| `docs/DISCOVERY_AND_TRAFFIC_PLAN.md` | 300 | План за discovery и трафик |
| `docs/OUTREACH_KIT.md` | 165 | Инструменти за връзка с екосистемата |
| `docs/OUTREACH_WAVE1.md` | 185 | **Чернови — НЕ СЕ ИЗПРАЩАТ** |
| `docs/CHET_WHALE_CANARY.md` | 54 | Чернова до Чет (PayAPI) — **не се изпраща както е, виж бележката в него** |
| `docs/CHET_DATA_PACKAGE.md` | 61 | Данни, изпратени на Чет |
| `docs/GLAMA_REPLY.md`, `docs/LOOPEMAIL_PACKAGE.md` | 51, 72 | Отговори към рецензенти |
| `docs/MARKET_WRITEUP.md` | 140 | Публичен анализ на пазара |
| `docs/MARKETING_KIT.md`, `docs/CONTENT_PACK_1.md` | 139, 180 | Маркетинг материали |
| `marketing/offer-and-ad-strategy.md`, `launch/` | — | Оферта и план за пускане |
| `docs/blog/2026-10-23-x401-x402-one-gate.md` | 79 | Публична публикация |

### Отчети (датирани, на български)

`docs/REPORT_2026-11-04_WORK.bg.md` (214) · `docs/REPORT_2026-11-04_DISTRIBUTION.bg.md` (206) ·
`docs/REPORT_2026-11-07_ORGANISM.bg.md` (198) · `docs/REPORT_2026-11-08_ORGANISM_LIVE.bg.md` (127) ·
`docs/REPORT_DVA_DNI_2026-11-08.bg.md` (209)

### Радар и разузнаване

`docs/AP2_RADAR.md` (366) · `docs/RECON_FINDINGS.md` (212) · `docs/PAYER_ORIGIN.md` (59) ·
`docs/NEW_PAYER_09b2.md` (85) · `docs/NEW_OPERATOR_ANALYSIS.md` (41)

---

## 4. Карта на кода

| файл | редове | какво е |
|---|---|---|
| `main.py` | ~9 700 | **Монолитът.** Платежен рейл, 402-ката, гейтовете, organism, таблото |
| `config.py` | 171 | Единствен източник за цени, получател, мрежа. Нормализира EIP-55 |
| `services/connectors.py` | ~1 550 | Фасилитаторската верига, self-broadcast, CDP JWT |
| `services/verifier.py` | 312 | Кръстосана проверка на цени (CoinGecko × DexScreener) |
| `integrations/dashboard_store.py` | ~4 400 | Postgres: ledger, гейт събития, продажби |
| `app/blueprints/discovery.py` | ~4 050 | Публични манифести: `/.well-known/x402`, OpenAPI, llms.txt |
| `redaction.py` | 74 | `redact_rpc` — маскира ключове и пароли в изключения |
| `tests/` | 1 415 теста | `python -m pytest tests -q` (~7 мин) |

**Правило за редакция:** всяко изключение, което може да стигне до публична
повърхност, минава през `redact_rpc()`. Нарушаването на това правило е било
най-повтарящият се дефект в проекта.

---

## 5. Какво НЕ е в репозитория

| какво | къде е | защо |
|---|---|---|
| `secrets/` | на машината на собственика, gitignore-нат | ключове: `gas_wallet_key.txt`, `receiver_key.txt`, `demo_private_key.txt`, `render_api_key.txt`, `cdp_api_key.json` |
| `_forensics/` | `C:\Users\AlienWare\.dsh\state\superagent\_forensics\` | ~40 диагностични скрипта. **Нова сесия не може да ги пусне, докато не ги намери там** |
| `.env` | машината | реални стойности; `.env.example` е в репото |
| Render env | Render dashboard | 40 променливи; виждат се с `secrets/render_api_key.txt` |

**Следствие за одитор:** твърдения от рода на „този адрес го няма в репото" не
доказват нищо за продукцията. Газовият портфейл например **не е** константа в
кода — извежда се от `WALLET_PRIVATE_KEY` при старт. Липсата му в репото е
правилното състояние, не пропуск.

---

## 6. Капаните, които вече са ни стрували

Четири класа дефекти се повтарят. Всеки е вписан в `HANDOVER.md` с дата.

1. **Нещо не може да бъде погледнато и повърхността го показва като погледнато и
   празно.** Празен панел, който изглежда като нула. `delivered_at IS NULL`,
   което изглеждаше като „купувачът не получи нищо", а значеше „още нямаше
   печат" (§55). Ако намериш такова място — то е по-важно от всеки срив.
2. **Документът се води за факт, след като е остарял.** Затова всяка секция в
   `HANDOVER.md` е датирана и казва измерване или извод.
3. **Изключение стига до публична повърхност без редакция.** Девет места в
   `services/connectors.py`, поправени на 16.11 (§66).
4. **Чакане, което отказва вместо да изчака.** Гейтът отказваше плащане за
   изчакване, което вече почти беше свършило (§66).

---

## 7. Ако търсиш нещо и не го намираш

Питай в този ред:

1. `HANDOVER.md` §62 — дали е в списъка с отвореното
2. `grep -rn "термин" .` в репото
3. `docs/ACTION_BOARD.md` — дали е записано като неадресирано
4. `_forensics/` на машината на собственика — там живеят еднократните диагностики
