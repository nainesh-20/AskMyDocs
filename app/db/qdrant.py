import logging

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PayloadSchemaType, VectorParams

from app.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 384  # bge-small-en output dimension

qdrant_client = QdrantClient(
    url=settings.qdrant_url,
    api_key=settings.qdrant_api_key,
)


async def init_collection() -> None:
    """Create the Qdrant collection if it doesn't already exist, and ensure payload indexes."""
    collections = qdrant_client.get_collections().collections
    existing_names = {c.name for c in collections}

    if settings.qdrant_collection_name not in existing_names:
        qdrant_client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=VectorParams(
                size=EMBEDDING_DIMENSION, distance=Distance.COSINE
            ),
        )
        logger.info("Created Qdrant collection: %s", settings.qdrant_collection_name)
    else:
        logger.info("Qdrant collection already exists: %s", settings.qdrant_collection_name)

    # Ensure payload indexes exist for filtered search (required in Qdrant 1.17+)
    for field, schema_type in [
        ("user_id", PayloadSchemaType.KEYWORD),
        ("doc_id", PayloadSchemaType.KEYWORD),
    ]:
        try:
            qdrant_client.create_payload_index(
                collection_name=settings.qdrant_collection_name,
                field_name=field,
                field_schema=schema_type,
            )
            logger.info("Created payload index: %s", field)
        except Exception:
            logger.debug("Payload index already exists or skipped: %s", field)
