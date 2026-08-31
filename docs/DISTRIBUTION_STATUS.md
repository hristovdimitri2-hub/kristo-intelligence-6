# DISTRIBUTION STATUS — пускане на Kristo Intelligence в x402 екосистемата

*Актуализирано: 2026-08-30 · Сървър: https://kristo-intelligence-api.onrender.com (Render, live)*

---

## 1. Директории и маркетплейси

| Платформа | Статус | Детайли |
|---|---|---|
| **x402scan** | ✅ РЕГИСТРИРАН | 11 resources, 3 платени routes. Каноничен x402 v2 challenge (CAIP-2 `eip155:8453`, atomic-unit amounts, bazaar schema) — валидиран срещу `@agentcash/discovery` 1.7.5. |
| **PayAPI Market** | 🟡 В ПРЕГЛЕД | Заявката е подадена (Provider Dashboard: "чакащ преглед"). v2-ready. Бележка към ревюиращия + платежни инструкции изпратени на hello@payapi.market. |
| **nohumans.directory** | ✅ 3× VERIFIED | Листинги активни. |
| **BlockRun (data source)** | 📨 ИЗПРАТЕН ИМЕЙЛ | Официален запрос за "List a data source" — whale flow, arb radar, rug scanner, market stats като BlockRun data tools. Очаква отговор. |
| **MCP Registry / PulseMCP / mcp.so / Smithery / Glama** | ⏳ ПРЕЗ PayAPI | PayAPI автоматично публикува одобрени листинги в тези канали. |
| **awesome-x402 (PR #1308) / awesome-mcp-servers (PR #12799)** | ⏳ Отворени PR-и | Чакат review. |

## 2. Платени endpoints (всички верифицирани live на 2026-08-30)

| Endpoint | Цена (USDC) | Atomic units | x402 v2 challenge |
|---|---|---|---|
| `GET /api/stats` | 0.005 | `5000` | ✅ 402, CAIP-2 `eip155:8453`, `extra.name = "USD Coin"` |
| `GET /api/bot-status` | 0.005 | `5000` | ✅ същото |
| `GET /api/arb/opportunities` | 0.005 | `5000` | ✅ същото |
| `GET /api/sales` | 0.05 | `50000` | ✅ същото |

- **Receiver (Base USDC):** `0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f`
- **USDC contract:** `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- **Платежни релси:** (1) `X-Payment-Proof: base64url(JSON({payer, transaction_hash, amount_usdc}))` — self-describing; (2) стандартен `X-PAYMENT` (EIP-3009) — verify + settle през x402 facilitator (`services/connectors.py`).

## 3. Discovery линкове (всички free, live)

| Линк | Статус |
|---|---|
| `/.well-known/x402` | ✅ 200 — version 1, resources, ownershipProofs |
| `/openapi.json` | ✅ 200 — OpenAPI 3.0.3, x-payment-info per operation, x-discovery.ownershipProofs |
| `/mcp/sse` | ✅ live — MCP SSE транспорт (Claude Desktop / Cursor) |
| `/api/mcp/manifest` | ✅ 200 — MCP/x402 манифест |
| `/api/v1/quickstart` | ✅ 200 — copy-paste first-call snippets (curl/Python/Node) |
| `/api/connectors` | ✅ 200 — connector registry (9 конектора, 8 активни) |
| `/favicon.ico` | ✅ 200 — SVG икона |

## 4. Mystery Agent одит (23/23 PASS)

Независима adversarial buyer симулация (`scripts/mystery_agent.py`) срещу live сървъра:
- Discovery от нулата: 6/6 ✅
- Challenge валидация (agentcash/x402scan канон): 3/3 ✅
- Ценова санитария (atomic units, payTo ≠ burned address): 4/4 ✅
- Anti-fraud (синтетичен proof → отхвърлен 401): 2/2 ✅
- Standard-client compatibility probe: 2/2 ✅ (документиран gap → отключен в EIP-3009 rail)
- Free tier: 6/6 ✅

Пълен доклад: [MYSTERY_AGENT_REPORT.md](MYSTERY_AGENT_REPORT.md)

## 5. История на регистрацията в x402scan

1. `0 valid resources` — описателен challenge формат
2. `x402 v1 detected — migrate to v2` — каноничен v1 → миграция до v2
3. `No valid x402 response` — липсващ bazaar schema → добавен
4. ✅ **11 resources, 0 errors** (commits `ebb993d`…`d6eeb12`, 108/108 теста)

## 6. Отворени action items

- [ ] PayAPI одобрение → редакция на листинговата цена $0.10 → $0.005
- [ ] BlockRun отговор → интеграционен договор (data-tool contract / rev-share)
- [ ] MCP Registry submission (през PayAPI одобрение или директно)
- [ ] Outreach кампания: 1 персонализирано съобщение/ден (виж [OUTREACH_KIT.md](OUTREACH_KIT.md))
