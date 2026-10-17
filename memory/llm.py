"""Thin Ollama client: schema-constrained chat output and embeddings."""
import json

import httpx

from memory.config import settings


class LLMError(RuntimeError):
    """The model was unreachable or answered with something unusable. Safe to retry later."""


def chat_json(system: str, user: str, schema: dict, model: str | None = None) -> dict:
    """Ask the model for JSON that matches `schema` (Ollama structured outputs)."""
    try:
        r = httpx.post(
            f"{settings.ollama_url}/api/chat",
            json={
                "model": model or settings.extract_model,
                "stream": False,
                "format": schema,
                "options": {"temperature": 0, "num_thread": settings.extract_threads},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
            timeout=300,
        )
        r.raise_for_status()
        out = json.loads(r.json()["message"]["content"])
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        raise LLMError(f"chat failed: {e}") from e
    if not isinstance(out, dict):
        raise LLMError(f"chat returned {type(out).__name__}, expected an object")
    return out


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        r = httpx.post(
            f"{settings.ollama_url}/api/embed",
            json={"model": settings.embed_model, "input": texts},
            timeout=120,
        )
        r.raise_for_status()
        vectors = r.json()["embeddings"]
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        raise LLMError(f"embed failed: {e}") from e
    if len(vectors) != len(texts):
        raise LLMError(f"embed returned {len(vectors)} vectors for {len(texts)} texts")
    return vectors
