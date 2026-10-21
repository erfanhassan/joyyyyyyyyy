# Production release gates

This build is an owner-only release candidate, not a certification of live provider delivery.

## Implemented safeguards

- Verified Clerk identity is bound to an explicit workspace membership. Public onboarding is off by default. Request-scoped ORM filtering adds isolation independently of the managed database owner's RLS privileges.
- Widget visitors receive signed, expiring, business-bound identities. Merchant origins are checked, public preflights are allowed, messages render through safe DOM APIs, and operator replies are polled.
- Website-origin setup has its own update endpoint, so it does not replace other business settings. Polling supports browser same-origin GET requests without an Origin header, without accepting a conflicting foreign Origin.
- Workbench WebSocket subscriptions enforce verified workspace membership as well as HTTP authorization.
- Webhook acknowledgements follow a durable database commit. Jobs have leases, bounded execution, retries and dead-letter states. Provider assets are resolved separately for every event.
- External sends reserve persistent receipts. Uncertain outcomes require human review instead of automatic duplicate sends.
- Store stock is authoritative only when verified through a single Shopify or WooCommerce connection. Uploaded text is not proof of availability. Follow-up purchases refresh the selected product.
- Shopify checkout uses a real draft invoice; WooCommerce uses a real single-use coupon and native checkout. No paid order or fake checkout URL is invented. Checkout is currently limited to an unambiguous single variant/simple product.
- New store credentials are verified with read-only provider calls before saving. Saved connection metadata is not proof that a checkout transaction has passed.
- Tokens are encrypted at rest and removed from graph state. Nested API responses are redacted. Unsubscription failure retains the connection for retry instead of falsely claiming success.
- Crawling is HTTPS-only, with public DNS validation, address pinning and no redirects. Upload, request, crawl, page, row and chunk limits are enforced.
- Unsupported agent types cannot be hired or activated. Phone calling is disabled instead of reporting simulated calls.
- WhatsApp Cloud API supports verified phone/WABA ownership and inbound text conversations with replies inside the customer-service window. Approved outbound templates and opt-in campaigns are not enabled.
- Meta-signed privacy requests revoke local credentials immediately. Data deletion is a separately confirmed app-owner action after in-flight processing finishes. Legacy ownership ambiguity is reported for review, not falsely marked complete.

## Required before public launch

1. Publish the verified workspace changes and schema through Replit's Publish flow. This workspace does not modify the live database or publish automatically.
2. Use an always-on API/worker deployment, or a separately managed continuously running worker. The worker command is `PYTHONPATH=artifacts/api-server uv run --frozen python -m app.services.webhook_jobs`. An autoscaling API alone does not guarantee timely retries after scaling to zero.
3. Configure the canonical merchant domain and provider webhook subscriptions. Set per-store webhook signing secrets. Run provider callbacks against the published routes, not the preview.
4. Complete required Meta business/app verification and advanced permissions. Verify Facebook, Instagram and WhatsApp connections with real merchant assets. Publication alone does not grant access to other customers' accounts.
5. Run an explicitly authorized test of inbound messages, AI and human replies, reconnect/disconnect, privacy requests, provider rate limits and expired credentials. Never use an unconsented customer conversation for testing.
6. Run Shopify/WooCommerce test purchases with the intended product variants, currency, tax, shipping, discount and payment setup. Verify the final checkout independently. Read-only credential verification does not test writes or payments.
7. For phone confirmation, implement/deploy a real LiveKit voice worker, provision the outbound SIP trunk, and verify AmberIT permits the chosen routing and egress location. Do not enable calling until a separately authorized test call proves audio, consent, caller identity and signed call results.
8. Review privacy retention, backup restoration, service monitoring, dead jobs and uncertain checkout/delivery outcomes. Do not replay an uncertain external operation until the provider confirms it was not accepted.
9. Enable `ALLOW_PUBLIC_SIGNUPS` only after merchant-isolation and provider acceptance checks succeed.

## Dependency advisory

Patchable advisories were updated. `braces@3.0.3` still has a high-severity advisory with no upstream patched release. A pinned local pnpm patch bounds parsed AST depth and converts overly nested patterns to escaped literals; regression checks exercise compilation, expansion and stringification below the package's existing input-length ceiling. Version-based audits will continue flagging it. The patch does not make arbitrary externally supplied AST objects safe. This dependency is in trusted build-time glob tooling, not the shipped browser runtime or Python API. Do not expose untrusted glob patterns or ASTs to that tooling; retain the patch until an upstream fix is available.

## Verification commands

The final backend suite passed 104 tests. Browser verification covered landing/sign-in, QA onboarding, integration setup, employee/workbench pages, website-origin registration, widget messaging and delivery of an operator reply through polling. These checks used disposable development QA data, not live provider transactions or production customer data.

```
PYTHONPATH=artifacts/api-server uv run --frozen python -m pytest -q artifacts/api-server/tests
pnpm --filter @workspace/joy run typecheck
pnpm --filter @workspace/joy run build
pnpm audit
node artifacts/joy/scripts/check-glob-depth.cjs
```

Production schema updates belong in the normal Publish workflow. Do not add schema-changing SQL to server startup or a recurring deployment build.
