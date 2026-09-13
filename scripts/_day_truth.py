"""Day of truth check: dashboard state after 14h catch-up."""
import requests

d = requests.get("https://kristo-intelligence-api.onrender.com/api/dashboard/data",
                 timeout=40).json()
o = d["sections"]["onchain"]
print("ОЧАКВАНО: $0.028 / 8 tx / 2 external (веригата — integrations/verified_sales.py)")
print("ЗАБЕЛЕЖКА: $0.026 / 3 external беше ГРЕШНО (0xA19F никога не е плащал)")
print("РЕАЛНО:  ", o["total_usdc"], "/", o["total_count"], "tx | external:",
      o["external_payers"])
print("by_class:", o["by_class"])
print("watermark:", o["last_scanned_block"])
print("история:")
for h in o["history"][:10]:
    print("  %s  $%-8s %-9s tx=%s" % (
        h["ts"][:19], h["amount_usdc"], h["payer_class"], h["tx_hash"][:24]))