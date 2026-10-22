import logging
import csv
import io
import json
import re
import httpx
from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.core.config import settings
from app.core.safety import PublicTransport, public_url

logger = logging.getLogger("joy.google_sheets")


class GoogleSheetsService:
    """
    Two-way synchronization between JOY Voice Confirmation and Google Sheets.
    Supports:
    1. Direct Google Sheets Apps Script Webhook API (Simplest zero-friction setup for merchants)
    2. Google Sheets Public / Shared CSV feed reader
    3. Google Sheets REST API v4 (Service Account Token)
    """

    @staticmethod
    def extract_sheet_id_from_url(url_or_id: str) -> str:
        """Extracts and validates a Google spreadsheet ID or canonical Sheets URL."""
        cleaned = url_or_id.strip()
        if "://" in cleaned:
            from urllib.parse import urlsplit
            parsed = urlsplit(cleaned)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "docs.google.com"
                or not parsed.path.startswith("/spreadsheets/d/")
            ):
                raise ValueError("Use a Google Sheets URL from docs.google.com.")
            cleaned = parsed.path.split("/spreadsheets/d/", 1)[1].split("/", 1)[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", cleaned):
            raise ValueError("The Google Sheets spreadsheet ID is invalid.")
        return cleaned

    @staticmethod
    def _apps_script_client():
        return httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            trust_env=False,
            transport=PublicTransport(),
        )

    @staticmethod
    async def _validate_apps_script_url(webhook_url: str) -> None:
        from urllib.parse import urlsplit
        parsed = urlsplit(webhook_url)
        if (
            parsed.hostname != "script.google.com"
            or not parsed.path.startswith("/macros/s/")
            or not parsed.path.endswith("/exec")
        ):
            raise ValueError("Use a deployed Google Apps Script web app URL.")
        await public_url(webhook_url)

    @staticmethod
    async def fetch_orders_via_apps_script(webhook_url: str) -> List[Dict[str, Any]]:
        """
        Fetches orders from merchant's Google Apps Script Webhook:
        GET {webhook_url}?action=get_pending_orders
        """
        await GoogleSheetsService._validate_apps_script_url(webhook_url)
        async with GoogleSheetsService._apps_script_client() as client:
            try:
                resp = await client.get(webhook_url, params={"action": "get_pending_orders"})
                if resp.status_code == 200:
                    data = resp.json()
                    orders = data.get("orders") or (data if isinstance(data, list) else [])
                    return orders if isinstance(orders, list) else []
                else:
                    logger.warning("Apps Script returned HTTP %s.", resp.status_code)
                    raise RuntimeError(f"Google Apps Script returned HTTP {resp.status_code}.")
            except Exception as e:
                if isinstance(e, (ValueError, RuntimeError)):
                    raise
                logger.error("Error fetching from Google Apps Script (%s).", type(e).__name__)
                raise RuntimeError("Could not read the Google Apps Script endpoint.") from None

    @staticmethod
    async def update_order_via_apps_script(
        webhook_url: str,
        order_id: str,
        status: str,
        tracking_code: Optional[str] = None,
        courier: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Updates order status in merchant's Google Sheet via Apps Script Webhook:
        POST {webhook_url} with { action: 'update_order', order_id, status, tracking_code, courier, notes }
        """
        payload = {
            "action": "update_order",
            "order_id": order_id,
            "status": status,
            "tracking_code": tracking_code or "",
            "courier": courier or "",
            "notes": notes or f"Call completed on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        }
        await GoogleSheetsService._validate_apps_script_url(webhook_url)
        async with GoogleSheetsService._apps_script_client() as client:
            try:
                resp = await client.post(webhook_url, json=payload)
                if resp.status_code not in (200, 201):
                    logger.warning("Apps Script update returned HTTP %s.", resp.status_code)
                    return False
                return True
            except Exception as e:
                logger.error("Failed to update sheet via Apps Script (%s).", type(e).__name__)
                return False

    @staticmethod
    async def fetch_orders_from_csv_export(sheet_id: str, gid: str = "0") -> List[Dict[str, Any]]:
        """
        Reads pending orders from a published or shareable Google Sheet CSV export link:
        https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}
        """
        sheet_id = GoogleSheetsService.extract_sheet_id_from_url(sheet_id)
        if not re.fullmatch(r"[0-9]{1,20}", str(gid)):
            raise ValueError("The sheet tab ID is invalid.")
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            trust_env=False,
            transport=PublicTransport(),
        ) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning("Could not read Google Sheet CSV (HTTP %s).", resp.status_code)
                    raise RuntimeError(f"Google Sheets CSV export returned HTTP {resp.status_code}.")

                content = resp.text
                reader = csv.DictReader(io.StringIO(content))
                orders = []
                for idx, row in enumerate(reader, start=2):
                    # Normalize common column headers
                    norm_row = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items() if k}
                    order_id = norm_row.get("order_id") or norm_row.get("invoice") or norm_row.get("id") or f"ROW-{idx}"
                    customer_name = norm_row.get("customer_name") or norm_row.get("name") or norm_row.get("customer") or "Valued Customer"
                    phone = norm_row.get("phone") or norm_row.get("phone_number") or norm_row.get("customer_phone") or norm_row.get("mobile")
                    address = norm_row.get("address") or norm_row.get("shipping_address") or norm_row.get("delivery_address") or "Dhaka, Bangladesh"
                    items = norm_row.get("items") or norm_row.get("product") or norm_row.get("order_items") or "Assorted Items"
                    total_str = norm_row.get("total_amount") or norm_row.get("total") or norm_row.get("amount") or norm_row.get("cod") or "0"
                    status = norm_row.get("confirmation_status") or norm_row.get("status") or "pending_confirmation"

                    try:
                        total = float(str(total_str).replace(",", "").replace("BDT", "").replace("৳", "").strip() or 0)
                    except ValueError:
                        total = 0.0

                    if phone:
                        orders.append({
                            "row_index": idx,
                            "order_id": order_id,
                            "customer_name": customer_name,
                            "customer_phone": phone,
                            "shipping_address": address,
                            "order_items": items,
                            "order_total": total,
                            "status": status,
                        })
                return orders
            except Exception as e:
                if isinstance(e, (ValueError, RuntimeError)):
                    raise
                logger.error("Error fetching Google Sheet CSV (%s).", type(e).__name__)
                raise RuntimeError("Could not read the Google Sheets CSV export.") from None

    @staticmethod
    async def sync_and_dispatch_pending_orders(
        tenant_id: UUID,
        sheet_config: Dict[str, Any],
        db_session,
    ) -> Dict[str, Any]:
        """
        Pulls pending orders from connected Google Sheet and triggers Voice Confirmation pipeline.
        """
        from app.db.models import Order
        from app.agents.voice_confirmation import VoiceConfirmationAgent
        import uuid
        import re

        webhook_url = sheet_config.get("webhook_url")
        sheet_url = sheet_config.get("sheet_url") or sheet_config.get("sheet_id")

        orders_to_process = []
        if webhook_url:
            orders_to_process = await GoogleSheetsService.fetch_orders_via_apps_script(webhook_url)
        elif sheet_url:
            sheet_id = GoogleSheetsService.extract_sheet_id_from_url(sheet_url)
            orders_to_process = await GoogleSheetsService.fetch_orders_from_csv_export(sheet_id)

        # Filter for pending status
        pending = [
            o for o in orders_to_process
            if str(o.get("status", "")).lower() in ("pending", "pending_confirmation", "unconfirmed", "")
        ]

        dispatched_count = 0
        fallback_count = 0
        skipped_count = 0
        results = []

        for item in pending:
            phone = str(item.get("customer_phone") or item.get("phone", "")).strip()
            digits = re.sub(r"\D", "", phone)
            if digits.startswith("01") and len(digits) == 11:
                phone = f"+880{digits[1:]}"
            elif digits.startswith("880"):
                phone = f"+{digits}"
            elif phone.startswith("+"):
                phone = f"+{digits}"
            else:
                phone = ""
            if not phone or not (8 <= len(digits) <= 15):
                skipped_count += 1
                continue

            external_order_id = str(item.get("order_id") or f"GS-{uuid.uuid4().hex[:6].upper()}")[:255]
            order_id = uuid.uuid4()
            order_data = dict(
                id=order_id,
                tenant_id=tenant_id,
                external_order_id=external_order_id,
                storefront_provider="google_sheets",
                customer_name=str(item.get("customer_name") or "Customer")[:255],
                customer_phone=phone,
                shipping_address=str(item.get("shipping_address") or "Address not provided"),
                order_total=max(0.0, float(item.get("order_total") or 0.0)),
                status="pending_confirmation",
                confirmation_channel="voice",
                call_attempts=0,
            )
            stmt = insert(Order).values(**order_data).on_conflict_do_nothing(
                index_elements=["tenant_id", "storefront_provider", "external_order_id"]
            ).returning(Order.id)
            inserted_id = (await db_session.execute(stmt)).scalar_one_or_none()
            await db_session.commit()
            if inserted_id is None:
                skipped_count += 1
                continue

            order_stmt = select(Order).where(Order.id == inserted_id, Order.tenant_id == tenant_id)
            order = (await db_session.execute(order_stmt)).scalars().first()
            if not order:
                skipped_count += 1
                continue

            # Trigger Confirmation Call
            call_res = await VoiceConfirmationAgent.process_order_confirmation(
                order_id=order.id,
                tenant_id=tenant_id,
                db=db_session,
                order_items=str(item.get("order_items") or item.get("items") or item.get("product") or "Order items"),
            )
            dispatch_status = call_res.get("status")
            if dispatch_status == "call_dispatched":
                dispatched_count += 1
            elif dispatch_status == "verification_link_created":
                fallback_count += 1
            results.append({
                "order_id": str(order.id),
                "external_order_id": order.external_order_id,
                "dispatch_status": dispatch_status,
                "room_name": call_res.get("room_name"),
            })

        return {
            "success": True,
            "total_found": len(orders_to_process),
            "pending_count": len(pending),
            "dispatched_count": dispatched_count,
            "fallback_link_count": fallback_count,
            "skipped_count": skipped_count,
            "dispatches": results,
        }
