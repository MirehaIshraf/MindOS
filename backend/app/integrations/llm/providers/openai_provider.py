import httpx

from app.integrations.llm.providers.base_provider import BaseChatProvider


class OpenAIProvider(BaseChatProvider):
    def __init__(self, api_key: str = "", base_url: str = "https://api.openai.com/v1") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def generate(self, messages: list[dict[str, str]], model_id: str, options: dict | None = None) -> str:
        if not self._api_key:
            raise RuntimeError("OpenAI API key is not configured.")
        payload = {"model": model_id, "messages": messages}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        with httpx.Client(timeout=120) as client:
            response = client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError("OpenAI returned an invalid response.")
        return content

    def health_check(self) -> bool:
        return bool(self._api_key)
