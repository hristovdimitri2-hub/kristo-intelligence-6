# ОДИТ: Канали за листинг (07.09, само четене)

Одит с четене на документи + живи проверки (GitHub API, Glama, GitHub web).
Нула промени по кода. payTo/endpoint недокоснати. 164/164 PASS.

## 1. Инвентар: PR-и — точни номера и статуси (GitHub API, 07.09)

| PR | Къде | Статус (точно) | Отворен | Затворен | Защо/от кого |
|---|---|---|---|---|---|
| **#11557** „Add Kristo Intelligence — DeFi intelligence MCP server" | punkpeye/awesome-mcp-servers | **ЗАТВОРЕН, не merged** | 05.08 | **07.09** | punkpeye: „Closing this PR due to inactivity. The last author activity was 32 days ago… (the server needs to be submitted to Glama, claimed, and have a quality score evaluated)" |
| **#12799** „Add Kristo Intelligence v6 — DeFi trading signals API" | punkpeye/awesome-mcp-servers | **ЗАТВОРЕН, не merged** | 24.08 | **29.08** | punkpeye: „this PR adds multiple servers. Please submit one server per PR" |
| **#13219** „Add Kristo Intelligence v6 — DeFi trading signals API" | punkpeye/awesome-mcp-servers | **ОТВОРЕН** ✅ | 30.08 | — | Чист PR: 1 файл, 1 ред, Finance & Fintech, алфабетично. Бот етикети: has-emoji, has-glama, valid-name. Няма maintainer review |
| **#1308** „Add Kristo Intelligence v6 — DeFi Trading Signals API" | xpaysh/awesome-x402 | **ОТВОРЕН** ✅ | 24.08 | — | Без ревю (1 участник, 0 коментара). Добавя v6 в „AI Agent Integration" |
| **#1081** „Add Kristo Intelligence — x402 DeFi Intelligence API" | xpaysh/awesome-x402 | **ОТВОРЕН** ✅ | 31.07 | — | Записът за kristo-travel-api (бонус находка — не беше в нашите документи) |

### Корекции на стари твърдения от нашите документи
- „PR #12799 Open" (DISTRIBUTION_STATUS/VISIBILITY_PLAN) — **НЕВЯРНО**: #12799 е
  затворен на 29.08. Заменен от #13219 (който документите изобщо не споменават!).
- „PR #1308 Open" — **ВЯРНО**.
- Твърдението в стария PR #11557: „15 tools… 0.10 USDC/call… Listed on
  official MCP registry (registry.modelcontextprotocol.io)" — **непотвърдено и
  несъвместимо с днешния продукт** (v6: 3 MCP инструмента, цени от $0.003).

## 2. PR #11557 — разбор (защо ботът споменава kristo-travel-api)

- **Съдържание:** заявка за запис „Kristo Intelligence" в секция Finance &
  Fintech. Ботът (github-actions) го е етикетирал has-emoji / has-glama /
  valid-name и е написал: „Thank you for adding the Glama badge! Please make
  sure the server has been evaluated by Glama and has a quality score."
- **Кой repo/линк сочи тялото на PR-а:**
  GitHub → `hristovdimitri2-hub/kristo-travel-api` (НЕ -6!),
  MCP URL → `https://kristo-intelligence.vercel.app/mcp` (Vercel, не Render).
- **Защо bot/maintainer споменава kristo-travel-api:** защото тялото на PR-а
  сочи именно repo-то kristo-travel-api. Пояснението на автора в #12799:
  „the branch was based on our fork main, which carried the kristo-travel-api
  entry" — форк-ът е носил двата записа и първият PR ги е смесил.
- **Контекст на kristo-travel-api repo-то:** това е СТАРАТА „Kristo
  Intelligence" кодова база (Next.js + FastAPI, 51 commits), чието README
  сочи **същия Render URL** (kristo-intelligence-api.onrender.com) и показва
  **друг wallet адрес** (`0xd4cdA980…Cfd88f` — не нашия payTo
  `0xd4cdA900…c6fd08f`) и стари цени (0.01 USDC). = Риск от объркване на
  марката и от разминаване с реалния payTo.
- **Затворен е на 07.09** с изричните изисквания на поддържащия:
  **(1) подаване в Glama, (2) claim, (3) оценен quality score** — само тогава
  един PR с Glama значка може да бъде merge-нат.

