"""Catalog knowledge is descriptive; only a connected store can verify stock."""
from typing import Optional
from uuid import UUID
from app.services.rag_service import RAGService
from app.services.commerce import CommerceService, CommerceUnavailable


class MCPCatalogService:
    @staticmethod
    async def catalog_lookup(db, tenant_id: UUID, query: str, top_k: int = 3):
        snippets = await RAGService.hybrid_query(db=db, tenant_id=tenant_id,
                                                query_text=query, top_k=top_k)
        return [{"chunk_id": s["chunk_id"], "content": s["content"],
                 "document_title": s["document_title"], "relevance_score": s["score"]}
                for s in snippets]

    @staticmethod
    async def stock_check(db, tenant_id: UUID, sku_or_title: str):
        try:
            return await CommerceService.stock(db, tenant_id, sku_or_title)
        except CommerceUnavailable as error:
            return {"item": sku_or_title, "in_stock": False, "quantity_available": None,
                    "status": "unverified_inventory", "message": str(error)}

    @staticmethod
    def discount_generate(tenant_id: UUID, requested_discount_pct: int,
                          max_discount_pct: int = 10, sku: Optional[str] = None,
                          store_domain: Optional[str] = None):
        """Legacy API: calculate policy only, never invent redeemable coupons."""
        pct = min(max(0, requested_discount_pct), max(0, max_discount_pct), 100)
        return {"requested_pct": requested_discount_pct, "approved_pct": pct,
                "is_capped": requested_discount_pct > max_discount_pct,
                "discount_code": None, "checkout_url": None,
                "status": "requires_store_checkout"}
