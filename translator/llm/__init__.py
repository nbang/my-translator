"""Model-agnostic LLM access."""

from translator.llm.provider import chat
from translator.llm.roles import chat_as

__all__ = ["chat", "chat_as"]
