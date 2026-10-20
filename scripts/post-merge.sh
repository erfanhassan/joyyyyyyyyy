#!/bin/bash
set -e
pnpm install --frozen-lockfile
uv sync --frozen
# Keep the imported SQLAlchemy schema; never run the empty Drizzle scaffold's push.
# This hook runs in development only. Production schema changes use Publish.
(
  cd artifacts/api-server
  uv run --project ../.. --frozen python -m alembic upgrade head
  PYTHONPATH=. uv run --project ../.. --frozen python scripts/seed_workspace.py
)
