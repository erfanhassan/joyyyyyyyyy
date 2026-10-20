# Project JOY

An imported digital workforce platform for retail and e-commerce: connect stores, train a knowledge brain, configure AI employees, and monitor conversations in an operator workbench.

## Run & Operate

- Start the managed workflows `artifacts/joy: web` and `artifacts/api-server: API Server`.
- The frontend is Vite/React at `/`; the original Python FastAPI backend handles `/api`, `/ws`, `/health`, `/docs`, `/redoc`, and `/openapi.json`.
- The backend reads `PORT` from its managed workflow and uses the project's `DATABASE_URL`. Database URL normalization for SQLAlchemy is preserved.
- Install dependencies with `pnpm install --frozen-lockfile` and `uv sync --frozen`. Python packages are managed by Replit's Python module, `pyproject.toml`, and `uv.lock`; do not create a separate virtual environment.
- Run browser regression checks with `pnpm exec playwright test`. They use the running app through the shared proxy at `localhost:80`. Set `CHROMIUM_PATH` if Chromium lives somewhere other than `/repl/tools/bin/chromium`.
- Frontend type check: `pnpm --filter @workspace/joy run typecheck`.

## Stack and source map

- `artifacts/joy/`: Vite/React, wouter, original Tailwind v3 configuration, original local Geist fonts, and all imported pages.
- `artifacts/api-server/app/`: original FastAPI routes, agents, services, SQLAlchemy models, and Alembic migrations.
- `artifacts/api-server/scripts/seed_workspace.py`: idempotently initializes the storefront used by the imported UI; it never overwrites existing data.
- `tests/migration.spec.ts`: navigation, guardrail persistence, live WebSocket, and mobile smoke checks.
- `docs/`: original product, design, architecture, and flow documentation.
- `.migration-backup/`: preserved import for reference, excluded from deployment.
- `lib/*` and the unused Express sources in `artifacts/api-server/src/` are workspace scaffold packages, not the active backend. Do not replace the Python backend with the empty Express implementation.

## Database operations

The original PostgreSQL/pgvector schema and tenant isolation policies are preserved. Development was initialized using the imported Alembic migrations and a default storefront; the import did not include existing merchant records or provider credentials.

For new development databases, from `artifacts/api-server`:

```sh
uv run --project ../.. --frozen python -m alembic upgrade head
PYTHONPATH=. uv run --project ../.. --frozen python scripts/seed_workspace.py
```

The development-only post-merge hook installs dependencies and applies these same migrations. Do not run Drizzle push against this database: its scaffold schema is empty and is not the source of truth. Production schema changes use Replit Publish; application startup and production build do not run DDL.

## External services and inherited limitations

- No external provider credentials were included in the import. Real Meta/Shopify/WooCommerce, AI, LiveKit, and telephony operations require their original service settings in Replit Secrets. The relevant setting names are in `artifacts/api-server/app/core/config.py`.
- Optional browser overrides are `VITE_API_URL`, `VITE_WS_URL`, and `VITE_META_APP_ID`. Default browser API/WebSocket requests stay on the same origin.
- Redis is optional for the inherited local/in-process fallback; shared cross-process event delivery and durable webhook deduplication require a configured Redis service.
- Existing offline AI/demo behavior and fixed workspace identity are unchanged. The workspace preview retains the imported behavior; it is not a production tenant-authentication system.
- Public deployments fail closed for administrative REST endpoints and all workbench sockets until tenant-authorized authentication is implemented. A banner explains this on published pages. Health and the public widget remain available; only configured, signature-verified providers may receive webhooks. The unverified telephony callback is not publicly exposed.
- Provider token encryption requires a private `ENCRYPTION_KEY_SECRET` or the existing `SESSION_SECRET` (at least 32 characters). The original publicly known key is rejected. Keep this secret stable or previously encrypted credentials cannot be read.
- The imported backend's legacy external-service tests can trigger real API requests or phone calls. Do not run those without provider setup and explicit approval. The migration browser tests do not invoke third-party actions.
