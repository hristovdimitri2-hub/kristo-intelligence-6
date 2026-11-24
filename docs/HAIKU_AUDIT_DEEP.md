# 🔬 Kristo Intelligence v6 — DEEP AUDIT

**Mode:** Read-only | **Date:** 2026-08-10  
**Scope:** Full payment chain + signal delivery + new files (coingecko, sentinel, demo_sponsored_pay)

---

## 🔍 FINDINGS TABLE

| № | Title | File | Risk | What happens | What you propose |
|---|----------|------|------|-----------------|-----------------|
| 1 | rejected_signals[] is not a durable log | main.py:4081-4119 | **MEDIUM** | Rejected signals are visible in the response, but are missing from guard_events after a restart | Write rejected_signals[] into dashboard_db.record_guard_event() |
| 2 | CoinGecko fallback cache is not invalidated | services/coingecko.py:145-174 | **MEDIUM** | On a Base44→public fallback the cache keeps the old price; the verifier rejects new signals | Clear the cache on fallback or include the API source in cache_key |
| 3 | demo_sponsored_pay client does NOT verify the nonce | scripts/demo_sponsored_pay.py:320-370 | **HIGH** | The server can return a different settlement (adoption); the client accepts it | Add verification: `assert settle["nonce"] == signed_nonce` |
| 4 | X-Forwarded-For fallback is imprecise | main.py:1380-1386 | **LOW** | All-private XFF takes the last entry (the oldest proxy) | Take the first entry for all-private or fail-closed |
| 5 | Base44 fallback does not log | services/coingecko.py:145-151 | **LOW** | debug level = invisible; the operator does not know the API was switched | Change to WARNING |
| 6 | Sentinel no atomic write | services/sentinel.py:60-65 | **MEDIUM** | Race condition on state write → corrupted JSON | Use a temp file + os.replace() |
| 7 | arb_radar division is guarded | services/arb_radar.py:180 | **—** | Theoretically a ZeroDivisionError, but the guard is sufficient | **✅ CLEAN** |

---

## 🔴 FINDING #1: rejected_signals[] is not a durable log

**main.py:4081-4119** (_verify_signal_values)

The verifier returns `rejected_signals[]` (in the response ✓), but **does not log to
guard_events** (in the DB) → after a restart the data is gone → the operator cannot
see whether the agent lies regularly.

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

## 🟠 FINDING #2: CoinGecko fallback cache is not invalidated

**services/coingecko.py:145-174** (_get)

The cache key does not include the Base44 status → on fallback it returns the old Base44
price → the verifier rejects.

**Scenario:** Base44 $2000 in cache → Base44 goes down → fallback → live $1950 → the
verifier compares $2000 vs $1950 → rejected!

**Fix:**
```python
use_base44 = self._base44_available
cache_key = tuple(sorted(sym.lower() for sym in tokens)) + (use_base44,)

# OR on fallback:
if not resp.ok and self._base44_available:
    self._base44_available = False
    with cls._cache_lock:
        cls._price_cache.clear()
```

---

## 🔴 FINDING #3: Client does NOT verify the returned nonce

**scripts/demo_sponsored_pay.py:320-370** (main)

The client signs EIP-3009 with a nonce, but does not check that PAYMENT-RESPONSE
returned it → adoption attack (a different settlement).

**Fix:**
```python
signed_nonce_hex = payload.get("nonce")  # Before signing
# ...
if settle.get("nonce") != signed_nonce_hex:
    fail(f"Nonce mismatch: {signed_nonce_hex} vs {settle.get('nonce')}")
```

---

## 🟠 FINDING #4: XFF fallback is imprecise

**main.py:1380-1386** (_get_client_ip)

All-private XFF takes **the last entry** (the first proxy) instead of the first one → it
can be spoofed.

**Fix:** `return entries[0]` for all-private, or `return peer` (fail-closed).

---

## 🟠 FINDING #5: Sentinel no atomic write

**services/sentinel.py:60-65** (_persist)

Race condition on the state file write → corrupted JSON.

**Fix:** Use `temp_file + os.replace()` for an atomic write.

---

## ✅ SUMMARY

**HIGH:** 1 (nonce verification)  
**MEDIUM:** 3 (rejected_signals, coingecko cache, sentinel atomicity)  
**LOW:** 2 (XFF parse, Base44 logging)  
**CLEAN:** 1 (arb_radar division)

---

**End of Deep Audit**
