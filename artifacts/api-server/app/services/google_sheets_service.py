import logging
import csv
import io
import json
import httpx
from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime, timezone
from app.core.config import settings

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
        """Extracts the 44-character spreadsheet ID from a full Google Sheets URL or raw ID."""
        cleaned = url_or_id.strip()
        if "/d/" in cleaned:
            parts = cleaned.split("/d/")[1]
            return parts.split("/")[0]
        return cleaned

    @staticmethod
    async def fetch_orders_via_apps_script(webhook_url: str) -> List[Dict[str, Any]]:
        """
        Fetches orders from merchant's Google Apps Script Webhook:
        GET {webhook_url}?action=get_pending_orders
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(webhook_url, params={"action": "get_pending_orders"})
                if resp.status_code == 200:
                    data = resp.json()
                    orders = data.get("orders") or (data if isinstance(data, list) else [])
                    return orders
                else:
                    logger.warning(f"Apps script returned {resp.status_code}: {resp.text}")
                    return []
            except Exception as e:
                logger.error(f"Error fetching from Google Apps Script webhook: {e}")
                return []

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
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(webhook_url, json=payload)
                return resp.status_code in (200, 201)
            except Exception as e:
                logger.error(f"Failed to update sheet via Apps Script: {e}")
                return False

    @staticmethod
    async def fetch_orders_from_csv_export(sheet_id: str, gid: str = "0") -> List[Dict[str, Any]]:
        """
        Reads pending orders from a published or shareable Google Sheet CSV export link:
        https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}
        """
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning(f"Could not read Google Sheet CSV ({resp.status_code})")
                    return []

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
                logger.error(f"Error fetching Google Sheet CSV: {e}")
                return []

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
        results = []

        for item in pending:
            phone = str(item.get("customer_phone") or item.get("phone", "")).strip()
            if not phone:
                continue

            order_id = uuid.uuid4()
            order = Order(
                id=order_id,
                tenant_id=tenant_id,
                external_order_id=str(item.get("order_id") or f"GS-{uuid.uuid4().hex[:6].upper()}"),
                storefront_provider="google_sheets",
                customer_name=str(item.get("customer_name") or "Valued Customer"),
                customer_phone=phone,
                shipping_address=str(item.get("shipping_address") or "Bangladesh"),
                order_total=float(item.get("order_total") or 0.0),
                status="pending_confirmation",
                confirmation_channel="voice",
                call_attempts=1,
            )
            db_session.add(order)
            await db_session.commit()

            # Trigger Confirmation Call
            call_res = await VoiceConfirmationAgent.process_order_confirmation(
                order_id=order.id,
                tenant_id=tenant_id,
                db=db_session,
                bypass_timezone_for_test=sheet_config.get("bypass_hours", False),
            )
            dispatched_count += 1
            results.append({
                "order_id": str(order.id),
                "external_order_id": order.external_order_id,
                "phone": phone,
                "dispatch_status": call_res.get("status"),
                "room_name": call_res.get("room_name"),
            })

        return {
            "success": True,
            "total_found": len(orders_to_process),
            "pending_count": len(pending),
            "dispatched_count": dispatched_count,
            "dispatches": results,
        }
