import logging
from typing import Dict, Any, Optional, List
import httpx
from fastapi import HTTPException
from app.core.config import settings
from app.core.deployment_guard import is_public_deployment

logger = logging.getLogger("joy.meta_api")
GRAPH_API_VERSION = "v24.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class MetaAPIClient:
    """
    Client for Meta Graph API:
    - Instagram Graph API (DMs, comments, private replies)
    - Facebook Messenger API (DMs, comment-to-DM auto-replies)
    - Handshake CTA to open the standard 24-hour messaging window
    - OAuth Exchange, Page & Instagram discovery, and Webhook subscriptions
    """

    @staticmethod
    async def get_page_identity(page_id: str, page_access_token: str) -> Dict[str, Any]:
        """Read-only live verification; never report a simulated Page as connected."""
        if not page_id or not page_id.isdigit() or not page_access_token or any(
            marker in page_access_token.lower() for marker in ("simulated", "sandbox_token")
        ) or page_access_token.startswith(("joy_", "mock_", "test_")):
            raise HTTPException(status_code=400, detail="A real Facebook Page ID and Page access token are required.")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{GRAPH_API_BASE}/{page_id}",
                    headers={"Authorization": f"Bearer {page_access_token}"},
                    params={"fields": "id,name,instagram_business_account{id,username}"},
                )
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Meta rejected the Page credentials or permissions. Reconnect the Page.")
            data = response.json()
            if data.get("id") != page_id or not data.get("name"):
                raise HTTPException(status_code=400, detail="The token does not identify the selected Facebook Page.")
            return {"id": data["id"], "name": data["name"],
                    "instagram_business_account": data.get("instagram_business_account") or {}}
        except (httpx.HTTPError, ValueError):
            raise HTTPException(status_code=502, detail="Meta could not be reached or returned an invalid response. Retry later.") from None

    @staticmethod
    def require_delivery_confirmation() -> None:
        if is_public_deployment():
            raise RuntimeError("Meta did not confirm delivery. Check the Page access token, approved permissions and messaging window.")

    @staticmethod
    async def exchange_code_for_user_token(code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchanges an OAuth authorization code for a user access token."""
        url = f"{GRAPH_API_BASE}/oauth/access_token"
        params = {
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            if resp.status_code != 200:
                logger.error(f"Meta OAuth exchange code error: {data}")
                raise Exception(data.get("error", {}).get("message", "Failed to exchange OAuth code with Meta"))
            return data

    @staticmethod
    async def get_long_lived_user_token(short_lived_token: str) -> Dict[str, Any]:
        """Exchanges a short-lived user token for a long-lived user token (60-day lifespan)."""
        url = f"{GRAPH_API_BASE}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "fb_exchange_token": short_lived_token,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            if resp.status_code != 200:
                logger.warning(f"Meta long-lived exchange warning: {data}")
                return {"access_token": short_lived_token}
            return data

    @staticmethod
    async def get_user_pages_and_instagram(user_access_token: str) -> List[Dict[str, Any]]:
        """
        Fetches all Facebook Pages the user manages, with their Page Access Tokens
        and connected Instagram Business Accounts.
        """
        url = f"{GRAPH_API_BASE}/me/accounts"
        params = {
            "fields": "id,name,category,access_token,tasks,instagram_business_account{id,username,name}",
            "access_token": user_access_token,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            if resp.status_code != 200:
                logger.error(f"Failed to fetch user pages: {data}")
                raise Exception(data.get("error", {}).get("message", "Failed to retrieve Facebook pages"))

            pages = []
            for item in data.get("data", []):
                ig = item.get("instagram_business_account")
                pages.append({
                    "page_id": item.get("id"),
                    "page_name": item.get("name"),
                    "page_access_token": item.get("access_token"),
                    "instagram_business_account_id": ig.get("id") if ig else None,
                    "instagram_username": ig.get("username") if ig else None,
                    "has_instagram": bool(ig),
                })
            return pages

    @staticmethod
    async def subscribe_page_to_webhooks(page_id: str, page_access_token: str) -> Dict[str, Any]:
        """Subscribes Joy to the Facebook Page's webhook events."""
        url = f"{GRAPH_API_BASE}/{page_id}/subscribed_apps"
        params = {
            "subscribed_fields": "messages,messaging_postbacks,feed",
            "access_token": page_access_token,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, params=params)
                return resp.json()
        except Exception as e:
            logger.warning(f"Could not auto-subscribe page {page_id} to webhooks: {e}")
    @staticmethod
    async def unsubscribe_page_from_webhooks(page_id: str, page_access_token: str) -> Dict[str, Any]:
        """Unsubscribes Joy app from the Facebook Page's webhooks upon disconnect."""
        url = f"{GRAPH_API_BASE}/{page_id}/subscribed_apps"
        params = {"access_token": page_access_token}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(url, params=params)
                return resp.json()
        except Exception as e:
            logger.warning(f"Could not unsubscribe page {page_id} from webhooks: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    async def send_facebook_messenger_dm(
        recipient_id: str,
        message_text: str,
        page_access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send direct message on Facebook Messenger."""
        return await MetaAPIClient.confirmed_post("me/messages", page_access_token, {
            "recipient":{"id":recipient_id}, "message":{"text":message_text}, "messaging_type":"RESPONSE"})

    @staticmethod
    async def send_instagram_dm(
        recipient_id: str,
        message_text: str,
        page_access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send direct message on Instagram Direct."""
        return await MetaAPIClient.confirmed_post("me/messages", page_access_token, {
            "recipient":{"id":recipient_id}, "message":{"text":message_text}})

    @staticmethod
    async def reply_public_comment(
        comment_id: str,
        message_text: str,
        page_access_token: Optional[str] = None,
        channel: str = "instagram",
    ) -> Dict[str, Any]:
        """Publish a public reply to an Instagram or Facebook post/Reels comment."""
        if not comment_id.replace("_", "").isdigit():
            raise RuntimeError("Invalid comment identifier.")
        suffix = "replies" if channel == "instagram" else "comments"
        return await MetaAPIClient.confirmed_post(f"{comment_id}/{suffix}", page_access_token, {"message":message_text})

    @staticmethod
    async def send_comment_to_dm_handshake(
        comment_id: str,
        private_message_text: str,
        cta_button_text: str = "Claim Offer & View Details",
        page_access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sends a private reply to a public comment.
        Implements the Meta 24-hour Comment-to-DM Handshake: includes a high-converting
        CTA prompt so the customer replies in DM, unlocking the 24-hour sales window.
        """
        # Plain text private replies are supported without claiming a discount
        # or promising a button that the provider has not actually rendered.
        return await MetaAPIClient.confirmed_post("me/messages", page_access_token, {
            "recipient":{"comment_id":comment_id}, "message":{"text":private_message_text}})

    @staticmethod
    async def confirmed_post(path, token, payload):
        if not token or token.startswith(("joy_", "mock_", "test_")):
            raise RuntimeError("A verified Meta connection is required; no message was simulated.")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(f"{GRAPH_API_BASE}/{path}",
                    headers={"Authorization":f"Bearer {token}"}, json=payload)
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise RuntimeError("Meta delivery could not be confirmed.") from None
        if response.status_code not in (200,201) or data.get("error") or not (data.get("id") or data.get("message_id")):
            raise RuntimeError("Meta rejected the message or did not return a delivery identifier.")
        return data
