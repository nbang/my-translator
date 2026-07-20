"""Structured per-book glossary: load, look up relevant terms, update.

A glossary lives at ``<book>/glossary.yaml``:

    terms:
      - chinese: 江秋秋
        hanviet: Giang Thu Thu
        role: nữ chính        # optional
        note: main character  # optional

This complements the prose ``EDITOR.md`` style guide: the glossary is the
machine-checkable list of names/terms, used both to inject relevant terms into
prompts and to verify compliance in QA.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml

from translator.config import book_root

GLOSSARY_FILE = "glossary.yaml"


def glossary_path(book_id: str) -> Path:
    return book_root(book_id) / GLOSSARY_FILE


def load_glossary(book_id: str) -> List[Dict[str, str]]:
    """Return the list of term dicts for a book (empty if none)."""
    path = glossary_path(book_id)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    terms = data.get("terms", [])
    return [t for t in terms if t.get("chinese") and t.get("hanviet")]


def relevant_terms(source_text: str, terms: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Subset of terms whose Chinese form appears in source_text."""
    return [t for t in terms if t["chinese"] in source_text]


def format_glossary_block(terms: List[Dict[str, str]]) -> str:
    """Render terms as a compact prompt block (Chinese -> Hán Việt [role/note])."""
    if not terms:
        return ""
    lines = ["## THUẬT NGỮ CỐ ĐỊNH (bắt buộc dùng đúng):"]
    for t in terms:
        extra = " — ".join(x for x in (t.get("role"), t.get("note")) if x)
        suffix = f"  ({extra})" if extra else ""
        lines.append(f"- {t['chinese']} → {t['hanviet']}{suffix}")
    return "\n".join(lines)


# --- Skill entry points ------------------------------------------------------


def glossary_lookup(args: Dict) -> Dict:
    """Skill: return glossary terms for a book, optionally only those in a text."""
    book_id = args["book_id"]
    terms = load_glossary(book_id)
    text = args.get("source_text")
    if text:
        terms = relevant_terms(text, terms)
    return {"count": len(terms), "terms": terms}


def glossary_update(args: Dict) -> Dict:
    """Skill: add or update a term in a book's glossary.yaml."""
    book_id = args["book_id"]
    path = glossary_path(book_id)
    data = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    terms: List[Dict[str, str]] = data.get("terms", [])

    entry = {"chinese": args["chinese"], "hanviet": args["hanviet"]}
    for opt in ("role", "note"):
        if args.get(opt):
            entry[opt] = args[opt]

    replaced = False
    for i, t in enumerate(terms):
        if t.get("chinese") == entry["chinese"]:
            terms[i] = entry
            replaced = True
            break
    if not replaced:
        terms.append(entry)

    data["terms"] = terms
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return {"book_id": book_id, "action": "updated" if replaced else "added", "term": entry, "total": len(terms)}


LOOKUP_SCHEMA = {
    "type": "function",
    "function": {
        "name": "glossary_lookup",
        "description": "Look up the fixed Chinese->Vietnamese glossary for a book. "
        "Optionally pass source_text to get only terms that appear in it.",
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book directory id, e.g. '2013956118'."},
                "source_text": {"type": "string", "description": "Optional Chinese text to filter terms by."},
            },
            "required": ["book_id"],
        },
    },
}

UPDATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "glossary_update",
        "description": "Add or update one fixed term in a book's glossary.",
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string"},
                "chinese": {"type": "string", "description": "Original Chinese term/name."},
                "hanviet": {"type": "string", "description": "Mandated Sino-Vietnamese (Hán Việt) rendering."},
                "role": {"type": "string", "description": "Optional role, e.g. 'nữ chính'."},
                "note": {"type": "string", "description": "Optional note."},
            },
            "required": ["book_id", "chinese", "hanviet"],
        },
    },
}
