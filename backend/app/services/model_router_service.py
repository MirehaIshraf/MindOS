from dataclasses import dataclass

from app.integrations.llm.providers.anthropic_provider import AnthropicProvider
from app.integrations.llm.providers.fake_provider import FakeProvider
from app.integrations.llm.providers.kimi_provider import KimiProvider
from app.integrations.llm.providers.ollama_provider import OllamaProvider
from app.integrations.llm.providers.openai_provider import OpenAIProvider
from app.schemas.models import ModelConfig
from app.services.model_registry_service import model_registry_service


@dataclass
class ModelRouteResult:
    reply: str
    model_used: str
    provider: str
    model_display_name: str
    warning: str | None = None


class ModelRouterService:
    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        requested_model_id: str | None,
        options: dict | None = None,
    ) -> ModelRouteResult:
        model, selection_warning = self._resolve_model(requested_model_id)
        if model and model.id == "fake-llm":
            return self._fake_result(selection_warning, messages, options)
        if model and model.enabled and model.configured and model.available:
            try:
                provider = self._provider_for(model.provider)
                reply = provider.generate(messages=messages, model_id=model.model_id, options=options)
                return ModelRouteResult(
                    reply=reply,
                    model_used=model.model_id,
                    provider=model.provider,
                    model_display_name=model.display_name,
                )
            except Exception:
                return self._fake_result(
                    f"{model.display_name} failed or is unavailable. Falling back to FakeLLM.",
                    messages,
                    options,
                )

        if model:
            return self._fake_result(
                f"{model.display_name} is disabled or not configured. Falling back to FakeLLM.",
                messages,
                options,
            )
        return self._fake_result("Selected chat model was not found. Falling back to FakeLLM.", messages, options)

    def _resolve_model(self, requested_model_id: str | None) -> tuple[ModelConfig | None, str | None]:
        if requested_model_id:
            return model_registry_service.get_model(requested_model_id), None
        return model_registry_service.resolve_selected_chat_model()

    def _provider_for(self, provider_id: str):
        if provider_id == "ollama":
            return OllamaProvider(model_registry_service.get_provider_config_value("ollama", "base_url"))
        if provider_id == "openai":
            return OpenAIProvider(api_key=model_registry_service.get_provider_config_value("openai", "api_key"))
        if provider_id == "anthropic":
            return AnthropicProvider(api_key=model_registry_service.get_provider_config_value("anthropic", "api_key"))
        if provider_id == "kimi":
            return KimiProvider(
                api_key=model_registry_service.get_provider_config_value("kimi", "api_key"),
                base_url=model_registry_service.get_provider_config_value("kimi", "base_url"),
            )
        return FakeProvider()

    def _fake_result(self, warning: str | None, messages: list[dict[str, str]], options: dict | None) -> ModelRouteResult:
        reply = FakeProvider().generate(messages=messages, model_id="fake-llm", options=options)
        return ModelRouteResult(
            reply=reply,
            model_used="fake-llm",
            provider="fake",
            model_display_name="FakeLLM",
            warning=warning or None,
        )


model_router_service = ModelRouterService()
