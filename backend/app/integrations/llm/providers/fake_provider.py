from app.integrations.llm.fake_llm import FakeLLMClient
from app.integrations.llm.providers.base_provider import BaseChatProvider


class FakeProvider(BaseChatProvider):
    def __init__(self) -> None:
        self._client = FakeLLMClient()

    def generate(self, messages: list[dict[str, str]], model_id: str, options: dict | None = None) -> str:
        options = options or {}
        user_message = next((message["content"] for message in reversed(messages) if message["role"] == "user"), "")
        return self._client.generate_response(
            message=user_message,
            history=messages,
            context=options.get("context_package"),
            system_prompt=messages[0]["content"] if messages else None,
        )

    def health_check(self) -> bool:
        return True
