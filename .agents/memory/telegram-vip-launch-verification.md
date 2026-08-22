---
name: Telegram VIP launch verification
description: Live configuration requirements that must be checked before claiming Telegram VIP fulfillment is ready.
---

Treat Telegram VIP delivery as unverified until the configured target is a supergroup, the bot is a current member with permission to create invite links, and a real one-use invite delivery has succeeded.

**Why:** A valid bot token and registered webhook can coexist with a stale group ID or a bot that has left the group. Telegram then rejects invite creation even though application health checks and webhook registration look healthy.

**How to apply:** Before public launch or after a group migration, run read-only `getChat`, `getChatMember`, and `getWebhookInfo` checks, then perform one controlled paid-delivery smoke test only after confirming the bot's admin invite permission.

Telegram webhook registration must remain an explicit production opt-in. Local starts and preview restarts must never silently call Telegram `setWebhook`.

**Why:** `setWebhook` overwrites the bot's remote delivery URL. A development runtime with an old configured URL can redirect live updates away from the intended production deployment.

**How to apply:** Keep automatic registration disabled by default. Only enable it in production after confirming the published URL and webhook secret; restart once, verify the resulting Telegram webhook, then keep development instances opt-out.