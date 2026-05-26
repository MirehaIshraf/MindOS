import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AppSettingRecord, get_session_factory, initialize_database
from app.integrations.llm.providers.ollama_provider import OllamaProvider
from app.schemas.models import EmbeddingModelConfig, EmbeddingSettingsResponse


EMBEDDING_MARKERS = ("embed", "embedding", "nomic-embed", "qwen3-embedding", "harrier")

CURATED_EMBEDDING_MODELS: list[dict[str, Any]] = [
    {
        "id": "embedding-nomic-embed-text",
        "provider": "ollama",
        "display_name": "nomic-embed-text",
        "model_id": "nomic-embed-text",
        "type": "local",
        "dimension": None,
        "description": "Reliable local embedding model for general semantic search.",
        "install_command": "ollama pull nomic-embed-text",
        "aliases": ["nomic-embed-text", "nomic-embed-text:latest"],
    },
    {
        "id": "embedding-qwen3-0-6b",
        "provider": "ollama",
        "display_name": "Qwen3 Embedding 0.6B",
        "model_id": "qwen3-embedding:0.6b",
        "type": "local",
        "dimension": None,
        "description": "Compact Qwen3 embedding model for multilingual/local retrieval.",
        "install_command": "ollama pull qwen3-embedding:0.6b",
        "aliases": ["qwen3-embedding:0.6b", "dengcao/qwen3-embedding-0.6b", "andersc/qwen3-embedding:0.6b"],
    },
    {
        "id": "embedding-harrier-0-6b",
        "provider": "ollama",
        "display_name": "Harrier 0.6B",
        "model_id": "harrier-oss:0.6b",
        "type": "local",
        "dimension": None,
        "description": "Compact multilingual embedding model.",
        "install_command": "ollama pull harrier-oss:0.6b",
        "aliases": ["harrier-oss:0.6b", "harrier:0.6b"],
    },
]


