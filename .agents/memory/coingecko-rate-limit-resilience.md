---
name: CoinGecko rate-limit resilience
description: Rules for responding safely to CoinGecko throttling without mislabeling cached market data.
---

On a CoinGecko 429, stop further upstream attempts, honor the bounded `Retry-After` cooldown, and return the last successful snapshot only with explicit stale/freshness metadata.

**Why:** Retrying immediately after a provider-issued throttle prolongs the limit and can make Telegram and dashboard responses slow or misleading.

**How to apply:** Keep cache age calculated at read time, use stale data only within a bounded retention window, and make all customer/admin surfaces distinguish live, cached, stale, and unavailable data.