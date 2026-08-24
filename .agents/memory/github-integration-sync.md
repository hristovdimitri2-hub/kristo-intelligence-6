---
name: GitHub integration sync
description: Safe GitHub synchronization when the local Git remote cannot push directly.
---

When HTTPS Git authentication is unavailable or local and remote histories have diverged, use the configured GitHub connection rather than force-pushing.

**Why:** A local commit can be valid while the remote branch has advanced independently. A force push risks deleting that remote work, and a CLI credential failure is not a reason to request a token from the user.

**How to apply:** Compare each changed file's remote blob to the local base blob first. Only when there is no overlap, create blobs, a tree, and a commit on the current remote tip through the GitHub API, then update the branch ref with `force: false`. Stop for a manual merge if any changed blob differs.