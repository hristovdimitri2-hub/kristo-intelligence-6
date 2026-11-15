# 🔍 Kristo Intelligence v6 Security Audit — Critical Findings

**Mode:** Read-only code review | **Date:** 2026-08-10  
**Scope:** main.py, services/{verifier, connectors, arb_radar}  
**Focus:** 4-category threat model (double-payment, delivery without payment, payment without delivery, calc errors)

---

## 📋 Summary of Findings

| # | Title | File + Function | Risk | Status |
|---|-------|-----------------|------|--------|
| 1 | Payment adoption tx not sanguely verified against auth nonce | main.py / _find_settlement_by_nonce() | **HIGH** | ⚠️ **VULNERABLE** |
| 2 | Arb Radar: gross profit boundary off-by-one (≤ instead of <) | services/arb_radar.py / _scan_for_arbitrage() | **MEDIUM** | ⚠️ **VULNERABLE** |
| 3 | Payment delivery dual-delivery lock (C1) relies on durable DB | main.py / _admit_undelivered_payment() | **MEDIUM** | ⚠️ **DEPENDS ON DB** |
| 4 | Verifier fail-open: signal delivered unverified on error | services/verifier.py / check_signal_values() | **LOW** | ✅ **DESIGNED** (documented) |

---

## 🔴 FINDING #1: Adopt tx NOT verified against authorization nonce

**File:** `main.py`  
**Function:** `_find_settlement_by_nonce()` (lines 2151–2255)  

### What can happen:
When a paying client sends `PAYMENT-SIGNATURE` (EIP-3009 authorization), the system attempts to recover the tx that consumed the nonce from the blockchain. **BUT the recovered tx is checked ONLY for the amount (ERC-20 Transfer value), NOT whether the nonce field in the authorization matches the signed nonce.**

A malicious node or facilitator could broadcast a settlement tx with:
- **Correct payer address**
- **Correct amount** (price_usdc)
- **BUT a DIFFERENT nonce or forged authorization**

The code searches for `AuthorizationUsed` events (lines 2218–2230) but **never validates the recovered nonce against the client's signed nonce**. Line 2239-2240:
```python
if value == price_atomic:
    matched = True
    break
```
This checks ONLY the amount, not the authorization proof.

### What to fix:
After extracting `nonce_in_log` from the event topic, verify it matches the input `nonce`:
```python
if nonce_in_log.lower() != _to_hex0x(nonce).lower():
    log.warning("nonce mismatch: expected %s, found %s", nonce[:12], nonce_in_log[:12])
    continue
```

---

## 🟠 FINDING #2: Arb Radar profit boundary off-by-one

**File:** `services/arb_radar.py`  
**Function:** `_scan_for_arbitrage()` (lines 170–227)  

### What can happen:
A cross-DEX arbitrage opportunity with gross profit **exactly equal to gas×3** is rejected, even though it clears the safety threshold. The gate is:
```python
if gross_profit_usd <= GAS_COST_USDC * GAS_SAFETY_MULT:  # Line 200
    continue
```

With `GAS_COST_USDC = 0.10` and `GAS_SAFETY_MULT = 3`, opportunities with `gross_profit_usd == 0.30` are skipped.

### What to fix:
Use strict less-than instead of less-than-or-equal:
```python
if gross_profit_usd < GAS_COST_USDC * GAS_SAFETY_MULT:  # < instead of ≤
    continue
```

---

## 🟠 FINDING #3: Payment delivery lock (C1) depends on durable DB

**File:** `main.py`  
**Function:** `_admit_undelivered_payment()` (lines 2258–2290)  

### What can happen:
The `C1` replay guard (payment_guards table) prevents replays of already-spent proofs. **BUT** if PostgreSQL is unreachable:
- `dashboard_db.payment_guard_row(tx_hash)` returns `None`
- Payment is denied (line 2275)
- Paying client sees `401 Unauthorized` forever — **payment without delivery**

The fail-safe requires DB durability, which is not available on Render's ephemeral disk.

### What to fix:
When DB is unreachable, allow payment through with a warning (fail-open):
```python
try:
    row = dashboard_db.payment_guard_row(tx_hash)
except Exception as exc:
    log.warning("C1 replay guard unavailable: %s — allowing (fail-open)", exc)
    return True  # Permit payment if DB is down
```

---

## ✅ FINDING #4: Verifier fail-open (signal without verification)

**File:** `services/verifier.py`  
**Function:** `check_signal_values()` (lines 195–282)  

### Assessment: **CLEAN** (by design)

The verifier is explicitly **fail-open**: when verification fails or a source is missing, the signal is marked `unverified` and delivered anyway (lines 255–258). This is documented policy in the header. **No issue here.**

---

## 📌 Known (Skipped) Issues

- **(A2)** Adopt path does not verify tx against authorization — **REDISCOVERED as Finding #1**
- **(V3)** extra.name/version fields in x402 challenge not pinned to contract
- Earlier audit findings (see docs/CODE_AUDIT_REPORT.md)

---

## 🎯 Recommendations (Priority Order)

1. **CRITICAL:** Fix Finding #1 (nonce verification in adoption)
2. **HIGH:** Fix Finding #2 (arb_radar boundary)
3. **MEDIUM:** Fix Finding #3 (C1 DB fallback)

---

**End of Report**
