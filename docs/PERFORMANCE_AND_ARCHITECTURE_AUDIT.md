# PERFORMANCE & ARCHITECTURE AUDIT — kristo-intelligence-6

**Дата:** 2026-11-03 · **Клон:** `main` · **HEAD по време на одита:** `66a0ce4` (2026-11-02, "step2: echo extensions + resource in x402 payment payload")
**Локален корен:** `C:\Users\AlienWare\Desktop\projects\kristo-intelligence-6`
**Отдалечено:** `https://github.com/hristovdimitri2-hub/kristo-intelligence-6` (origin, main)
**Обхват:** 345 `.py` файла (без `venv/`), 5859 реда `main.py`, 44 `@app.route` + 26 blueprint рута, 89 файла в `docs/`, 55 файла в `tests/`.

> **Какво НЕ е пипано:** одитът е **само за четене**. Не е променен нито един файл по кода, x402 хедърите, ценообразуването, `payTo`/комисионната или защитените конфигурации. `secrets\` и `.env` **не са отваряни** (само `.env.example`). Няма `git add/commit/push`. Единственият записан файл е този отчет.
> **Защо това е важно:** `main` → авто-деплой на Render. Всяка препоръка по-долу е **предложение**, не извършена промяна; прилага се през отделна врата.

---

## 0. Индекс на констатациите (по приоритет)

| ID | Сев. | Констатация | Доказателство |
|---|---|---|---|
| **F-01** | 🔴 Critical | Платените продукти се раздават безплатно през `/api/dashboard-stats` и `/api/dashboard/data` | `main.py:142-157, 3427-3428, 3986-3989, 5573-5582` |
| **F-02** | 🔴 Critical | `accepted.amount` (от клиента) замества подписаната `authorization.value` → underpayment | `services/connectors.py:195-200` |
| **F-03** | 🔴 Critical | При нечетим receipt платеното обаждане се доставя (fail-open) | `main.py:3082-3110, 3132, 3158-3159` |
| **F-04** | 🔴 Critical | Безплатен GET прави 4 ЗАПИСА в таблицата на replay-заключването (`payment_guards`) | `integrations/dashboard_store.py:1542-1555` |
| **F-05** | 🟠 High | Реорг никога не отменя кредитирано плащане | `main.py:2631-2690` |
| **F-06** | 🟠 High | Приемане на сетълмент по nonce **без** проверка за дълбочина | `main.py:2321-2435` |
| **F-07** | 🟠 High | Нула rate limit по платежния път; gas-разход, контролиран от анонимен клиент | `main.py:1406-1416, 3431-3523` |
| **F-08** | 🟠 High | Един RPC доставчик, без fallback и без cooldown при 429 | `config.py:57` |
| **F-09** | 🟠 High | Една споделена DB връзка под глобален lock, отваряна без `connect_timeout` | `integrations/dashboard_store.py:307, 334-340, 342-372` |
| **F-10** | 🟠 High | `/health` зависи от DB и връща 503 → рестарт на единствения worker → цикъл | `app/blueprints/discovery.py:32-76` |
| **F-11** | 🟠 High | `/mcp/sse` (безплатен, неограничен) пинира 1 от 8 нишки за ≥15 s → пълен DoS | `app/blueprints/discovery.py:665-717` |
| **F-12** | 🟠 High | Неограничен thread-per-payment reorg watch + нечанкнат `eth_getLogs(5000 блока)` | `main.py:3217, 2321-2435, 2621-2628` |
| **F-13** | 🟠 High | Суровият RPC текст (`rpc_error`) се публикува на безплатен рут | `main.py:643 → 3792 → 3986` |
| **F-14** | 🟠 High | Telegram bot token може да изтече в логовете през `requests` изключения | `services/telegram_sales.py:72, 80-81, 198-212` |
| **F-15** | 🟠 High | `secrets/` се bake-ва в Docker образа (`.dockerignore` няма запис) | `Dockerfile:29`, `.dockerignore:47-50` |
| **F-16** | 🟡 Medium | X-Payment-Proof е препредаваем bearer токен върху публично публикувани данни | `main.py:2879-2900` |
| **F-17** | 🟡 Medium | Едно плащане може да достави два пъти при конкурентност | `main.py:2438-2470` |
| **F-18** | 🟡 Medium | `payment.amount_usdc` връща атомарни единици под име на USDC (5000 вместо 0.005) | `main.py:1723-1733` |
| **F-19** | 🟡 Medium | Рекламираните цени дрейфват от 402 предизвикателството в 5+ повърхности | `discovery.py:866-892, 1057, 1276, 1454, 1528` |
| **F-20** | 🟡 Medium | „$29 VIP — неограничен достъп" не е имплементиран никъде | `discovery.py:873-881` |
| **F-21** | 🟡 Medium | `FREE_TIER_LIMIT` по подразбиране е 1; продукцията разчита на env | `main.py:129-134` |
| **F-22** | 🟡 Medium | Статистическият агрегат: 12 заявки, 5 пълни сканирания, ~528 ms локално / ~41 s в продукция, без кеш на 2 от 3 рута | `main.py:3944-3945, 4067-4071, 5573-5582` |
| **F-23** | 🟡 Medium | Бюджети за блокиране по платения път > gunicorn `--timeout 120` (един worker!) | `main.py:2596-2598, 3082-3096`, `connectors.py:390-410` |
| **F-24** | 🟡 Medium | Stripe SDK без timeout: 80 s × 3 опита ≈ 4 min по checkout пътя + неограничена пагинация | `stripe/_http_client.py:512`, `stripe/__init__.py:39` |
| **F-25** | 🟡 Medium | `_stripe_payment_snapshot_loop` е единственият цикъл без `try/except` → тихо умира | `main.py:1113-1121` |
| **F-26** | 🟡 Medium | `/api/launch/health` без auth: брой лийдове, платени клиенти, Stripe режим | `main.py:5198-5216` |
| **F-27** | 🟡 Medium | `/api/connectors` разкрива hot wallet и вътрешния settlement маршрут | `services/connectors.py:944-947, 988` |
| **F-28** | 🟡 Medium | Render конфигурацията не е версионирана (няма `render.yaml`); брой workers е security-значим | `Procfile:1`, `Dockerfile:46` |
| **F-29** | 🟡 Medium | Админ токенът пада обратно към `SESSION_SECRET` (няма разделяне на ключове) | `main.py:178, 1802-1813` |
| **F-30** | 🟡 Medium | `_t2_render_env_check.py` принтира живи env стойности (RPC ключ, ADMIN токен) | `scripts/_t2_render_env_check.py:30-45` |
| **F-31** | 🟡 Medium | Неограничени in-RAM карти + липса на индекси по `user_agent`/`source`/`funnel` | `main.py:1319, 1345, 2260`, `dashboard_store.py:659-733` |
| **F-32** | 🟢 Low/Med | Ръчно поддържан guard списък без тест за покритие | `main.py:137-139` |
| **F-33** | 🟢 Low | `/validation` публикува живи платени адреси и остаряло „550/550" | `discovery.py:179-203` |
| **F-34** | 🟢 Low | Мъртви/остарели цени: `KRISTO_WHALE_PRICE=0.01`, `KRISTO_RUG_PRICE` извън картата | `config.py:78-79` |
| **F-35** | 🟢 Low | `requirements.lock` не възпроизвежда `requirements.txt` (`cryptography` липсва, без `--hash`) | `requirements.txt:33`, `requirements.lock` |
| **F-36** | 🟢 Low | `docker-compose.yml` публикува Postgres с подразбираща се парола | `docker-compose.yml:27, 31-32` |
| **F-37** | 🟢 Low | Обемната отстъпка е no-op (твърдолитерална цена в монолит) | `main.py:83, 1476-1478` |
| **F-38** | 🟢 Low | Времева зона: Sentinel седмичен отчет ползва локално време, всичко друго е UTC | `services/sentinel.py:464-467` |
| **F-39** | 🟢 Low | Мониторът на блокове не персистира курсора си → пропуска трансфери при рестарт | `main.py:714-716, 774` |
| **F-40** | 🟢 Low | Дубликат на цялото репо в `.kilo/worktrees/believed-dancer` (~2× диск, риск от „редакция на грешния файл") | `.git/info/exclude:9` |

---

## 1. Корекция на изходните предпоставки (важно за всеки следващ асистент)

Техническото описание, с което беше поискан одитът, **не съвпада с реалното репо**. Това е първата и най-важна констатация, защото всяка инструкция, базирана на описанието, ще търси несъществуващи файлове:

| Твърдение в заданието | Реалност (проверено) |
|---|---|
| `app.py` (FastAPI) | **Липсва.** Приложението е `main.py` — **Flask 3.1.3 + gunicorn 26.1.0** (`requirements.txt:11-12`, `main.py:41, 166`). Няма `fastapi`/`uvicorn` никъде. |
| `mcp_server.py` (FastAPIMCP обвивка) | **Липсва.** MCP сървърът е вграден в `app/blueprints/discovery.py` (рутове `/mcp/sse`:670, `/mcp/message`:720, `/mcp` POST/DELETE:742, `/mcp` GET:766, `/mcp.json`:1026, `/api/mcp/manifest`:835). |
| `auth.py`, `guard.py` | **Липсват.** Paywall-ът е `@app.before_request def _x402_paywall()` — `main.py:3396`. Guard логиката е в `main.py` + `integrations/dashboard_store.py` (`payment_guards` таблица). |
| `gas.py`, `wallet.py`, `facilitator.py`, `rpc.py` | **Липсват.** Има само `blockchain/wallet.py` (8594 B). Газ/settlement/facilitator са в `services/connectors.py` (46329 B); RPC логиката е в `integrations/dashboard_store.py` + `main.py`. |
| `render.yaml` (авто-деплой от main) | **Липсва и никога не е бил в git.** `git log --all -- render.yaml` → празно; `git grep "render.ya?ml"` → 0 попадения в tracked файлове. Има `Procfile:1`, който Render **не** консумира. |
| „35 сканиращи рута" | **Не съществува такова твърдение в репото.** Реално: **6 платени** x402 рута (`main.py:89-100, 2071-2134`), 27 безплатни в allow-list-а, 44 `@app.route` в `main.py` + 26 blueprint рута. |
| „550+ теста минават" | ✅ **Потвърдено първоначално:** `550 passed, 1 warning in 180.46s` (пълен пробег, Python 3.12.10, pytest 9.1.1). |
| „x402 хедъри, ценообразуване, сигурност — непокътнати" | ✅ Съблюдавано: **нищо не е променяно.** |
| Glama „A4.7 / 100% uptime / 47 дни" | 4.7 се среща като TDQS, но същото репо казва **„A 3.6/5.0"** (`PROJECT_STATUS.md:1199,1204`; `PROJECT_CHRONOLOGY.md:128`). Низовете „100% uptime" и „47 дни" **не съществуват** в репото. |
| README: „zero payment incidents" | ❌ **Невярно.** `PROJECT_STATUS.md:34-45` документира INCIDENT 14.09: външен платец плати $0.003 на `/api/v1/signal` (tx `0x06b4c8f2…58ce7`, блок 51313253) и получи **HTTP 401**, без claim и без доставка. |

**Извод:** описът в заданието изглежда от по-ранна/друга версия на продукта. Всички препратки към `app.py`, `mcp_server.py`, `auth.py`, `guard.py`, `gas.py`, `facilitator.py`, `rpc.py`, `render.yaml` трябва да се третират като невалидни. Документацията в репото **не** препраща към тези файлове (проверено с пълно търсене) — разминаването е само в заданието.

---

## 2. Реална архитектура

### 2.1 Карта на кода (без `venv/`, `.git/`, `.kilo/`)

| Файл | Размер | Роля |
|---|---|---|
| `main.py` | 272 244 B / **5859 реда** | Монолит: Flask app, x402 paywall, 44 рута, wallet state, background threads, 140 top-level функции |
| `app/blueprints/discovery.py` | 74 072 B | Discovery + **MCP сървър** + OpenAPI/llms.txt/robots/sitemap/glama.json, `/health`, `/validation`, 6 `/sample` рута |
| `integrations/dashboard_store.py` | 124 935 B | Durable store (SQLite **или** Postgres): sales, requests, payment_guards, whaleflow, meta watermarks |
| `integrations/stripe_checkout.py` | 20 057 B | Човешки абонаменти (втори, off-chain рейл) |
| `integrations/catalog_store.py`, `crm_store.py`, `research_store.py`, `verified_sales.py` | 46 370 / 30 029 / 12 197 / 5 827 B | Каталог от агенти, CRM/лийдове, research, seed-нати верифицирани продажби |
| `services/connectors.py` | 46 329 B | x402 facilitator верига (self-broadcast → CDP → PayAI), EIP-712 precheck, broadcast |
| `services/telegram_sales.py`, `sentinel.py`, `market_data.py`, `verifier.py`, `arb_radar.py`, `signal_track_record.py`, `trading_agent.py`, `coingecko.py`, `defi_signals.py`, `base_listener.py`, `ai_engine.py` | 45 158 … 3 470 B | Продажби през Telegram, Sentinel мониторинг/отчети, CoinGecko/DEXScreener, верификация на сигнали, арбитраж, track record |
| `blockchain/wallet.py` | 8 594 B | Base wallet, USDC трансфери, `pay_request_fee()` (**мъртъв код**, без извикващи) |
| `src/nexus/*` | 7 файла | NEXUS „интелигентен" слой (`mount_nexus_engine`) |
| `config.py` | 4 819 B | Единствен източник на цени/адреси (`KRISTO_*_PRICE`, `BOUND_BASE_FEE_RECEIVER`) |
| `tests/` | 55 файла | 550 теста |
| `docs/` | 89 файла / 0.57 MB | 46 `.md` + 26 probe `.py` + JSON/PNG/PDF |

### 2.2 Топология на изпълнение

```
Render / Docker → gunicorn --workers=1 --threads=8 --timeout=120 main:app   (gthread, 1 процес)
   ├── 8 нишки = ЦЯЛАТА HTTP способност (всяко блокиращо обаждане = −12.5% капацитет)
   ├── 11 background нишки в СЪЩИЯ процес (monitor, dashboard scan, whale scan, agent,
   │    catalog, stripe snapshot, arbitrage, sentinel, keep-alive, reorg-watch-per-call …)
   └── in-RAM състояние: free-tier броячи, `_verified_payments`, кешове, `_lock`
```

- `Procfile:1`, `Dockerfile:46`, `DEPLOYMENT.md:96`, `DEPLOYMENT_CHECKLIST.md:37` са съгласувани на **1 worker / 8 threads**.
- `PROJECT_STATUS.md:107` твърди, че продукцията реално върви на `python main.py` (Werkzeug), `numInstances=1` — **несъответствие**, което трябва да се провери.
- Единственият предпазен механизъм срещу дублиране на нишките е `KRISTO_BG_THREADS_STARTED` (`main.py:5734`) — **process-local env променлива**. При `--workers 2+` или втори instance всичките 11 цикъла и всички in-RAM guard-ове се удвояват **тихо** (`tests/test_background_thread_guard.py` тества само единичния процес).
- `--timeout 120` при `--workers 1` означава: **една прекалено бавна заявка убива целия сървис** (8 нишки + 11 цикъла + всички кешове).

### 2.3 Жизнен цикъл на заявката (платен път)

```
HTTP → @app.before_request _x402_paywall()            main.py:3396
        ├─ parked demo surface? → 404                 3417
        ├─ path ∈ X402_FREE_ENDPOINTS (27 записа) → свободно   3427
        ├─ path ∈ X402_PAID_ENDPOINTS (6 записа, ТОЧНО съвпадение) → 3431
        │    ├─ free tier (per-IP, in-RAM) → пропусни   3433-3442
        │    ├─ Rail 1: PAYMENT-SIGNATURE / X-PAYMENT (EIP-3009)   3450-3488
        │    │     ├─ 402→401 при невалиден; 425 при „settled, но възелът не е наваксал"
        │    │     └─ _try_consume_standard_payment → connectors.verify/settle
        │    └─ Rail 2: X-Payment-Proof (legacy, base64 JSON)      3490-3518
        └─ всичко останало → НЕ се проверява (deny-by-default липсва)   3525-3526
      → handler (route)
      → @app.after_request _capture_live_request → INSERT в request_log за ВСЕКИ отговор   2185-2216
```

**Ключов архитектурен факт:** защитата е **allow-list по точен `request.path`**, не deny-by-default и не per-route декоратор. Всичко, което не е изброено в двата set-а (`main.py:137-157`), минава **безплатно и без проверка** — включително `/api/launch/health` (F-26) и, по-важно, огледалните dashboard рутове (F-01).

### 2.4 Данни и индекси (измерено локално)

`data/dashboard_state.db` — **41 398 272 B**; таблици `dashboard_meta, guard_events, meta, onchain_sales, payapi_state, payment_guards, pr_watch_state, request_log, signal_history, vip_invites, whaleflow_events`.
Индекси: `idx_guard_events_ts, idx_onchain_sales_ts, idx_request_log_path, idx_request_log_ts, idx_signal_history_issued, idx_vip_invites_wallet, idx_whaleflow_ts` (+PK).
Редове: `request_log` **46 301**, `onchain_sales` 10, `payment_guards` 3, `guard_events` 128, `whaleflow_events` 0.
**Липсват индекси** по `request_log.user_agent` (филтърът `LIKE 'Render/%'`), `source`, `funnel`, както и по `payment_guards.consumed_at`.

---

## 3. x402 платежен рейл

### 3.1 Какво е коректно (проверено — не се пипа)

1. **Паритет на 402 плика.** `PAYMENT-REQUIRED` и тялото (`accepts`, `accepts[]`, `x402_accepts`, `resource`, `extensions`) са идентични **включително ред на ключовете**, защото тялото се връща като суров `Response(json.dumps(body), status=402)`, заобикаляйки сортирането на Flask (`main.py:1750-1763, 1791-1793`; тест `tests/test_envelope_body_mirror.py:48-62`).
2. **Версиониране.** v2 навън (`x402Version: 2`, CAIP-2 `eip155:8453`, атомарни низове, `payTo`, `asset`, `extra: {USD Coin, 2}`, `maxTimeoutSeconds: 60` — `main.py:1577-1589`); навътре приема `PAYMENT-SIGNATURE` (v2) и `X-PAYMENT` (v1), v2 с предимство (`main.py:2970-2981`); рекламира се само схема `exact`.
3. **402 хигиена.** `Cache-Control: no-store` + CORS `Expose-Headers` **само** при статус 402 (`main.py:3386-3393`). Шестте `/sample` рута са статични с честни дисклеймъри — не изтичат живи платени данни.
4. **Локална криптографска верификация.** Няма обаждане до facilitator при verify (`connectors.py:672-727`); EIP-712 recovery трябва да съвпадне с `authorization.from`; `auth.to` трябва да е сървърният `payTo` (клиент не може да пренасочи средствата към себе си); `asset` = сървърният USDC; прозорецът на авторизацията е ограничен ≤60 s сървърно (`connectors.py:203-225`).
5. **Replay заключване.** `payment_guards.tx_hash` PRIMARY KEY + `INSERT … ON CONFLICT DO NOTHING` с rowcount — атомарно между нишки/процеси, БД-то е истината, RAM кешът може само да откаже, изрично fail-closed при грешка в store-а (`dashboard_store.py:1313-1370, 439-448`). Един tx купува точно едно обаждане и не може да се пренасочи към друг endpoint (H2 обвързване), включително при равноценни съседни рутове.
6. **Отчетност на доставката.** `delivered_at` се слага само при 2xx/3xx (`main.py:3309-3316`), така че платено обаждане, чийто handler е умрял, е възстановимо точно веднъж и след това окончателно отказано; слотът се освобождава при грешка, за да не се губи плащане.
7. **Rail 2 (legacy) интегритет на сумата.** `amount_usdc` от proof-а се декодира, но **не** се вярва (`main.py:2744-2750`); сумата идва от receipt-а/записаната продажба; underpayment, грешен платец, непознат tx и несъответствие на endpoint → 401. Тук C2 изисква **12** потвърждения (`main.py:2487-2493, 2775-2799`) срещу 1 при синхронния рейл.
8. **Няма кеширане на достъп и няма session bypass.** Грантовете са per-call; `_verified_payments` е само block-list; в Flask сесията не се пише; `_is_dashboard_request()` е сведена до `return False` (`main.py:1797-1799`); MCP `tools/call` връща **само инструкции за плащане**, не проксира платени данни (`discovery.py:635-657`).
9. **Произход на цената в предизвикателството.** `_x402_challenge_core` извежда `payTo`, `asset`, мрежа и атомарна сума от `config` (`main.py:74-100, 1577-1588`); конверсията е вярна (0.005 → `"5000"`); `X-Payment-Amount-USDC`, `WWW-Authenticate`, `x402_amount` и `accepts[0].amount` съвпадат числово (`main.py:1688, 1705, 1766, 1774`).
10. **Webhook-ове fail-closed.** Stripe: `Stripe-Signature` → `Webhook.construct_event(payload, sig, secret)` върху **суровия** тяло-байт; при липсващ секрет/библиотека → **503**, никога грант (`main.py:4714-4723`, `stripe_checkout.py:313-322`). Telegram: `X-Telegram-Bot-Api-Secret-Token` през `hmac.compare_digest`, липсващ секрет сам по себе си отказва с 401 (`main.py:4108-4117`).
11. **Всички админ рутове имат guard**, нито един не е достъпен без auth (проверени индивидуално); всички споделени секрети се сравняват с `hmac.compare_digest` (`main.py:1835, 1852, 1859, 4113, 5151, 5177, 2019`); cookie-то е `HttpOnly + Secure + SameSite=Lax`, `session.clear()` преди login (анти-fixation); `ProxyFix(x_for=0)` умишлено **не** пренаписва `remote_addr` от хедър (`main.py:174`); error handler-ът не изтича traceback (`main.py:218-236`); SQL е параметризиран (двете интерполации са по константи); `MAX_CONTENT_LENGTH` 512 KB се налага преди handler-ите.

### 3.2 Констатации по платежния рейл

#### 🔴 F-01 — Платените продукти се раздават безплатно (нарушен бизнес модел)
`main.py:142-157` съдържа в **безплатния** allow-list двата dashboard JSON рута; paywall-ът ги пропуска на `main.py:3427-3428`:

```python
X402_FREE_ENDPOINTS = { ..., "/api/dashboard-stats", "/api/dashboard/data", ... }
if path in X402_FREE_ENDPOINTS:
    return None
```

- `/api/dashboard-stats` (`main.py:3986-3989`) → `_cached_statistics_payload()` → `_statistics_payload(include_recent_requests=False)`; **единствената** разлика с платения `/api/stats` (`main.py:4067-4071`) е:
  `if include_recent_requests: payload["recent_requests"] = recent_requests[-50:]` (`main.py:3818-3819`).
  Всичко останало, за което клиент плаща, е в безплатното тяло: `"history"` (≤100 durable реда), `total_volume_usd`, `total_sales`, `by_token`, `market_data`, `products`, `wallet` (`main.py:3792, 3797-3800`).
- Редовете идват от `dashboard_store.py:1240-1244` — `SELECT tx_hash, block_number, ts, sender, amount_usdc, payer_class, payer_label, source` — т.е. **tx hash + платец + сума + вътрешната операторска класификация на платеца** са публични (`main.py:5259-5263`).
- `/api/dashboard/data` (`main.py:5573-5582`) е още по-лошо: `"history": sales["history"][:100]` (`main.py:5452`) и `"whales": whales["whales"]` (`main.py:5503`) — второто **е** продуктът, за който `/api/v1/whaleflow` таксува $0.003 (`main.py:5625-5634`), при това с повече полета. Цялото тяло на `/api/sales` (`main.py:3630-3639`) е подмножество на `sections.onchain`.

**Защо е сериозно:** `X402_PRICE_MAP` е практически неспазваем — рационален купувач сравнява един безплатен URL срещу шест 402 отговора. Освен това публикуването на `(tx_hash, sender)` прави F-16 експлоатируем. Това е продуктово решение, не бъг в кода: paywall-ът не може да се „поправи", докато съществува безплатно огледало.

#### 🔴 F-02 — `accepted.amount` замества подписаната стойност; реално платената сума не се проверява
`services/connectors.py:195-200`:

```python
want_amount = str(requirements.get("amount", ""))
got_amount = str(accepted.get("amount") or auth.get("value") or "")
if want_amount and got_amount.isdigit() and int(got_amount) < int(want_amount):
```

Клиентското `accepted.amount` има предимство пред подписаното `authorization.value` и двете никога не се сравняват. Доказано с реалната функция (`precheck_payment_payload`, read-only):

```
A  accepted.amount=5000, подписано value=1  -> []                                  (минава!)
B  без accepted.amount, подписано value=1   -> ['amount below price: 1 < 5000 …']  (хваща се)
C  нечислов amount "1_000"                  -> []                                  (проверката се прескача)
```

Сетълментът после излъчва точно подписаното (`connectors.py:360-368`, `abi_encode(... int(auth["value"]) ...)`), а при успех `main.py:3182-3213` прави claim и доставя **без** да чете сумата на Transfer-а (четат се само `status`, `blockNumber`, `blockHash` — `main.py:3076-3120`), записвайки продажбата по сървърната цена (`main.py:3210-3213`). Допълнително `_merged_requirements` (`connectors.py:287-294`) подава **клиентския** amount и към facilitator-а.

**Защо е сериозно:** директно недоплащане; всяка продажба през стандартния рейл може да е под отчетената стойност. Сигурно експлоатируемо по self-broadcast пътя (нужни са `WALLET_PRIVATE_KEY` + газ); при PayAI/CDP зависи дали техният facilitator сравнява подписаната стойност — защита по случайност, не по дизайн.

#### 🔴 F-03 — При нечетим receipt платеното обаждане се доставя (fail-open)
`main.py:3082-3110` умишлено отменя провалената проверка на receipt-а:

```python
log.warning("c2_receipt_status_override_delivered: tx=%s receipt status=%s след ~8s poll — fail-open, доставя се", ...)
```

При спрял RPC всяко `get_transaction_receipt` хвърля изключение, `receipt` остава `None` през 4-те опита и заявката продължава към C1 claim и доставка само по думата на facilitator-а. Пропуска се и проверката за дълбочина (`if receipt is not None …`, `main.py:3132`). Цялата проверка е обвита в поглъщане, което при изключение **дава** достъп (`main.py:3158-3159`), така че и `read_head()` при RPC смущение води до грант. Legacy рейлът обвива **същия** helper и задава `deep_enough = False` (`main.py:2790-2793`) — асиметрията изглежда случайна.

#### 🔴 F-04 — Безплатен GET прави 4 ЗАПИСА в таблицата на replay-заключването
`/api/dashboard/data` (безплатен, `main.py:142-157`) → `_canonical_dashboard_payload` (`main.py:5400`) → `dashboard_db.guard_stats()` → `integrations/dashboard_store.py:1542-1555`:

```
DELETE FROM payment_guards WHERE tx_hash = ?
INSERT INTO payment_guards (tx_hash, endpoint, payer, amount_usdc, consumed_at) VALUES (?,?,?,?,?)
SELECT COUNT(*) … WHERE tx_hash = ?
DELETE … WHERE tx_hash = ?
```

Всяко през `_run`, което взима `_pg_lock` (`dashboard_store.py:307, 353` — „one shared, serialised link") и прави commit. `templates/dashboard.html:763` го вика с `cache:'no-store'`, а `:800` го повтаря на всеки 45 s на отворен таб.

**Защо е сериозно:** това е **същият lock, който `claim_payment_tx` използва за C1 replay защитата**, върху **същата таблица**. Анонимен poll може да забави replay claim на платещ клиент; endpoint-ът може да се върти в цикъл за неограничени INSERT/DELETE/WAL; а самият код документира (`dashboard_store.py:1532-1537`), че провалена проба е fail-closed условието, при което започват да се отказват плащания. **Писането върху read път е най-опасният единичен модел в кода.**

#### 🟠 F-05 — Реорг никога не отменя кредитирано плащане
`main.py:2631-2690` препрочита анкерните височини и записва `c2_reorg_detected` — **нищо друго**. Редът в `onchain_sales` (`dashboard_store.py:812-845`), claim-ът в `payment_guards` (`:1313-1370`) и VIP поканата (`main.py:882-898`) оцеляват. Дълбочината на стандартния рейл е **1** (`main.py:2484`), т.е. прозорецът е един Base блок (~2 s). `tests/test_reorg_watch.py:100-118` изрично фиксира, че детекцията **не** е отказ и не мести `blocked_total`.

#### 🟠 F-06 — Приемане на сетълмент по nonce без проверка за дълбочина
`main.py:2321-2435` (`_find_settlement_by_nonce`) приема всеки `AuthorizationUsed` лог от последните 5000 блока, чийто receipt съдържа съответстващия `Transfer`, проверявайки **само** `receipt.status == 1` — без `_confirmations_ok` и без сравнение с главата на веригата. Вика се от `main.py:3021` преди всеки сетълмент: сетълмент на самия връх (или такъв, който ще бъде реорганизиран) се приема и после се доставя по същия път като F-03.

#### 🟠 F-07 — Нула rate limit по платежния път; газ-разходът е под контрола на анонимен клиент
`main.py:1406-1416` дефинира 9 scope-а за rate limit; **нито един не покрива paywall-а** и `_x402_paywall` (`main.py:3431-3523`) никога не вика `_check_rate_limit`. Всяка заявка с валидно подписан, свеж authorization води до: `eth_getLogs` през 5000 блока (`main.py:3020-3021` → `:2364-2374`), после сетълмент. Ако `WALLET_PRIVATE_KEY` е наличен, `_self_broadcast_settlement` излъчва **наша** транзакция за купувач, който може умишлено да я направи revert (нулев USDC баланс или бомбастичен EIP-712 домейн — F-16/F-33 контекст), т.е. ние плащаме газа, и държи нишката до 24 s (`connectors.py:390-410`: `deadline = time.time() + 24`, `time.sleep(2)`).

#### 🟠 F-12 — Неограничен reorg watch на нишка-на-плащане + нечанкнат `getLogs`
`main.py:3217` стартира `threading.Thread(target=_detect_reorgs, …)` от `_try_consume_standard_payment` (fire-and-forget, без throttle и без single-flight), а `_read_block_hash` (`main.py:2621-2628`) строи **нов** `Web3(HTTPProvider(…, timeout=20))` при всяко викане, до 25 викания вътре в `_detect_reorgs` → до 25 нови provider-а и 25 RPC обаждания на платено обаждане. Паралелно `_find_settlement_by_nonce` прави `get_logs` за 5000 блока **на един ред**, докато `services/market_data.py:194+` има `_adaptive_get_logs` с намаляване на прозореца, което този път не използва. 5000-блоков `getLogs` е класически тригер за 429/timeout, а 429 точно там превръща „платено и търпеливо" в „платено и провалено".

#### 🟡 F-16 — X-Payment-Proof е препредаваем bearer токен върху публично публикувани данни
Бързият път (`main.py:2879-2900`) приема proof за всеки tx, който вече е в `_sales_history`, ако заявеният платец съвпадне със записания sender:

```python
if recorded_sender != proof["payer"]:
    ... return False
amount = float(s.get("amount_usd", 0.0))
```

Самият proof е неавтентикиран base64 JSON (`main.py:2729-2752`: `{payer, transaction_hash, amount_usdc}`), а **двете** половини на проверката се публикуват безплатно от F-01 (tx hash **и** sender в ≤100 реда история). Тестът в репото сам описва модела на заплахата (`tests/test_payment_guards.py:396-429`). Прозорец: всеки трансфер, открит от монитора, но още без ред в `payment_guards` (напр. 9-те seed-нати хеша в `integrations/verified_sales.py:58-122`).

#### 🟡 F-17 — Едно плащане може да достави два пъти при конкурентност
Durable claim-ът е коректен, но recovery слотът re-admit-ва братче, което още е in flight (`main.py:2438-2470`): губещият `claim_payment_tx` получава False, но `delivered_at` още е NULL (победителят не е излъчил отговора), затова губещият взима retry слота и също доставя. Ограничено до 2 доставки.

#### 🟡 F-18 — `payment.amount_usdc` връща атомарни единици под име на USDC
`main.py:1723-1733`: `"amount_usdc": int(atomic_amount),` → за рут от $0.005 тялото казва `5000`, докато хедърът казва `X-Payment-Amount-USDC: 0.005` (`main.py:1766`), а съобщението — „Send 0.005 USDC" (`main.py:1719-1722`). `x402_amount` е документиран като атомарен (`main.py:1705`), но това поле — не, а тялото съществува именно за да може агент да конструира плащането без документация (`main.py:1698-1700`). `tests/test_402_response_headers.py:81` фиксира грешната единица. **Агент, който чете само JSON-а, се инструктира да авторизира 5000 USDC за обаждане от $0.005.**

#### 🟡 F-19 — Рекламираните цени дрейфват от предизвикателството
- `discovery.py:866-867`: tier `price_usdc: MICRO_FEE_USDC` (=0.005) с описание „from {KRISTO_SIGNAL_PRICE}" (=0.003) — две различни числа в един обект; `:887-892` ценообразува `/api/stats`, `/api/sales`, `/api/bot-status` от `MICRO_FEE_USDC` вместо от картата.
- `discovery.py:1057, 1276, 1454, 1528`: `price_per_call_usdc: X402_FEE_USDC` (плоско 0.005), докато `/api/v1/signal` и `/api/v1/whaleflow` таксуват 0.003.
- `discovery.py:440`: whaleflow sample казва „$0.005", а `KRISTO_WHALEFLOW_PRICE` е 0.003 (`config.py:83`); `:416/:462/:482/:504` също твърдолитерални.
- MCP инструментите (`discovery.py:535, 555, 576`) рекламират `X402_FEE_USDC` за endpoints, ценообразувани от картата.
- Правилният модел вече съществува: `discovery.py:950-956` извежда от `X402_PRICE_MAP` — просто не е приложен навсякъде.

#### 🟡 F-20 — „$29 VIP — неограничен достъп" не е имплементиран
`discovery.py:873-881` го продава на `VIP_MONTHLY_USDC = 29.00` (`main.py:402`), но **нито един рут не консултира `_vip_subscribers`** (grep: само запис в `main.py:474`, dedup в `:887`, два брояча `:4949/:4980`); paywall-ът няма клон за абонамент. Единственият VIP тригер е плащане ≥ `VIP_THRESHOLD_USDC = KRISTO_VIP_ANALYSIS_PRICE` = **$0.10** (`main.py:406, 882-898`), което издава Telegram покана. Т.е. или платено обещание, което API-ът не изпълнява (риск от refund/dispute), или $0.10 праг върху $29 полза. Поканата nav nav се задейства и при всеки несвързан трансфер ≥$0.10 към получателя.

#### 🟡 F-21 — `FREE_TIER_LIMIT` по подразбиране е 1
`main.py:129-134`: `FREE_TIER_LIMIT = max(0, int(os.getenv("KRISTO_FREE_TIER_LIMIT", "1")))`. Само коментар твърди, че продукцията работи с 0. `.env.example` **не** документира нито този ключ, нито който и да е x402 ключ. Броячът е in-RAM, по IP, без pruning (`main.py:1319`); при 1 worker е консистентен, но всяко мащабиране умножава безплатните обаждания. 402 тялото публикува `"free_tier_limit": FREE_TIER_LIMIT` (`main.py:1735`).

#### 🟢 F-32 — Ръчно поддържан guard списък без тест за покритие
`main.py:137-139` (шест литерала, точно съвпадение) е **единственото**, което paywall-ът налага, докато рекламираният списък е `REAL_X402_ROUTES` (`:2071-2134`), а цените — `X402_PRICE_MAP` (`:89-100`). Добавяне в единия списък без другия прави рут безплатен или го ценообразува с fallback-а `BASE_FEE_AMOUNT_USDC` (`:1473`). Няма тест, който да твърди `REAL_X402_ROUTES ⊆ X402_PAID_ENDPOINTS` (grep в `tests/` — 0 попадения). Днес няма втори рут към платен ресурс, но дизайнът го допуска по конструкция.

#### 🟢 F-37 — Обемната отстъпка е no-op и е твърдолитерална цена
`main.py:83` `X402_FEE_USDC_DISCOUNT = 0.01` в файл, чието собствено docstring казва „Nothing in this file may hardcode a price" (`main.py:14-16`), прилага се като **таван** (`:1476-1478`): `return min(X402_FEE_USDC_DISCOUNT, base)`. Всичките шест цени са ≤ $0.01, значи `min(0.01, base) == base` винаги — рекламираната отстъпка след 10 платени обаждания никога не се случва. Броячът е per-process RAM по IP (`:1345, 1475`).

---

## 4. Производителност и тесни места

### 🟡 F-22 — Статистическият агрегат: 12 заявки, 5 пълни сканирания, без кеш на 2 от 3 рута
Измерено локално върху **46 301** реда (`requests_summary`, `dashboard_store.py:659-733`), с `EXPLAIN QUERY PLAN`:

| Заявка | Време | План |
|---|---|---|
| `count_total` | 4.14 ms | covering index `idx_request_log_path` |
| `count_today` | 0.37 ms | index |
| **`noise_total`** | **159.49 ms** | **`SCAN request_log`** |
| `noise_today` | 0.10 ms | index |
| **`by_source`** | **60.76 ms** | `SCAN` + 2× temp B-tree |
| **`by_source_clean`** | **89.32 ms** | `SCAN` + 2× temp B-tree |
| **`by_channel`** | **15.82 ms** | `SCAN` + 2× temp B-tree |
| `by_path_top10` | 61.57 ms | covering index + temp B-tree |
| **`top_user_agents`** | **91.74 ms** | `SCAN` + 2× temp B-tree |
| `hourly_today` | 0.20 ms | index |
| `funnel_grouped` | 44.48 ms | `SEARCH idx_request_log_path` |
| `recent_25` | 0.20 ms | index |
| **ОБЩО** | **528.22 ms** | **5 пълни таблични + 1 пълен индексен скан** |

- Причината: **няма индекс по `request_log.user_agent`** (филтърът `LIKE 'Render/%'`), нито по `source`/`funnel`.
- В продукция мащабът е друг: самият код отбелязва (`main.py:3944-3945`) „~783K реда, ~22 seq scans", „измерени ~41 s на живо" — над 30-секундния timeout на клиента на Sentinel.
- На Postgres `user_agent LIKE 'Render/%'` **не може** да ползва btree → гарантиран seq scan върху 783K реда.
- Кешът от 60 s покрива **само** `/api/dashboard-stats` (`main.py:3951-3955, 3966-3983`). `/api/stats` (`:4067-4071`) и `/api/dashboard/data` (`:5573-5582`) са **некеширани**, а `_cached_statistics_payload` умишлено допуска дублирани конкурентни build-ове (`:3966-3983`): изтичане на TTL + 8 едновременни попадения = 8 × ~41 s DB работа, сериализирана зад `_pg_lock`.
- Допълнително `_sanitize_json` (`main.py:1482-1496`) рекурсивно пре-създава цялото дърво на **всеки** отговор.
- **F-31:** `payment_guards` се дърпа цялата в Python при всеки dashboard poll, **два пъти** (`dashboard_store.py:1615-1625` — `SELECT tx_hash, endpoint FROM payment_guards` без WHERE/LIMIT; викана от `main.py:5400` и отново в `clients_summary` `:1933-2002`), а `payment_guard_stats` (`:1479-1486`) добавя `ORDER BY consumed_at DESC LIMIT 1` без индекс по `consumed_at`.

### 🟠 F-09 — Една споделена DB връзка под глобален lock, без `connect_timeout`
`dashboard_store.py:307` (`_pg_lock`), `:334-340` (`_pg_connection()` — **без** `connect_timeout`), `:342-372` (`_run` държи `_pg_lock` и при изключение затваря споделената връзка). Същият файл ползва `connect_timeout=5` за странична връзка на `:624-625`. `integrations/crm_store.py:399-473` също е без `connect_timeout`, а `:490-493` отваря **нова** връзка на всяко четене.
**Ефект:** psycopg не подава timeout → libpq default 0 = чака вечно. Мрежова партида или Postgres failover блокира **първата** заявка завинаги, държейки `_pg_lock` → всичките 8 нишки + всички background цикли + `/health`. SQLite пътят не е по-добър: `_run` държи `self._lock` през connect+execute+commit, а `DashboardStore._connect` (`:1659-1662`) отваря **нова** `sqlite3.connect(..., timeout=30)` на всяко викане → едно `/api/dashboard/data` отваря ~35-40 връзки.

### 🟠 F-10 — `/health` зависи от DB и може да предизвика рестарт-цикъл
`app/blueprints/discovery.py:32-76` вика `crm_store.is_healthy()` и връща **503** при нездрав CRM store (`:58, :76`); `crm_store.py:639-645 / 390-396` отваря връзка на всяко викане без `connect_timeout`. Проверяващи: `Dockerfile:39` (`--interval=30s --timeout=10s --retries=3`), платформената проверка, keep-alive цикълът (`main.py:5681-5713`) и `sentinel.py:144-165`.
**Ефект:** транзиентно DB забавяне → 503 → оркестраторът рестартира **единствения** worker → студен старт (виж F-04 от перф. анализа: ~1.3 s import + DB работа + Telegram round trip) → още 503. Самоподдържащ се цикъл. Освен това **само RPC смущение не обръща `/health.status`**, значи няма Telegram аларма при пълен RPC отказ.

### 🟠 F-11 — `/mcp/sse` пинира 1 от 8 нишки за ≥15 s, безплатно и без throttle
`discovery.py:665-667` (`_SSE_SESSIONS`, `_SSE_SESSIONS_LOCK`, `_SSE_IDLE_CLOSE_SECONDS = 15`), рут `:670-717`. Липсва **и** в `X402_FREE_ENDPOINTS`, **и** в `X402_PAID_ENDPOINTS`, **и** в rate-limit scope-овете (`main.py:1406-1448`; липсват scope-ове и за `/api/stats`, `/api/sales`, `/api/v1/signal`, `/api/v1/whaleflow`, `/api/arb/opportunities`, `/dashboard`, `/api/dashboard/data`). 8 анонимни SSE връзки = 8/8 нишки заети ≥15 s → пълен отказ на услугата, включително `/health`. Един `curl` цикъл е достатъчен.

### 🟡 F-23 — Бюджетите за блокиране по платения път надхвърлят `--timeout 120`
- `main.py:2596-2598` — `time.sleep(wait)` (C2 lag, `C2_LAG_WAIT_SECONDS_DEFAULT = 2.5` при `:2528`, до 3 препрочитания на главата).
- `main.py:3082-3096` — `time.sleep(2)` цикъл ≈ 8 s.
- `connectors.py:390-410` и `:656-667` — `deadline = time.time() + 24` + `time.sleep(2)` → до **24 s** вътре в `_self_broadcast_settlement`/`_broadcast_client_transaction`.
- `connectors.py:100-136` — facilitator POST с `FACILITATOR_TIMEOUT=15` (`:47`), верига PayAI→CDP (`:55-58`) в `settle_standard_payment` (`:799-899`) → до ~2×15 s на набор доставчици.
- `main.py:4389-4478` → `verifier.py:252` — **последователно** строене на DEXScreener картата: до 4 символа × `SOURCE_TIMEOUT_SECONDS=5` = **+20 s** при студен кеш, ×8 конкурентни = 32 upstream заявки.
- **F-24:** Stripe SDK без конфигуриран timeout — измерено `_http_client.py:512` `timeout = 80`, `stripe/__init__.py:39` `max_network_retries = 2` → до ~240 s в една checkout заявка (`stripe_checkout.py:290, 336, 361`; викани от `main.py:4188, 4330, 4561, 4708`), плюс `list_recent_completed_payments` (`:347-395`), която обхожда **цялата** история на checkout сесиите на акаунта, докато намери 25 платени.

**Верижен ефект:** едно платено обаждане може да навърже агрегат (41 s) + C2 изчакване (2.5 s) + self-broadcast (≤24 s) + facilitator верига (≤30-60 s) > **120 s**. При 1 worker това не е „1 от N worker-а зацикли", а **целият API умира и рестартира по средата на плащане**.

### 🟡 F-25 — Един цикъл без `try/except`
`main.py:1113-1121` (`_stripe_payment_snapshot_loop`) е единственият намерен background цикъл, чието тяло не е защитено: едно неочаквано изключение го убива **завинаги** и админ панелът показва „stale" без никой да бъде уведомен.

### 🟢 F-39 — Курсорът на блоковия монитор е само в RAM
`main.py:714` задава `last_block = wallet.w3.eth.block_number` при старт; цикълът сканира `last_block+1 … min(current, from_block+1000)` (`:749-750`). `_wallet_state["last_block_checked"]` е само за показване (`:716, 774`). Рестарт **пропуска** всеки трансфер, минат по време на престоя. Dashboard пътят частично компенсира с durable watermark (`dashboard_store.py:2235-2247`), но мониторът — не.

### 4.1 Какво е коректно по производителност (не се пипа)
- `/api/arb/opportunities` е наистина евтин: `arb_radar.py:61-92` копира списък под кратък lock; `data_age_blocks` от стенен часовник — **нула RPC на обаждане**.
- `/api/connectors` → `connectors.py:950-1034` е чист CPU; `_ACTIVITY` е с 9 фиксирани ключа (ограничено).
- `market_data._CACHE` е ограничен коректно (64 записа, TTL 900 s, stale 21600 s, `RLock`); `CoinGeckoClient._price_cache` — 32 записа (`coingecko.py:79-81`) с 5 s timeout.
- `verifier.py` има 60 s `_dex_cache` (`:44, 47, 70-71, 111-114`) — `/api/v1/signal` **не** удря DEXScreener на всяко платено обаждане.
- `main.py` има **140 top-level функции без нито едно дублирано име** (AST проверка) — хипотезата за „дублирани/мъртви helper-и" не се потвърждава.
- Нито един тест не пре-импортира `main.py`; thread guard-ът работи за еднопроцесния случай, за който е проектиран.
- Всички `requests`/`urlopen`/`Web3` в `market_data.py`, `verifier.py`, `sentinel.py`, `telegram_sales.py`, `arb_radar.py`, `connectors.py` имат **експлицитен timeout** — проблемите са в **бюджети и сериализация**, не в липсващи timeout-и. Изключенията са Stripe SDK (F-24) и DB connect (F-09).
- `web3` (3.832 s студен импорт) се зарежда **лениво**; модулният импорт на `main.py` е 1.27-1.37 s и не включва web3/psycopg/stripe/telegram.

---

## 5. RPC, блокчейн и външни зависимости

### 5.1 Таблица на зависимостите

| Зависимост | Конфигурация | Timeout | Fallback | Поведение при отказ | Blast radius |
|---|---|---|---|---|---|
| **Base RPC** | `config.py:57` (`BASE_RPC_URL`, default `https://mainnet.base.org`; прод. стойност `https://base.drpc.org` според `scripts/_render_env_set.py:17` и `PROJECT_STATUS.md:2473`) | 15-30 s (различни по места) | **Няма** втори доставчик | `_adaptive_get_logs` намалява прозореца и повтаря **същия** начален блок на всеки 2 s (`dashboard_store.py:243-255`), **без** `Retry-After` | **Най-висок.** И двата платежни рейла fail-closed (401) → никой не може да плати; скановете спират; цената в сигнала става `None` |
| **Postgres / `DATABASE_URL`** | `dashboard_store.py:300-371` | `connect_timeout=5` само на request-log пътя (`:625`); другаде default (безкрайно) | SQLite файл при липсващ `DATABASE_URL` — **не** е runtime failover | `claim_payment_tx` връща False → `C1 replay lock UNREACHABLE … refusing every payment` (`:1359-1364`) | **Критичен:** недостъпна БД отказва всяко платено обаждане, макар парите да са on-chain |
| **CoinGecko** | `coingecko.py:32-33`, `market_data.py:31`; ключове `COINGECKO_API_KEY`/`BASE44_API_KEY` | 5 s | Base44 прокси → публичен API (`coingecko.py:144-169`); stale кеш до 6 h | 2 опита + експоненциален backoff; 429 → process-wide cooldown ≤120 s | Среден за парите; **висок за платения сигнал** (цена `None` → confidence ×0.8) |
| **DexScreener** | `verifier.py:39, 68`, `market_data.py:32` | 5 s / 10 s | `search` → `tokens` вътре във verifier-а; няма крос-доставчик | Връща `[]`/`"error"`; присъдата става `unverified` → **fail-open, сигналът се доставя** | Среден: платен сигнал се доставя неверифициран |
| **Telegram Bot API** | `main.py:536`, `sentinel.py:123`, `telegram_sales.py:74, 199` | 10-20 s | Няма | Логва се, не е фатално | Нисък: забавени аларми/VIP кодове |
| **Stripe** | `stripe_checkout.py:85-133` | **Няма** → SDK default 80 s × 3 | Няма | `stripe_checkout_creation_failed`; snapshot остава `stale` | Нисък за x402 paywall-а (човешки продукт) |
| **x402 facilitator-и** (PayAI, CDP) | `connectors.py:55-63`, верига `:86-97` | 15 s | Верига: self-broadcast → CDP → PayAI (`:860-899`) | HTTP/транспортна грешка → следващият; всички fail → `settlement_failed` | Среден: **значим само ако hot wallet-ът няма газ** |
| **GitHub API / DefiLlama / alternative.me** | `sentinel.py:248, 271, 362, 370`; `market_data.py:33, 494` | 25-30 s / 10 s | Няма | Полето показва `n/a`; baseline се запазва | Незначителен |

### 5.2 Аритметика на натоварването (изведено от кода — **не** измерено в продукция)

| Цикъл | Интервал | RPC обаждания/цикъл | RPC/час |
|---|---|---|---|
| `_blockchain_monitor_loop` (`main.py:679-780`) | 30 s | 1 `block_number` + 2 `balanceOf/decimals` + ~1 receiver balance + 1 `get_logs`(≤1000 блока) | **~480** |
| `_dashboard_scan_loop` (`main.py:1151-1154`) | 60 s | 1 `block_number` + 1 `get_logs` + 1 `get_block` **на трансфер** | ~60 + ~60·N |
| `_whaleflow_scan_loop` (`main.py:1229-1236`) | 60 s | 1 `block_number` + 1 `get_logs` + 1 `get_block` **на кит** | ~60 + ~60·M |
| `arb_radar` (`arb_radar.py:27`) | 60 s | 1 RPC + 8 последователни DEXScreener GET | ~60 |
| **Сумарно** | | | **~600-900/час при ниска активност; ~2 700/час при висока** (втората оценка е от отделен анализатор и предполага 30+ трансфера на цикъл — третирай я като песимистична горна граница) |

> **Бележка за честност:** двама независими анализатори дадоха 480/час и ~2 700/час. Разликата е в допускането за брой трансфери на цикъл (локалната БД има само **10** `onchain_sales` общо). Числата са **изведени от кода**, не измерени в продукция.
>
> **Boot backfill (веднъж на деплой):** продажби — 30 дни × 86400 / 2 s = 1 296 000 блока ÷ 5000 = **260 `getLogs`** + 1 `get_block` на трансфер; китове — 24 h × 3600 / 2 = 43 200 блока ÷ 100 = **432 `getLogs`** + 1 `get_block` на кит.

### 5.3 Допълнителни находки

#### 🟠 F-08 — Един RPC доставчик, без fallback и без cooldown
`config.py:57` дефинира един `BASE_RPC_URL`; всеки консуматор го препрочита със същия default (`main.py:661, 2625, 3062`; `connectors.py:335, 646`; `dashboard_store.py:2125…2410`; `wallet.py:117`). Няма втора константа за доставчик. `_block_timestamps` дори твърдолитерално ползва `mainnet.base.org` (`dashboard_store.py:2078-2079`) — това е **друг** доставчик, не fallback. Единственото „backoff" е намаляване на прозореца. `scan_window` дори продължава при `is_connected() == False` (`dashboard_store.py:2137-2146`).

#### 🟠 F-40-свързано — Несериализирано nonce управление и газ без таван
`connectors.py:319-417` (`_self_broadcast_settlement`) чете `get_transaction_count` на `:376` без lock и без проследяване на pending nonce → две конкурентни платени заявки могат да построят един и същ nonce, едната revert-ва, а nonce-ът на купувача все пак е изразходен. `maxFeePerGas = gas_price * 2` **без таван** (`:350`). `connectors.py` не импортира `threading` — в модула няма нито един lock.

#### 🟠 F-16-свързано — Услугата излъчва клиентска raw транзакция почти без валидация
`connectors.py:641-669` декодира и `send_raw_transaction`-ва каквото има в `payload.transaction`. `_local_verify_transaction_payload` (`:561-634`) проверява signer == `from`, chainId == 8453, `to` == USDC и calldata префикса `transfer(payTo, amount ≥ price)` — **но не** `gas`, `gasPrice`/`maxFeePerGas`, `nonce` или `value`. Извикващ може да ни накара да излъчим USDC трансфер с екстремен gas price или препредаден nonce.

#### 🟡 H5 — CoinGecko кешът на verifier-а е с несъответстващ регистър
`coingecko.py:89` търси `prices.get(s.lower(), prices.get(s))`, но кешираният речник се строи с регистъра на извикващия (`:221-228`). Агентският цикъл го пълни с малки букви (`main.py:1067` → `trading_agent.py:76`), а verifier-ът подава `[s.lower() for s in symbols]`, където `symbols` са с главни букви (`verifier.py:250-252, 237`). Ключът е нормализиран (`:179`), **payload-ът — не** → verifier-ът пропуска кеша и прави живо CoinGecko обаждане **на всяко платено `/api/v1/signal`**.

#### 🟡 M6 — 24-часовият прозорец на китовете може тихо да изпусне събития
`dashboard_store.py:775-776` строи cutoff от `datetime.now(utc) - 24h` и го сравнява с `ts` низове, записани от **блокови** времена (`:2316-2317`). При провалено четене на блок fallback-ът е `datetime.now(utc)` (`:2319`), което **надува** timestamp-а и може да избута реални събития извън прозореца; stale watermark също оставя прозореца празен. `all_time_count` ползва друга предикатна логика (`:784-788`) → двете числа могат да се разминават.

#### 🟡 M7 — Отказан диапазон може да придвижи watermark вместо да го повтори
`dashboard_store.py:2423-2424` (`whaleflow_increment`) и `:2246-2247` (`scan_increment`) падат към `to_block`, когато `safe` е 0, т.е. когато **целият** прозорец е отказан; `whaleflow_backfill` прави същото (`:2401`). Правилото „никога не пропускай диапазон", заявено на `:2343-2345`, не се спазва на тотално-проваления клон.

#### 🟢 M3 — Всеки входящ USDC трансфер се записва като продажба, без минимум
`main.py:764-765` → `_process_incoming_transfer` → `_record_real_sale` (`:815-822`) и `dashboard_store.record_sale` (`:812-845`) приемат **всякаква** сума; `VIP_THRESHOLD_USDC` само гейтва поканата (`:882`). Dust-спамър може да надуе `total_sales`, `total_volume_usd` и 7-дневната линия в Sentinel отчета (`sentinel.py:377-387`) и да задейства `New payment received!` аларми (`sentinel.py:200-211`).

#### 🟢 F-38 — Времева зона: само Sentinel седмичният отчет е с локално време
`sentinel.py:464-467` ползва `datetime.now()` и `local.weekday()/hour`. Всичко останало е UTC (`sentinel.py:382, 405`; `main.py:3661, 3712`; `dashboard_store.py:1223`). На non-UTC хост отчетът „неделя 18:00" излиза в грешен ден или се пропуска; `last_report_date` е локален низ. Паричните пътища са UTC-консистентни — DST рискът е само в този гейт.

#### 🟢 L3 — `data_age_blocks` е изведен от стенен часовник
`arb_radar.py:75` дели изминали секунди на твърдолитерално 2 s блоково време — оценка, не измерване на веригата, подвеждащо име.

---

## 6. Сигурност и deployment конфигурация

### 🟠 F-13 — Суров RPC текст се публикува на анонимен безплатен рут
`main.py:643` — `_wallet_state["rpc_error"] = str(exc)` (сурово). Всички останали места в същия файл **умишлено** редактират: `main.py:769, 778, 1141, 1158, 1228, 1235` ползват `redact_rpc(exc)`. Самият редактор съществува, защото RPC URL-ите носят ключове (`dashboard_store.py:46-48`: `(\/v[0-9]+\/|apikey=|api-key=|key=|token=)([A-Za-z0-9_\-]{6,})`). Суровата стойност се сервира през `main.py:3792` (`"wallet": wallet_info`) в `_statistics_payload`, достижима от `/api/dashboard-stats` (`:3986-3989`) — **безплатен** (`:147`). `_safe_jsonify` (`:1499-1501`) само маха NaN/Infinity, **не** редактира.
**Експлоатация:** ако `BASE_RPC_URL` е доставчик с ключ в URL-а (Alchemy/DRPC/POKT се използват в репото) и мониторният Web3 init се провали веднъж, изключението (което обикновено съдържа пълния URL с ключа) се връща на всеки анонимен `GET /api/dashboard-stats`.

### 🟠 F-14 — Telegram bot token може да изтече в логовете
`telegram_sales.py:72` строи `url = TELEGRAM_API_BASE.format(token=token, method=method)` — токенът е в пътя на URL-а; `:80-81` логва `log.warning("Telegram API %s failed: %s", method, exc)`; същото на `:198-199, 211-212` за `setWebhook`. `requests` изключенията стрингифицират **пълния** URL → `.../bot<TOKEN>/sendMessage` попада в лог реда. `stripe_checkout.py:57-59` има `redact()` helper, но се прилага само на Stripe пътища и regex-ът му не хваща Telegram токен.
**Експлоатация:** всяко транзиентно мрежово смущение към `api.telegram.org` записва живия токен в Render лог потока → пълно поемане на бота.

### 🟠 F-15 — `secrets/` се bake-ва в Docker образа
`Dockerfile:29` — `COPY --chown=kristo:kristo . .` копира целия build context. `.dockerignore:47-50` изключва `.env`, `.env.local`, `.env.production`, но **няма запис за `secrets/`**, докато `.gitignore:53` го изключва. Също липсват `kristo_paid_demo_clip.mp4` (120 MB) и `kristo_paid_demo_clip_web.mp4` (20 MB).
**Експлоатация:** `docker build` от това дърво произвежда образ с `secrets/cdp_api_key.json`, `secrets/demo_private_key.txt`, `secrets/render_api_key.txt`; всяко push-ване в registry, layer inspection или `docker save` предава CDP ключовата двойка, private key на демо wallet и Render API ключа. (Файловете **не** са отваряни — само имената им са изброени.)

### 🟡 F-26 — `/api/launch/health` без auth
`main.py:5198-5216` няма auth проверка в тялото: `payment_provider` (Stripe или mock), `crm_backend`, `lead_count`, `pipeline` (вкл. брой платени клиенти), `public_url`. Не е в нито един от двата endpoint set-а → `_x402_paywall` пада към `:3526` без дори предизвикателство.

### 🟡 F-27 — `/api/connectors` разкрива hot wallet и вътрешен маршрут
`main.py:149` (безплатен) + `:3992-4007` (без auth). `connectors.py:988` — `"detail": f"payer wallet={wallet_addr}"` → **payer-side hot wallet** (страната, сдвоена с `WALLET_PRIVATE_KEY`), която кодът изрично разграничава от публичния fee receiver (`main.py:3793-3796`). `connectors.py:944-947` чрез `:980` → `f"...(gas={gas}) → CDP ({cdp}) → payai"`, т.е. дали `WALLET_PRIVATE_KEY` е зареден, здраве на CDP JWT/PEM и вътрешната settlement верига. Липсва в `_RATE_LIMIT_DEFAULTS` (`main.py:1406-1416`) и прави ES256 JWT на всяка заявка (`connectors.py:941-943`).

### 🟡 F-28 — Render конфигурацията не е версионирана
Проверено, не предположено: `render.yaml` липсва; не е в `git ls-files`; `git log --all -- render.yaml` е празно; `git grep "render.ya?ml"` → 0 попадения в tracked файлове. Единственото описание е проза (`DEPLOYMENT.md:95-96`, `DEPLOYMENT_CHECKLIST.md:36-37`), `Procfile:1` не се консумира от Render, а програмният деплой е 3 императивни скрипта, искащи `RENDER_API_KEY` от env или от untracked `secrets/render_api_key.txt`.
**Защо е security-значимо:** start командата, броят workers, health пътят и регионът живеят само в dashboard-а. Инвариантите на кода зависят от тях: `main.py:1404-1405` и `Dockerfile:45` предполагат **един** worker (in-RAM rate limiter, free-tier броячи, `_verified_payments` replay set на `main.py:2260`), а редакция в dashboard-а не оставя следа за review.

### 🟡 F-29 — Админ токенът пада към `SESSION_SECRET`
`main.py:1802-1813` връща `ADMIN_API_TOKEN`, иначе `SESSION_SECRET`; `main.py:178` вдига `SECRET_KEY` от същия `SESSION_SECRET`. Един секрет едновременно подписва session cookie-та и автентикира админ API-то. Коректността е ок (fail-closed, ако нищо не е зададено — `:1835`), а fallback-ът се предупреждава (`:1809-1812`), но не е фатален.

### 🟡 F-30 — Операторски скрипт принтира живи env стойности
`scripts/_t2_render_env_check.py:30-31` дефинира `watch = ("RPC", "CHUNK", ..., "ADMIN")`; `:35-36` принтира `f"  {k} = {e.get('value')}"`; `:45` принтира `startCommand`, `buildCommand`, `plan`, `region`, `numInstances`, `healthCheckPath` от живия сървис. Списъкът хваща `BASE_RPC_URL` (ключ на доставчик) и `ADMIN_API_TOKEN` (споделената админ парола) по име, а файлът е **tracked в git**.

### 🟡 F-31 / M6 — Админ brute-force лимит и XFF допускане
`main.py:1407` — `"admin_login": (20, 300)` (20 опита/5 min на IP, без lockout, без глобален брояч); ключът е `(scope, _get_client_ip())` (`:1434`). `main.py:174` — `ProxyFix(x_for=0)` → в продукция `request.remote_addr` е **винаги** частният адрес на Render прокси-то; следователно `if fwd and _is_private_or_loopback(peer):` (`:1391`) е **винаги истина** и „anti-spoofing" клонът, документиран на `:1386-1387`, е **недостижим** в продукция. Защитата разчита изцяло на това Render да добавя реалния клиентски IP **последен**. Регресионният тест покрива само публичния peer-клон (`tests/test_v6_launch.py:170` подава TEST-NET адрес). **Това изисква един live probe, за да се затвори.**

### 🟢 F-33 — `/validation` публикува живи платени адреси и остаряло число
`discovery.py:186-203` сервира статичен `recent_payments` списък с 4 реални сетълмента с `payer`, `amount_usdc` и пълен `tx` — данните на платения `/api/sales` — на **постоянно безплатна** страница; `:179-183` публикува `"passed": 550, "total": 550` с `last_run: 2026-10-30`.

### 🟢 F-34 / F-35 / F-36 / L2 / L4 / L7 — По-дребни
- **F-34:** `config.py:79` `KRISTO_WHALE_PRICE = 0.01` и `:78` `KRISTO_RUG_PRICE = 0.003` **не са** в `X402_PRICE_MAP` — консумирани само от мъртвия демо каталог. `docs/OUTREACH_KIT.md:20` още цитира Whale Flow „$0.01/call".
- **F-35:** `requirements.txt:33` има `cryptography>=42.0.0` (диапазон във файл, чието заглавие твърди „pinned"), а `cryptography` **липсва изцяло** в `requirements.lock`; lock-ът е без `--hash`. Продукцията инсталира `requirements.txt`, не lock-а (`DEPLOYMENT.md:95`). `requirements.txt:32` вкарва `pytest==9.1.1` в продукционния образ (`Dockerfile:22-25`).
- **F-36:** `docker-compose.yml:27` — `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-kristo_dev}` с `:31-32` `ports: "5432:5432"` и `env_file: .env` (`:43, :64`). Copy-paste деплой на non-localhost хост излага CRM БД-то (имейли, Stripe checkout id-та, суми) на `kristo:kristo_dev`.
- **L2:** `catalog_store.py:462-489` `grant_entitlement()` иска само `checkout_id` и валиден продукт; `_checkout_matches` (`:400-417`) **никога** не проверява `agent_checkouts.payment_status`. Днес няма жива експлоатация (единственият извикващ е подписаният webhook, зад `payment_status != "paid"` гейт), но всеки бъдещ извикващ може да издаде 30 дни достъп от неплатен checkout id.
- **L4:** `main.py:1319` (`_free_tier_usage`) и `:1345` (`_paid_calls_usage`) са IP-ключовани и **никога** не се prune-ват (само `_rate_limit_hits` се чисти на `:1443-1447`); `/api/leads` и `/api/funnel/track` приемат имейл с произволна дължина до 512 KB cap без ограничение в `LeadRecord`.
- **L7:** `glama-connector-claim.json` е committed и публично сервиран ownership токен (`discovery.py:822-832`) — умишлено (HTTP challenge), но подлежи на ротация след claim прозореца.
- **Хигиена на теста:** `tests/test_secret_hygiene.py:8-26` сканира само 5 поименно зададени файла с 5 regex-а; `ROOT` се изчислява на `:5`, но никога не се използва за откриване — затова **не може** да хване F-13, F-14 или F-30.

---

## 7. Документация, твърдения и хигиена на репото

### 7.1 Инвентар
`docs/` — **89 файла / 597 925 B (0.57 MB)**: 46 `.md`, 26 probe `.py`, 7 `.json`, 3 `.png`, 2 `.pdf`, 2 `.static`, 1 `.prisma`, 1 `.txt`, 1 `.js`. **75 tracked, 14 untracked** (вкл. `AP2_RADAR.md`, `BAZAAR_RESEARCH.md`, `GRANT_APPLICATION.md`, `HAIKU_AUDIT*.md`, `SCAN_LISTING_*.md`, `WATCH_LIST.md`, `monitor_state.json`, `glama_thumbnails/`). Остатък: `docs/evidence/pytest_cache/` — untracked, не е gitignored, ACL-недостъпен.

### 7.2 Проверка на публичните твърдения

| Твърдение | Присъда |
|---|---|
| „550 tests" (`README.md:105,115`) | ✅ **Потвърдено** — `550 passed in 180.46s` |
| MCP „3 инструмента" | ✅ **Потвърдено** — `discovery.py:508` `_mcp_tools()`: `get_market_stats` (`:522`), `get_onchain_sales` (`:541`), `get_bot_status` (`:561`). **Но:** вторият каталог (`/api/mcp/manifest`, `discovery.py:1061-1110`) нарича същия инструмент `get_sales_history` (`:1071`) — две каталог-дефиниции с различни имена за един рут |
| Цени „$0.003–$0.005" | ✅ **Потвърдено** за живата карта: стойности {0.003, 0.005} от `config.py:75-83` през `main.py:89-100`. ❌ Невярно в `docs/PRODUCT_AUDIT.md:43` и `docs/MYSTERY_AGENT_REPORT.md:23,26` ($0.05) |
| „35 scanning routes" | ❌ **Не съществува никъде в репото.** Реално 6 платени |
| Glama „A4.7" | ⚠️ **Вътрешно противоречиво** — `PROJECT_CHRONOLOGY.md:196`, `PROJECT_STATUS.md:526`, `weekly/2026-09-29.md:39` = 4.7, но `PROJECT_STATUS.md:1199,1204` и `PROJECT_CHRONOLOGY.md:128` = **A 3.6/5.0**. Низът `A4.7` се среща 0 пъти |
| „100% uptime (47 дни)" | ❌ **Не съществува** в репото (0 попадения) |
| „11 resources on x402scan" (`README.md:112`) | ⚠️ **Неверифицируемо локално**; кодът експонира **6** ресурса (`discovery.py:969-1007`) |
| …„zero payment incidents" (`README.md:111`) | ❌ **Невярно** — `PROJECT_STATUS.md:34-45` документира INCIDENT 14.09 (платени $0.003 → 401, без доставка); `TASK.md:43-44` го потвърждава |
| agentic.market #66, MCPso #5200, awesome-x402 PR #1308 | ⚠️ **#66 и #5200 не съществуват в репото**; #1308 е документиран като OPEN без review (`LISTING_CHANNELS_AUDIT.md:23,29,118`) |
| PulseMCP | ⚠️ `PULSEMCP_SUBMISSION_READY.md:9-17` — „**НЕ сме там**", подаванията са спрени. Всяко твърдение за присъствие е невярно |

### 7.3 Противоречия между документи (конкретни двойки)
1. **Брой платени рутове: 6 vs 5 vs 4 vs 3.** Истина = 6 (`main.py:89-100`; `tests/test_whaleflow.py:255`). `PROJECT_STATUS.md:27`/`TASK.md:19`/`weekly:38` = 6; `PRODUCT_AUDIT.md:9` = 5; `README.bg.md:206` = 4; `DISTRIBUTION_STATUS.md:11` = 3, докато собствената му таблица `:20-27` изрежда 4; `MYSTERY_AGENT_REPORT.md:18,21` = 3.
2. **Цена на `/api/sales`:** `config.py:76` = 0.005 vs `PRODUCT_AUDIT.md:43` и `MYSTERY_AGENT_REPORT.md:23,26` = 0.05.
3. **Праг за китове:** код = $5 000 000 (`dashboard_store.py:98`, `main.py:1514`) vs `WHALE_FLOW_SPEC.md:19` = $50 000.
4. **Цена на whale flow:** `config.py:83` = 0.003 vs `OUTREACH_KIT.md:20` = 0.01 (плюс осиротялото `config.py:79`).
5. **Glama: 4.7 vs A 3.6/5.0** (виж таблицата).
6. **PulseMCP път:** `DISTRIBUTION_STATUS.md:16` („PayAPI автоматично публикува") vs `PULSEMCP_SUBMISSION_READY.md:16-17` („все още не се е случило").
7. **Тестове: 8/8 → 17 → 77 → 152 → 154 → 164 → 410 → 422 → 426 → 550** в девет различни документа.
8. **„100% production-ready"** (`FINAL_STATUS.txt:5`, `PROJECT_COMPLETION_REPORT.md:4,11`, `TEST_REPORT_2026-08-17.md:5,100`) срещу **собствения** `CODE_AUDIT_REPORT.md:9-19` (Critical: неавтентикиран Stripe webhook, неавтентикирани админ endpoints, x402 bypass) и `PROJECT_STATUS_REPORT_2026-08-20.md:5` („Не е коректно да бъде обявен за „100% готов"").
9. **Стек/деплой:** `README.md:98`/`DEPLOYMENT.md:13` (Render, Flask) vs `ARCHITECTURE.md:1,20`/`QUICK_START.md:1-45`/`TEST_REPORT_2026-08-17.md:4` (**V5** sales engine) vs `PROJECT_STATUS_REPORT_2026-08-20.md:18` (Replit).
10. **`MYSTERY_AGENT_REPORT.md` е самоостарял:** `:18` „3 resources", `:23,26` $0.05 vs днес 6 ресурса и 0.005 — а `README.md:114` още цитира неговото „23/23".

### 7.4 Хигиена: какво не бива да стига до клиент или registry reviewer
**Tracked в git:**
- `CODE_AUDIT_REPORT.md` — първите пет находки са Critical/High дефекти (вкл. неавтентикиран Stripe webhook `:23-27` и x402 bypass през `Referer` `:15`). Даването му на reviewer е самоуличаващо.
- `PROJECT_STATUS.md` (271 953 B) — финансови вътрешности, адреси на платци, инцидентът от 14.09, бележки за ротация на секрети; `:20` обсъжда компрометирания `WALLET_PRIVATE_KEY` адрес.
- `docs/_origin_data.json`, `docs/_operator_fingerprint.json`, `docs/_recon_currency_api_7d.json`, `docs/_cadence_*.json` — on-chain проследяване на трети страни (35 payTo адреса, тотали по wallet).
- `docs/DASHBOARD_AUDIT.md:13` — документира, че `/nexus` показва **симулирани случайни данни като жива активност**.
- `FINAL_STATUS.txt`, `PROJECT_COMPLETION_REPORT.md`, `docs/TEST_REPORT_2026-08-17.md` — „100% production-ready / 8-8 теста", опровергани от по-късните одити.
- `docs/DISTRIBUTION_STATUS.md:66` — сочи читателя към `secrets/render_api_key.txt`.

**Untracked / на диска:**
- `kristo_paid_demo_clip.mp4` — **120 112 530 B (~114.5 MB)** + `_web.mp4` 19.9 MB + `preview.jpg` 583 KB (gitignored, но на диска в проектна папка).
- `ops/kristo-intelligence-6-main.zip` — 885 327 B, пълен source snapshot (проверен: 272 записа, **без** `.env`/ключове вътре, но съдържа `PROJECT_STATUS.md`, `CODE_AUDIT_REPORT.md`, `FINAL_STATUS.txt` и целия `docs/`).
- `commit_54a7ba3_full.txt` / `_diff_only.txt` (38.5/38.2 KB), `main_py_diff.txt`, `main_py_full_diff.txt`, `temp_*.log`, `server_err.log`, `server_out.log`.
- **`.kilo/worktrees/believed-dancer/`** — пълно **второ копие** на репото (`main.py` 242 907 B, `dashboard_store.py` 118 472 B, …), detached HEAD `d08748f`. Игнорирано само през `.git/info/exclude:9` — **локално**, а не в `.gitignore`; всяко сканиране на диска дава сдвоени резултати (затова и инвентарът на `.py` е 345, а не ~176). Риск: редакция на грешното копие.
- `docs/monitor_state.json` — untracked и **не** игнориран → влиза с `git add -A`.
- `kristo-intelligence/` (`.clinerules/`, `.specify/`, `specs/`) — untracked speckit скеле.

**Git състояние:** 29 записа в `git status --porcelain` (untracked `.mcp.json`, `TASK.md`, diff-файлове, 10 `docs/` файла, `scripts/_*.py`, `kristo-intelligence/`) — локална работа, която **не е комитвана**. 351 комита, първи 2026-08-19, последен 2026-11-02.

---

## 8. Приоритизиран план за действие

> Всичко по-долу е **предложение**. Нищо не е прилагано. Промени в продукция минават през вратата „push = авто-деплой".
> **Непокътнати инварианти:** x402 хедъри и структура на плика, `payTo`/`X402_RECEIVER_ADDRESS`, цените в `config.py`, `/.well-known/x402-trust.txt`, `secrets/` и `.env`.

### P0 — блокиращи за бизнес модела (без тях таксуването е декоративно)
1. **F-01 — премахни огледалото на платените данни.** Реши кое поле реално се продава и го махни от публичния read model на `/api/dashboard-stats` и `/api/dashboard/data` (история с `tx_hash`+`sender`, `whales`, market snapshot). Алтернатива: dashboard payload зад админ/session обхват. Това е продуктово решение — paywall-ът не може да се „поправи" при налично безплатно копие.
2. **F-02 — верифицирай подписаната стойност.** Извличай amount-а **само** от `auth.value`; отказвай при несъответствие с `accepted.amount`; отказвай нечислови amount-и вместо да прескачаш проверката; препрочети сумата на `Transfer` от receipt-а преди грант (adoption пътят вече го прави правилно на `main.py:2419-2421`).
3. **F-03 — махни fail-open при нечетим receipt.** Една изрична политика: fail-closed след poll-а (401/425 с tx hash, както прави in-flight клонът `main.py:3144-3157`), или override само с независимо потвърждение. Никога не позволявай **изключение** в confirmation проверката да води до доставка.
4. **F-04 — махни записа от read пътя.** `guard_stats()` не трябва да прави INSERT/DELETE; пробата за живост се мести в background цикъла, а рутът чете последния резултат (и получава кеширан read model).
5. **F-05 + F-06 — реши семантиката на реорг.** Минимум: маркирай `onchain_sales` реда като `reorged` и го изключи от тоталите; добави проверка за дълбочина на adoption пътя по nonce.
6. **F-07 — rate limit/budget по платежния път** (per IP и per signer), pre-check на USDC баланса на купувача преди broadcast, и изнеси сетълмента извън request нишката.

### P1 — стабилност и изтичане на информация
7. **F-22 + F-31** — един кеширан read model с single-flight за `/api/dashboard/data`, `/api/dashboard-stats` **и** платения `/api/stats`; индекси по `request_log(user_agent)`, `(source)`, `(funnel)`; агрегирай `payment_guards` в SQL и индексирай `consumed_at`.
8. **F-09** — `psycopg_pool` + `connect_timeout` + `statement_timeout`; престани да държиш един глобален lock върху една споделена връзка (`dashboard_store.py:624` вече показва правилния модел).
9. **F-10** — `/health` да е чисто liveness (без DB); readiness отделно.
10. **F-11** — изолирай и ограничи `/mcp/sse` (кап на едновременни сесии + rate limit).
11. **F-23 + F-24 + F-25** — ограничи всеки блокиращ бюджет по платения път; задай явни timeout-и на Stripe (и `max_network_retries=0` за request-path); обвий тялото на `_stripe_payment_snapshot_loop` в `try/except`.
12. **F-08 + F-12** — списък от RPC доставчици с health ротация + process-wide cooldown с `Retry-After`; един ограничен reorg watcher с опашка вместо нишка на плащане; чанкни `getLogs` през вече съществуващия `_adaptive_get_logs`.
13. **F-13 + F-14 + F-15 + F-30** — приложи `redact_rpc()` на `main.py:643`; редактирай Telegram токена преди логване; добави `secrets/` и `*.mp4` в `.dockerignore`; маскирай env стойностите в `_t2_render_env_check.py`. Разшири `tests/test_secret_hygiene.py` да **открива** файлове, вместо да проверява 5 поименно зададени.
14. **F-26 + F-27** — админ guard за `/api/launch/health`; махни `payer wallet=`, `gas=` и CDP детайла от публичния `/api/connectors`.
15. **F-28 + F-29** — комитни `render.yaml` (или изрично документирай дрейфа и фиксирай `--workers=1`); изисквай `ADMIN_API_TOKEN` в продукция вместо тихо преизползване на `SESSION_SECRET`.
16. **F-21** — задай и документирай `KRISTO_FREE_TIER_LIMIT=0` в `.env.example`; изнеси броячите в durable store.

### P2 — документация и хигиена
17. **F-19 + F-20 + F-32 + F-34 + F-37** — един аксесор над `X402_PRICE_MAP`/`REAL_X402_ROUTES` за **всички** рекламни повърхности (моделът на `discovery.py:950-956` вече е верен); реши съдбата на $29 VIP (Telegram продукт или API entitlement); тест за `REAL_X402_ROUTES ⊆ X402_PAID_ENDPOINTS`; махни мъртвите цени; премести отстъпката в `config.py` с assert.
18. **F-33** — махни суровите платец-адреси от `/validation` и избери едно число за тестовете.
19. **Документация** — прочети първо `TASK.md` (единственият onboarding бриф с верни оперативни факти; untracked, затова `git add` + опресняване). Пренапиши: `README.md` (махни „zero payment incidents"; оправи „550 tests"; маркирай „11 resources" като индекс на x402scan, не факт за репото), `DISTRIBUTION_STATUS.md` (§1 vs §2 брой рутове; PulseMCP), `MYSTERY_AGENT_REPORT.md` (датирай или пре-изпълни), `VISIBILITY_PLAN.md` (mojibake + остарелия #12799), `OUTREACH_KIT.md:20`. Архивирай V5 документите (`ARCHITECTURE.md`, `QUICK_START.md`, `TEST_REPORT_2026-08-17.md`, `DASHBOARD_AUDIT.md`, `PRODUCT_AUDIT.md`, `LISTING_CHANNELS_AUDIT.md`, `MCP_*`), както и `docs/evidence/probes/`. Изтрий `FINAL_STATUS.txt`, `PROJECT_COMPLETION_REPORT.md`, diff-файловете, `temp_*.log`, `server_*.log`. Премести извън репото (непубликуемо): `PROJECT_STATUS.md`, `CODE_AUDIT_REPORT.md`, `TASK*.md`, `docs/_*.json`, `docs/DASHBOARD_AUDIT.md`, `docs/DISTRIBUTION_STATUS.md`.
20. **Хигиена на диска** — изтрий/премахни `.kilo/worktrees/believed-dancer` (второ копие на репото) или го добави в `.gitignore`; gitignore-ни `docs/monitor_state.json`; реши какво да е с ~134 MB видео артефакти.
21. **F-35 + F-36** — регенерирай `requirements.lock` от `requirements.txt` с `--hash`, отдели dev/test зависимости, пинни `cryptography`; вържи compose Postgres на `127.0.0.1` и махни подразбиращата се парола.

---

## 9. Методология, ограничения и какво остава непроверено

**Как е правен одитът:** инвентар през PowerShell (read-only), целеви `grep`/четене с номера на редове, AST-анализ на `main.py`, `EXPLAIN QUERY PLAN` + тайминги върху локалната SQLite БД (read-only, `mode=ro&immutable=1`), изолирани измервания на студен импорт, четене на инсталирания Stripe SDK, пълен пробег на тестовете.

**Измерено първоначално:**
- ✅ `550 passed, 1 warning in 180.46s` (пълен пробег в `venv`, Python 3.12.10, pytest 9.1.1).
- ✅ 46 301 реда `request_log`; 12 заявки на `requests_summary` = **528.22 ms**, 5 пълни сканирания.
- ✅ Студен импорт: `web3` 3.832 s, `stripe` 0.963, `psycopg` 0.934, `telegram` 0.935, `flask` 0.655; модулният сет на `main.py` 1.27-1.37 s.
- ✅ `main.py` = 5859 реда (CRLF), 140 top-level функции, **0 дублирани имена**.
- ✅ Stripe SDK: `timeout = 80`, `max_network_retries = 2`.
- ✅ Липса на `render.yaml`, `app.py`, `mcp_server.py`, `auth.py`, `guard.py`, `gas.py`, `facilitator.py`, `rpc.py` — потвърдено с търсене в цялото репо.

**Изведено от кода (не измерено в продукция):** RPC/час и backfill аритметиката, оценките за CoinGecko/DexScreener, „~40 s worst case" за платен сигнал, „~41 s / ~783K реда" (цитат от коментар в `main.py:3944-3945`).

**Непроверено / ограничения:**
1. **`.env` и `secrets/` не са отваряни** (изрично ограничение). Затова е неизвестно дали в продукция са зададени `KRISTO_FREE_TIER_LIMIT=0`, `WALLET_PRIVATE_KEY`, `DATABASE_URL`, `KRISTO_DISABLE_BACKGROUND_THREADS`, `FACILITATOR_CDP_*`. Част от находките (F-02, F-07, F-15, F-21, F-28) зависят от тези стойности.
2. **Няма мрежови проверки** — Glama, x402scan, PayAPI, Smithery, PulseMCP, GitHub PR-ове остават UNVERIFIABLE; поведението на живите facilitator-и (сравняват ли подписаната стойност) също е ненаблюдавано.
3. **X-Forwarded-For семантиката на Render** (F-31/M6) изисква един live probe, за да се определи дали админ лимитът и free tier-ът са заобиколими.
4. **Продукционната Postgres план-карта** и реалните бройки редове не са възпроизведени — няма достъп до живата БД.
5. `main.py` **не е изпълняван** (импортът му пише в `data/dashboard_state.db`), затова стартовото време и шевът между `after_request` куките са изведени от кода, не премерени край-до-край.
6. Два независими анализатора дадоха различна оценка за RPC натоварването (480/час vs ~2 700/час); представени са и двете с изрична бележка.

---

## 10. Приложение A — Пълен инвентар на рутовете

### `main.py` (44 `@app.route`)
`/.well-known/x402-trust.txt`:2223 · `/f/<channel>`:2242 · `/api/arb/opportunities`:3549 · `/api/sales`:3582 · `/api/admin/seed-sales`:3823 · `/public/signals/history`:3912 · `/api/dashboard-stats`:3986 · `/api/connectors`:3992 · `/api/v1/quickstart`:4010 · `/api/stats`:4067 · `/api/bot-status`:4074 · `/api/telegram-webhook`:4089 · `/`:4152 · `/launch`:4182 · `/sales/checkout`:4188 · `/api/leads`:4299 · `/api/checkout`:4330 · `/api/v1/signal`:4389 · `/api/v1/agents`:4481 · `/api/v1/agents/<agent_id>`:4491 · `/api/v1/agents/<agent_id>/playground`:4500 · `/agents`:4537 · `/api/v1/agents/<agent_id>/click`:4543 · `/api/v1/agents/<agent_id>/checkout`:4561 · `/api/v1/agents/<agent_id>/access`:4624 · `/api/webhooks/stripe`:4708 · `/api/sales/summary`:4868 · `/api/admin/leads`:4890 · `/api/admin/overview`:5057 · `/api/admin/catalog-metrics`:5066 · `/api/v1/research/ingest`:5075 · `/api/admin/research-insights`:5102 · `/api/admin/research-insights/<insight_id>`:5118 · `/sales/admin/login`:5140 · `/admin/login`:5141 · `/sales/admin/logout`:5160 · `/sales/admin`:5166 · `/sales/admin/research`:5186 · `/api/launch/health`:5198 · `/api/funnel/track`:5219 · `/api/dashboard/data`:5573 · `/api/v1/whaleflow`:5585 · `/dashboard`:5642 · `/nexus`:5655

### `app/blueprints/discovery.py` (26 рута)
`/health`:32 · `/validation`:79 · `/api/v1/signal/sample`:356 · `/api/stats/sample`:399 · `/api/v1/whaleflow/sample`:420 · `/api/sales/sample`:444 · `/api/bot-status/sample`:466 · `/api/arb/opportunities/sample`:486 · `/mcp/sse`:670 · `/mcp/message`:720 · `/mcp` (POST/DELETE):742 · `/mcp` (GET):766 · `/glama.json`:804 · `/.well-known/glama.json`:822 · `/api/mcp/manifest`:835 · `/.well-known/x402.json`:914 · `/.well-known/x402`:922 · `/mcp.json`:1026 · `/openapi.json`:1127 · `/favicon.ico`:1358 · `/favicon.svg`:1359 · `/robots.txt`:1374 · `/sitemap.xml`:1387 · `/agents.json`:1416 · `/.well-known/ai-plugin.json`:1485 · `/llms.txt`:1536

### Платен allow-list (`main.py:137-139`) — 6 рута
`/api/sales` · `/api/stats` · `/api/bot-status` · `/api/arb/opportunities` · `/api/v1/signal` · `/api/v1/whaleflow`

### Меродавни константи
`FREE_TIER_LIMIT` = `KRISTO_FREE_TIER_LIMIT` (default **1**) `main.py:134` · `X402_PAID_ENDPOINTS` 6 · `X402_FREE_ENDPOINTS` 27 · `STATS_CACHE_TTL_SECONDS` 60 `main.py:3951` · `BLOCKCHAIN_POLL_INTERVAL` 30 `main.py:692` · `KRISTO_DASHBOARD_SCAN_INTERVAL` 60 `main.py:1133` · `WHALEFLOW_SCAN_INTERVAL` 60 `main.py:1219` · `AGENT_POLL_INTERVAL` 300 `main.py:1059` · `KEEPALIVE_INTERVAL_SECONDS` 600 `main.py:5681` · `SCAN_INTERVAL` (arb) 60 `arb_radar.py:27` · `SALES_CHUNK_BLOCKS` 5000 `dashboard_store.py:2117` · `WHALEFLOW_CHUNK_BLOCKS` 100 `:2276` · `WHALEFLOW_BACKFILL_HOURS` 24 `:106` · `WHALE_THRESHOLD_USDC` 5 000 000 `:98` · `C2_LAG_WAIT_SECONDS_DEFAULT` 2.5 `main.py:2528` · `FACILITATOR_TIMEOUT` 15 `connectors.py:47` · `BASE_RPC_URL` default `https://mainnet.base.org` `config.py:57`.

---

*Отчетът е генериран на 2026-11-03 при HEAD `66a0ce4`. Всички номера на редове се отнасят за това ревизионно състояние.*
