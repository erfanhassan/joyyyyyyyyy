"""Keep inherited unauthenticated admin endpoints closed in public deployments.

No shared password or tenant ID is treated as authentication. Until proper
tenant-authorized login is implemented, production administration is unavailable.
"""
import os
from starlette.responses import JSONResponse
from app.core.config import settings


def is_public_deployment() -> bool:
    return (
        settings.ENVIRONMENT.lower() == "production"
        or os.environ.get("NODE_ENV") == "production"
        or os.environ.get("REPLIT_DEPLOYMENT") == "1"
    )


def is_public_route(path: str, method: str) -> bool:
    if path in ("/health", "/api/healthz"):
        return method in ("GET", "HEAD")
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
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            if scope["type"] == "http" and not is_public_route(
                scope["path"], scope["method"]
            ):
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "Administration is disabled in public deployments until tenant-authorized sign-in is configured."},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
