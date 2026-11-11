# AP2 RADAR — какво се промени от миналия път

Проверено: 2026-11-11 18:00 UTC · read-only, публични артефакти, без идентичности.

## Промени по мониторирани repos

### google-agentic-commerce/AP2

- Няма нови комити от миналата проверка.


### google-agentic-commerce/a2a-x402

- Няма нови комити от миналата проверка.


### Merit-Systems/x402scan

- `20bba0ff30` 2026-08-24 — remove trpc routers
  - файл: apps/scan/src/trpc/routers/public/facilitator-observability.ts
  - файл: apps/scan/src/trpc/routers/public/index.ts
  - файл: apps/scan/src/trpc/routers/public/observability.ts
  - файл: pnpm-lock.yaml
- `37c10ade3a` 2026-08-24 — remove upsert from proxy
  - файл: apps/proxy/.env.example
  - файл: apps/proxy/package.json
  - файл: apps/proxy/src/routes/proxy.ts
  - файл: apps/proxy/src/server.ts
- `80b9f357b1` 2026-08-24 — remove db from the scan and admin
  - файл: apps/scan/package.json
  - файл: apps/scan/src/app/(app)/_contexts/sorting/resource-search/context.ts
  - файл: apps/scan/src/app/(app)/admin/resource-search/_components/table/columns.tsx
  - файл: apps/scan/src/app/(app)/admin/resource-search/_components/table/results-table.tsx
  - файл: apps/scan/src/env.ts
  - файл: apps/scan/src/services/resource-search/clickhouse-search.ts
- `b305581faa` 2026-08-24 — remove trigger job and delete clickaus db since it is no longer used
  - файл: .changeset/config.json
  - файл: .changeset/pre.json
  - файл: .github/workflows/deploy-analytics.yml
  - файл: knip.config.ts
  - файл: package.json
  - файл: packages/internal/databases/analytics/.gitignore
- `4b29346e90` 2026-08-24 — Merge pull request #1096 from Merit-Systems/aec/cleanup-db
  - файл: .changeset/config.json
  - файл: .changeset/pre.json
  - файл: .github/workflows/deploy-analytics.yml
  - файл: apps/proxy/.env.example
  - файл: apps/proxy/package.json
  - файл: apps/proxy/src/routes/proxy.ts
- `f6fc282bf5` 2026-08-25 — Merge remote-tracking branch 'origin/main' into feat/svm-channel-schemes-indexing
  - файл: .changeset/config.json
  - файл: .changeset/pre.json
  - файл: .github/workflows/deploy-analytics.yml
  - файл: .oxlintrc.json
  - файл: apps/proxy/.env.example
  - файл: apps/proxy/package.json
- `32249e1c59` 2026-08-25 — chore(svm): type payout extractor input structurally, run sync tests in CI
  - файл: package.json
  - файл: sync/transfers/scripts/probe-channels.ts
  - файл: sync/transfers/test/channels-query.test.ts
  - файл: sync/transfers/trigger/chains/solana/bitquery-channels/query.ts
- `ab37d7322d` 2026-08-25 — fix(svm): track a sync-state cursor for the channels sync
  - файл: sync/transfers/trigger/chains/solana/bitquery-channels/config.ts
  - файл: sync/transfers/trigger/sync.ts
- `e2526d65fe` 2026-08-25 — Merge pull request #1091 from lgalabru/feat/svm-channel-schemes-indexing
  - файл: package.json
  - файл: packages/internal/databases/transfers/prisma/migrations/20260821000000_transfer_event_scheme/migration.sql
  - файл: packages/internal/databases/transfers/prisma/schema.prisma
  - файл: pnpm-lock.yaml
  - файл: sync/transfers/db/services.ts
  - файл: sync/transfers/package.json
- `f1f3428e5c` 2026-09-01 — Remove unused example servers and evals
  - файл: .changeset/config.json
  - файл: evals/.gitignore
  - файл: evals/README.md
  - файл: evals/fixtures/express-openapi/package.json
  - файл: evals/fixtures/express-openapi/server.js
  - файл: evals/fixtures/next-wellknown/app/.well-known/x402/route.js
