"""Global singleton instances for Vera-AI."""
from .qdrant_service import QdrantService
from .config import config

_qdrant_service: QdrantService = None


def get_qdrant_service() -> QdrantService:
    """Get or create the global QdrantService singleton."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService(
            host=config.qdrant_host,
            collection=config.qdrant_collection,
            embedding_model=config.embedding_model,
            vector_size=config.vector_size,
            ollama_host=config.ollama_host
        )
    return _qdrant_service