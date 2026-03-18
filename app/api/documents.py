import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import create_client

from app.config import settings
from app.core.dependencies import get_current_user
from app.db.models import Document
from app.db.postgres import get_db
from app.schemas.documents import DocumentListItem, DocumentListResponse, DocumentStatus, UploadResponse
from app.services.ingestion import process_pdf_and_index

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


def get_storage():
    """Create Supabase storage client with service_role key (bypasses RLS)."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Upload a PDF document for ingestion. Returns 202 immediately while processing runs in background."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )

    user_id = current_user["user_id"]

    doc_count = await db.scalar(
        select(func.count()).where(Document.user_id == user_id)
    )
    if doc_count >= settings.max_documents_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Free tier limit reached ({settings.max_documents_per_user} documents). Check back when we scale up!",
        )
    doc_id = uuid.uuid4()
    storage_path = f"{user_id}/{doc_id}/{file.filename}"

    file_content = await file.read()
    if len(file_content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    try:
        supabase_storage = get_storage()
        supabase_storage.storage.from_(settings.supabase_storage_bucket).upload(
            path=storage_path,
            file=file_content,
            file_options={"content-type": "application/pdf"},
        )
    except Exception as e:
        logger.error("Storage upload failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file to storage",
        )

    document = Document(
        id=doc_id,
        user_id=user_id,
        filename=file.filename,
        storage_path=storage_path,
        status="pending",
    )
    db.add(document)
    await db.commit()

    background_tasks.add_task(
        process_pdf_and_index,
        doc_id=str(doc_id),
        storage_path=storage_path,
        user_id=user_id,
        filename=file.filename,
    )

    return UploadResponse(
        id=doc_id,
        filename=file.filename,
        status="pending",
        message="Document uploaded. Processing started in background.",
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all documents for the current user, including usage limits."""
    stmt = (
        select(Document)
        .where(Document.user_id == current_user["user_id"])
        .order_by(Document.created_at.desc())
    )
    result = await db.execute(stmt)
    documents = result.scalars().all()
    max_docs = settings.max_documents_per_user
    return DocumentListResponse(
        documents=documents,
        max_documents=max_docs,
        remaining=max(0, max_docs - len(documents)),
    )


@router.get("/{doc_id}/status", response_model=DocumentStatus)
async def get_document_status(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Poll the processing status of a specific document."""
    stmt = select(Document).where(
        Document.id == doc_id,
        Document.user_id == current_user["user_id"],
    )
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return document
