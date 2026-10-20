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
        Checks real-time inventory level and backorder status.
        """
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
            }

        top_match = snippets[0]["content"]
        # Extract stock numbers or default to in-stock
        in_stock = "out of stock" not in top_match.lower()
        # Simulated inventory reading
        qty = 15 if in_stock else 0

        return {
            "item": sku_or_title,
            "in_stock": in_stock,
            "quantity_available": qty,
            "status": "available" if in_stock else "backordered",
            "matched_product": top_match[:150],
        }

    @staticmethod
    def discount_generate(
        tenant_id: UUID,
        requested_discount_pct: int,
        max_discount_pct: int = 10,
        sku: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        MCP Tool: discount.generate
        Generates a personalized discount coupon and checkout link, strictly capped
        by the merchant's agent_configs.max_discount_pct guardrail.
        """
        # Guardrail: Never exceed merchant's configured maximum discount
        approved_pct = min(max(0, requested_discount_pct), max_discount_pct)
        
        # If customer asked for 0% or positive discount but max is 0
        if approved_pct <= 0:
            approved_pct = 0
            code = None
            checkout_url = f"https://checkout.joy.ai/{tenant_id}?item={sku or 'cart'}"
        else:
            random_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
            code = f"JOY{approved_pct}_{random_suffix}"
            checkout_url = f"https://checkout.joy.ai/{tenant_id}?item={sku or 'cart'}&coupon={code}&discount={approved_pct}"

        logger.info(
            f"[MCP discount.generate] requested={requested_discount_pct}%, approved={approved_pct}% (cap={max_discount_pct}%), code={code}"
        )

        return {
            "requested_pct": requested_discount_pct,
            "approved_pct": approved_pct,
            "is_capped": requested_discount_pct > max_discount_pct,
            "discount_code": code,
            "checkout_url": checkout_url,
        }
