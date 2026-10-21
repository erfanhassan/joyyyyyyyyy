import hashlib
import math
import logging
from typing import List
import httpx
from app.core.config import settings

logger = logging.getLogger("joy.embeddings")

EMBEDDING_DIM = 1536


class EmbeddingService:
    """
    Generates 1536-dimensional vector embeddings for Knowledge Brain catalog chunks.
    Uses OpenAI text-embedding-3-small API when OPENAI_API_KEY is configured.
    Falls back to deterministic normalized hashing in test/sandbox environments.
    """

    @staticmethod
    async def get_embedding(text: str) -> List[float]:
        """Generate embedding vector for a single string."""
        results = await EmbeddingService.get_embeddings([text])
        return results[0] if results else [0.0] * EMBEDDING_DIM

    @staticmethod
    async def get_embeddings(texts: List[str]) -> List[List[float]]:
        """
        Generate embedding vectors for a list of strings.
        Returns List of 1536-dimensional float vectors.
        """
        if not texts:
            return []

        # 1. If OpenAI API key is configured, call text-embedding-3-small with retry
        if settings.OPENAI_API_KEY:
            max_retries = 3
            backoff = 1.0
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            "https://api.openai.com/v1/embeddings",
                            headers={
                                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": "text-embedding-3-small",
                                "input": texts,
                                "dimensions": EMBEDDING_DIM,
                            },
                        )
                        if response.status_code == 200:
                            data = response.json()
                            embeddings = [item["embedding"] for item in data["data"]]
                            return embeddings
                        else:
                            last_err = f"OpenAI embedding API returned status {response.status_code}: {response.text}"
                            logger.warning(f"Embedding attempt {attempt}/{max_retries} failed: {last_err}")
                except Exception as e:
                    last_err = str(e)
                    logger.warning(f"Embedding attempt {attempt}/{max_retries} encountered exception: {e}")

                if attempt < max_retries:
                    import asyncio
                    await asyncio.sleep(backoff)
                    backoff *= 2.0

            # Do NOT silently fall back to deterministic vectors when API key is configured
            raise RuntimeError(f"OpenAI embedding generation failed after {max_retries} attempts: {last_err}")

        from app.core.deployment_guard import is_public_deployment
        if is_public_deployment():
            raise RuntimeError("Production knowledge indexing requires an embedding provider; synthetic vectors are disabled.")
        # Deterministic vectors are available only for offline/local tests.
        logger.info("OPENAI_API_KEY not configured. Generating deterministic embeddings for testing.")
        return [EmbeddingService._generate_deterministic_embedding(t) for t in texts]

    @staticmethod
    def _generate_deterministic_embedding(text: str) -> List[float]:
        """
        Generates a deterministic, unit-normalized 1536-dimensional pseudo-semantic vector
        derived from character n-grams and cryptographic hashing.
        """
        clean_text = text.strip().lower()
        vector = [0.0] * EMBEDDING_DIM

        # Distribute tokens and character tri-grams across dimensions
        words = clean_text.split()
        for i, word in enumerate(words):
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % EMBEDDING_DIM
            vector[idx] += 1.0 / (1.0 + i * 0.1)

            # Character tri-grams
            for j in range(len(word) - 2):
                trigram = word[j:j+3]
                th = int(hashlib.sha256(trigram.encode("utf-8")).hexdigest(), 16)
                tidx = th % EMBEDDING_DIM
                vector[tidx] += 0.5

        # L2-normalization (unit vector for cosine distance)
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        else:
            # Fallback uniform
            val = 1.0 / math.sqrt(EMBEDDING_DIM)
            vector = [val] * EMBEDDING_DIM

        return vector
