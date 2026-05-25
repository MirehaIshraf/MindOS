import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.integrations.llm.base import LLMClient


class OllamaLLMError(RuntimeError):
    pass


class OllamaLLMClient(LLMClient):
    def __init__(self) -> None:
        self._settings = get_settings()
        self.model = self._settings.ollama_chat_model

    def generate_response(
        self,
        message: str,
        history: list[dict],
        context: Any,
        system_prompt: str | None = None,
    ) -> str:
        messages = self._build_messages(
            message=message,
            history=history,
            formatted_context=str(context or "").strip(),
            system_prompt=system_prompt,
        )
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": self._settings.ollama_num_ctx,
                "think": self._settings.ollama_thinking_mode,
            },
        }
        try:
            with httpx.Client(timeout=self._settings.ollama_timeout_seconds) as client:
                response = client.post(f"{self._base_url()}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise OllamaLLMError("Ollama chat request failed.") from error

        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaLLMError("Ollama returned an invalid chat response.")
        return strip_thinking(content).strip()

    def _build_messages(
        self,
        *,
        message: str,
        history: list[dict],
        formatted_context: str,
        system_prompt: str | None,
    ) -> list[dict[str, str]]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        context_text = formatted_context or "No local memory context was found for this request."
        messages.append({"role": "user", "content": f"Local memory context:\n\n{context_text}"})

        history_limit = self._settings.chat_history_limit
        for item in history[-history_limit:]:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": f"/no_think\n\nUser question: {message}"})
        return messages

    def _base_url(self) -> str:
        return self._settings.ollama_base_url.rstrip("/")


def strip_thinking(content: str) -> str:
    without_tags = re.sub(r"<think>.*?</think>", "", content, flags=re.IGNORECASE | re.DOTALL)
    without_prefix = re.sub(r"(?is)^thinking:.*?(?:\n\n|$)", "", without_tags).strip()
    return without_prefix or content
