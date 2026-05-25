import re

import httpx

from app.core.config import get_settings
from app.integrations.llm.providers.base_provider import BaseChatProvider


class OllamaProvider(BaseChatProvider):
    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._timeout = settings.ollama_timeout_seconds
        self._num_ctx = settings.ollama_num_ctx
        self._think = settings.ollama_thinking_mode

    def generate(self, messages: list[dict[str, str]], model_id: str, options: dict | None = None) -> str:
        payload = {
            "model": model_id,
            "messages": self._with_no_think(messages, model_id),
            "stream": False,
            "options": {"num_ctx": self._num_ctx, "think": self._think},
        }
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        content = data.get("message", {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError("Ollama returned an invalid response.")
        return content

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[str]:
        with httpx.Client(timeout=5) as client:
            response = client.get(f"{self._base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
        return [model["name"] for model in data.get("models", []) if isinstance(model, dict) and model.get("name")]

    def _with_no_think(self, messages: list[dict[str, str]], model_id: str) -> list[dict[str, str]]:
        if not re.search(r"qwen", model_id, re.IGNORECASE):
            return messages
        updated = [dict(message) for message in messages]
        if updated:
            updated[0]["content"] = "/no_think\n\n" + updated[0]["content"].replace("/no_think", "").strip()
            updated[-1]["content"] = "/no_think\n\n" + updated[-1]["content"].replace("/no_think", "").strip()
        return updated
