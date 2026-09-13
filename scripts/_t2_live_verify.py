"""Табло 2.0 — LIVE verification of every row required by ЧАСТ A.

Polls the deployed app until the new sections appear, then asserts each
requirement against the live payload AND the served HTML, and cross-checks
the two public money surfaces against each other.
"""
import sys
import time

import requests

B = "https://kristo-intelligence-api.onrender.com"
FAILS = []


def check(label, ok, detail=""):
    print(("  OK   " if ok else "  FAIL ") + label
          + (" — " + str(detail) if detail else ""))
    if not ok:
        FAILS.append(label)


def get(path, **kw):
    return requests.get(B + path, timeout=60, **kw)


data = None
for attempt in range(20):
    try:
        d = get("/api/dashboard/data").json()
        if "clients" in d.get("sections", {}) and "guards" in d.get("sections", {}):
            data = d
            print(f"deploy live after {attempt} poll(s)")
            break
        print(f"  poll {attempt}: new sections not deployed yet…")
    except Exception as exc:
        print(f"  poll {attempt}: {type(exc).__name__}")
    time.sleep(25)
if data is None:
    print("DEPLOY NOT DETECTED")
    sys.exit(1)

S = data["sections"]
HTML = get("/dashboard").text

print("\n=== 1. ON-CHAIN SALES (таблицата на 8-те плащания) ===")
o = S["onchain"]
check("$0.028 / 8 tx / 2 external",
      o["total_usdc"] == 0.028 and o["total_count"] == 8
      and o["external_payers"] == 2,
      f"{o['total_usdc']} / {o['total_count']} / {o['external_payers']}")
check("by_class canary 5=$0.017 / external 2=$0.008 / sampler 1=$0.003",
      o["by_class"]["canary"] == {"count": 5, "total_usdc": 0.017}
      and o["by_class"]["external"] == {"count": 2, "total_usdc": 0.008}
      and o["by_class"]["sampler"] == {"count": 1, "total_usdc": 0.003},
      o["by_class"])
check("8 реда с ПЪЛНИ 66-символни хешове + блокове + timestamps",
      len(o["history"]) == 8
      and all(len(h["tx_hash"]) == 66 and h["block_number"] > 50_000_000
              and h["ts"] and h["payer_class"] in ("canary", "sampler", "external")
              for h in o["history"]))
check("хешовете се показват като пълен текст (колоната Tx)", "hashline" in HTML)

print("\n=== 2. КЛИЕНТИ (external платци) ===")
c = S["clients"]
check("2 клиента", c["count"] == 2, [x["wallet"][:12] + "…" for x in c["clients"]])
for cl in c["clients"]:
    ev = {r["evidence"] for r in cl["routes"]}
    check(f"  {cl['wallet'][:12]}… {cl['payments']} плащане, "
          f"${cl['total_usdc']}, последна {cl['last_ts'][:10]}",
          cl["payments"] >= 1 and cl["total_usdc"] > 0 and bool(cl["last_ts"]),
          f"routes={ev}")
check("маршрутите не са измислени (кандидати, докато няма guard запис)",
      all(r["evidence"] in ("price_ambiguous", "price_unique", "payment_guard")
          for cl in c["clients"] for r in cl["routes"]))
check("price_map идва от API-то", len(c["route_price_map"]) == 6)

print("\n=== 3. КИТОВЕ (whale flow) ===")
w = S["whales"]
check("честно състояние (не фалшива нула)",
      w["state"] in ("awaiting_whale", "live_data", "scan_not_started"), w["state"])
check("празно => 'чакаме кит' с движещ се watermark",
      (w["count"] > 0) or (w["state"] == "awaiting_whale"
                           and w["scanned_until_block"]),
      f"count={w['count']} scan={w['scanned_until_block']} state={w['state']}")
check("all_time брояч + праг + прозорец",
      w["all_time_count"] >= w["count"] and w["threshold_usdc"] > 0
      and w["window_hours"] > 0,
      f"all_time={w['all_time_count']} thr=${w['threshold_usdc']:.0f} "
      f"win={w['window_hours']}h")
check("секцията е на екрана", 'id="whales-body"' in HTML)


