"""Skills = reusable, schema-described translation tools.

Each skill is a plain ``fn(args: dict) -> dict`` plus a JSON-Schema tool
definition. ``TOOL_REGISTRY`` maps tool name -> (schema, callable) and is the
single source of truth consumed by the pipeline runner today and, later, by any
agent-framework adapter (e.g. Hermes Agent).
"""

from __future__ import annotations

from typing import Callable, Dict, Tuple

from translator.skills import book, edit_chapter, glossary, qa_chapter, scrape_chapters, translate_chapter

# name -> (json-schema tool def, callable)
TOOL_REGISTRY: Dict[str, Tuple[dict, Callable[[dict], dict]]] = {
    "scrape_chapters": (scrape_chapters.SCHEMA, scrape_chapters.scrape_chapters),
    "translate_chapter": (translate_chapter.SCHEMA, translate_chapter.translate_chapter),
    "edit_chapter": (edit_chapter.SCHEMA, edit_chapter.edit_chapter),
    "qa_chapter": (qa_chapter.SCHEMA, qa_chapter.qa_chapter),
    "glossary_lookup": (glossary.LOOKUP_SCHEMA, glossary.glossary_lookup),
    "glossary_update": (glossary.UPDATE_SCHEMA, glossary.glossary_update),
    "book_info": (book.SCHEMA, book.book_info),
}


def tool_schemas() -> list[dict]:
    """All tool schemas, in the OpenAI/Hermes `tools` array shape."""
    return [schema for schema, _ in TOOL_REGISTRY.values()]


def call_tool(name: str, args: dict) -> dict:
    """Dispatch a tool call by name."""
    if name not in TOOL_REGISTRY:
        raise KeyError(f"unknown tool: {name}")
    _, fn = TOOL_REGISTRY[name]
    return fn(args)
