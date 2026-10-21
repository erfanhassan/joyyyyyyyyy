import logging
import httpx
from app.core.config import settings


async def token_owner(token):
    if not settings.META_APP_ID or not settings.META_APP_SECRET:
        raise RuntimeError("Meta app verification is not configured.")
    # Debug-token requests contain credentials in provider-required query fields.
    # Do not allow httpx's informational request logger to print those URLs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.get("https://graph.facebook.com/v26.0/debug_token",
            headers={"Authorization": f"Bearer {settings.META_APP_ID}|{settings.META_APP_SECRET}"},
            params={"input_token": token})
        data = response.json().get("data", {})
    if response.status_code != 200 or not data.get("is_valid") or str(data.get("app_id")) != settings.META_APP_ID:
        raise RuntimeError("The token does not belong to the configured Meta application.")
    if not data.get("user_id"):
        raise RuntimeError("Meta did not identify the authorizing user.")
    return str(data["user_id"])
