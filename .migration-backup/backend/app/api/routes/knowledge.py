import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from pydantic import BaseModel, HttpUrl
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
    query: str
    tenant_id: UUID
    top_k: int = 3


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
    file_bytes = await file.read()

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
    }
