import logging

from fastapi import APIRouter, HTTPException

from app.schemas.models import (
    ChatModelsResponse,
    ModelConfig,
    EmbeddingSettingsResponse,
    ModelSettingsResponse,
    UpdateModelEnabledRequest,
    UpdateSelectedEmbeddingModelRequest,
    UpdateProviderConfigRequest,
    UpdateSelectedModelRequest,
)
from app.services.embedding_model_registry_service import embedding_model_registry_service
from app.services.model_registry_service import model_registry_service

router = APIRouter(prefix="/models", tags=["models"])
logger = logging.getLogger(__name__)


@router.get("/settings", response_model=ModelSettingsResponse)
def get_model_settings() -> ModelSettingsResponse:
    try:
        return model_registry_service.get_settings_response()
    except Exception as error:
        logger.exception("Failed to load model settings")
        fake = model_registry_service.fake_model()
        return ModelSettingsResponse(
            providers=[],
            models=[fake],
            selected_chat_model=fake.id,
        )


@router.get("/chat", response_model=ChatModelsResponse)
def get_chat_models() -> ChatModelsResponse:
    try:
        return model_registry_service.get_chat_models_response()
    except Exception:
        fake = model_registry_service.fake_model()
        return ChatModelsResponse(
            models=[fake],
            selected_chat_model=fake.id,
            warning="Model settings unavailable. Using fallback.",
        )


@router.post("/select")
def select_chat_model(request: UpdateSelectedModelRequest) -> dict[str, str]:
    try:
        model = model_registry_service.get_model(request.model_id)
        if model is None:
            raise HTTPException(status_code=404, detail="Unknown model.")
        if model.id != "fake-llm" and (not model.enabled or not model.configured or not model.available):
            raise HTTPException(status_code=400, detail="Selected model is not available for chat.")
        model_registry_service.select_chat_model(request.model_id)
    except ValueError as error:
        logger.exception("Failed to select chat model")
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"status": "selected", "selected_chat_model": request.model_id}


@router.post("/provider-config")
def update_provider_config(request: UpdateProviderConfigRequest) -> dict[str, object]:
    try:
        model_registry_service.update_provider_config(
            provider=request.provider,
            api_key=request.api_key,
            base_url=request.base_url,
            enabled=request.enabled,
        )
    except ValueError as error:
        logger.exception("Failed to update provider config")
        raise HTTPException(status_code=404, detail=str(error)) from error
    provider_status = model_registry_service.provider_status().get(request.provider, {})
    return {
        "status": "configured",
        "provider": request.provider,
        "configured": bool(provider_status.get("configured")),
        "enabled": bool(provider_status.get("enabled")),
        "has_api_key": bool(provider_status.get("has_api_key")),
    }


@router.post("/{model_id}/enabled")
def set_model_enabled(model_id: str, request: UpdateModelEnabledRequest) -> dict[str, object]:
    try:
        model_registry_service.set_model_enabled(model_id, request.enabled)
    except ValueError as error:
        logger.exception("Failed to update model enabled state")
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"status": "updated", "model_id": model_id, "enabled": request.enabled}


@router.get("/providers/health")
def get_provider_health() -> dict[str, object]:
    return model_registry_service.provider_health()


@router.get("/embeddings", response_model=EmbeddingSettingsResponse)
def get_embedding_models() -> EmbeddingSettingsResponse:
    return embedding_model_registry_service.get_settings_response()


@router.post("/embeddings/select", response_model=EmbeddingSettingsResponse)
def select_embedding_model(request: UpdateSelectedEmbeddingModelRequest) -> EmbeddingSettingsResponse:
    try:
        return embedding_model_registry_service.select_model(request.model_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
