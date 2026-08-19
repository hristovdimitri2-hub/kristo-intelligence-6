---
name: Git history secret sanitization
description: Requirements for removing exposed credentials before a repository becomes public.
---

Removing a credential from the current worktree is insufficient: sanitize every reachable ref, prune old objects, and verify the public branch has no history path to the exposed value.

**Why:** A deleted secret remains retrievable from ancestor commits, backup refs, and remote-tracking branches. Rotation limits the impact but does not make publication safe.

**How to apply:** Before publishing after a credential exposure, run history cleanup as an explicit maintenance step, then scan all refs, rewrite or replace the public branch history, expire reflogs and garbage-collect local objects, and verify the local object store plus public remote files. Keep automated tests non-destructive.