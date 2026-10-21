import logging
import random
import string
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.rag_service import RAGService

logger = logging.getLogger("joy.mcp.catalog")


class MCPCatalogService:
    """
    Model Context Protocol (MCP) Tool Server for Storefront Catalogs:
    - catalog.lookup: Hybrid vector + full-text search across merchant inventory
    - stock.check: Real-time stock availability validation
    - discount.generate: Merchant-capped dynamic coupon & checkout URL generator
    """

    @staticmethod
    async def catalog_lookup(
        db: AsyncSession,
        tenant_id: UUID,
        query: str,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        MCP Tool: catalog.lookup
        Retrieves matching products, SKUs, and prices from the Knowledge Brain.
        """
        logger.info(f"[MCP catalog.lookup] tenant={tenant_id}, query='{query}'")
        snippets = await RAGService.hybrid_query(
            db=db,
            tenant_id=tenant_id,
            query_text=query,
            top_k=top_k,
        )

        results = []
        for s in snippets:
            results.append({
                "chunk_id": s["chunk_id"],
                "content": s["content"],
                "document_title": s["document_title"],
                "relevance_score": s["score"],
            })
        return results

    @staticmethod
    async def stock_check(
        db: AsyncSession,
        tenant_id: UUID,
        sku_or_title: str,
    ) -> Dict[str, Any]:
        """
        MCP Tool: stock.check
        Checks real-time inventory level from knowledge catalog and connected store integrations.
        Never fabricates availability when stock is 0 or unverified.
        """
        import re
        logger.info(f"[MCP stock.check] tenant={tenant_id}, item='{sku_or_title}'")
        snippets = await RAGService.hybrid_query(
            db=db,
            tenant_id=tenant_id,
            query_text=sku_or_title,
            top_k=1,
        )

        if not snippets:
            return {
                "item": sku_or_title,
                "in_stock": False,
                "quantity_available": 0,
                "status": "not_found",
                "message": "Product not found in store catalog.",
            }

        top_match = snippets[0]["content"]
        lower_match = top_match.lower()

        # 1. Explicit out of stock checks
        explicit_out_of_stock = any(
            phrase in lower_match
            for phrase in [
                "out of stock",
                "sold out",
                "stock: 0",
                "qty: 0",
                "quantity: 0",
                "quantity 0",
                "0 in stock",
                "0 available",
                "unavailable",
                "backordered",
            ]
        )

        if explicit_out_of_stock:
            return {
                "item": sku_or_title,
                "in_stock": False,
                "quantity_available": 0,
                "status": "out_of_stock",
                "matched_product": top_match[:150],
                "message": "Item is currently out of stock.",
            }

        # 2. Extract numeric quantity if present
        qty_match = re.search(r"(?:quantity|qty|stock|available)[\s:]*(\d+)", lower_match)
        if qty_match:
            qty = int(qty_match.group(1))
            in_stock = qty > 0
            return {
                "item": sku_or_title,
                "in_stock": in_stock,
                "quantity_available": qty,
                "status": "in_stock" if in_stock else "out_of_stock",
                "matched_product": top_match[:150],
            }

        # 3. If explicit 'in stock' or 'available' is mentioned without numeric count
        if "in stock" in lower_match or "available" in lower_match:
            return {
                "item": sku_or_title,
                "in_stock": True,
                "quantity_available": None,
                "status": "available",
                "matched_product": top_match[:150],
            }

        # 4. If stock is not verified from catalog, explicitly report unverified - NEVER invent availability
        return {
            "item": sku_or_title,
            "in_stock": False,
            "quantity_available": 0,
            "status": "unverified_inventory",
            "matched_product": top_match[:150],
            "message": "Inventory availability cannot be verified from the catalog. Please confirm directly with store staff.",
        }

    @staticmethod
    def discount_generate(
        tenant_id: UUID,
        requested_discount_pct: int,
        max_discount_pct: int = 10,
        sku: Optional[str] = None,
        store_domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        MCP Tool: discount.generate
        Generates a personalized discount coupon and checkout link, strictly capped
        by the merchant's agent_configs.max_discount_pct guardrail.
        Uses the merchant's authoritative store domain instead of a fake endpoint.
        """
        # Guardrail: Never exceed merchant's configured maximum discount
        approved_pct = min(max(0, requested_discount_pct), max_discount_pct)
        
        # Resolve real merchant domain
        domain = (store_domain or "").strip()
        if not domain or "checkout.joy.ai" in domain:
            from app.core.config import settings
            domain = getattr(settings, "DOMAIN", None) or "joy.sonictch.com"

        if not domain.startswith("http://") and not domain.startswith("https://"):
            domain = f"https://{domain}"

        # Clean item parameter
        item_param = sku.strip() if sku else "cart"

        # If customer asked for 0% or positive discount but max is 0
        if approved_pct <= 0:
            approved_pct = 0
            code = None
            checkout_url = f"{domain}/checkout?item={item_param}"
        else:
            random_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
            code = f"JOY{approved_pct}_{random_suffix}"
            checkout_url = f"{domain}/checkout?item={item_param}&coupon={code}&discount={approved_pct}"

        logger.info(
            f"[MCP discount.generate] requested={requested_discount_pct}%, approved={approved_pct}% (cap={max_discount_pct}%), code={code}, url={checkout_url}"
        )

        return {
            "requested_pct": requested_discount_pct,
            "approved_pct": approved_pct,
            "is_capped": requested_discount_pct > max_discount_pct,
            "discount_code": code,
            "checkout_url": checkout_url,
        }
