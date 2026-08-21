---
name: Telegram VIP launch verification
description: Live configuration requirements that must be checked before claiming Telegram VIP fulfillment is ready.
---

Treat Telegram VIP delivery as unverified until the configured target is a supergroup, the bot is a current member with permission to create invite links, and a real one-use invite delivery has succeeded.

**Why:** A valid bot token and registered webhook can coexist with a stale group ID or a bot that has left the group. Telegram then rejects invite creation even though application health checks and webhook registration look healthy.

**How to apply:** Before public launch or after a group migration, run read-only `getChat`, `getChatMember`, and `getWebhookInfo` checks, then perform one controlled paid-delivery smoke test only after confirming the bot's admin invite permission.