---
name: Migration boundaries
description: Why the imported backend and database schema must not be replaced by the generic workspace scaffold
---

Preserve the existing Python/FastAPI backend and the original website's design when maintaining this imported product. The conversion to a pnpm workspace was an environment port, not permission to redesign or replace the product's backend or storage model.

**Why:** The import includes a substantial Python agent runtime, PostgreSQL tenant policies, pgvector knowledge storage, and realtime conversations. Replacing it with the empty Express/Drizzle scaffold would lose those behaviors. The original scope required visual and functional parity.

**How to apply:** Treat the imported SQLAlchemy/Alembic schema as authoritative, never the empty Drizzle scaffold. Keep schema changes out of production startup/build. Existing merchant data and external service credentials were not included in the import; do not claim those were migrated or tested.

Public deployments must keep the imported administrative API and workbench sockets disabled until tenant-authorized authentication is implemented. Do not remove that deployment guard merely to make the published dashboard look functional.

**Why:** The imported product has no administrative authentication. Exposing its existing tenant identifier does not grant a safe authorization boundary.

**How to apply:** Preserve local preview behavior for migration parity, but explicitly report the public-deployment limitation. Require private deployment-provided token encryption material; never restore the original known default key.
