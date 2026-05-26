from fastapi import APIRouter

from app.core.config import get_settings
from app.services.embedding_index_service import embedding_index_service

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.get("/status")
def embedding_status() -> dict:
    try:
        return embedding_index_service.status()
    except Exception as error:
        settings = get_settings()
        return {
            "enabled": settings.enable_embeddings,
            "embedding_model": settings.ollama_embed_model,
            "selected_embedding_model": settings.ollama_embed_model,
            "selected_embedding_model_id": "",
            "index_model": None,
            "index_stale": False,
            "embedding_model_available": False,
            "ollama_available": False,
            "chroma_available": False,
            "chroma_path": settings.chroma_path,
            "indexed_count": 0,
            "event_status": {},
            "warning": f"Embedding status unavailable: {error}",
        }


@router.post("/reindex")
def reindex_embeddings() -> dict:
    return embedding_index_service.reindex_all()


@router.post("/clear")
def clear_embeddings() -> dict:
    return embedding_index_service.clear_index()
