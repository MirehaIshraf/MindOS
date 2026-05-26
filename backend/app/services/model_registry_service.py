import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import AppSettingRecord, get_session_factory, initialize_database
from app.integrations.llm.providers.ollama_provider import OllamaProvider
from app.schemas.models import ChatModelsResponse, ModelConfig, ModelProvider, ModelSettingsResponse

# Development storage: API keys are stored locally in SQLite for the MVP.
# Later use OS keychain or a credential manager instead.

PROVIDER_DEFINITIONS = [
    ("ollama", "Ollama", "local", False, "Local models run on this machine through Ollama."),
    ("openai", "OpenAI", "cloud", True, "Cloud models send selected memory context to OpenAI."),
    ("anthropic", "Claude", "cloud", True, "Cloud models send selected memory context to Anthropic."),
    ("kimi", "Kimi", "cloud", True, "Cloud models send selected memory context to Kimi."),
]

EMBEDDING_MODEL_MARKERS = {"embed", "embedding", "nomic-embed-text", "qwen3-embedding", "mxbai-embed-large", "all-minilm"}

CURATED_OLLAMA_MODELS: dict[str, dict[str, str]] = {
    "llama3.2:1b": {
        "id": "ollama-llama3-2-1b",
        "display_name": "Llama 3.2 1B Local",
        "description": "Speed Mode - very fast local chat, lower reasoning quality.",
        "default_context_profile": "speed_chat",
    },
    "llama3.2:latest": {
        "id": "ollama-llama3.2",
        "display_name": "Llama 3.2 Local",
        "description": "Fast local general chat model.",
        "default_context_profile": "fast_chat",
    },
    "llama3.2": {
        "id": "ollama-llama3.2",
        "display_name": "Llama 3.2 Local",
        "description": "Fast local general chat model.",
        "default_context_profile": "fast_chat",
    },
    "qwen3.5:4b": {
        "id": "ollama-qwen3-5-4b",
        "display_name": "Qwen 3.5 4B Local",
        "description": "Balanced local model for chat and coding.",
        "default_context_profile": "fast_chat",
    },
    "qwen3:8b": {
        "id": "ollama-qwen3",
        "display_name": "Qwen 3 8B Local",
        "description": "Stronger local reasoning model, slower on CPU.",
        "default_context_profile": "fast_chat",
    },
    "mistral:latest": {
        "id": "ollama-mistral",
        "display_name": "Mistral Local",
        "description": "Fast general local model.",
        "default_context_profile": "fast_chat",
    },
    "mistral": {
        "id": "ollama-mistral",
        "display_name": "Mistral Local",
        "description": "Fast general local model.",
        "default_context_profile": "fast_chat",
    },
}

PREFERRED_LOCAL_MODEL_IDS = [
    "ollama-llama3-2-1b",
    "ollama-qwen3-5-4b",
    "ollama-qwen3",
]

CLOUD_MODEL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "openai-gpt-mini",
        "provider": "openai",
        "display_name": "GPT Mini",
        "model_id": "gpt-5-mini",
        "type": "cloud",
        "privacy_level": "cloud_external",
        "description": "Curated OpenAI mini model.",
    },
    {
        "id": "openai-gpt-4.1",
        "provider": "openai",
        "display_name": "GPT-4.1",
        "model_id": "gpt-4.1",
        "type": "cloud",
        "privacy_level": "cloud_external",
        "description": "Curated OpenAI GPT-4.1 model.",
    },
    {
        "id": "openai-gpt-5",
        "provider": "openai",
        "display_name": "GPT-5",
        "model_id": "gpt-5",
        "type": "cloud",
        "privacy_level": "cloud_external",
        "description": "Curated OpenAI GPT-5 model.",
    },
    {
        "id": "anthropic-claude-sonnet",
        "provider": "anthropic",
        "display_name": "Claude Sonnet",
        "model_id": "claude-sonnet-latest",
        "type": "cloud",
        "privacy_level": "cloud_external",
        "description": "Curated Claude Sonnet model.",
    },
    {
        "id": "anthropic-claude-opus",
        "provider": "anthropic",
        "display_name": "Claude Opus",
        "model_id": "claude-opus-latest",
        "type": "cloud",
        "privacy_level": "cloud_external",
        "description": "Curated Claude Opus model.",
    },
    {
        "id": "kimi-latest",
        "provider": "kimi",
        "display_name": "Kimi Latest",
        "model_id": "kimi-k2.6",
        "type": "cloud",
        "privacy_level": "cloud_external",
        "description": "Curated Kimi model.",
    },
]

