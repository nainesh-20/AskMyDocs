from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class SourceChunk(BaseModel):
    filename: str
    page: int
    score: float
    text: str


class QueryResponse(BaseModel):
    """Three-mode response based on retrieval confidence.

    mode="answer"         — high confidence, full LLM answer with sources
    mode="low_confidence" — moderate match, LLM answer with warning
    mode="no_match"       — no relevant context found, LLM skipped
    """

    mode: str
    answer: str
    sources: list[SourceChunk]
    warning: str | None = None
