---
name: GitHub access and synchronization
description: Canonical JOY repository, remote verification, and distinctions between API and Git transport permissions.
---

Use `https://github.com/erfanhassan/joyyyyyyyyy` as JOY's main source repository, not the old `project-joy` repository.

**Why:** The user explicitly confirmed that `joyyyyyyyyy` is the main repository.

**How to apply:** Verify the active workspace's `origin` before fetching or pulling. Do not assume a repository-switch task updated the parent workspace's Git configuration: one such task was merged while the active remote still pointed to the old repository. Preserve local commits when merging upstream updates.

Do not infer Git transport authentication or repository-deletion permission from a successful GitHub API read or an `admin: true` repository permissions field. Replit's GitHub API connection can manage repository content while its configured OAuth scopes still block repository deletion; the workspace Git CLI may also lack credentials even when a GitHub source-control connection is active.

**Why:** A repository migration succeeded through GitHub's Git Data API, but deleting the old repository was denied because the connected authorization did not include repository-deletion permission, and `git push` was unauthenticated.

**How to apply:** Before a repository migration that includes deletion, verify the exact deletion endpoint permission and Git transport access early. If unavailable, finish and verify the replacement repository, then report that deletion needs an authorized owner action; never bypass the provider's permission checks.
