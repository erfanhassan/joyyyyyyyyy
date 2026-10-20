import io
import csv
import logging
import uuid
from typing import List, Dict, Any, Optional
from uuid import UUID
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import KnowledgeDocument, DocumentChunk
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger("joy.rag")


class RAGService:
    """
    Knowledge Brain RAG Engine:
    - Ingests PDFs, CSVs, and storefront URLs
    - Recursively chunks text (500 tokens / ~2,000 chars, 50 token / ~200 char overlap)
    - Generates 1536-dim vector embeddings
    - Executes multi-tenant hybrid retrieval (pgvector HNSW + tsvector BM25)
    """

    # ==========================================
    # 1. Text Parsing & URL Crawling
    # ==========================================
    @staticmethod
    async def crawl_storefront_url(url: str) -> str:
        """
        Crawls a merchant storefront URL and extracts clean structured catalog text.
        """
        headers = {
            "User-Agent": "JoyStorefrontCrawler/1.0 (+https://joy.ai; bot@joy.ai)"
        }
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text

        soup = BeautifulSoup(html, "html.parser")

        # Strip unneeded HTML tags
        for element in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
            element.decompose()

        # Extract meta description and title
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if meta_tag and meta_tag.get("content"):
            meta_desc = meta_tag["content"].strip()

        # Extract text blocks
        text_content = soup.get_text(separator="\n", strip=True)
        # Collapse multiple blank lines
        clean_lines = [line.strip() for line in text_content.splitlines() if line.strip()]
        body_text = "\n".join(clean_lines)

        full_content = f"Page Title: {title}\nSummary: {meta_desc}\n\nContent:\n{body_text}"
        return full_content

    @staticmethod
    def parse_pdf_bytes(file_bytes: bytes) -> str:
        """Extract text from an uploaded PDF file."""
        reader = PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for i, page in enumerate(reader.pages):
            text_val = page.extract_text()
            if text_val:
                pages_text.append(f"--- Page {i + 1} ---\n{text_val.strip()}")
        return "\n\n".join(pages_text)

    @staticmethod
    def parse_csv_bytes(file_bytes: bytes) -> str:
        """
        Parse CSV product catalog rows into readable knowledge blocks.
        """
        text_stream = io.StringIO(file_bytes.decode("utf-8", errors="replace"))
        reader = csv.DictReader(text_stream)
        rows_text = []
        for i, row in enumerate(reader):
            # Format row as key-value pairs
            row_items = [f"{k.strip()}: {v.strip()}" for k, v in row.items() if k and v]
            rows_text.append(f"Item #{i + 1}:\n" + "\n".join(row_items))
        return "\n\n".join(rows_text)

    # ==========================================
    # 2. Recursive Character Text Chunker
    # ==========================================
    @staticmethod
    def chunk_text(
        text: str,
        chunk_size: int = 2000,  # ~500 tokens
        chunk_overlap: int = 200, # ~50 tokens
    ) -> List[str]:
        """
        Recursively splits text into overlapping chunks respecting natural paragraph
        and sentence boundaries.
        """
        if not text:
            return []

        if len(text) <= chunk_size:
            return [text.strip()]

        separators = ["\n\n", "\n", ". ", " ", ""]
        return RAGService._recursive_split(text, separators, chunk_size, chunk_overlap)

    @staticmethod
    def _recursive_split(text: str, separators: List[str], chunk_size: int, chunk_overlap: int) -> List[str]:
        final_chunks = []
        separator = separators[-1]
        new_separators = []

        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1:]
                break

        splits = text.split(separator) if separator else list(text)
        current_chunk = []
        current_len = 0

        for s in splits:
            s_len = len(s) + len(separator)
            if current_len + s_len > chunk_size and current_chunk:
                chunk_str = separator.join(current_chunk).strip()
                if chunk_str:
                    final_chunks.append(chunk_str)
                # Keep overlap from the end of the current chunk
                overlap_items = []
                overlap_len = 0
                for item in reversed(current_chunk):
                    if overlap_len + len(item) + len(separator) <= chunk_overlap:
                        overlap_items.insert(0, item)
                        overlap_len += len(item) + len(separator)
                    else:
                        break
                current_chunk = overlap_items
                current_len = overlap_len

            current_chunk.append(s)
            current_len += s_len

        if current_chunk:
            final_str = separator.join(current_chunk).strip()
            if final_str:
                final_chunks.append(final_str)

        return final_chunks

    # ==========================================
    # 3. Ingestion into PostgreSQL & pgvector
    # ==========================================
    @staticmethod
    async def ingest_document(
        db: AsyncSession,
        tenant_id: UUID,
        title: str,
        source_type: str,
        content: str,
        source_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parses, chunks, embeds, and stores a document in document_chunks with pgvector HNSW indexing.
        """
        # 1. Create Knowledge Document header
        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            source_type=source_type,
            source_url=source_url,
            title=title,
        )
        db.add(doc)
        await db.flush()

        # 2. Chunk text
        chunks = RAGService.chunk_text(content)
        if not chunks:
            return {"document_id": str(doc.id), "chunks_count": 0}

        # 3. Generate embeddings
        embeddings = await EmbeddingService.get_embeddings(chunks)

        # 4. Insert DocumentChunks
        chunk_objects = []
        for chunk_text, emb in zip(chunks, embeddings):
            chunk_obj = DocumentChunk(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                document_id=doc.id,
                content=chunk_text,
                embedding=emb,
            )
            chunk_objects.append(chunk_obj)

        db.add_all(chunk_objects)
        await db.commit()

        logger.info(f"Ingested document '{title}' ({source_type}) with {len(chunks)} chunks for tenant {tenant_id}")
        return {
            "document_id": str(doc.id),
            "title": title,
            "source_type": source_type,
            "chunks_count": len(chunks),
        }

    # ==========================================
    # 4. Hybrid Retrieval (Vector Cosine + BM25 TSVector)
    # ==========================================
    @staticmethod
    async def hybrid_query(
        db: AsyncSession,
        tenant_id: UUID,
        query_text: str,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Executes hybrid vector + full-text search strictly scoped by tenant_id.
        Combines pgvector cosine similarity and PostgreSQL tsvector BM25 rank.
        """
        # 1. Generate query embedding
        query_vector = await EmbeddingService.get_embedding(query_text)
        vector_str = "[" + ",".join(str(f) for f in query_vector) + "]"

        # 2. Hybrid SQL Query with Reciprocal Rank Fusion / Combined Scoring
        sql = text("""
            SELECT 
                dc.id,
                dc.content,
                kd.title AS document_title,
                kd.source_type,
                (1.0 - (dc.embedding <=> CAST(:query_vector AS vector))) AS vector_similarity,
                COALESCE(ts_rank_cd(dc.tsv, websearch_to_tsquery('english', :query_text)), 0.0) AS text_rank,
                -- Combined score: 60% semantic vector + 40% keyword match
                ((1.0 - (dc.embedding <=> CAST(:query_vector AS vector))) * 0.6 + 
                 COALESCE(ts_rank_cd(dc.tsv, websearch_to_tsquery('english', :query_text)), 0.0) * 0.4) AS hybrid_score
            FROM document_chunks dc
            JOIN knowledge_documents kd ON dc.document_id = kd.id
            WHERE dc.tenant_id = :tenant_id
            ORDER BY hybrid_score DESC
            LIMIT :top_k;
        """)

        result = await db.execute(
            sql,
            {
                "tenant_id": str(tenant_id),
                "query_vector": vector_str,
                "query_text": query_text,
                "top_k": top_k,
            },
        )

        rows = result.fetchall()
        snippets = []
        for row in rows:
            snippets.append({
                "chunk_id": str(row.id),
                "content": row.content,
                "document_title": row.document_title,
                "source_type": row.source_type,
                "vector_similarity": round(float(row.vector_similarity or 0.0), 4),
                "text_rank": round(float(row.text_rank or 0.0), 4),
                "score": round(float(row.hybrid_score or 0.0), 4),
            })

        return snippets