## 3. Инвентар: repos под hristovdimitri2-hub (публични: 14)

⚠ През GitHub API личат САМО публичните repos — private, ако има такива, не
се виждат оттук (локалният remote е https://github.com/hristovdimitri2-hub/
kristo-intelligence-6.git).

| Repo | Вид | Последен push | Статус |
|---|---|---|---|
| **kristo-intelligence-6** | оригинал, API-то (Render) | **06.09 (днес)** | 🟢 **АКТИВНОТО** — всичко води нас |
| thd-ice | оригинал | 31.08 | неутрален (страничен) |
| awesome-mcp-servers | **форк** (за PR-ите) | 30.08 | 🟡 работен форк — носи клоновете add-kristo-intelligence-v6 |
| nexus | оригинал | 30.08 | неутрален (NEXUS източник) |
| foresight-oracle | оригинал | 30.08 | неутрален |
| autonomous-agent-x402-usdc-example | оригинал (demo) | 25.08 | неутрален; homepage сочи Render API |
| awesome-x402 | **форк** (за PR #1308) | 24.08 | 🟡 работен форк |
| **kristo-travel-api** | оригинал (старата база) | 18.08 | 🔴 неактивен, но публичен; README сочи СЪЩИЯ Render API + чужд wallet адрес → объркващо; стои в затворения #11557 |
| kristo | оригинал | 16.08 | стар/спящ |
| kristo-inteligents | оригинал | 16.08 | стар/спящ |
| base44-projekti | оригинал | 15.08 | стар/спящ |
| corten-landing, Setas, My-protect-1 | оригинал | фев–март | спящи |
| — | никое не е archived | — | — |

**Извод:** единствено `kristo-intelligence-6` е жив и обвързан с продукция.
`kristo-travel-api` е единственият проблемен — публичен, свързан с един
затворен PR, и сочи нашия Render URL с ГРЕШЕН wallet адрес в README.

## 4. Glama: какво значи „claim" и къде сме ние (билет #130688574)

### Как работи Glama (проверено на живо 07.09)
- Директорията има **83 219 сървъра**; записите идват от автоматично
  индексиране на GitHub + ръчно „Add Server".
- **Claim = потвърждаване на собственост върху листинг.** „Claimed" е официален
  атрибут (филтър) — 3 986 сървъра са claimed. Прави се с влизане в Glama
  **с GitHub акаунта** (OAuth) — така Glama свързва акаунта с repo-то.
  Claim-ът отключва управление на листинга (редакция, статус) и е ПРЕДПОВИД
  за quality score значката.
- **Quality score** = оценка A/B/C по три оси (license / quality / maintenance),
  изчислена от Glama след преглед. Значката в README (която ботът на
  awesome-mcp-servers иска) сочи точно този score → затова редът е:
  **подаване → одобрение → claim → score → значка → PR merge.**

### Нашето състояние в Glama (проверено)
- Търсене „kristo" в glama.ai/mcp/servers → **0 резултата от нас** (има само
  други „kristo" сървъри). Слъговете `hristovdimitri2-hub/kristo-intelligence-6`
  и `hristovdimitri2-hub/kristo-travel-api` → 404. **Ние НЕ сме листнати.**
- **Билет #130688574** = нашето подаване („Add Server") за човешки преглед.
  Вече има един отказ: „README няма достатъчно информация". Подготвен отговор
  е в `docs/GLAMA_REPLY.md` (разширен README + линкове; правилото: нула wallet
  адреса в имейла; праща се САМО след жива проверка на POST /mcp).
- **Какво остава след одобрението на #130688574:** листингът се появява в
  директорията → влизаме с GitHub в glama.ai → **claimваме** листинга →
  чакаме/проверяваме quality score (A/B/C) → взимаме URL-а на значката от
  Glama → чак тогава значката в README на -6 е „истинска".

## 5. Сводна таблица: канал → статус → какво чака → чие действие

| Канал | Статус (07.09) | Какво чака | Чие действие |
|---|---|---|---|
| **PayAPI Market** | Листнат; band „unscored/baseline" | Chet's compute да пусне оценка (band/score) | ⏳ Chet/market — не е наше |
| **Glama** (билет #130688574) | Подадено; 1 отказ (README); отговор подготвен | Човешки преглед; при „ОК" → claim + score | **Собственик**: (1) жива проверка POST /mcp, (2) прати GLAMA_REPLY.md, (3) после claim с GitHub в glama.ai |
| **awesome-mcp-servers** | #11557 затворен; #12799 затворен; **#13219 ОТВОРЕН** | Glama листинг + claimed + quality score → значка в README → ъпдейт на PR | **Собственик** (Glama стъпките) → после **ние**: ъпдейт на #13219 |
| **awesome-x402** | #1308 ОТВОРЕН (v6); #1081 ОТВОРЕН (travel) | Ревю от maintainer (xpaysh); нисък приоритет — 286 звезди | ⏳ maintainer; ние — само ако поискат промяна |
| **MCP Registry (official)** | Заявен „през PayAPI" (твърдението в #11557 не е потвърдено) | PayAPI одобрение → автоматична публикация | ⏳ Chet/market |
| **PulseMCP / Smithery** | По план MCP_SUBMISSIONS.md — не стартирани | Решение на собственика кога | **Собственик** (~15 мин, ръчно) |

## 6. Чернова-план (без изпълнение): чист PR към awesome-mcp-servers

**Важно уточнение: НЯМА нужда от „ново" PR — #13219 вече Е чистият PR**
(1 файл, 1 ред, отворен на 30.08, без забележки от maintainer). Планът е
да го **довършим**, не да отваряме четвърти. Внимание: последната активност
на #13219 е 30.08 → при 32-дневно правило (както при #11557) рискът от
авто-затваряне е около **01.10**. Дейност преди тази дата.

**Предпоставки (подредени):**
1. Билет #130688574 одобрен → листингът на живо в glama.ai.
2. Claim с GitHub акаунта на hristovdimitri2-hub.
3. Quality score оценен (A/B/C) → взимаме официалния URL на значката от
   страницата на сървъра в Glama.
4. README на -6: значката Glama + актуални факти (3 MCP инструмента, цени от
   $0.003, Base mainnet, Streamable HTTP на /mcp). Без wallet адреси.

**Съдържание на PR-а (готова рецепта):**
- Клон: нов от **upstream/main** на punkpeye (никога от форк main — това
  удави #12799).
- **1 файл, 1 ред** в README.md, секция Finance & Fintech, алфабетично
  (след HuggingAGI/mcp-baostock-server, преди hypeprinter007-stack/
  anchor-x402-mcp — позицията вече е проверена в #13219).
- Ред примерно: `- [Kristo Intelligence](https://github.com/hristovdimitri2-hub/kristo-intelligence-6) - [ badges ] DeFi trading signals API for AI agents on Base — x402 pay-per-call (from $0.003), no signup, real on-chain sales` (точният формат — по примера на соседните редове).
- **Включва:** Glama значка (само след реален score!), линк към repo.
- **Изключва:** wallet адрес, твърдения за „official MCP registry" (не са
  потвърдени), Vercel линкове, стари цени (0.10 USDC), „15 tools".
- Описание на PR-а: 3–4 реда (какво/защо/транспорт/плащане) + линк към
  Glama листинга; нула wallet адреса и в описанието.
- След отваряне: отговор в рамките на 48 ч на всяко maintainer питане
  (анти-„inactivity close").

**Паралелно (препоръка):** за kristo-travel-api — НЕ възраждаме #11557, докато
repo-то не е или изчистено (README: верен wallet/линкове или изрично
„separate legacy project"), или направено private. Едно repo с чужд (грешен)
wallet адрес, сосящ нашия API, е риск за доверието още преди да сме
listнати. Решение е на собственика.

> ✅ **ИЗПЪЛНЕНО (07.09):** `kristo-travel-api` е направено **private** през
> GitHub API с owner акаунта (потвърдено: анонимен GET → 404; 0 stars/forks/
> watchers — никой не е засегнат). Регистрирано в PROJECT_STATUS.md.
> Последица: PR #11557 остава затворен безпредметен; open PR awesome-x402
> #1081 (travel-api запис) сочи сега скрито repo — maintainer-ът вероятно ще
> го затвори сам, или собственикът го затваря изрично (решение предстои).