"""Audit ONE payment end to end, in the order the money travels — READ-ONLY.

Written for the project's FIRST human payment ($29 Starter, 16.09) and used for
every sale after it. Every call is a GET: our own service, Stripe's read
endpoints, the Render log API and (for the chain) a Base RPC read. Nothing is
written, nothing is sent to anyone, and no secret is ever printed.

It answers, in order:

  1. STRIPE      — the money event, its delivery state (pending_webhooks = 0 means
                   Stripe considers it delivered) and what the customer actually
                   paid (subtotal vs tax: Managed Payments adds VAT on top)
  2. REFUNDS     — whether the owner has refunded it yet
  3. CRM         — the paid lead behind that email, through the ADMIN API
                   (payment_status, plan, amount, when the lead was created)
  4. OUR LOG     — the durable request log for /api/webhooks/stripe, plus the
                   Stripe feed's own state (cache_state / detail / age)
  5. STABILITY   — three consecutive dashboard reads must agree: a number that
                   changes between refreshes is a bug, not a fluctuation
  6. ROUTES      — every x402 route answers 402 with EXACTLY the price it
                   advertises, and payTo still equals the configured receiver
  7. THE LINK    — whether Stripe's paid list agrees with the CRM records
  8. THE CHAIN   — every on-chain row, plus an independent receipt check on the
                   newest transfer (status, token, receiver, amount)

Usage:
    python -X utf8 scripts/audit_payment_path.py
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://kristo-intelligence-api.onrender.com"
SERVICE = "srv-d9maroe7bikc73adkaug"
LEAD_EMAIL = "hristovdimitri2@gmail.com"


def mask_email(value: str) -> str:
    v = (value or "").strip()
    if "@" not in v:
        return v or "(none)"
    name, domain = v.split("@", 1)
    return "%s%s@%s" % (name[:2], "…" * (len(name) > 2), domain)


def render_env():
    for _ in range(6):
        try:
            key = open(os.path.join(ROOT, "secrets", "render_api_key.txt"),
                       encoding="utf-8").read().strip()
            out = {}
            for item in requests.get(
                    "https://api.render.com/v1/services/%s/env-vars?limit=100"
                    % SERVICE,
                    headers={"Authorization": "Bearer " + key,
                             "Accept": "application/json"},
                    timeout=90).json():
                ev = item.get("envVar", item)
                out[ev.get("key")] = ev.get("value")
            return out
        except Exception:
            time.sleep(4)
    return {}


def ts(sec) -> str:
    return datetime.fromtimestamp(sec or 0, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC")


env = render_env()
sk = (env.get("STRIPE_API_KEY") or "").strip()
admin = (env.get("ADMIN_API_TOKEN") or "").strip()
auth = {"Authorization": "Bearer " + sk}

print("=== 1. STRIPE: the money event and its delivery ===")
events = requests.get("https://api.stripe.com/v1/events", headers=auth,
                      params={"limit": 100}, timeout=90).json().get("data", [])
completed = [e for e in events if e.get("type") == "checkout.session.completed"]
if not completed:
    print("    !! no checkout.session.completed event found in the last 100")
    print("    types present:", sorted({e.get("type") for e in events}))
for e in completed[:5]:
    obj = (e.get("data") or {}).get("object") or {}
    print("    %s | %s | pending_webhooks=%s"
          % (e.get("id"), ts(e.get("created")), e.get("pending_webhooks")))
    print("      session %s | paid=%s | $%.2f %s | subtotal=$%.2f tax=$%.2f"
          % (obj.get("id"), obj.get("payment_status"),
             (obj.get("amount_total") or 0) / 100.0,
             (obj.get("currency") or "").upper(),
             (obj.get("amount_subtotal") or 0) / 100.0,
             ((obj.get("total_details") or {}).get("amount_tax") or 0) / 100.0))
    print("      customer=%s | metadata=%s"
          % (mask_email((obj.get("customer_details") or {}).get("email")
                        or obj.get("customer_email")),
             json.dumps(obj.get("metadata") or {})))
event_delivered = any((e.get("pending_webhooks") == 0) for e in completed)

print("\n=== 2. REFUNDS (money going back out) ===")
refunds = requests.get("https://api.stripe.com/v1/refunds", headers=auth,
                       params={"limit": 5}, timeout=60).json()
print("    refunds found:", len(refunds.get("data", [])))
for r in refunds.get("data", []):
    print("    %s | %s | $%.2f | status=%s"
          % (r.get("id"), ts(r.get("created")), (r.get("amount") or 0) / 100.0,
             r.get("status")))
stripe_refunded_total = round(sum(
    (r.get("amount") or 0) for r in refunds.get("data", [])
    if (r.get("status") or "") in ("succeeded", "pending")) / 100.0, 2)

print("\n=== 3. CRM (Postgres, via the admin API) ===")
leads = requests.get(BASE + "/api/admin/leads",
                     headers={"X-Admin-Token": admin}, timeout=90)
the_lead = {}
print("    GET /api/admin/leads →", leads.status_code)
if leads.status_code == 200:
    body = leads.json()
    print("    pipeline:", json.dumps(body.get("pipeline")))
    print("    total leads:", body.get("total"))
    for lead in body.get("leads", []):
        if lead.get("email", "").lower() == LEAD_EMAIL:
            the_lead = lead
            print("    ── THE PAID LEAD ──")
            print(json.dumps({k: (mask_email(v) if k == "email" else v)
                              for k, v in lead.items()},
                             ensure_ascii=False, indent=1))
else:
    print("    body:", leads.text[:200])

print("\n=== 4. OUR OWN DURABLE LOG (the webhook's 200) ===")
ov = requests.get(BASE + "/api/admin/overview",
                  headers={"X-Admin-Token": admin}, timeout=120)
print("    GET /api/admin/overview →", ov.status_code)
if ov.status_code == 200:
    body = ov.json()
    print("    keys:", sorted(body))
    log_rows = body.get("request_log") or []
    hits = [r for r in log_rows if "webhooks/stripe" in str(r.get("path", ""))]
    print("    request_log rows: %d | /api/webhooks/stripe rows: %d"
          % (len(log_rows), len(hits)))
    for r in hits[:6]:
        print("      %s | %s %s | HTTP %s | ua=%s"
              % (str(r.get("timestamp"))[:19], r.get("method"), r.get("path"),
                 r.get("status_code"), str(r.get("user_agent"))[:40]))
    snap = body.get("stripe_snapshot") or {}
    print("    stripe snapshot:", json.dumps(
        {k: snap.get(k) for k in ("available", "state", "reason", "fetched_at",
                                  "age_seconds")}, ensure_ascii=False))
    print("    snapshot payments:", len(snap.get("payments") or []))
    print("    payments[]:", json.dumps(body.get("payments"),
                                       ensure_ascii=False)[:300])
else:
    print("    body:", ov.text[:200])

print("\n=== 5. DASHBOARD STABILITY (repeat reads, 6s apart) ===")
fingerprints = []
for i in range(3):
    d = requests.get(BASE + "/api/dashboard/data", timeout=90).json()
    s = d.get("sections", {})
    fingerprints.append({
        "onchain": (s["onchain"]["total_usdc"], s["onchain"]["total_count"],
                    s["onchain"]["external_payers"]),
        "crm": (s["crm_stripe"]["total_usd"], s["crm_stripe"]["count"],
                s["crm_stripe"]["source"], s["crm_stripe"]["durable"]),
        "guards": (s["guards"]["lock_alive"], s["guards"]["blocked_total"],
                   s["guards"]["consumed_total"],
                   s["guards"]["config"]["c2_proof_confirmations"]),
        "routes": s["routes"]["count"],
    })
    print("    read %d: %s" % (i + 1, json.dumps(fingerprints[-1],
                                                 ensure_ascii=False)))
    if i < 2:
        time.sleep(6)
print("    stable across reads:", all(f == fingerprints[0]
                                     for f in fingerprints))

print("\n=== 6. THE SIX ROUTES: live 402 vs declared price, and payTo ===")
pay_to_env = (env.get("BASE_FEE_RECEIVER") or "").strip()
data = requests.get(BASE + "/api/dashboard/data", timeout=90).json()
bad = 0
last_pay_to = ""
for r in data["sections"]["routes"]["routes"]:
    live = requests.get(BASE + r["endpoint"], timeout=60)
    if live.status_code != 402:
        print("    !! %s → HTTP %s (expected 402)" % (r["endpoint"],
                                                      live.status_code))
        bad += 1
        continue
    accepts = (live.json().get("accepts") or [{}])[0]
    atomic = int(accepts.get("amount") or 0)
    expected = round(float(r["price_usdc"]) * 1_000_000)
    last_pay_to = (accepts.get("payTo") or accepts.get("pay_to") or "")
    if atomic != expected:
        bad += 1
    print("    %s%-26s 402=%d (declared %s) payTo=…%s"
          % ("OK " if atomic == expected else "!! ", r["endpoint"], atomic,
             r["price_usdc"], last_pay_to[-6:]))
print("    all six match their declared price:", bad == 0)
print("    live payTo == env BASE_FEE_RECEIVER:",
      bool(pay_to_env) and last_pay_to.lower() == pay_to_env.lower(),
      "(env tail …%s)" % pay_to_env[-6:])

print("\n=== 7. WHY THE STRIPE SNAPSHOT IS NOT LINKED ===")
ov = requests.get(BASE + "/api/admin/overview",
                  headers={"X-Admin-Token": admin}, timeout=120).json()
svc = ov.get("services", {})
print("    payment_source:", ov.get("payment_source"))
print("    services.stripe:", json.dumps(svc.get("stripe"), ensure_ascii=False))
print("    services.crm   :", json.dumps(svc.get("crm"), ensure_ascii=False))
print("    blockchain     :", json.dumps(
    {k: v for k, v in (svc.get("blockchain") or {}).items()
     if k in ("ready", "rpc_connected", "chain_id", "fee_receiver")},
    ensure_ascii=False))
m = ov.get("metrics") or {}
print("    metrics: paid_payments=%s active_vip_plans=%s "
      "active_agent_entitlements=%s vip_invites=%s"
      % (m.get("paid_payments"), m.get("active_vip_plans"),
         m.get("active_agent_entitlements"), m.get("vip_invites_generated")))
print("    agent_catalog totals:", json.dumps(
    (ov.get("agent_catalog") or {}).get("totals"), ensure_ascii=False))

print("\n=== 8. ON-CHAIN: the new 11th transfer, and the 10 older rows ===")
data = requests.get(BASE + "/api/dashboard/data", timeout=90).json()
rows = data["sections"]["onchain"]["history"]
for h in rows:
    print("    %s $%-7s %-9s block=%-10s %s"
          % (h["ts"][:19], h["amount_usdc"], h["payer_class"],
             h["block_number"], h["tx_hash"]))
cl = data["sections"]["clients"]
print("    clients:", [(c["wallet"][:10] + "…", c["payments"],
                       c["total_usdc"], c["last_ts"][:19]) for c in cl["clients"]])
print("    potentially_new:", len(cl.get("potentially_new") or []))

NEW_TX = ("0x08bc09390d0a9c5563338a6a5eefdd9d44677ea3237f387da34c686a450eeb0f")
rpc = (env.get("BASE_RPC_URL") or "").strip()
receiver = (env.get("BASE_FEE_RECEIVER") or "").strip().lower()
usdc = (env.get("BASE_USDC_CONTRACT")
        or "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913").lower()
try:
    from eth_utils import keccak
    TRANSFER_TOPIC = "0x" + keccak(
        text="Transfer(address,address,uint256)").hex()
except Exception:
    TRANSFER_TOPIC = ("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f5"
                      "5a4df523b3ef")

receipt = requests.post(rpc, timeout=60, json={
    "jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionReceipt",
    "params": [NEW_TX]}).json().get("result") or {}
print("    receipt status:", receipt.get("status"), "| block:",
      int(receipt.get("blockNumber") or "0x0", 16),
      "| from:", (receipt.get("from") or "")[:12] + "…")
found = False
for entry in receipt.get("logs", []):
    topics = entry.get("topics") or []
    if len(topics) >= 3 and topics[0].lower() == TRANSFER_TOPIC:
        to_addr = "0x" + topics[2][-40:]
        value = int(entry.get("data") or "0x0", 16)
        print("    USDC Transfer: contract=%s | to=%s…%s | %s atomic (%.6f)"
              % ((entry.get("address") or "")[:12] + "…", to_addr[:8],
                 to_addr[-6:], value, value / 1e6))
        print("      to == our fee receiver:", to_addr.lower() == receiver)
        print("      token == USDC env:", (entry.get("address") or "").lower()
              == usdc)
        found = True
        break
print("    Transfer log found:", found)

print("\n=== VERDICT: the four greens ===")
crm_refunded = round(float(the_lead.get("refund_usd") or 0), 2)
greens = {
    "stripe event delivered": event_delivered,
    "refund recorded in Stripe": stripe_refunded_total > 0,
    "payment facts in CRM": bool(the_lead.get("paid_at")
                                 and the_lead.get("checkout_id")),
    # The point of the 17.09 fix: the book must COUNT what came back, and its
    # number must equal Stripe's — a refund visible in Stripe but invisible in the
    # CRM is money missing from our own records.
    "refunds visible in CRM": (crm_refunded > 0
                               and bool(the_lead.get("refunded_at"))
                               and abs(crm_refunded - stripe_refunded_total) < 0.01),
}
for name, ok in greens.items():
    print("    %-28s %s" % (name, "GREEN" if ok else "RED"))
print("    CRM refunded $%.2f · Stripe refunded $%.2f · refunded_at=%s"
      % (crm_refunded, stripe_refunded_total,
         the_lead.get("refunded_at") or "(unset)"))
if all(greens.values()):
    print("    ALL FOUR GREEN — the payment path AND the refund path agree end "
          "to end.")
    raise SystemExit(0)
print("    NOT ALL GREEN: %s" % ", ".join(k for k, v in greens.items() if not v))
raise SystemExit(1)