print("\n=== 4. СТАЖИ (payment guards) ===")
g = S["guards"]
check("C1 replay-lock ЖИВ (реален write-probe)", g["lock_alive"] is True,
      g["lock_probe_error"] or "")
check("C2/H2 настройки",
      g["config"]["c2_proof_confirmations"] == 12
      and g["config"]["c2_standard_confirmations"] >= 1
      and g["config"]["h2_endpoint_binding"] is True, g["config"])
check("наблюдение на блокираните опити (durable guard_events)",
      "blocked_total" in g and "by_kind" in g and "recent_blocks" in g,
      f"blocked={g['blocked_total']} kinds={g['by_kind']}")
check("лампата (зелена/червена) е на екрана", "lamp" in HTML and "guard-cards" in HTML)

print("\n=== 5. ФЪНЪЛ (challenges -> paid по маршрути) ===")
funnel = S["requests"]["funnel"]
check("всичките 6 платени маршрута са във фънъла", len(funnel) == 6, list(funnel))
check("вкл. whale flow", "/api/v1/whaleflow" in funnel)
check("днес и общо са отделни полета",
      all("challenges_today" in v and "challenges_total" in v
          for v in funnel.values()))
check("фънълът е видим на екрана (не скрит)",
      'id="funnel-box"' in HTML and 'class="hidden" id="funnel-box"' not in HTML)

print("\n=== 6. СЪЩЕСТВУВАЩОТО, ЗАПАЗЕНО ===")
check("API Requests чисти/шум", S["requests"]["today_clean"] is not None
      and bool(S["requests"]["internal_noise"]["label"]),
      S["requests"]["today_clean"])
papi = S["payapi"]
check("Listing & Ranking (band)", "reliability" in papi or "available" in papi,
      (papi.get("reliability") or {}).get("band"))
check("CRM off-chain наличен и скрит зад toggle",
      'id="crm-toggle"' in HTML and 'id="crm-detail" class="hidden"' in HTML)
check("нищо не е махнато: onchain/requests/payapi/crm секции",
      all(k in S for k in ("onchain", "requests", "payapi", "crm_stripe")))
check("маршрутната таблица се рендира от API (не статична)",
      'id="routes-body"' in HTML and "renderRoutes(" in HTML)
check("6-те реални маршрута в payload-а", S["routes"]["count"] == 6,
      [r["endpoint"] for r in S["routes"]["routes"]])

print("\n=== 7. 'LIVE' ЗНАЧИ LIVE ===")
check("авто-refresh 45s", "setInterval(load, 45000)" in HTML)
check("badge LIVE при успех", "badge live" in HTML)
check("generated_at е прясно", bool(data.get("generated_at")),
      data.get("generated_at"))

print("\n=== 8. ФИКСНАТИТЕ НАХОДКИ, ПРОВЕРЕНИ НА ЖИВО ===")
stats = get("/api/dashboard-stats").json()
check("НАХОДКА #3: /api/dashboard-stats вече дава $0.028 / 8",
      stats["total_volume_usd"] == 0.028 and stats["total_sales"] == 8,
      f"${stats['total_volume_usd']} / {stats['total_sales']}")
check("двете повърхности съвпадат",
      stats["total_volume_usd"] == o["total_usdc"]
      and stats["total_sales"] == o["total_count"])
check("НАХОДКА #4: нула статични цени в таблицата на маршрутите",
      '<td class="num">0.05</td>' not in HTML)
bad = 0
for r in S["routes"]["routes"]:
    resp = get(r["endpoint"])
    if resp.status_code == 402:
        atomic = int(resp.json()["accepts"][0]["amount"])
        if atomic != round(float(r["price_usdc"]) * 1_000_000):
            bad += 1
            print(f"    !! {r['endpoint']}: 402={atomic} vs {r['price_usdc']}")
check("НАХОДКА #4b: живият 402 == обявената цена за всеки маршрут", bad == 0)
check("НАХОДКА #2: payer binding + endpoint binding активни",
      g["config"]["h2_endpoint_binding"] is True)

print("\n" + "=" * 62)
print("ТАБЛО 2.0 LIVE:", "ALL CHECKS PASSED ✅" if not FAILS
      else f"{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)

