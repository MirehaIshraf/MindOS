from fastapi import APIRouter

from app.services.embedding_index_service import embedding_index_service

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.get("/status")
def embedding_status() -> dict:
    return embedding_index_service.status()


@router.post("/reindex")
def reindex_embeddings() -> dict:
    return embedding_index_service.reindex_all()


@router.post("/clear")
def clear_embeddings() -> dict:
    return embedding_index_service.clear_index()
