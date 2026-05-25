import httpx

from app.core.config import get_settings

OLLAMA_FALLBACK_WARNING = "Ollama is unavailable. Falling back to FakeLLM."


class ModelRuntimeService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def check_ollama_available(self) -> bool:
        try:
            self.list_models()
            return True
        except RuntimeError:
            return False

    def list_models(self) -> list[str]:
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self._base_url()}/api/tags")
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError("Ollama is unavailable.") from error

        models = data.get("models", [])
        if not isinstance(models, list):
            return []
        names = []
        for model in models:
            if isinstance(model, dict) and isinstance(model.get("name"), str):
                names.append(model["name"])
        return names

    def is_model_available(self, model_name: str) -> bool:
        return model_name in self.list_models()

    def active_llm_name(self) -> str:
        if self._settings.enable_local_llm:
            try:
                if self.is_model_available(self._settings.ollama_chat_model):
                    return self._settings.ollama_chat_model
            except RuntimeError:
                return "fake-llm"
        return "fake-llm"

    def get_status(self) -> dict[str, object]:
        models: list[str] = []
        ollama_available = False
        model_available = False
        if self._settings.enable_local_llm:
            try:
                models = self.list_models()
                ollama_available = True
                model_available = self._settings.ollama_chat_model in models
            except RuntimeError:
                models = []
        return {
            "local_llm_enabled": self._settings.enable_local_llm,
            "ollama_available": ollama_available,
            "chat_model": self._settings.ollama_chat_model,
            "active_llm": self._settings.ollama_chat_model if self._settings.enable_local_llm and model_available else "fake-llm",
            "ollama_models": models,
            "ollama_num_ctx": self._settings.ollama_num_ctx,
            "chat_context_direct_limit": self._settings.chat_context_direct_limit,
            "chat_context_related_per_event": self._settings.chat_context_related_per_event,
            "chat_context_max_total_chars": self._settings.chat_context_max_total_chars,
            "chat_history_limit": self._settings.chat_history_limit,
        }

    def _base_url(self) -> str:
        return self._settings.ollama_base_url.rstrip("/")


model_runtime_service = ModelRuntimeService()
