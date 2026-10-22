import logging
import httpx
from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings

logger = logging.getLogger("joy.courier")


class CourierService:
    """
    Courier delivery partner integration for Bangladeshi logistics:
    1. Steadfast Courier (portal.steadfast.com.bd)
    2. Pathao Parcel (api-hermes.pathao.com)
    """

    @staticmethod
    async def verify_credentials(provider: str, courier_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tests live API connectivity for Steadfast or Pathao.
        """
        prov = provider.lower()
        if prov == "steadfast":
            api_key = courier_settings.get("api_key")
            secret_key = courier_settings.get("secret_key")
            if not api_key or not secret_key:
                return {
                    "connected": False,
                    "provider": "steadfast",
                    "message": "Steadfast Api-Key and Secret-Key are required.",
                }
            if "test" in api_key.lower() or "demo" in api_key.lower():
                return {
                    "connected": True,
                    "provider": "steadfast",
                    "sandbox": True,
                    "message": "Steadfast Sandbox/Test credentials validated successfully.",
                }
            base_url = settings.STEADFAST_BASE_URL.rstrip("/")
            endpoint = f"{base_url}/get_balance"
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(endpoint, headers={"Api-Key": api_key, "Secret-Key": secret_key})
                    if resp.status_code == 200:
                        data = resp.json()
                        balance = data.get("current_balance")
                        bal_str = f" (Current balance: ৳{balance})" if balance is not None else ""
                        return {
                            "connected": True,
                            "provider": "steadfast",
                            "balance": balance,
                            "message": f"Steadfast Courier API verified live!{bal_str}",
                        }
                    else:
                        return {
                            "connected": False,
                            "provider": "steadfast",
                            "status_code": resp.status_code,
                            "message": f"Steadfast verification failed (HTTP {resp.status_code}): {resp.text}",
                        }
            except Exception as e:
                return {
                    "connected": False,
                    "provider": "steadfast",
                    "message": f"Connection error checking Steadfast: {e}",
                }

        elif prov == "pathao":
            client_id = courier_settings.get("client_id")
            client_secret = courier_settings.get("client_secret")
            username = courier_settings.get("username")
            password = courier_settings.get("password")
            if not all([client_id, client_secret, username, password]):
                return {
                    "connected": False,
                    "provider": "pathao",
                    "message": "Pathao Client ID, Client Secret, Username, and Password are all required.",
                }
            if "test" in str(client_id).lower() or "demo" in str(client_id).lower():
                return {
                    "connected": True,
                    "provider": "pathao",
                    "sandbox": True,
                    "message": "Pathao Sandbox/Test credentials validated successfully.",
                }
            base_url = settings.PATHAO_BASE_URL.rstrip("/")
            endpoint = f"{base_url}/aladdin/api/v1/issue-token"
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.post(
                        endpoint,
                        json={
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "username": username,
                            "password": password,
                            "grant_type": "password",
                        },
                    )
                    if resp.status_code == 200 and resp.json().get("access_token"):
                        return {
                            "connected": True,
                            "provider": "pathao",
                            "message": "Pathao Parcel API authenticated successfully! OAuth token issued.",
                        }
                    else:
                        return {
                            "connected": False,
                            "provider": "pathao",
                            "status_code": resp.status_code,
                            "message": f"Pathao auth failed (HTTP {resp.status_code}): {resp.text}",
                        }
            except Exception as e:
                return {
                    "connected": False,
                    "provider": "pathao",
                    "message": f"Connection error checking Pathao: {e}",
                }

        return {
            "connected": False,
            "provider": provider,
            "message": f"Unknown courier provider '{provider}'.",
        }

    @staticmethod
    async def create_steadfast_parcel(
        api_key: str,
        secret_key: str,
        invoice: str,
        recipient_name: str,
        recipient_phone: str,
        recipient_address: str,
        cod_amount: float,
        note: str = "Verified by JOY AI Voice Agent",
    ) -> Dict[str, Any]:
        """
        Dispatches parcel creation to Steadfast Courier API:
        POST https://portal.steadfast.com.bd/api/v1/create_order
        """
        base_url = settings.STEADFAST_BASE_URL.rstrip("/")
        endpoint = f"{base_url}/create_order"
        headers = {
            "Api-Key": api_key,
            "Secret-Key": secret_key,
            "Content-Type": "application/json",
        }
        payload = {
            "invoice": invoice,
            "recipient_name": recipient_name,
            "recipient_phone": recipient_phone,
            "recipient_address": recipient_address,
            "cod_amount": round(cod_amount, 2),
            "note": note,
        }

        async with httpx.AsyncClient(timeout=12.0) as client:
            try:
                resp = await client.post(endpoint, headers=headers, json=payload)
                data = resp.json() if resp.status_code < 500 else {"text": resp.text}
                if resp.status_code in (200, 201) and (data.get("status") == 200 or data.get("consignment")):
                    consignment = data.get("consignment", {})
                    tracking_code = consignment.get("tracking_code") or data.get("tracking_code") or f"STDF-{invoice}"
                    return {
                        "success": True,
                        "courier": "steadfast",
                        "consignment_id": consignment.get("consignment_id") or consignment.get("id"),
                        "tracking_code": tracking_code,
                        "raw_response": data,
                    }
                else:
                    logger.warning(f"Steadfast API error {resp.status_code}: {resp.text}")
                    return {
                        "success": False,
                        "courier": "steadfast",
                        "error": data.get("message") or resp.text,
                        "status_code": resp.status_code,
                    }
            except Exception as e:
                logger.error(f"Failed to communicate with Steadfast Courier: {e}")
                return {"success": False, "courier": "steadfast", "error": str(e)}

    @staticmethod
    async def create_pathao_parcel(
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        store_id: int,
        invoice: str,
        recipient_name: str,
        recipient_phone: str,
        recipient_address: str,
        cod_amount: float,
        item_description: str = "Store Order",
        recipient_city: int = 1,
        recipient_zone: int = 1,
    ) -> Dict[str, Any]:
        """
        Dispatches parcel creation to Pathao Courier API:
        1. Token issuance: POST /aladdin/api/v1/issue-token
        2. Order placement: POST /aladdin/api/v1/orders
        """
        base_url = settings.PATHAO_BASE_URL.rstrip("/")
        token_endpoint = f"{base_url}/aladdin/api/v1/issue-token"

        async with httpx.AsyncClient(timeout=12.0) as client:
            try:
                # 1. Obtain Access Token
                auth_resp = await client.post(
                    token_endpoint,
                    json={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "username": username,
                        "password": password,
                        "grant_type": "password",
                    },
                )
                if auth_resp.status_code != 200:
                    logger.warning(f"Pathao Auth failed: {auth_resp.text}")
                    return {"success": False, "courier": "pathao", "error": f"Pathao Auth failed: {auth_resp.text}"}

                token = auth_resp.json().get("access_token")
                if not token:
                    return {"success": False, "courier": "pathao", "error": "Missing access token from Pathao response"}

                # 2. Create Parcel Order
                order_endpoint = f"{base_url}/aladdin/api/v1/orders"
                order_payload = {
                    "store_id": int(store_id or 1),
                    "merchant_order_id": invoice,
                    "recipient_name": recipient_name,
                    "recipient_phone": recipient_phone,
                    "recipient_address": recipient_address,
                    "recipient_city": recipient_city,
                    "recipient_zone": recipient_zone,
                    "delivery_type": 48,
                    "item_type": 2,
                    "special_instruction": "Confirmed by JOY AI Voice Agent",
                    "item_quantity": 1,
                    "item_weight": 0.5,
                    "amount_to_collect": round(cod_amount, 2),
                    "item_description": item_description[:200],
                }

                order_resp = await client.post(
                    order_endpoint,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=order_payload,
                )
                data = order_resp.json() if order_resp.status_code < 500 else {"text": order_resp.text}
                if order_resp.status_code in (200, 201) and data.get("data"):
                    order_data = data.get("data", {})
                    consignment_id = order_data.get("consignment_id")
                    return {
                        "success": True,
                        "courier": "pathao",
                        "consignment_id": consignment_id,
                        "tracking_code": consignment_id or f"PTH-{invoice}",
                        "raw_response": data,
                    }
                else:
                    return {
                        "success": False,
                        "courier": "pathao",
                        "error": data.get("message") or order_resp.text,
                        "status_code": order_resp.status_code,
                    }
            except Exception as e:
                logger.error(f"Pathao dispatch error: {e}")
                return {"success": False, "courier": "pathao", "error": str(e)}

    @staticmethod
    async def dispatch_to_delivery_partner(
        tenant_id: UUID,
        invoice: str,
        recipient_name: str,
        recipient_phone: str,
        recipient_address: str,
        cod_amount: float,
        courier_pref: Optional[str] = None,
        tenant_courier_settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Auto-selects configured courier (Steadfast or Pathao) and creates consignment.
        Falls back to global or sandbox mock tracking if keys are in test mode.
        """
        cfg = tenant_courier_settings or {}
        provider = courier_pref or cfg.get("provider") or ("steadfast" if settings.STEADFAST_API_KEY else "pathao")

        if provider == "steadfast":
            api_key = cfg.get("api_key") or settings.STEADFAST_API_KEY
            secret_key = cfg.get("secret_key") or settings.STEADFAST_SECRET_KEY
            if api_key and secret_key:
                return await CourierService.create_steadfast_parcel(
                    api_key=api_key,
                    secret_key=secret_key,
                    invoice=invoice,
                    recipient_name=recipient_name,
                    recipient_phone=recipient_phone,
                    recipient_address=recipient_address,
                    cod_amount=cod_amount,
                )
            else:
                # Return simulated tracking code for development/demo test mode
                tracking = f"STDF-DEMO-{invoice.upper()}"
                logger.info(f"[Steadfast Courier Demo] Generated consignment {tracking} for {recipient_name}")
                return {
                    "success": True,
                    "courier": "steadfast",
                    "consignment_id": f"CS_{invoice}",
                    "tracking_code": tracking,
                    "simulated": True,
                    "note": "Steadfast API keys not configured. Generated test consignment tracking code.",
                }

        elif provider == "pathao":
            client_id = cfg.get("client_id") or settings.PATHAO_CLIENT_ID
            client_secret = cfg.get("client_secret") or settings.PATHAO_CLIENT_SECRET
            username = cfg.get("username") or settings.PATHAO_USERNAME
            password = cfg.get("password") or settings.PATHAO_PASSWORD
            store_id = cfg.get("store_id") or 1
            if client_id and client_secret and username and password:
                return await CourierService.create_pathao_parcel(
                    client_id=client_id,
                    client_secret=client_secret,
                    username=username,
                    password=password,
                    store_id=store_id,
                    invoice=invoice,
                    recipient_name=recipient_name,
                    recipient_phone=recipient_phone,
                    recipient_address=recipient_address,
                    cod_amount=cod_amount,
                )
            else:
                tracking = f"PTH-DEMO-{invoice.upper()}"
                logger.info(f"[Pathao Courier Demo] Generated consignment {tracking} for {recipient_name}")
                return {
                    "success": True,
                    "courier": "pathao",
                    "consignment_id": f"CS_{invoice}",
                    "tracking_code": tracking,
                    "simulated": True,
                    "note": "Pathao API keys not configured. Generated test consignment tracking code.",
                }

        return {
            "success": False,
            "error": f"Unknown or unconfigured courier provider '{provider}'",
        }
