from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
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
    # Auto-initialize database tables if PostgreSQL is available
    try:
        async with async_engine.begin() as conn:
            try:
                await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
            except Exception as e:
                logger.warning(f"uuid-ossp extension creation skipped: {e}")
            try:
                await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "vector";'))
            except Exception as e:
                logger.warning(f"vector extension creation skipped: {e}")
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/initialized successfully on startup.")
    except Exception as e:
        logger.warning(f"Database auto-initialization skipped or delayed: {e}")
    yield


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
async def health_check():
    """Health check endpoint to verify backend service status."""
    return {
        "status": "ok",
        "app": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0",
    }


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
