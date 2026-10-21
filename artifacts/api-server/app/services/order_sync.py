import logging
from typing import Dict, Any, Optional
from uuid import UUID
import httpx
from app.core.config import settings

logger = logging.getLogger("joy.order_sync")


class OrderSyncService:
    """
    Storefront Synchronization Service:
    - Syncs verified order statuses back to Shopify and WooCommerce
    - Updates order tags, verification notes, and corrected shipping addresses
    """

    @staticmethod
    async def sync_order_status(
        tenant_id: UUID,
        external_order_id: str,
        storefront_provider: str,
        new_status: str,  # 'confirmed' or 'flagged_for_review'
        transcript_summary: Optional[str] = None,
        updated_address: Optional[str] = None,
        storefront_api_url: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Updates external storefront status for Shopify or WooCommerce.
        """
        logger.info(
            f"[Storefront Sync] Updating order {external_order_id} ({storefront_provider}) "
            f"to '{new_status}' for tenant {tenant_id}"
        )

        verification_tag = f"joy_{new_status}"
        sync_payload = {
            "order_id": external_order_id,
            "provider": storefront_provider,
            "status": new_status,
            "tag": verification_tag,
            "updated_address": updated_address,
        }

        # 1. Shopify Order API
        if storefront_provider == "shopify" and storefront_api_url and access_token:
            try:
                # Use current supported Shopify Admin REST API
                api_version = "2024-10"
                order_endpoint = f"{storefront_api_url.rstrip('/')}/admin/api/{api_version}/orders/{external_order_id}.json"
                headers = {
                    "X-Shopify-Access-Token": access_token,
                    "Content-Type": "application/json",
                }

                async with httpx.AsyncClient(timeout=15.0) as client:
                    # First fetch current order to preserve existing tags
                    existing_tags = ""
                    get_resp = await client.get(order_endpoint, headers=headers)
                    if get_resp.status_code == 200:
                        existing_tags = get_resp.json().get("order", {}).get("tags", "")

                    combined_tags = f"{existing_tags}, {verification_tag}".strip(", ")

                    update_payload = {
                        "order": {
                            "id": int(external_order_id) if external_order_id.isdigit() else external_order_id,
                            "tags": combined_tags,
                            "note": f"Project JOY Voice Verification: {new_status.upper()}.\n{transcript_summary or ''}".strip(),
                        }
                    }
                    if updated_address:
                        update_payload["order"]["shipping_address"] = {"address1": updated_address}

                    resp = await client.put(order_endpoint, headers=headers, json=update_payload)
                    if resp.status_code == 200:
                        return {"status": "synced", "provider": "shopify", "response": resp.json()}
                    else:
                        logger.error(f"Shopify order update rejected with status {resp.status_code}: {resp.text}")
                        return {
                            "status": "failed",
                            "provider": "shopify",
                            "error": resp.text,
                            "status_code": resp.status_code,
                        }
            except Exception as e:
                logger.error(f"Shopify order update error: {e}")
                return {"status": "failed", "provider": "shopify", "error": str(e)}

        # 2. WooCommerce Order API
        elif storefront_provider == "woocommerce" and storefront_api_url and access_token:
            try:
                # WooCommerce REST API uses Consumer Key and Consumer Secret via HTTP Basic Auth
                # Token may be stored as 'ck_...:cs_...' or raw key
                ck = access_token
                cs = ""
                if ":" in access_token:
                    ck, cs = access_token.split(":", 1)

                woo_status = "processing" if new_status == "confirmed" else "on-hold"
                order_endpoint = f"{storefront_api_url.rstrip('/')}/wp-json/wc/v3/orders/{external_order_id}"

                auth = httpx.BasicAuth(username=ck, password=cs) if cs else None
                headers = {"Content-Type": "application/json"}
                if not auth:
                    headers["Authorization"] = f"Bearer {access_token}"

                update_payload = {
                    "status": woo_status,
                    "customer_note": f"Project JOY Voice Verification: {new_status.upper()}.\n{transcript_summary or ''}".strip(),
                }
                if updated_address:
                    update_payload["shipping"] = {"address_1": updated_address}

                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.put(
                        order_endpoint,
                        auth=auth,
                        headers=headers,
                        json=update_payload,
                    )
                    if resp.status_code == 200:
                        return {"status": "synced", "provider": "woocommerce", "response": resp.json()}
                    else:
                        logger.error(f"WooCommerce order update rejected with status {resp.status_code}: {resp.text}")
                        return {
                            "status": "failed",
                            "provider": "woocommerce",
                            "error": resp.text,
                            "status_code": resp.status_code,
                        }
            except Exception as e:
                logger.error(f"WooCommerce order update error: {e}")
                return {"status": "failed", "provider": "woocommerce", "error": str(e)}

        # If no credentials were configured
        return {
            "status": "unconfigured_storefront",
            "provider": storefront_provider,
            "external_order_id": external_order_id,
            "applied_status": new_status,
            "message": f"No active {storefront_provider} credentials configured for tenant.",
        }
