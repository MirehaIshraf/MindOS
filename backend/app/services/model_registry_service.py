import json
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

MODEL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "ollama-llama3.2",
        "provider": "ollama",
        "display_name": "Llama 3.2 Local",
        "model_id": "llama3.2",
        "type": "local",
        "privacy_level": "local_private",
        "description": "Fast local general model.",
    },
    {
        "id": "ollama-qwen3",
        "provider": "ollama",
        "display_name": "Qwen 3 Local",
        "model_id": "qwen3:8b",
        "type": "local",
        "privacy_level": "local_private",
        "description": "Local reasoning/code model.",
    },
    {
        "id": "ollama-mistral",
        "provider": "ollama",
        "display_name": "Mistral Local",
        "model_id": "mistral",
        "type": "local",
        "privacy_level": "local_private",
        "description": "Lightweight local chat model.",
    },
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

    def get_settings_response(self) -> ModelSettingsResponse:
        return ModelSettingsResponse(
            providers=self.list_providers(),
            models=self.list_models(),
            selected_chat_model=self.get_selected_chat_model(),
        )

    def get_chat_models_response(self) -> ChatModelsResponse:
        models = self.list_chat_models()
        selected, warning = self.resolve_selected_chat_model(models)
        return ChatModelsResponse(models=models, selected_chat_model=selected.id, warning=warning)

    def list_chat_models(self) -> list[ModelConfig]:
        models = [self.fake_model()]
        models.extend(
            model
            for model in self.list_models()
            if model.enabled and model.configured and model.available and self._provider_enabled(model.provider)
        )
        return models

    def list_models(self) -> list[ModelConfig]:
        ollama_models = self._ollama_models()
        return [self._to_model(definition, ollama_models) for definition in MODEL_DEFINITIONS]

    def list_providers(self) -> list[ModelProvider]:
        provider_status = self.provider_status()
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

    def provider_status(self) -> dict[str, dict[str, object]]:
        ollama_available = self._provider_healthy("ollama")
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
        fallback = next((model for model in available_models if model.id == "fake-llm"), self.fake_model())
        return fallback, "Selected model unavailable. Falling back to FakeLLM."

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
