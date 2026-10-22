---
name: Meta reconnect notices
description: Decision on how JOY represents owner-facing Meta reconnect alerts.
---

Meta reconnect notices are derived from the existing tenant integration recovery state rather than stored as separate notification rows. The state is tenant-scoped, deduplicated on first transition, and cleared by replacing or validating the connection settings. Expose only safe provider/channel labels to workspace owners; never return credential or provider error payloads.

**Why:** A second alert record would duplicate the connection lifecycle and could remain stale after a successful reconnect.

**How to apply:** Keep dashboard alerts tied to the integration's current reconnect state. Add a separate durable notification model only if future requirements introduce independent delivery channels, read/unread history, or per-recipient delivery status.
