"""Role -> model routing.

Skills ask for a *role* ("translator", "editor", "critic"); config decides which
endpoint/model/temperature that role maps to. Swapping providers is a config edit,
never a code change.
"""

from __future__ import annotations

from typing import Optional

from translator.config import load_config
from translator.llm.provider import Endpoint, LLMError, chat


def _resolve(role: str) -> tuple[Endpoint, str, float]:
    cfg = load_config()
    roles = cfg.get("roles", {})
    if role not in roles:
        raise LLMError(f"role '{role}' not defined in config.roles")
    rc = roles[role]

    endpoints = cfg.get("endpoints", {})
    ep_name = rc.get("endpoint")
    if ep_name not in endpoints:
        raise LLMError(f"endpoint '{ep_name}' for role '{role}' not defined in config.endpoints")
    ec = endpoints[ep_name]

    endpoint = Endpoint(
        provider=ec.get("provider", "openai"),
        base_url=ec.get("base_url") or None,
        api_key=ec.get("api_key") or None,
    )
    model = rc.get("model") or ""
    if not model:
        raise LLMError(f"role '{role}' has no model configured")
    temperature = float(rc.get("temperature", 0.3))
    return endpoint, model, temperature


def chat_as(
    role: str,
    system: str,
    user: str,
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Run a chat turn using whichever model `role` is bound to in config."""
    endpoint, model, role_temp = _resolve(role)
    return chat(
        system,
        user,
        endpoint=endpoint,
        model=model,
        temperature=role_temp if temperature is None else temperature,
        max_tokens=max_tokens,
    )
