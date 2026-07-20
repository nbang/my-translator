"""Model-agnostic chat client.

One ``chat()`` entry point with pluggable backends. Everything is plain HTTP via
``requests`` so no heavy SDKs are required and any OpenAI-compatible server
(vLLM, Ollama, LM Studio, OpenAI, DeepSeek, ...) works out of the box.

Backends:
- ``openai``   : POST {base_url}/chat/completions  (Bearer auth)
- ``google``   : Gemini generateContent REST API
- ``anthropic``: Messages API

Retries with backoff live here so callers never re-implement them.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class Endpoint:
    """A resolved provider endpoint."""

    provider: str = "openai"  # openai | google | anthropic
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class LLMError(RuntimeError):
    """Raised when a completion cannot be obtained after all retries."""


def chat(
    system: str,
    user: str,
    *,
    endpoint: Endpoint,
    model: str,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    retries: int = 3,
    timeout: int = 180,
) -> str:
    """Return the assistant text for a single system+user turn.

    Raises ``LLMError`` if all retries fail.
    """
    provider = (endpoint.provider or "openai").lower()
    last_err: Optional[str] = None

    for attempt in range(1, retries + 1):
        try:
            if provider == "google":
                text = _google(system, user, endpoint, model, temperature, max_tokens, timeout)
            elif provider == "anthropic":
                text = _anthropic(system, user, endpoint, model, temperature, max_tokens, timeout)
            else:
                text = _openai(system, user, endpoint, model, temperature, max_tokens, timeout)
            if text is not None and text.strip():
                return text.strip()
            last_err = "empty response"
        except Exception as e:  # noqa: BLE001 - surfaced via LLMError below
            last_err = str(e)
            logger.warning("LLM call failed (attempt %d/%d): %s", attempt, retries, e)

        if attempt < retries:
            time.sleep(2 * attempt)

    raise LLMError(f"{provider}:{model} failed after {retries} attempts: {last_err}")


def _openai(system, user, ep: Endpoint, model, temperature, max_tokens, timeout) -> Optional[str]:
    if not ep.base_url:
        raise LLMError("openai-compatible endpoint requires base_url")
    headers = {"Content-Type": "application/json"}
    if ep.api_key:
        headers["Authorization"] = f"Bearer {ep.api_key}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    resp = requests.post(
        f"{ep.base_url.rstrip('/')}/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"]


def _google(system, user, ep: Endpoint, model, temperature, max_tokens, timeout) -> Optional[str]:
    if not ep.api_key:
        raise LLMError("google endpoint requires api_key")
    base = (ep.base_url or "https://generativelanguage.googleapis.com").rstrip("/")
    url = f"{base}/v1beta/models/{model}:generateContent?key={ep.api_key}"
    gen_cfg = {"temperature": temperature}
    if max_tokens:
        gen_cfg["maxOutputTokens"] = max_tokens
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user}]}],
        "generationConfig": gen_cfg,
    }
    resp = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise LLMError(f"no candidates: {str(data)[:300]}")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def _anthropic(system, user, ep: Endpoint, model, temperature, max_tokens, timeout) -> Optional[str]:
    if not ep.api_key:
        raise LLMError("anthropic endpoint requires api_key")
    base = (ep.base_url or "https://api.anthropic.com").rstrip("/")
    payload = {
        "model": model,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens or 8192,
    }
    headers = {
        "x-api-key": ep.api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    resp = requests.post(f"{base}/v1/messages", headers=headers, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    blocks = resp.json().get("content", [])
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
