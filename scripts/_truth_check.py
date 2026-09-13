"""Day of truth check: dashboard vs the owner's prediction (read-only)."""
import requests

d = requests.get("https://kristo-intelligence-api.onrender.com/api/dashboard/data",
                 timeout=40).json()
o = d["sections"]["onchain"]
print("ОЧАКВАНО: $0.028 / 8 tx / 2 external + Chet canary 0xc302… (recovered) последен по блок")
print("РЕАЛНО:  ", o["total_usdc"], "/", o["total_count"], "tx | external:",
      o["external_payers"])
print("by_class:", o["by_class"])
print("история (нови -> стари):")
for h in o["history"][:9]:
    print("  %s  $%-8s %-9s %-28s tx=%s" % (
        h["ts"][:19], h["amount_usdc"], h["payer_class"],
        h["payer_label"][:26], h["tx_hash"][:22]))
print("wm:", o["last_scanned_block"])