import httpx

from app.integrations.llm.providers.base_provider import BaseChatProvider


class AnthropicProvider(BaseChatProvider):
    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key

    def generate(self, messages: list[dict[str, str]], model_id: str, options: dict | None = None) -> str:
        if not self._api_key:
            raise RuntimeError("Anthropic API key is not configured.")
        system = "\n\n".join(message["content"] for message in messages if message["role"] == "system")
        user_messages = [message for message in messages if message["role"] != "system"]
        payload = {
            "model": model_id,
            "max_tokens": 2048,
            "system": system,
            "messages": user_messages,
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        with httpx.Client(timeout=120) as client:
            response = client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        parts = data.get("content", [])
        text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))
        if not text.strip():
            raise RuntimeError("Anthropic returned an invalid response.")
        return text

    def health_check(self) -> bool:
        return bool(self._api_key)
