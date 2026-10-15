import json
import urllib.error
import urllib.request
from typing import Any

from app.config import config


def _request_json(url: str, payload: dict[str, Any] | None = None, method: str = "POST", timeout: int | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout or config.request_timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP error for {url}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach Ollama at {config.ollama_base_url}: {error.reason}") from error
    except TimeoutError as error:
        raise RuntimeError(f"Ollama request to {url} timed out after {config.request_timeout_seconds} seconds.") from error

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Ollama returned invalid JSON from {url}.") from error
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Ollama returned a non-object response from {url}.")
    return parsed


def list_available_models() -> list[str]:
    response = _request_json(f"{config.ollama_base_url}/api/tags", method="GET")
    models = response.get("models") or []
    return [str(model.get("name", "")) for model in models if isinstance(model, dict) and model.get("name")]


def check_model_available(model_name: str | None = None) -> str:
    model = model_name or config.ollama_chat_model
    available = list_available_models()
    if model not in available:
        raise RuntimeError(f"Ollama model '{model}' is not installed. Run: ollama pull {model}")
    return model


def generate_text(prompt: str, *, system_prompt: str = "You are a helpful assistant.", model: str | None = None, max_tokens: int = 384) -> str:
    if not prompt or not str(prompt).strip():
        raise ValueError("Prompt must not be empty.")
    payload = {
        "model": model or config.ollama_chat_model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0, "num_predict": max_tokens},
    }
    response = _request_json(f"{config.ollama_base_url}/api/chat", payload)
    message = response.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama returned an empty chat response.")
    return content.strip()


def generate_structured(prompt: str, schema: dict, *, system_prompt: str = "Return valid JSON only.", model: str | None = None, max_tokens: int = 384) -> dict:
    payload = {
        "model": model or config.ollama_chat_model,
        "stream": False,
        "format": schema,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0, "num_predict": max_tokens},
    }
    response = _request_json(f"{config.ollama_base_url}/api/chat", payload)
    message = response.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama returned an empty structured chat response.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError("Ollama returned malformed JSON for a structured response.") from error
    if not isinstance(parsed, dict):
        raise RuntimeError("Ollama structured response was not a JSON object.")
    return parsed


def generate_embedding(text: str, *, model: str | None = None) -> list[float]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Embedding input text cannot be empty.")
    payload = {"model": model or config.ollama_embedding_model, "input": text}
    response = _request_json(f"{config.ollama_base_url}/api/embed", payload)
    embeddings = response.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings:
        raise RuntimeError("Ollama returned no embeddings.")
    vector = embeddings[0] if isinstance(embeddings[0], list) else embeddings
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("Ollama returned an empty embedding vector.")
    return [float(value) for value in vector]


def generate_embeddings(texts: list[str], *, model: str | None = None) -> list[list[float]]:
    if not texts:
        return []
    cleaned = [str(text).strip() for text in texts if str(text).strip()]
    if not cleaned:
        raise ValueError("No non-empty text values were supplied for embedding.")
    payload = {"model": model or config.ollama_embedding_model, "input": cleaned}
    response = _request_json(f"{config.ollama_base_url}/api/embed", payload)
    embeddings = response.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(cleaned):
        raise RuntimeError("Ollama returned an invalid embedding batch.")
    result: list[list[float]] = []
    for vector in embeddings:
        if not isinstance(vector, list) or not vector:
            raise RuntimeError("Ollama returned an empty embedding vector.")
        result.append([float(value) for value in vector])
    return result
