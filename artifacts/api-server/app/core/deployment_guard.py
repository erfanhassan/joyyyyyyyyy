"""Restrict public production administration to the configured JOY owner."""
import os
from starlette.responses import JSONResponse
from app.core.config import settings
from app.core.clerk_auth import (
    ClerkAuthFailure,
    authenticate_owner,
    clerk_auth_configured,
)


def is_public_deployment() -> bool:
    return (
        settings.ENVIRONMENT.lower() == "production"
        or os.environ.get("NODE_ENV") == "production"
        or os.environ.get("REPLIT_DEPLOYMENT") == "1"
    )


def is_public_route(path: str, method: str) -> bool:
    if path in ("/health", "/api/healthz"):
        return method in ("GET", "HEAD")
    if path == "/api/__clerk" or path.startswith("/api/__clerk/"):
        return method in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    if path in ("/api/widget/widget.js", "/api/v1/widget/widget.js"):
        return method == "GET"
    if path in ("/api/widget/chat", "/api/v1/widget/chat"):
        return method == "POST"
    # Only providers that already verify signatures may receive public webhooks.
    prefix = "/api/v1/webhooks/"
    if path.startswith(prefix):
        provider = path[len(prefix):].split("/", 1)[0]
        secrets = {
            "meta": settings.META_APP_SECRET,
            "shopify": settings.SHOPIFY_API_SECRET,
            "woocommerce": settings.WOOCOMMERCE_WEBHOOK_SECRET,
            "custom": settings.SHOPIFY_API_SECRET or settings.ENCRYPTION_KEY_SECRET,
        }
        if provider == "meta" and method == "GET":
            return bool(
                settings.META_VERIFY_TOKEN
                and settings.META_VERIFY_TOKEN != "joy_meta_verify_token_default"
            )
        return method == "POST" and bool(secrets.get(provider))
    return False


class DeploymentGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if is_public_deployment():
            scope_type = scope["type"]
            path = scope.get("path", "")
            method = scope.get("method", "")
            if scope_type == "http" and is_public_route(path, method):
                await self.app(scope, receive, send)
                return

            if scope_type not in ("http", "websocket"):
                await self.app(scope, receive, send)
                return

            if not clerk_auth_configured():
                if scope_type == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    response = JSONResponse(
                        status_code=403,
                        content={
                            "detail": "Administration is disabled until secure sign-in is configured."
                        },
                    )
                    await response(scope, receive, send)
                return

            try:
                identity = await authenticate_owner(scope)
            except ClerkAuthFailure as exc:
                if scope_type == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    response = JSONResponse(
                        status_code=exc.status_code,
                        content={"detail": exc.detail},
                    )
                    await response(scope, receive, send)
                return

            scope.setdefault("state", {}).update(
                {
                    "clerk_user_id": identity["user_id"],
                    "is_joy_owner": True,
                }
            )
        await self.app(scope, receive, send)