class EmbeddingModelRegistryService:
    def __init__(self) -> None:
        initialize_database()
        self._session_factory = get_session_factory()
        self._settings = get_settings()

    def get_settings_response(self, installed_models: set[str] | None = None) -> EmbeddingSettingsResponse:
        models = self.list_models(installed_models=installed_models)
        selected_id = self.get_selected_embedding_model_id(models)
        selected = next((model for model in models if model.id == selected_id), None) or models[0]
        index_model = self.get_index_model_name()
        return EmbeddingSettingsResponse(
            embedding_enabled=self._settings.enable_embeddings,
            selected_embedding_model=selected.model_id,
            selected_embedding_model_id=selected.id,
            index_model_id=index_model,
            index_stale=bool(index_model and index_model != selected.model_id),
            models=models,
        )

    def list_models(self, installed_models: set[str] | None = None) -> list[EmbeddingModelConfig]:
        installed = self._ollama_models() if installed_models is None else installed_models
        used_names: set[str] = set()
        models: list[EmbeddingModelConfig] = []
        for definition in CURATED_EMBEDDING_MODELS:
            installed_name = self._matching_installed_name(definition, installed)
            if installed_name:
                used_names.add(installed_name)
            models.append(
                EmbeddingModelConfig(
                    id=definition["id"],
                    provider=definition["provider"],
                    display_name=definition["display_name"],
                    model_id=installed_name or definition["model_id"],
                    type=definition["type"],
                    enabled=True,
                    configured=bool(installed_name),
                    available=bool(installed_name),
                    dimension=definition["dimension"],
                    description=definition["description"],
                    install_command=definition["install_command"],
                )
            )

        for model_name in sorted(name for name in installed if name not in used_names and self._is_embedding_model(name)):
            models.append(
                EmbeddingModelConfig(
                    id=f"embedding-{self._slug(model_name)}",
                    provider="ollama",
                    display_name=f"{self._display_name(model_name)}",
                    model_id=model_name,
                    type="local",
                    enabled=True,
                    configured=True,
                    available=True,
                    dimension=None,
                    description="Other installed Ollama embedding model.",
                    install_command=None,
                )
            )
        return models

    def select_model(self, model_id: str) -> EmbeddingSettingsResponse:
        model = self.get_model(model_id)
        if model is None:
            raise ValueError("Unknown embedding model.")
        self._set_setting("selected_embedding_model_id", model.id)
        self._set_setting("selected_embedding_model_name", model.model_id)
        return self.get_settings_response()

    def get_model(self, model_id: str) -> EmbeddingModelConfig | None:
        return next((model for model in self.list_models() if model.id == model_id), None)

    def selected_model(self) -> EmbeddingModelConfig:
        models = self.list_models()
        selected_id = self.get_selected_embedding_model_id(models)
        return next((model for model in models if model.id == selected_id), models[0])

    def selected_model_name(self) -> str:
        return self.selected_model().model_id

    def get_selected_embedding_model_id(self, models: list[EmbeddingModelConfig] | None = None) -> str:
        model_list = models or self.list_models()
        env_default = self._id_for_model_name(self._settings.ollama_embed_model, model_list)
        selected_id = self._get_setting("selected_embedding_model_id", env_default)
        if any(model.id == selected_id for model in model_list):
            return selected_id
        return env_default

    def get_index_model_name(self) -> str | None:
        return self._get_setting("embedding_index_model_name", None)

    def mark_index_model(self, model_name: str, stale: bool = False) -> None:
        self._set_setting("embedding_index_model_name", model_name)
        self._set_setting("embedding_index_stale", stale)

    def mark_index_stale(self) -> None:
        self._set_setting("embedding_index_stale", True)

    def index_stale(self) -> bool:
        response = self.get_settings_response()
        return response.index_stale or bool(self._get_setting("embedding_index_stale", False))

    def selected_model_available(self, installed_models: set[str] | None = None) -> bool:
        if installed_models is None:
            return self.selected_model().available
        response = self.get_settings_response(installed_models=installed_models)
        return any(model.id == response.selected_embedding_model_id and model.available for model in response.models)

    def _id_for_model_name(self, model_name: str, models: list[EmbeddingModelConfig]) -> str:
        for model in models:
            if model.model_id == model_name or model.model_id == f"{model_name}:latest":
                return model.id
        return "embedding-nomic-embed-text"

    def _ollama_models(self) -> set[str]:
        try:
            return set(OllamaProvider(self._settings.ollama_base_url).list_models())
        except Exception:
            return set()

    def _matching_installed_name(self, definition: dict[str, Any], installed: set[str]) -> str | None:
        normalized_installed = {name.lower(): name for name in installed}
        for alias in definition.get("aliases", []):
            lowered = str(alias).lower()
            if lowered in normalized_installed:
                return normalized_installed[lowered]
            latest = f"{lowered}:latest"
            if latest in normalized_installed:
                return normalized_installed[latest]
        return None

    def _is_embedding_model(self, model_name: str) -> bool:
        normalized = model_name.lower()
        return any(marker in normalized for marker in EMBEDDING_MARKERS)

    def _display_name(self, model_name: str) -> str:
        name = model_name.replace("/", " ").replace(":", " ")
        return " ".join(part.capitalize() for part in re.split(r"[-_\s]+", name) if part)

    def _slug(self, model_name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")

    def _get_setting(self, key: str, default: Any = None) -> Any:
        with self._session_factory() as session:
            record = session.get(AppSettingRecord, key)
            if record is None:
                return default
            return json.loads(record.value)

    def _set_setting(self, key: str, value: Any) -> None:
        with self._session_factory() as session:
            record = session.get(AppSettingRecord, key)
            if record is None:
                record = AppSettingRecord(key=key, value=json.dumps(value), updated_at=datetime.now(timezone.utc))
                session.add(record)
            else:
                record.value = json.dumps(value)
                record.updated_at = datetime.now(timezone.utc)
            session.commit()


embedding_model_registry_service = EmbeddingModelRegistryService()