- `3700a520dc` 2026-09-01 — Merge pull request #1130 from Merit-Systems/json/remove-example-servers-and-evals
  - файл: .changeset/config.json
  - файл: evals/.gitignore
  - файл: evals/README.md
  - файл: evals/fixtures/express-openapi/package.json
  - файл: evals/fixtures/express-openapi/server.js
  - файл: evals/fixtures/next-wellknown/app/.well-known/x402/route.js
- `dbe073f50d` 2026-09-16 — better warnings ← КЛЮЧОВИ ДУМИ: discovery
  - файл: apps/scan/src/app/(app)/(home)/resources/register/_components/form.tsx
  - файл: apps/scan/src/app/(app)/_components/discovery/discovery-actions.tsx
  - файл: apps/scan/src/app/(app)/_components/discovery/discovery-panel.tsx
  - файл: apps/scan/src/lib/discovery/favicon-blocked.test.ts
  - файл: apps/scan/src/lib/discovery/favicon-blocked.ts
  - файл: apps/scan/src/lib/discovery/server-host-mismatch.test.ts
- `131a5d3ca9` 2026-09-16 — rm cal link
  - файл: apps/scan/src/app/(app)/(home)/resources/register/_components/form.tsx
- `c0c178675c` 2026-10-14 — rm cal link from register support links
  - файл: apps/scan/src/app/(app)/(home)/resources/register/page.tsx
- `5732bb83c8` 2026-10-14 — fix build: use <a> for mailto link (typedRoutes rejects string href)
  - файл: apps/scan/src/app/(app)/(home)/resources/register/_components/form.tsx


### developerfred/x402-conformance-probe

- `e6904c30d5` 2026-11-02 — feat: x402 conformance probe with 20 endpoints, fixtures, report, test endpoint, and paid retry
  - файл: .gitignore
  - файл: REPORTED.md
  - файл: discover.ts
  - файл: endpoints-discovered.json
  - файл: fixtures/averray-verify-verify-runs.json
  - файл: fixtures/browserbase-x402-endpoint.json
- `25883ed0b0` 2026-11-02 — feat: add REPORTED.md with issue links for all defects
  - файл: REPORTED.md
- `9918c61ab1` 2026-11-02 — feat: expand to 30 endpoints, add response time/body size columns, CI workflow, Vercel deploy
  - файл: .github/workflows/conformance.yml
  - файл: .gitignore
  - файл: fixtures/averray-verify-verify-runs.json
  - файл: fixtures/browserbase-x402-endpoint.json
  - файл: fixtures/coinmarketcap-dex-search.json
  - файл: fixtures/exa-search-api.json
- `e0fb7d3161` 2026-11-02 — feat: add landing page and vercel config so production site has full documentation
  - файл: index.html
- `8344b30a8b` 2026-11-02 — feat: track vercel.json in repo (remove from gitignore)
  - файл: .gitignore
  - файл: vercel.json
- `8d9bf500bc` 2026-11-02 — feat: melhorar diagramação do REPORTED.md e templates de issue no GitHub
  - файл: .github/ISSUE_TEMPLATE/config.yml
  - файл: .github/ISSUE_TEMPLATE/x402-conformance-defect.md
  - файл: REPORTED.md
  - файл: discover-all.ts
  - файл: endpoints-discovered.json
  - файл: generate-config.ts


### alchemyplatform/alchemy-x402

- `1cf2ff51ae` 2026-03-10 — Merge branch 'main' into chris/architecture-required
  - файл: .changeset/config.json
  - файл: .changeset/switch-changelog-github.md
  - файл: .github/workflows/publish.yml
  - файл: CHANGELOG.md
  - файл: MAINTAINERS.md
  - файл: package.json
- `99aa16e2b4` 2026-03-10 — Merge pull request #24 from alchemyplatform/chris/architecture-required
  - файл: README.md
