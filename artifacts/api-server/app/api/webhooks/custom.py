"""Custom-site chat is supported; generic order ingestion has no agreed schema."""
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/custom", tags=["Custom Storefront Webhooks"])


@router.post("")
@router.post("/{tenant_id}")
async def receive_custom_webhook(request: Request, tenant_id: str = "default"):
    raise HTTPException(501, "Custom order ingestion is unavailable. Use the web chat widget or a supported store connector. No order was accepted.")
