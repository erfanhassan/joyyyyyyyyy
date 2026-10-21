---
name: Async database test isolation
description: Why database fixtures must not reuse pooled connections across pytest and TestClient event loops.
---

Use a test-specific async engine with NullPool when a test creates its own event loop. Reuse the application's normalized engine URL rather than interpreting the raw database configuration again.

**Why:** TestClient and pytest async tests can run on different loops; pooled asyncpg connections retain the loop that created them. A raw PostgreSQL URL can also select an unavailable psycopg driver under a newer SQLAlchemy default.

**How to apply:** New database regression tests should follow the existing isolated-engine fixture convention and dispose their engine after cleanup. Do not change the production connection pool to work around a test-only loop problem.
