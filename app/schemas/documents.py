from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UploadResponse(BaseModel):
    id: UUID
    filename: str
    status: str
    message: str


class DocumentListItem(BaseModel):
    id: UUID
    filename: str
    status: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentStatus(BaseModel):
    id: UUID
    filename: str
    status: str
    chunk_count: int
    error_message: str | None = None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]
    max_documents: int
    remaining: int
