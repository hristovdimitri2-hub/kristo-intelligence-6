# CHET DATA PACKAGE — извлечено 04.09 (втора проверка), read-only

Източник: `GET /agent/get?id=kristo-intelligence-defi-signals-api` +
`/agent/search?q=<term>` ×8. Диф срещу `docs/monitor_state.json`
(baseline, записан при първо пускане на монитора същия ден).

## A) STATUS таблица

| Поле | Baseline (04.09 утро) | Сега (04.09, втора проверка) | Промяна |
|---|---|---|---|
| **Reliability band** | unscored (score=null, computed_at=null) | **unscored** (score=null, computed_at=null) | — |
| **Заглавие** | Kristo Intelligence — DeFi Signals API | Kristo Intelligence — DeFi Signals API | същата |
| q=defi | #1 (от 3) | #1 (от 3) | = |
| q=whale | #1 (от 1) | #1 (от 1) | = |
| q=signals | #3 (от 7) | #3 (от 7) | = |
| q=rug | #2 (от 2) | #2 (от 2) | = |
| q=eth | ABSENT (2) | ABSENT (2) | = |
| q=ondo | ABSENT (1) | ABSENT (1) | = |
| q=kaito | ABSENT (0) | ABSENT (0) | = |
| q=degen | ABSENT (0) | ABSENT (0) | = |

Формат-проверка: отговорите са в очаквания формат (reliability обект + списъци
с резултати); няма нужда от raw-dump.

## B) VERDICT

**NOTHING TO SEND — band още unscored, титла не е сменена.**

Граматиката на нишката важи: без разписка, данни или число — не се праща нищо.
Следващият валиден ход: повтори `python scripts/listing_monitor.py` след
сигнал от Chet (или най-рано следващата седмица — той каза, че compute-ът
е ръчен, „ когато нов верифициран листинг трябва band").

## C) Драфт — не се прилага (VERDICT = NOTHING TO SEND)

## D) Специална проверка (defi): неизпълнима в момента
Титлата НЕ е сменена → „defi" продължава да идва от името (#1) и description-а
("DeFi signals" + substring-мачър: доказано индексира описанието — whale #1
без "whale" в името; CMS „de**fi**ciencies" е #2 за q=defi). Условието за
D-линията (нова титла live + defi ABSENT) не е настъпило. Fallback редът е
записан в RECON_FINDINGS.md и се активира автоматично от следващия мониторинг.