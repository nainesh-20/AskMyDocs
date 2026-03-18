import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.core.dependencies import get_current_user
from app.schemas.query import QueryRequest, QueryResponse, SourceChunk
from app.services.llm import call_groq
from app.services.retrieval import embed_query, search_qdrant

logger = logging.getLogger(__name__)
router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query_documents(
    body: QueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """Query your documents with confidence-aware retrieval.

    Three response modes based on the top similarity score:
    - answer (>= 0.75): High confidence — full LLM-generated answer with sources
    - low_confidence (>= 0.45): Moderate match — answer with uncertainty warning
    - no_match (< 0.45): No relevant context — LLM skipped entirely
    """
    user_id = current_user["user_id"]

    try:
        query_embedding = embed_query(body.question)
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to embed query",
        )

    try:
        chunks = search_qdrant(query_embedding, user_id, top_k=5)
    except Exception as e:
        logger.error("Qdrant search failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search documents",
        )

    sources = [
        SourceChunk(
            filename=c["filename"],
            page=c["page"],
            score=round(c["score"], 4),
            text=c["chunk_text"][:200],
        )
        for c in chunks
    ]

    if not chunks:
        return QueryResponse(
            mode="no_match",
            answer="No documents found. Please upload documents first.",
            sources=[],
        )

    top_score = chunks[0]["score"]

    # High confidence — full answer
    if top_score >= settings.confidence_threshold:
        answer = call_groq(body.question, chunks)
        return QueryResponse(mode="answer", answer=answer, sources=sources)

    # Moderate confidence — answer with warning
    if top_score >= settings.no_match_threshold:
        answer = call_groq(body.question, chunks)
        return QueryResponse(
            mode="low_confidence",
            answer=answer,
            sources=sources,
            warning=(
                f"The best matching context has a relevance score of {top_score:.2f}, "
                "which is below the confidence threshold. The answer may not be fully accurate."
            ),
        )

    # No match — skip LLM entirely
    return QueryResponse(
        mode="no_match",
        answer=(
            "I couldn't find sufficiently relevant information in your documents "
            "to answer this question. The closest matches are included below, "
            "but they may not be directly related."
        ),
        sources=sources,
    )
