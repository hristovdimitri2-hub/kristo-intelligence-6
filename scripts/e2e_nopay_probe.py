# -*- coding: utf-8 -*-
"""F1 гейт, стъпка A2 — жив NO-PAY probe от външна машина.

Прави ВСИЧКО по recovery механиката без реално плащане:
  1. discovery (/.well-known/x402) — timing
  2. 402 challenge на /api/v1/signal — timing + parse (amount/payTo/scheme)
  3. retry цикъл (6× без proof) — всеки отново 402, challenge-ът е идентичен,
     latency статистика (min/median/max)
  4. retry със СИНТЕТИЧЕН X-Payment-Proof — очаквано 401 fail-closed
     (никакво плащане; същият probe е одобрен в MYSTERY_AGENT_REPORT)
  5. retry без proof отново — пак 402 => нищо не е консумирано, нищо не е claim-нато
  6. последната стъпка (реално плащане $0.003 → 425 прозорец → 200) се
     ДОКУМЕНТИРА като "чака wallet" — не като "чака решение"

Защити: payTo/цени/стражи НЕ се пипат (само четене + синтетичен proof,
който сървърът отказва). Никакъв ключ, никакво балансово движение.
"""
from __future__ import annotations

import base64
import json
import statistics
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://kristo-intelligence-api.onrender.com"
ENDPOINT = "/api/v1/signal"
FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  OK   " if ok else "  FAIL ") + label + (" — " + detail if detail else ""))
    if not ok:
        FAILS.append(label)


def timed_get(path: str, headers: dict | None = None) -> tuple[int, float, str]:
    t0 = time.perf_counter()
    r = requests.get(BASE + path, headers=headers or {}, timeout=60)
    dt = (time.perf_counter() - t0) * 1000
    return r.status_code, dt, r.text


def b64url(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


print("=" * 66)
print("F1 GATE · A2 NO-PAY E2E probe (външна машина, без плащане)")
print("=" * 66)

# ── 1. Discovery ──────────────────────────────────────────────────────────────
code, ms, body = timed_get("/.well-known/x402")
try:
    n_res = len(json.loads(body).get("resources", []))
except Exception:
    n_res = -1
print(f"[1] discovery            {code}  {ms:7.1f} ms  resources={n_res}")
check("discovery 200", code == 200, str(code))

# ── 2. Challenge ──────────────────────────────────────────────────────────────
code, ms, body = timed_get(ENDPOINT)
challenge_ms = ms
try:
    c = json.loads(body)["accepts"][0]
    amount, pay_to, scheme, network = (c["amount"], c["payTo"], c["scheme"],
                                       c["network"])
except Exception as exc:
    amount = pay_to = scheme = network = f"parse-error:{exc}"
print(f"[2] challenge            {code}  {ms:7.1f} ms  amount={amount} "
      f"scheme={scheme} network={network}")
print(f"    payTo={pay_to}")
check("challenge е 402", code == 402, str(code))
check("challenge е каноничен (exact / eip155:8453 / 3000 atomic)",
      scheme == "exact" and network == "eip155:8453" and str(amount) == "3000",
      f"{scheme} {network} {amount}")

# ── 3. Retry цикъл без proof ─────────────────────────────────────────────────
latencies: list[float] = []
codes_seen: list[int] = []
bodies_seen: list[str] = []
for i in range(6):
    code, ms, body = timed_get(ENDPOINT)
    latencies.append(ms)
    codes_seen.append(code)
    bodies_seen.append(body)
    print(f"[3.{i + 1}] retry (no proof)     {code}  {ms:7.1f} ms")
check("всеки retry отново 402 (идемпотентен challenge)",
      all(c == 402 for c in codes_seen), str(set(codes_seen)))
check("challenge тялото е идентично при всеки retry",
      len(set(bodies_seen)) == 1, f"{len(set(bodies_seen))} варианта")
lat = sorted(latencies)
print(f"    latency: min={lat[0]:.1f} median={statistics.median(lat):.1f} "
      f"max={lat[-1]:.1f} ms (n={len(lat)})")

# ── 4. Retry със синтетичен proof → fail-closed ──────────────────────────────
synth_proof = b64url({
    "payer": "0x" + "11" * 20,
    "transaction_hash": "0x" + "de" * 32,
    "amount_usdc": float(amount) / 1e6 if str(amount).isdigit() else 0.003,
})
code, ms, body = timed_get(ENDPOINT, {"X-Payment-Proof": synth_proof})
reason = ""
try:
    j = json.loads(body)
    reason = str(j.get("reason") or j.get("error") or "")[:160]
except Exception:
    pass
print(f"[4] synthetic proof      {code}  {ms:7.1f} ms  → {reason or body[:160]}")
check("синтетичният proof е отхвърлен 401 (fail-closed, без плащане)",
      code == 401, str(code))

# ── 5. Отново без proof — нищо не е консумирано ──────────────────────────────
code, ms, body = timed_get(ENDPOINT)
print(f"[5] retry (no proof)     {code}  {ms:7.1f} ms")
check("challenge-ът се издава отново — claim няма, state не е променен",
      code == 402, str(code))

# ── 6. Какво остава (документира се, не се изпълнява) ────────────────────────
print("-" * 66)
print("[6] ПОСЛЕДНА СТЪПКА — ЧАКА WALLET (човешко зареждане, не решение):")
print("     плати 3000 atomic ($0.003 USDC) → незабавен retry цикъл")
print("     (~6× на 3-5s, за да се улови естественият 425 прозорец на")
print("     вътрешния node) → до 200 данни. Нужно: funded DEMO_PRIVATE_KEY.")
print("=" * 66)
print("A2 NO-PAY:", "ALL CHECKS PASSED ✅" if not FAILS
      else f"{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
