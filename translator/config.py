"""Configuration loading.

Merges three sources (highest precedence last):
1. Built-in defaults
2. config.yaml at the repo root (or $TRANSLATOR_CONFIG)
3. Environment variables / .env (for secrets and quick overrides)

``${VAR}`` placeholders inside config.yaml are expanded from the environment,
so secrets never live in the committed file.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG: Dict[str, Any] = {
    # Where per-book directories live. Books may also be referenced by an
    # absolute/relative path directly.
    "books_dir": ".",
    "endpoints": {
        # An OpenAI-compatible endpoint (vLLM / Ollama / OpenAI / DeepSeek ...).
        "local": {
            "provider": "openai",
            "base_url": "${LLM_API_BASE}",
            "api_key": "${LLM_API_KEY}",
        },
    },
    # role -> which endpoint + model + sampling to use.
    "roles": {
        "translator": {"endpoint": "local", "model": "${LLM_MODEL}", "temperature": 0.25},
        "editor": {"endpoint": "local", "model": "${LLM_MODEL}", "temperature": 0.5},
        "critic": {"endpoint": "local", "model": "${LLM_MODEL}", "temperature": 0.3},
        "glossary": {"endpoint": "local", "model": "${LLM_MODEL}", "temperature": 0.1},
    },
    "pipeline": {
        "chunk_chars": 4000,
        "max_fix_attempts": 2,
        "request_delay_s": 1.0,
    },
}

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand(value: Any) -> Any:
    """Recursively expand ${ENV_VAR} placeholders in strings."""
    if isinstance(value, str):
        def repl(m: "re.Match[str]") -> str:
            return os.getenv(m.group(1), "")
        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """Load and cache the merged, env-expanded config."""
    config_path = Path(os.getenv("TRANSLATOR_CONFIG", REPO_ROOT / "config.yaml"))
    merged = dict(DEFAULT_CONFIG)
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        merged = _deep_merge(merged, user_cfg)
    return _expand(merged)


def book_root(book_id: str) -> Path:
    """Resolve a book id (e.g. '2013956118' or '52shuku/bjXRF') to a directory."""
    p = Path(book_id)
    if p.is_absolute() or p.exists():
        return p
    return REPO_ROOT / load_config().get("books_dir", ".") / book_id
