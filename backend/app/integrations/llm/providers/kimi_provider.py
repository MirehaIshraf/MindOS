import httpx

from app.integrations.llm.providers.base_provider import BaseChatProvider


class KimiProvider(BaseChatProvider):
    def __init__(self, api_key: str = "", base_url: str = "") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def generate(self, messages: list[dict[str, str]], model_id: str, options: dict | None = None) -> str:
        if not self._api_key or not self._base_url:
            raise RuntimeError("Kimi API key or base URL is not configured.")
        payload = {"model": model_id, "messages": messages}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        with httpx.Client(timeout=120) as client:
            response = client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError("Kimi returned an invalid response.")
        return content

    def health_check(self) -> bool:
        return bool(self._api_key and self._base_url)
