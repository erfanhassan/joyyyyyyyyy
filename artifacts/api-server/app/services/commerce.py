"""Authoritative store reads and hosted, unpaid checkout creation.

No provider requests are performed during setup or application startup.
"""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.core.config import settings
from app.core.safety import public_url, PublicTransport
from app.core.security import decrypt_token
from app.db.models import TenantIntegration, CheckoutRequest


class CommerceUnavailable(RuntimeError):
    pass


class CommerceService:
    @staticmethod
    async def verify_read(record):
        from datetime import datetime, timezone
        metadata = {"connection_verified_at": datetime.now(timezone.utc).isoformat()}
        if record.provider == "shopify":
            data = await CommerceService.graphql(record,
                "{shop{id name currencyCode} currentAppInstallation{accessScopes{handle}}}")
            if not data.get("shop", {}).get("id"):
                raise CommerceUnavailable("Shopify did not identify this store.")
            metadata["store_name"] = data["shop"]["name"]
            metadata["store_currency"] = data["shop"]["currencyCode"]
            metadata["granted_scopes"] = [s["handle"] for s in data.get("currentAppInstallation",{}).get("accessScopes",[])]
        elif record.provider == "woocommerce":
            data = await CommerceService.request(record,"GET","products",params={"per_page":1})
            if not isinstance(data,list):
                raise CommerceUnavailable("WooCommerce did not return a verified product response.")
        else:
            raise CommerceUnavailable("This provider does not implement a store connection.")
        return metadata

    @staticmethod
    async def integration(db, tenant_id):
        records = (await db.execute(select(TenantIntegration).where(
            TenantIntegration.tenant_id == UUID(str(tenant_id)),
            TenantIntegration.provider.in_(["shopify", "woocommerce"]),
            TenantIntegration.is_active.is_(True)))).scalars().all()
        if len(records) != 1:
            raise CommerceUnavailable("Connect exactly one authoritative store before enabling automated checkout.")
        return records[0]

    @staticmethod
    def credential(value):
        if not value:
            raise CommerceUnavailable("Store credentials are incomplete.")
        return decrypt_token(value[4:]) if value.startswith("enc:") else value

    @staticmethod
    async def request(record, method, path, **kwargs):
        config = record.settings or {}
        token = decrypt_token(record.access_token_encrypted)
        if record.provider == "shopify":
            shop = config.get("shop_domain", "").removeprefix("https://").rstrip("/")
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com", shop):
                raise CommerceUnavailable("A canonical myshopify.com domain is required.")
            url = f"https://{shop}/admin/api/{settings.SHOPIFY_API_VERSION}/{path}"
            headers = {"X-Shopify-Access-Token": token}
            auth = None
        else:
            base = config.get("store_url", "").rstrip("/")
            await public_url(base)
            url = f"{base}/wp-json/wc/v3/{path}"
            headers = {}
            key = CommerceService.credential(config.get("consumer_key", ""))
            auth = httpx.BasicAuth(key, token)
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False, transport=PublicTransport()) as client:
            response = await client.request(method, url, headers=headers, auth=auth, **kwargs)
            if response.status_code >= 300:
                raise CommerceUnavailable(f"Store rejected the operation (HTTP {response.status_code}). Reconnect or check API permissions.")
            data = response.json()
        if isinstance(data, dict) and data.get("errors"):
            raise CommerceUnavailable("The store rejected the GraphQL operation.")
        return data

    @staticmethod
    async def graphql(record, query, variables):
        result = await CommerceService.request(record, "POST", "graphql.json",
                                               json={"query": query, "variables": variables})
        return result.get("data") or {}

    @staticmethod
    async def stock(db, tenant_id, query):
        record = await CommerceService.integration(db, tenant_id)
        # Treat search as data, not Shopify query syntax.
        words = re.findall(r"[a-zA-Z0-9_-]+", query)[:8]
        if not words:
            raise CommerceUnavailable("Select a product or provide its SKU.")
        if record.provider == "shopify":
            data = await CommerceService.graphql(record, """
              query($q:String!){productVariants(first:10,query:$q){nodes{
                id sku title inventoryQuantity inventoryPolicy price inventoryItem{tracked}
                product{title status}
              }}}
            """, {"q": " ".join(words)})
            variants = data.get("productVariants", {}).get("nodes", [])
            exact = [p for p in variants if p.get("sku", "").casefold() == query.strip().casefold()]
            variants = exact or variants
            if len(variants) != 1:
                raise CommerceUnavailable("Product selection is ambiguous or no matching variant was found. Please provide an exact SKU.")
            p = variants[0]
            return {"item": p["product"]["title"], "sku": p.get("sku"), "variant_id": p["id"],
                    "in_stock": p["product"].get("status") == "ACTIVE" and (
                        not p.get("inventoryItem", {}).get("tracked", True)
                        or (p.get("inventoryQuantity") or 0) > 0),
                    "quantity_available": p.get("inventoryQuantity"),
                    "price": p["price"], "provider": "shopify", "status": "verified",
                    "integration_id": str(record.id)}
        products = await CommerceService.request(record, "GET", "products",
                                                  params={"search": " ".join(words), "per_page": 10})
        exact = [p for p in products if p.get("sku", "").casefold() == query.strip().casefold()]
        products = exact or products
        if len(products) != 1 or products[0].get("type") != "simple":
            raise CommerceUnavailable("Select an exact simple-product SKU; variable products require variant selection.")
        p = products[0]
        return {"item": p["name"], "sku": p.get("sku"), "variant_id": p["id"],
                "in_stock": p.get("stock_status") == "instock", "quantity_available": p.get("stock_quantity"),
                "price": p.get("price"), "provider": "woocommerce", "status": "verified",
                "integration_id": str(record.id)}

    @staticmethod
    async def checkout(db, tenant_id, stock, percentage, request_key):
        key = hashlib.sha256(f"{tenant_id}:{request_key}".encode()).hexdigest()
        claimed = (await db.execute(insert(CheckoutRequest).values(
            key=key, tenant_id=UUID(str(tenant_id)), status="creating")
            .on_conflict_do_nothing(index_elements=["key"]).returning(CheckoutRequest.key))).scalar_one_or_none()
        await db.commit()
        if not claimed:
            receipt = (await db.execute(select(CheckoutRequest).where(
                CheckoutRequest.key == key, CheckoutRequest.tenant_id == UUID(str(tenant_id))))).scalar_one()
            if receipt.status == "completed":
                return receipt.result
            raise CommerceUnavailable("An earlier checkout request requires review. It will not be created twice.")
        try:
            result = await CommerceService._create_checkout(db, tenant_id, stock, percentage, request_key)
            receipt = (await db.execute(select(CheckoutRequest).where(CheckoutRequest.key == key))).scalar_one()
            receipt.status, receipt.result = "completed", result
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            receipt = (await db.execute(select(CheckoutRequest).where(CheckoutRequest.key == key))).scalar_one()
            receipt.status = "needs_review"
            await db.commit()
            raise CommerceUnavailable("Checkout could not be confirmed. A store specialist must review the request before retrying.") from None

    @staticmethod
    async def _create_checkout(db, tenant_id, stock, percentage, request_key):
        if not stock or stock.get("status") != "verified" or not stock.get("in_stock"):
            raise CommerceUnavailable("Checkout requires a uniquely selected, currently available product.")
        record = await CommerceService.integration(db, tenant_id)
        if str(record.id) != stock.get("integration_id"):
            raise CommerceUnavailable("The selected store has changed. Select the product again.")
        pct = max(0, min(100, int(percentage)))
        marker = "joy-" + hashlib.sha256(f"{tenant_id}:{request_key}".encode()).hexdigest()[:24]
        if record.provider == "shopify":
            # Reuse an existing draft after a timeout/retry instead of inventing coupons.
            previous = await CommerceService.graphql(record, """
              query($q:String!){draftOrders(first:1,query:$q){nodes{id invoiceUrl}}}
            """, {"q": f"tag:{marker}"})
            nodes = previous.get("draftOrders", {}).get("nodes", [])
            if nodes:
                return {"checkout_url": nodes[0]["invoiceUrl"], "discount_code": None, "approved_pct": pct}
            draft = {"lineItems": [{"variantId": stock["variant_id"], "quantity": 1}],
                     "tags": [marker], "note": "Customer-requested JOY checkout. Payment is not collected by JOY."}
            if pct:
                draft["appliedDiscount"] = {"title": "JOY approved offer", "value": pct,
                                            "valueType": "PERCENTAGE"}
            data = await CommerceService.graphql(record, """
              mutation($input:DraftOrderInput!){draftOrderCreate(input:$input){
                draftOrder{id invoiceUrl} userErrors{field message}
              }}
            """, {"input": draft})
            result = data.get("draftOrderCreate", {})
            if result.get("userErrors") or not result.get("draftOrder", {}).get("invoiceUrl"):
                raise CommerceUnavailable("The store could not create a checkout. Check draft-order permissions.")
            return {"checkout_url": result["draftOrder"]["invoiceUrl"], "discount_code": None, "approved_pct": pct}
        # Native WooCommerce cart flow collects billing/shipping and calculates
        # taxes before payment. Never manufacture an order with no address.
        if pct:
            existing = await CommerceService.request(record, "GET", "coupons", params={"code": marker})
            if not existing:
                await CommerceService.request(record, "POST", "coupons", json={
                    "code": marker, "discount_type": "percent", "amount": str(pct),
                    "individual_use": True, "usage_limit": 1, "product_ids": [stock["variant_id"]],
                    "date_expires": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()})
        base = (record.settings or {})["store_url"].rstrip("/")
        checkout_path = (record.settings or {}).get("checkout_path", "/checkout/")
        if not checkout_path.startswith("/") or checkout_path.startswith("//") or "?" in checkout_path:
            raise CommerceUnavailable("Configure a valid store checkout path.")
        url = f"{base}{checkout_path}?" + urlencode({"add-to-cart": stock["variant_id"], "quantity": 1})
        return {"checkout_url": url, "discount_code": marker if pct else None, "approved_pct": pct}
