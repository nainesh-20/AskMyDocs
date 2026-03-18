import logging
import uuid

import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.http.models import PointStruct
from sqlalchemy import update
from supabase import create_client

from app.config import settings
from app.db.models import Document
from app.db.postgres import async_session
from app.db.qdrant import qdrant_client
from app.services.embeddings import get_embedding_model

logger = logging.getLogger(__name__)

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=50,
    length_function=len,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def download_from_storage(storage_path: str) -> bytes:
    """Download a file from Supabase Storage and return raw bytes."""
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    response = client.storage.from_(settings.supabase_storage_bucket).download(storage_path)
    return response


def extract_text_by_page(pdf_bytes: bytes) -> list[dict]:
    """Extract text from each page of a PDF, returning page number + text."""
    pages = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            if text.strip():
                pages.append({"page": page_num, "text": text})
    return pages


def chunk_text(pages: list[dict]) -> list[dict]:
    """Split page text into smaller chunks, preserving page number metadata."""
    chunks = []
    for page_data in pages:
        page_chunks = text_splitter.split_text(page_data["text"])
        for chunk in page_chunks:
            chunks.append({"page": page_data["page"], "text": chunk})
    return chunks


def embed_chunks(chunks: list[dict]) -> list[list[float]]:
    """Batch-embed all chunk texts using FastEmbed."""
    texts = [c["text"] for c in chunks]
    embeddings = list(get_embedding_model().embed(texts))
    return [e.tolist() for e in embeddings]


def upsert_to_qdrant(
    chunks: list[dict],
    embeddings: list[list[float]],
    user_id: str,
    doc_id: str,
    filename: str,
) -> int:
    """Upsert embedded chunks into Qdrant with full payload for filtering."""
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                "user_id": user_id,
                "doc_id": doc_id,
                "filename": filename,
                "page": chunk["page"],
                "chunk_text": chunk["text"],
            },
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]

    BATCH_SIZE = 100
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        qdrant_client.upsert(
            collection_name=settings.qdrant_collection_name,
            points=batch,
        )

    return len(points)


async def update_document_status(
    doc_id: str, status: str, chunk_count: int = 0, error_message: str | None = None
) -> None:
    """Update the document status in PostgreSQL."""
    async with async_session() as session:
        stmt = (
            update(Document)
            .where(Document.id == doc_id)
            .values(
                status=status,
                chunk_count=chunk_count,
                error_message=error_message,
            )
        )
        await session.execute(stmt)
        await session.commit()


async def process_pdf_and_index(
    doc_id: str, storage_path: str, user_id: str, filename: str
) -> None:
    """Full ingestion pipeline: download → extract → chunk → embed → upsert.

    Runs as a FastAPI BackgroundTask. Updates document status on completion or failure.
    """
    try:
        logger.info("Starting ingestion for doc=%s file=%s", doc_id, filename)

        await update_document_status(doc_id, "processing")

        pdf_bytes = download_from_storage(storage_path)
        logger.info("Downloaded %d bytes from storage", len(pdf_bytes))

        pages = extract_text_by_page(pdf_bytes)
        if not pages:
            await update_document_status(doc_id, "failed", error_message="No text found in PDF")
            return

        logger.info("Extracted text from %d pages", len(pages))

        chunks = chunk_text(pages)
        logger.info("Created %d chunks", len(chunks))

        embeddings = embed_chunks(chunks)
        logger.info("Generated %d embeddings", len(embeddings))

        chunk_count = upsert_to_qdrant(chunks, embeddings, user_id, doc_id, filename)
        logger.info("Upserted %d vectors to Qdrant", chunk_count)

        await update_document_status(doc_id, "indexed", chunk_count=chunk_count)
        logger.info("Ingestion complete for doc=%s", doc_id)

    except Exception as e:
        logger.exception("Ingestion failed for doc=%s: %s", doc_id, e)
        await update_document_status(doc_id, "failed", error_message=str(e))
