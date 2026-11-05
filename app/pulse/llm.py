from __future__ import annotations

import requests

from pulse import config

DEFAULT_MODELS = {
    "anthropic": "claude-haiku-5-5",
    "ollama": "qwen2.5-coder:7b",
}


class LLMError(RuntimeError):
    pass


def model_name() -> str:
    if config.LLM_PROVIDER not in DEFAULT_MODELS:
        raise LLMError(f"Unknown LLM_PROVIDER '{config.LLM_PROVIDER}' - use 'anthropic' or 'ollama'.")
    return config.LLM_MODEL or DEFAULT_MODELS[config.LLM_PROVIDER]


def complete(system: str, user: str, max_tokens: int = 1500) -> str:
    model = model_name()
    if config.LLM_PROVIDER == "anthropic":
        return _anthropic(system, user, model, max_tokens)
    return _ollama(system, user, model)


def _anthropic(system: str, user: str, model: str, max_tokens: int) -> str:
    if not config.ANTHROPIC_API_KEY:
        raise LLMError("ANTHROPIC_API_KEY is not set (or switch to LLM_PROVIDER=ollama).")
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIError as exc:
        raise LLMError(f"Anthropic API error: {exc}") from exc
    return "".join(block.text for block in response.content if block.type == "text")


def _ollama(system: str, user: str, model: str) -> str:
    try:
        resp = requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "stream": False,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=300,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise LLMError(f"Ollama error ({config.OLLAMA_URL}): {exc}") from exc
    return resp.json()["message"]["content"]