FAKE_MODEL_DEFINITION: dict[str, Any] = {
    "id": "fake-llm",
    "provider": "fake",
    "display_name": "FakeLLM fallback",
    "model_id": "fake-llm",
    "type": "local",
    "privacy_level": "local_private",
    "description": "Fallback development model.",
}


class ModelRegistryService:
    def __init__(self) -> None:
        initialize_database()
        self._session_factory = get_session_factory()
        self._settings = get_settings()

    def get_settings_response(self, ollama_models: set[str] | None = None, ollama_available: bool | None = None) -> ModelSettingsResponse:
        return ModelSettingsResponse(
            providers=self.list_providers(ollama_available=ollama_available),
            models=self.list_models(ollama_models=ollama_models),
            selected_chat_model=self.get_selected_chat_model(),
        )

    def get_chat_models_response(self, ollama_models: set[str] | None = None) -> ChatModelsResponse:
        models = self.list_chat_models(ollama_models=ollama_models)
        selected, warning = self.resolve_selected_chat_model(models)
        return ChatModelsResponse(models=models, selected_chat_model=selected.id, warning=warning)

    def list_chat_models(self, ollama_models: set[str] | None = None) -> list[ModelConfig]:
        models = [
            model
            for model in self.list_models(ollama_models=ollama_models)
            if model.enabled and model.configured and model.available and self._provider_enabled(model.provider)
        ]
        models.append(self.fake_model())
        return models

    def list_models(self, ollama_models: set[str] | None = None) -> list[ModelConfig]:
        ollama_models = self._ollama_models() if ollama_models is None else ollama_models
        local_models = [self._to_discovered_ollama_model(model_name) for model_name in sorted(self._chat_ollama_models(ollama_models))]
        cloud_models = [self._to_model(definition, ollama_models) for definition in CLOUD_MODEL_DEFINITIONS]
        return [*local_models, *cloud_models]

    def list_providers(self, ollama_available: bool | None = None) -> list[ModelProvider]:
        provider_status = self.provider_status(ollama_available=ollama_available)
        return [
            ModelProvider(
                id=provider_id,
                name=name,
                type=provider_type,
                configured=bool(provider_status[provider_id]["configured"]),
                enabled=self._provider_enabled(provider_id),
                requires_api_key=requires_api_key,
                has_api_key=bool(provider_status[provider_id]["has_api_key"]),
                available=provider_status[provider_id]["available"],
                privacy_note=privacy_note,
            )
            for provider_id, name, provider_type, requires_api_key, privacy_note in PROVIDER_DEFINITIONS
        ]

    def get_model(self, model_id: str) -> ModelConfig | None:
        if model_id == "fake-llm":
            return self.fake_model()
        return next((model for model in self.list_models() if model.id == model_id), None)

    def get_selected_chat_model(self) -> str:
        return self._get_setting("selected_chat_model", self._settings.selected_chat_model)

    def select_chat_model(self, model_id: str) -> None:
        if self.get_model(model_id) is None:
            raise ValueError("Unknown model.")
        self._set_setting("selected_chat_model", model_id)

    def update_provider_config(self, provider: str, api_key: str | None, base_url: str | None, enabled: bool) -> None:
        if provider not in {item[0] for item in PROVIDER_DEFINITIONS}:
            raise ValueError("Unknown provider.")
        if api_key is not None:
            self._set_setting(f"provider.{provider}.api_key", api_key)
        if base_url is not None:
            self._set_setting(f"provider.{provider}.base_url", base_url)
        self._set_setting(f"provider.{provider}.enabled", enabled)
        self._set_setting(f"provider.{provider}.configured", True)

    def set_model_enabled(self, model_id: str, enabled: bool) -> None:
        if self.get_model(model_id) is None:
            raise ValueError("Unknown model.")
        self._set_setting(f"model.{model_id}.enabled", enabled)

    def provider_health(self) -> dict[str, object]:
        return self.provider_status()

    def provider_status(self, ollama_available: bool | None = None) -> dict[str, dict[str, object]]:
        ollama_available = self._provider_healthy("ollama") if ollama_available is None else ollama_available
        return {
            "ollama": {
                "configured": ollama_available,
                "enabled": self._provider_enabled("ollama"),
                "has_api_key": False,
                "available": ollama_available,
            },
            "openai": {
                "configured": self._provider_configured("openai"),
                "enabled": self._provider_enabled("openai"),
                "has_api_key": bool(self.get_provider_config_value("openai", "api_key")),
                "available": None,
            },
            "anthropic": {
                "configured": self._provider_configured("anthropic"),
                "enabled": self._provider_enabled("anthropic"),
                "has_api_key": bool(self.get_provider_config_value("anthropic", "api_key")),
                "available": None,
            },
            "kimi": {
                "configured": self._provider_configured("kimi"),
                "enabled": self._provider_enabled("kimi"),
                "has_api_key": bool(self.get_provider_config_value("kimi", "api_key")),
                "available": None,
            },
        }

    def resolve_selected_chat_model(self, models: list[ModelConfig] | None = None) -> tuple[ModelConfig, str | None]:
        available_models = models or self.list_chat_models()
        selected_id = self.get_selected_chat_model()
        selected = next((model for model in available_models if model.id == selected_id), None)
        if selected:
            return selected, None
        fallback = self._preferred_fallback_model(available_models)
        return fallback, f"Selected model unavailable. Falling back to {fallback.display_name}."

    def fake_model(self) -> ModelConfig:
        return ModelConfig(
            **FAKE_MODEL_DEFINITION,
            enabled=True,
            configured=True,
            available=True,
            status="available",
        )

    def get_provider_config_value(self, provider: str, key: str, default: str = "") -> str:
        env_defaults = {
            ("openai", "api_key"): self._settings.openai_api_key,
            ("anthropic", "api_key"): self._settings.anthropic_api_key,
            ("kimi", "api_key"): self._settings.kimi_api_key,
            ("kimi", "base_url"): self._settings.kimi_base_url,
            ("ollama", "base_url"): self._settings.ollama_base_url,
        }
        return self._get_setting(f"provider.{provider}.{key}", env_defaults.get((provider, key), default))

    def _to_model(self, definition: dict[str, Any], ollama_models: set[str]) -> ModelConfig:
        model_id = definition["id"]
        provider = definition["provider"]
        configured = self._model_configured(definition, ollama_models)
        available = self._model_available(definition, ollama_models)
        default_enabled = configured if provider == "ollama" else False
        enabled = self._get_bool_setting(f"model.{model_id}.enabled", default_enabled)
        status = "available" if available else "unavailable"
        return ModelConfig(**definition, enabled=enabled, configured=configured, available=available, status=status)

    def _to_discovered_ollama_model(self, model_name: str) -> ModelConfig:
        metadata = self._ollama_metadata(model_name)
        model_id = metadata["id"]
        enabled = self._get_bool_setting(f"model.{model_id}.enabled", True)
        return ModelConfig(
            id=model_id,
            provider="ollama",
            display_name=metadata["display_name"],
            model_id=model_name,
            type="local",
            enabled=enabled,
            configured=True,
            available=True,
            status="available",
            supports_tools=False,
            supports_vision=False,
            default_context_profile=metadata["default_context_profile"],
            privacy_level="local_private",
            description=metadata["description"],
        )

    def _model_configured(self, definition: dict[str, Any], ollama_models: set[str]) -> bool:
        provider = definition["provider"]
        if provider == "ollama":
            return self._ollama_model_available(definition["model_id"], ollama_models)
        return self._provider_configured(provider)

    def _model_available(self, definition: dict[str, Any], ollama_models: set[str]) -> bool:
        provider = definition["provider"]
        if provider == "ollama":
            return self._ollama_model_available(definition["model_id"], ollama_models)
        return self._provider_configured(provider)

    def _provider_configured(self, provider: str) -> bool:
        if provider == "ollama":
            return self._provider_healthy("ollama")
        if provider == "openai":
            return bool(self.get_provider_config_value("openai", "api_key"))
        if provider == "anthropic":
            return bool(self.get_provider_config_value("anthropic", "api_key"))
        if provider == "kimi":
            return bool(self.get_provider_config_value("kimi", "api_key") and self.get_provider_config_value("kimi", "base_url"))
        return False

    def _provider_enabled(self, provider: str) -> bool:
        default = provider == "ollama" or bool(self._provider_configured(provider))
        return self._get_bool_setting(f"provider.{provider}.enabled", default)

    def _provider_healthy(self, provider: str) -> bool:
        if provider == "ollama":
            try:
                return OllamaProvider(self.get_provider_config_value("ollama", "base_url")).health_check()
            except Exception:
                return False
        return self._provider_configured(provider)

    def _ollama_models(self) -> set[str]:
        try:
            return set(OllamaProvider(self.get_provider_config_value("ollama", "base_url")).list_models())
        except Exception:
            return set()

    def _ollama_model_available(self, model_id: str, ollama_models: set[str]) -> bool:
        return model_id in ollama_models or f"{model_id}:latest" in ollama_models

    def _chat_ollama_models(self, ollama_models: set[str]) -> set[str]:
        return {model_name for model_name in ollama_models if not self._is_embedding_model(model_name)}

    def discovered_ollama_models(self) -> list[str]:
        return sorted(self._ollama_models())

    def local_chat_models_count(self) -> int:
        return len(self._chat_ollama_models(self._ollama_models()))

    def embedding_models_filtered_count(self) -> int:
        models = self._ollama_models()
        return len(models) - len(self._chat_ollama_models(models))

    def _is_embedding_model(self, model_name: str) -> bool:
        normalized = model_name.lower()
        return any(marker in normalized for marker in EMBEDDING_MODEL_MARKERS)

    def _ollama_metadata(self, model_name: str) -> dict[str, str]:
        normalized = model_name.lower()
        base = normalized.removesuffix(":latest")
        metadata = CURATED_OLLAMA_MODELS.get(normalized) or CURATED_OLLAMA_MODELS.get(base)
        if metadata:
            return metadata
        if "deepseek-r1" in normalized:
            return {
                "id": f"ollama-{self._slug_model_id(model_name)}",
                "display_name": self._display_name(model_name).replace("Deepseek", "DeepSeek R1"),
                "description": "Reasoning model. May be slower and may output thinking unless controlled.",
                "default_context_profile": "deep_chat",
            }
        return {
            "id": f"ollama-{self._slug_model_id(model_name)}",
            "display_name": f"{self._display_name(model_name)} Local",
            "description": "Installed Ollama model.",
            "default_context_profile": "fast_chat",
        }

    def _display_name(self, model_name: str) -> str:
        name = model_name.split(":", 1)[0].replace(".", " ")
        size = model_name.split(":", 1)[1] if ":" in model_name else ""
        words = " ".join(part.capitalize() for part in re.split(r"[-_\s]+", name) if part)
        return f"{words} {size.upper()}".strip()

    def _slug_model_id(self, model_name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")

    def _preferred_fallback_model(self, models: list[ModelConfig]) -> ModelConfig:
        for model_id in PREFERRED_LOCAL_MODEL_IDS:
            model = next((item for item in models if item.id == model_id), None)
            if model:
                return model
        local = next((item for item in models if item.provider == "ollama"), None)
        if local:
            return local
        return next((model for model in models if model.id == "fake-llm"), self.fake_model())

    def _get_setting(self, key: str, default: Any = None) -> Any:
        with self._session_factory() as session:
            record = session.get(AppSettingRecord, key)
            if record is None:
                return default
            return json.loads(record.value)

    def _get_bool_setting(self, key: str, default: bool) -> bool:
        return bool(self._get_setting(key, default))

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

    def clear_settings(self) -> None:
        with self._session_factory() as session:
            session.execute(delete(AppSettingRecord))
            session.commit()


model_registry_service = ModelRegistryService()
