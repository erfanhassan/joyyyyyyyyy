# Pull request and browser checks

## Automatic GitHub checks

`.github/workflows/pull-request-checks.yml` runs on pull requests, pushes to
`main`, and manual workflow dispatch. It runs two independent jobs:

- **Frontend type check** — `pnpm --filter @workspace/joy run typecheck`
- **Deployment safety tests** — `PYTHONPATH=artifacts/api-server uv run --frozen python -m pytest -q artifacts/api-server/tests/test_deployment_guard.py`

Both jobs use lockfiles and test-only configuration. They do not need production
credentials, a production database, or access to customer data. GitHub shows each
job and its failure details on the pull request. A repository administrator must
make these checks required in branch protection if merges should be blocked until
they pass.

## Browser regression check in Replit

The browser suite in `tests/migration.spec.ts` uses the Replit local app proxy at
`http://localhost:80`, a running JOY web and API server, and existing development
agent data. It is therefore run from the configured Replit `migration-browser`
workflow rather than GitHub-hosted runners.

1. Start the JOY web and API workflows for the development environment.
2. Run the **migration-browser** workflow, or run `pnpm exec playwright test` in
   the Replit Shell.
3. Review the workflow output for failures.

Run this check against development data only, never production: the guardrails
test temporarily changes a development employee's discount limit and restores
it when the test finishes. The GitHub workflow intentionally does not claim this
browser suite passed; browser CI can be added after the app and test data can be
started reproducibly without the Replit proxy.
