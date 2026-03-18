import logging

from fastembed import TextEmbedding
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from app.config import settings
from app.db.qdrant import qdrant_client

logger = logging.getLogger(__name__)

embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")


def embed_query(query: str) -> list[float]:
    """Embed a single query string using the same model as ingestion."""
    embeddings = list(embedding_model.embed([query]))
    return embeddings[0].tolist()


def search_qdrant(query_embedding: list[float], user_id: str, top_k: int = 5) -> list[dict]:
    """Search Qdrant with mandatory user_id filter for tenant isolation.

    Returns list of dicts with keys: chunk_text, filename, page, score, doc_id.
    """
    response = qdrant_client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=query_embedding,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id),
                )
            ]
        ),
        limit=top_k,
        with_payload=True,
    )

    chunks = []
    for hit in response.points:
        chunks.append(
            {
                "chunk_text": hit.payload.get("chunk_text", ""),
                "filename": hit.payload.get("filename", ""),
                "page": hit.payload.get("page", 0),
                "score": hit.score,
                "doc_id": hit.payload.get("doc_id", ""),
            }
        )

    return chunks
