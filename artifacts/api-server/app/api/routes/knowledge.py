import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from pydantic import BaseModel, HttpUrl, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.rag_service import RAGService

logger = logging.getLogger("joy.routes.knowledge")
router = APIRouter(prefix="/knowledge", tags=["Knowledge Brain"])


# Pydantic Request Models
class CrawlRequest(BaseModel):
    url: str
    tenant_id: UUID
    title: Optional[str] = None


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    tenant_id: UUID
    top_k: int = Field(default=3, ge=1, le=20)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: UUID = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload and index a PDF or CSV product catalog file for a tenant.
    Parses content, splits into recursive 500-token chunks, and indexes via pgvector HNSW.
    """
    filename = file.filename or "uploaded_document"
    from app.core.config import settings
    file_bytes = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Maximum upload size is 25 MB.")

    if filename.lower().endswith(".pdf"):
        source_type = "pdf"
        try:
            content = RAGService.parse_pdf_bytes(file_bytes)
        except Exception as e:
            logger.error(f"Failed to parse PDF {filename}: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid PDF file: {e}")
    elif filename.lower().endswith(".csv"):
        source_type = "csv"
        try:
            content = RAGService.parse_csv_bytes(file_bytes)
        except Exception as e:
            logger.error(f"Failed to parse CSV {filename}: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid CSV file: {e}")
    elif filename.lower().endswith((".txt", ".md")):
        source_type = "text"
        content = file_bytes.decode("utf-8", errors="replace")
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a PDF, CSV, TXT, or MD file.",
        )

    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file contains no extractable text.",
        )

    # Ingest into knowledge brain
    result = await RAGService.ingest_document(
        db=db,
        tenant_id=tenant_id,
        title=filename,
        source_type=source_type,
        content=content,
    )

    return {
        "status": "success",
        "message": f"Successfully ingested {filename}",
        **result,
    }


@router.post("/crawl")
async def crawl_storefront(
    request: CrawlRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Crawls a merchant storefront URL, strips HTML boilerplate, chunks content,
    and stores 1536-dimensional HNSW embeddings.
    """
    title = request.title or f"Crawl: {request.url}"

    try:
        content = await RAGService.crawl_storefront_url(request.url)
    except Exception as e:
        logger.error(f"Failed to crawl URL {request.url}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to crawl URL: {str(e)}",
        )

    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No readable text content found at the provided URL.",
        )

    result = await RAGService.ingest_document(
        db=db,
        tenant_id=request.tenant_id,
        title=title,
        source_type="web_crawl",
        content=content,
        source_url=request.url,
    )

    return {
        "status": "success",
        "message": f"Successfully crawled and indexed {request.url}",
        **result,
    }


@router.post("/query")
async def query_knowledge_brain(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Executes hybrid retrieval (pgvector cosine similarity + tsvector BM25 keyword rank)
    strictly isolated by tenant_id. Returns top-K snippets.
    """
    if not request.query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query cannot be empty.")

    snippets = await RAGService.hybrid_query(
        db=db,
        tenant_id=request.tenant_id,
        query_text=request.query,
        top_k=request.top_k,
    )

    return {
        "status": "success",
        "tenant_id": str(request.tenant_id),
        "query": request.query,
        "results_count": len(snippets),
        "snippets": snippets,
        "results": snippets,
    }


@router.get("/documents")
async def list_documents(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    List all ingested documents and their chunk counts for a tenant.
    """
    from app.db.models import KnowledgeDocument, DocumentChunk
    from sqlalchemy import func, select

    stmt = (
        select(
            KnowledgeDocument.id,
            KnowledgeDocument.title,
            KnowledgeDocument.source_type,
            KnowledgeDocument.source_url,
            KnowledgeDocument.created_at,
            func.count(DocumentChunk.id).label("chunks_count"),
        )
        .outerjoin(DocumentChunk, DocumentChunk.document_id == KnowledgeDocument.id)
        .where(KnowledgeDocument.tenant_id == tenant_id)
        .group_by(KnowledgeDocument.id)
        .order_by(KnowledgeDocument.created_at.desc())
    )
    res = await db.execute(stmt)
    rows = res.all()

    docs = []
    for r in rows:
        docs.append({
            "id": str(r.id),
            "title": r.title,
            "sourceType": r.source_type,
            "sourceUrl": r.source_url,
            "chunksCount": r.chunks_count,
            "createdAt": r.created_at.strftime("%b %d, %Y") if r.created_at else "Recently",
            "status": "HNSW 1536-dim Indexed",
        })

    return {"status": "success", "documents": docs}


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: UUID,
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Deletes a knowledge document and cascades deletion of its vector chunks.
    """
    from app.db.models import KnowledgeDocument
    from sqlalchemy import delete

    stmt = delete(KnowledgeDocument).where(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.tenant_id == tenant_id,
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "success", "message": "Document deleted successfully"}
