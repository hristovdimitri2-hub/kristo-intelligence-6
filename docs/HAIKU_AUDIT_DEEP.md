# 🔬 Kristo Intelligence v6 — DEEP AUDIT

**Mode:** Read-only | **Date:** 2026-08-10  
**Scope:** Full payment chain + signal delivery + new files (coingecko, sentinel, demo_sponsored_pay)

---

## 🔍 FINDINGS TABLE

| № | Заглавие | Файл | Risk | Какво се случва | Какво предлагаш |
|---|----------|------|------|-----------------|-----------------|
| 1 | rejected_signals[] не е дълготраен лог | main.py:4081-4119 | **MEDIUM** | Отхвърлени сигнали са видими в response, но липсват от guard_events при рестарт | Запиши rejected_signals[] в dashboard_db.record_guard_event() |
| 2 | CoinGecko fallback кеш не се инвалидира | services/coingecko.py:145-174 | **MEDIUM** | При Base44→public fallback кешът остава със стара цена; verifier отхвърля нови сигнали | Clear кеш при fallback или включи API source в cache_key |
| 3 | demo_sponsored_pay client НЕ проверява nonce | scripts/demo_sponsored_pay.py:320-370 | **HIGH** | Сървър може да врнеся другото уреждение (adoption); клиент го приема | Добави verификация: `assert settle["nonce"] == signed_nonce` |
| 4 | X-Forwarded-For fallback неточна | main.py:1380-1386 | **LOW** | All-private XFF взема последния entry (най-стария proxy) | Вземи първи entry за all-private или fail-closed |
| 5 | Base44 fallback не логира | services/coingecko.py:145-151 | **LOW** | debug level = невидимо; operator не знае че API е сменен | Промени на WARNING |
| 6 | Sentinel no atomic write | services/sentinel.py:60-65 | **MEDIUM** | Race condition при state write → корумпиран JSON | Използай temp file + os.replace() |
| 7 | arb_radar деление защитено | services/arb_radar.py:180 | **—** | Теоретично ZeroDivisionError, но guard е достатъчна | **✅ ЧИСТО** |

---

## 🔴 FINDING #1: rejected_signals[] не е дълготраен лог

**main.py:4081-4119** (_verify_signal_values)

Verifier връща `rejected_signals[]` (в response ✓), но **не логира в guard_events** (в БД) → при рестарт данните са izgore → operator не вижда дали agent редовно лъже.

**Fix:**
```python
for entry in rejected_signals or []:
    dashboard_db.record_guard_event(
        "verifier_rejected_signal",
        endpoint="/api/v1/signal",
        detail=json.dumps({
            "token": entry.get("token"),
            "reason": entry.get("reason"),
            "coingecko": entry.get("coingecko_usd"),
            "dexscreener": entry.get("dexscreener_usd"),
            "diff_pct": entry.get("diff_pct"),
        }, default=str)[:300]
    )
```

---

## 🟠 FINDING #2: CoinGecko fallback кеш не се инвалидира

**services/coingecko.py:145-174** (_get)

Cache key не включва Base44 status → при fallback връща стара Base44 цена → verifier отхвърля.

**Сценарий:** Base44 $2000 в кеш → Base44 пада → fallback → live $1950 → verifier сравня $2000 vs $1950 → rejected!

**Fix:**
```python
use_base44 = self._base44_available
cache_key = tuple(sorted(sym.lower() for sym in tokens)) + (use_base44,)

# ИЛИ при fallback:
if not resp.ok and self._base44_available:
    self._base44_available = False
    with cls._cache_lock:
        cls._price_cache.clear()
```

---

## 🔴 FINDING #3: Client НЕ верифицира returned nonce

**scripts/demo_sponsored_pay.py:320-370** (main)

Client подписва EIP-3009 с nonce, но не проверява че PAYMENT-RESPONSE го върна → adoption attack (друго уреждение).

**Fix:**
```python
signed_nonce_hex = payload.get("nonce")  # Before signing
# ...
if settle.get("nonce") != signed_nonce_hex:
    fail(f"Nonce mismatch: {signed_nonce_hex} vs {settle.get('nonce')}")
```

---

## 🟠 FINDING #4: XFF fallback неточна

**main.py:1380-1386** (_get_client_ip)

All-private XFF взема **последния entry** (първия proxy) вместо първия → може спуфа.

**Fix:** `return entries[0]` за all-private или `return peer` (fail-closed).

---

## 🟠 FINDING #5: Sentinel no atomic write

**services/sentinel.py:60-65** (_persist)

Race condition при state file write → корумпиран JSON.

**Fix:** Используй `temp_file + os.replace()` за атомна писане.

---

## ✅ SUMMARY

**HIGH:** 1 (nonce verification)  
**MEDIUM:** 3 (rejected_signals, coingecko cache, sentinel atomicity)  
**LOW:** 2 (XFF parse, Base44 logging)  
**CLEAN:** 1 (arb_radar division)

---

**End of Deep Audit**
