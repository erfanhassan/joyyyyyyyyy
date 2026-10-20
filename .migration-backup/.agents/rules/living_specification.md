# Antigravity Living Specification Rules

1. **Source of Truth:** All product vision, technical architecture, data schemas, UI designs, and roadmaps are governed by the markdown files in `/docs`:
   - `docs/PRD.md` (Product Requirements Document)
   - `docs/TRD.md` (Technical Requirements Document)
   - `docs/APP_FLOW.md` (System Interaction & Event Flows)
   - `docs/BACKEND_SCHEMA.md` (PostgreSQL DDL, RLS & Redis Schemas)
   - `docs/DESIGN_BRIEF.md` (UI/UX Design System & Page Frameworks)
   - `docs/ROADMAP.md` (Sprint Execution & Milestone Plan)

2. **Cascading Bi-Directional Spec Synchronization:**
   - Whenever code, database models, API endpoints, or integrations are added or changed, you MUST update the corresponding markdown file(s) in `/docs` first or in tandem with the code.
   - If the user modifies any markdown file in `/docs`, you MUST automatically refactor the backend and frontend codebase to match the updated specifications.

3. **Multi-Tenant Isolation:** Every SQL model, pgvector search, Redis key, and API route MUST enforce strict `tenant_id` scoping.

4. **Security & Guardrails:** Enforce HMAC-SHA256 signature verification on all webhooks, AES-256 token encryption at rest, and Redis idempotency before execution.
