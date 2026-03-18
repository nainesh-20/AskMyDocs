import logging
from functools import lru_cache

from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding:
    """Return the shared TextEmbedding singleton, loading it on first call."""
    logger.info("Loading embedding model: %s", MODEL_NAME)
    return TextEmbedding(MODEL_NAME)
