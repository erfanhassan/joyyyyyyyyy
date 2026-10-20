from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
import httpx
from starlette.responses import Response
from app.core.config import settings
from app.core.clerk_auth import clerk_auth_configured
from app.core.deployment_guard import DeploymentGuard, is_public_deployment
from app.api.webhooks.meta import router as meta_webhook_router
from app.api.webhooks.shopify import router as shopify_webhook_router
from app.api.webhooks.woocommerce import router as woocommerce_webhook_router
from app.api.webhooks.custom import router as custom_webhook_router
from app.api.webhooks.telephony import router as telephony_webhook_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.widget import router as widget_router
from app.api.routes.tenant import router as tenant_router
from app.api.routes.agent_config import router as agent_config_router
from app.api.websockets.workbench import router as workbench_router

from contextlib import asynccontextmanager
import logging
from sqlalchemy import text
from app.db.session import async_engine
from app.db.models import Base

logger = logging.getLogger("joy.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed separately: Alembic in development, Publish in production.
    # Never run schema-changing statements while the application starts.
    yield
    await async_engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Project Joy: Multi-Tenant Agentic AI SaaS Platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DeploymentGuard)

# Register Ingestion Webhook Routers
app.include_router(meta_webhook_router, prefix="/api/v1/webhooks")
app.include_router(shopify_webhook_router, prefix="/api/v1/webhooks")
app.include_router(woocommerce_webhook_router, prefix="/api/v1/webhooks")
app.include_router(custom_webhook_router, prefix="/api/v1/webhooks")
app.include_router(telephony_webhook_router, prefix="/api/v1/webhooks")
app.include_router(telephony_webhook_router, prefix="/api/webhooks")

# Register Knowledge Brain Routers
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api")

# Register Universal Web Widget Routers
app.include_router(widget_router, prefix="/api/v1")
app.include_router(widget_router, prefix="/api")

# Register Operator Workbench & WebSocket Routers
app.include_router(workbench_router, prefix="/api/v1")
app.include_router(workbench_router)

# Register Tenant & Digital Employee Management Routers
app.include_router(tenant_router, prefix="/api/v1")
app.include_router(tenant_router, prefix="/api")
app.include_router(agent_config_router, prefix="/api/v1")
app.include_router(agent_config_router, prefix="/api")


@app.get("/health", tags=["System"])
@app.get("/api/healthz", tags=["System"])
async def health_check():
    """Health check endpoint to verify backend service status."""
    return {
        "status": "ok",
        "app": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0",
        "administration_available": (
            not is_public_deployment() or clerk_auth_configured()
        ),
        "administration_requires_sign_in": is_public_deployment(),
    }


@app.get("/api/auth/me", tags=["Authentication"], include_in_schema=False)
async def current_admin(request: Request):
    if is_public_deployment() and not request.scope.get("state", {}).get(
        "is_joy_owner"
    ):
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return {
        "authenticated": True,
        "role": "owner",
        "meta_app_id": settings.META_APP_ID,
    }


@app.api_route(
    "/api/__clerk",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
@app.api_route(
    "/api/__clerk/{path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def clerk_frontend_api_proxy(request: Request, path: str = ""):
    if not is_public_deployment():
        raise HTTPException(status_code=404, detail="Not found.")
    if not settings.CLERK_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Sign-in proxy is not configured.")

    headers = dict(request.headers)
    for hop_header in (
        "host",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
    ):
        headers.pop(hop_header, None)

    forwarded_host = (
        request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
        or request.headers.get("host", "").split(",", 1)[0].strip()
    )
    if not forwarded_host:
        raise HTTPException(status_code=400, detail="Missing request host.")
    forwarded_proto = (
        request.headers.get("x-forwarded-proto", "https").split(",", 1)[0].strip()
        or "https"
    )
    headers["Clerk-Proxy-Url"] = (
        f"{forwarded_proto}://{forwarded_host}/api/__clerk"
    )
    headers["Clerk-Secret-Key"] = settings.CLERK_SECRET_KEY
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if not forwarded_for and request.client:
        forwarded_for = request.client.host
    if forwarded_for:
        headers["X-Forwarded-For"] = forwarded_for

    upstream_url = f"https://frontend-api.clerk.dev/{path}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            upstream = await client.request(
                request.method,
                upstream_url,
                headers=headers,
                content=await request.body(),
            )
    except httpx.HTTPError as exc:
        logger.warning("Clerk frontend proxy failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Sign-in service is unavailable.") from None

    hop_headers = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-encoding",
        "content-length",
    }
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in hop_headers and key.lower() != "set-cookie"
    }
    response = Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )
    for cookie in upstream.headers.get_list("set-cookie"):
        response.raw_headers.append((b"set-cookie", cookie.encode("latin-1")))
    return response


@app.get("/", tags=["System"])
async def root():
    """Root endpoint welcoming clients to Project Joy."""
    return {
        "message": "Welcome to Project JOY - Multi-Tenant Digital Workforce Platform",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "meta_webhook": "/api/v1/webhooks/meta",
            "shopify_webhook": "/api/v1/webhooks/shopify",
            "woocommerce_webhook": "/api/v1/webhooks/woocommerce",
            "custom_webhook": "/api/v1/webhooks/custom",
            "telephony_webhook": "/api/v1/webhooks/telephony/completion",
            "knowledge_upload": "/api/v1/knowledge/upload",
            "knowledge_crawl": "/api/v1/knowledge/crawl",
            "knowledge_query": "/api/v1/knowledge/query",
            "widget_script": "/api/v1/widget/widget.js",
            "widget_chat": "/api/v1/widget/chat",
        },
    }
