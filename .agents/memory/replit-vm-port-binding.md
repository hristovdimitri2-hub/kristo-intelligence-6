---
name: VM deployment port binding
description: How Replit VM deployment health checks discover the application listener.
---

Production server commands for Replit VM deployments must bind to the runtime-provided `PORT` value rather than a fixed development port.

**Why:** The deployment proxy health-checks its assigned port; a process that listens only on a hardcoded port can start normally but still fail health checks and leave the public URL unavailable.

**How to apply:** When configuring the deployment run command, preserve the runtime `PORT` variable in the server bind argument and verify the production logs show the same port being listened on.