- `fdd3b3934d` 2026-03-11 — gp/revert changes - i give up for now (#36)
  - файл: .github/workflows/publish.yml
  - файл: package.json
- `2960f9edef` 2026-03-11 — chore: add changeset for v0.6.3 (#37)
  - файл: .changeset/update-readme-solana-support.md
  - файл: .claude/skills/changeset/SKILL.md
  - файл: MAINTAINERS.md
- `a6337cf358` 2026-03-11 — chore: release v0.6.3
  - файл: .changeset/update-readme-solana-support.md
  - файл: CHANGELOG.md
  - файл: package.json
- `a4b4575e38` 2026-03-11 — chore: add husky pre-commit hook with lint-staged (#38)
  - файл: .husky/pre-commit
  - файл: package.json
  - файл: pnpm-lock.yaml
- `d6527e270e` 2026-03-11 — fix(ci): restore GitHub release creation in publish workflow (#39)
  - файл: .changeset/fix-github-release.md
  - файл: .github/workflows/publish.yml
- `24e04a21eb` 2026-03-11 — chore: release v0.6.4
  - файл: .changeset/fix-github-release.md
  - файл: CHANGELOG.md
  - файл: package.json
- `fef4a164ec` 2026-03-11 — fix(ci): upgrade GitHub Actions to Node.js 24-compatible versions (#40)
  - файл: .github/workflows/ci.yml
  - файл: .github/workflows/publish.yml
- `b88e5d2c09` 2026-03-11 — gp/test OIDC again (#41)
  - файл: .changeset/puny-doodles-thank.md
  - файл: .github/workflows/publish.yml
- `9f40ecd33e` 2026-03-11 — chore: release v0.6.4
  - файл: .changeset/puny-doodles-thank.md
- `97584c3122` 2026-03-11 — fix: add missing version bump and validate changeset files in CI (#42)
  - файл: .changeset/fix-missed-version-bump.md
  - файл: .github/workflows/ci.yml
- `34163bc903` 2026-03-11 — chore: release v0.6.5
  - файл: .changeset/fix-missed-version-bump.md
  - файл: CHANGELOG.md
  - файл: package.json
- `3c691c6580` 2026-03-11 — fix: add repository URL to package.json for npm provenance verification (#43)
  - файл: .changeset/fix-repository-url.md
  - файл: package.json
- `b5253ae81d` 2026-03-11 — chore: release v0.6.6
  - файл: .changeset/fix-repository-url.md
  - файл: CHANGELOG.md
  - файл: package.json


### tanaka-77/mart402-agent-kit

- `d8884449d5` 2026-07-22 — Initial commit
  - файл: LICENSE
  - файл: README.md
- `d58c305a44` 2026-07-22 — Create pay_and_parse.py
  - файл: examples/python/pay_and_parse.py
- `eaa122b2e8` 2026-07-22 — Create extract.ts
  - файл: examples/typescript/extract.ts
- `4809a6f695` 2026-07-22 — Create config.json
  - файл: examples/mcp/config.json
- `bf9ea7c93d` 2026-07-22 — Create selftest.yml
  - файл: .github/workflows/selftest.yml
- `d5800b9f65` 2026-07-22 — Update README.md
  - файл: README.md


### node4dev/x402-agent-toolkit

- `26ff86cf8d` 2026-04-19 — Initial commit
- `753973ea1d` 2026-04-22 — feat: full rewrite for x402 v2 (v0.1.1)
- `e5a1d938d3` 2026-04-22 — docs: trim README for public repo
- `5403073e76` 2026-04-22 — feat: accept PRIVATE_KEY with or without 0x prefix
- `31ce483671` 2026-04-25 — updated with additional tool
  - файл: README.md
  - файл: package.json
  - файл: src/index.ts
  - файл: src/tools/x402Quote.ts
  - файл: src/tools/x402Request.ts
- `a15366a2bb` 2026-04-25 — Merge pull request #1 from node4dev/feat/x402-quote-tool
  - файл: README.md
  - файл: package.json
  - файл: src/index.ts
  - файл: src/tools/x402Quote.ts
  - файл: src/tools/x402Request.ts


### haoruilee/awesome-agent-native-services

- (API грешка: HTTP 403)


### Drudley/indexagentica

- (API грешка: HTTP 403)


### Nikolife2016/pulsefeed-x402

- (API грешка: HTTP 403)


## Разговорът (issues и PR-и, обновени от миналия път)

### google-agentic-commerce/AP2

- (API грешка: HTTP 403)

### google-agentic-commerce/a2a-x402

- (API грешка: HTTP 403)

### Merit-Systems/x402scan

- (API грешка: HTTP 403)

### developerfred/x402-conformance-probe

- (API грешка: HTTP 403)

### alchemyplatform/alchemy-x402

- (API грешка: HTTP 403)

### tanaka-77/mart402-agent-kit

- (API грешка: HTTP 403)

### node4dev/x402-agent-toolkit

- (API грешка: HTTP 403)

### haoruilee/awesome-agent-native-services

- (API грешка: HTTP 403)

### Drudley/indexagentica

- (API грешка: HTTP 403)

### Nikolife2016/pulsefeed-x402

- (API грешка: HTTP 403)

## Нови публични WG repos (търсене при всяка проверка)

- Нищо ново публично по WG патерните.

## Цензус серия (растеж през месеците)

- Още няма публикуван цензус в мониторирани repos.

## СЪБИТИЯ (дневник · дата на публикуване + източник)

### 2026-08-19 — Stripe придобива OpenRouter — marketplace за pay-per-use AI API-та

- **Публикувано:** 2026-08-19 · **записано в радара:** 2026-09-14
- **Какво:** Stripe обявява, че купува OpenRouter (единен вход към стотици модели на цена на токен). Проверено на 14.09 в ДВА независими публични източника; и двата дават 19.08.2026 (датата на публикуване, не на забелязване).
- **СИГНАЛ:** микро-платените API-та стават стратегическа суровина, а разплащането на микросуми — инфраструктурен слой, който гигант купува, вместо да строи. Подкрепя тезата на проекта: agentic/micro-payments са входа към новите пазари.
- **Източник:** stripe.com/newsroom — „Stripe agrees to acquire OpenRouter to help businesses optimise token routing and usage“; openrouter.ai/blog — „OpenRouter is Joining Stripe“

### 2026-09-18 — Solvador — confidential settlement върху x402 (Slack #general)

- **Публикувано:** 2026-09-18 · **записано в радара:** 2026-09-18
- **Какво:** Собственикът съобщава за Solvador — проект за **confidential settlement**. Датата е от дневния дайджест на #general, подадена от собственика; аз не съм я проверявал в публичен източник (каналът е частен и не се сканира).
- **СИГНАЛ:** Trust-слоят (ниша №2) получава още един строител. Влиза в **конкурентната карта за №2** — наблюдаваме, без реакция.
- **Източник:** x402 Slack #general (частен) — дневен дайджест от собственика

### 2026-09-18 — „402 Wall“ (Sergei) — trust/visibility проект (Slack #general)

- **Публикувано:** 2026-09-18 · **записано в радара:** 2026-09-18
- **Какво:** Проект на Sergei с фокус trust/visibility („402 Wall“), споделен в #general. Пак по дайджеста на собственика, не проверено публично.
- **СИГНАЛ:** Втори независим строител в trust/visibility слоя — същата ниша като нашата, различен ъгъл. Наблюдаваме.
- **Източник:** x402 Slack #general (частен) — дневен дайджест от собственика

### 2026-09-18 — Dr J — code402 + live MCP endpoint + x402-conformance (безплатен offline верификатор)

- **Публикувано:** 2026-09-18 · **записано в радара:** 2026-09-18
- **Какво:** Dr J показва code402, работещ MCP endpoint и **x402-conformance** — БЕЗПЛАТЕН **offline верификатор на разписки** (receipts).
- **СИГНАЛ:** Потенциален **ПАРТНЬОР за cross-check**: независим верификатор на разписки е точно това, което прави нашите 4 одита проверими отвън. Предложението за cross-check **вече е направено в нашия отговор** в #general.
- **Източник:** x402 Slack #general (частен) — нашият отговор към Dr J, подаден от собственика

### 2026-09-18 — Brickken dev challenge — отбелязано за по-късно

- **Публикувано:** 2026-09-18 · **записано в радара:** 2026-09-18
- **Какво:** Обявен dev challenge от Brickken (дайджест на #general, от собственика).
- **СИГНАЛ:** Отбелязано, БЕЗ ангажимент: възможен **RWA сегмент** — за по-късен етап, не е приоритет сега.
- **Източник:** x402 Slack #general (частен) — дневен дайджест от собственика

### 2026-09-18–2026-09-23 — x402 Slack #general (18–23.09): Мигел прие методологията · нови x402 продавачи · discovery/metadata позициониране

- **Публикувано:** 2026-09-18–2026-09-23 · **записано в радара:** 2026-09-27
- **Какво:** (1) Мигел публично прие методологията + покана за крос-проверка при следващо тяхно плащане (23.09); (2) нови x402 продавачи: PipeForge Inspector (Algorand+Bazaar), Berneta Price Watcher ($0.02/call, Base+Bazaar+x402scan), Алекс OpenChatNet ($1/24ч, agent chat rooms) — пазарът се населява, цените наоколо 5-300× нашите; (3) discovery/metadata позиционирането е активна тема — аудитория за Outreach вълна 1.
- **СИГНАЛ:** Извод: вратата е точно тази стая, времето е след merge+гейт.
- **Източник:** x402 Slack #general (частен) — дайджест от собственика, период 18–23.09

### 2026-09-27 — Външен сигнал: концепцията „Intelligence Contract“ в AI автоматизация кръгове

- **Публикувано:** 2026-09-27 · **записано в радара:** 2026-09-27
- **Какво:** Концепцията „Intelligence Contract“ (информационен vs автономен; толерантност калибровка; explicit decision rights) циркулира в AI автоматизация кръгове. НАШЕТО СЪОТВЕТСТВИЕ: 425 кодът, fail-closed калибровката, F4 retry правото, guard-methodology = разпръснати парчета от точно този документ.
- **СИГНАЛ:** Ниша за вълна 3: „Intelligence Contract за x402 плащания“ — methodology v2. Не се строи сега; записва се и чака първите оператор deals като доказателство, че продаваме от опит, не от теория.
- **Източник:** Външен сигнал, подаден от собственика (AI автоматизация кръгове) — не е публичен артефакт с URL, не проверяван публично

## ТЕРМОМЕТРИ (ръчно поддържани — вече в шаблона, за да не се губят при презаписване)

1. Реален дневен x402 обем: **~$28k/ден** (външни данни, 13.09) — бележка: **за ревизия** (източникът и методът на измерване не са проверени).
2. Флаг — първи публичен провал/скандал в agent payments: **не е наблюдаван** (13.09).
3. Флаг — регулаторен документ за agent payments: **не е наблюдаван** (13.09).
4. Trust-слой (ниша №2): **3+ независими строителя** — Solvador (confidential settlement), „402 Wall“ (Sergei), Dr J (code402 + x402-conformance) — 18.09, x402 Slack #general. **Извод: фазата е потвърдена.** Нашето преимущество остава непроменено: **публикуваният метод + 4-те одита + работещ касов път**.

## ИНДЕКСИРАНЕ — появяваме ли се в публичните x402 индекси?

| Дата | Индекс | Общо записи | Наши записи |
|---|---|---|---|
| 2026-09-15 | Coinbase bazaar discovery (canonical) | 16035 | 0 |
| 2026-09-15 | x402scan | n/a | origin page exists, 0 resources shown |

- **Coinbase bazaar discovery (canonical) (2026-09-15):** Търсено по хост в целия индекс — нула наши ресурси. 402-та ни носи extensions.bazaar, а последният сетълмент дойде през външен facilitator (relayer 0x64cc42b1…). Механизмът, по който индексът се пълни от сетълменти, НЕ е публично документиран — не се измисля, само се наблюдава.
- **x402scan (2026-09-15):** /server/<host> отговаря 200 (познати сме като origin), но ресурсите се зареждат client-side и не се виждат в payload-а. Регистрацията иска SIWX подпис; четящите API-та са платени. Действие за собственика: /resources/register с портфейл.

Метод (фиксиран, за да е сравнимо): Coinbase bazaar — `GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources`, търси нашия хост в `items[].resource`. Регистрация в x402scan — от браузър с портфейл (SIWX подпис), един `register-origin` регистрира всичките ни ресурси.

---
Slack каналите (wg-tax, wg-domain-discovery) са ЧАСТНИ и НЕ се
сканират — чете ги собственикът на око, месечно.
