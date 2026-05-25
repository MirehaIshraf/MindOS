import httpx

from app.core.config import get_settings
from app.integrations.embeddings.base import EmbeddingClient


class OllamaEmbeddingClient(EmbeddingClient):
    def embed(self, text: str) -> list[float]:
        settings = get_settings()
        base_url = settings.ollama_base_url.rstrip("/")
        payload = {"model": settings.ollama_embed_model, "prompt": text}
        timeout = httpx.Timeout(settings.ollama_timeout_seconds)

        with httpx.Client(timeout=timeout) as client:
            try:
                response = client.post(f"{base_url}/api/embeddings", json=payload)
                response.raise_for_status()
                data = response.json()
                embedding = data.get("embedding")
                if isinstance(embedding, list):
                    return [float(value) for value in embedding]
            except Exception:
                pass

            response = client.post(
                f"{base_url}/api/embed",
                json={"model": settings.ollama_embed_model, "input": text},
            )
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings")
            if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
                return [float(value) for value in embeddings[0]]

        raise RuntimeError("Ollama did not return an embedding.")

    def health_check(self) -> bool:
        try:
            settings = get_settings()
            with httpx.Client(timeout=httpx.Timeout(5.0)) as client:
                response = client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
                response.raise_for_status()
            return True
        except Exception:
            return False
