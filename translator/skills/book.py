"""Skill: read/write per-book metadata (book.yaml)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import yaml

from translator.config import book_root

BOOK_FILE = "book.yaml"


def book_info(args: Dict) -> Dict:
    """Return a book's metadata and stage counts (chapters per stage)."""
    book_id = args["book_id"]
    root = book_root(book_id)
    meta = {}
    path = root / BOOK_FILE
    if path.exists():
        meta = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def count(stage: str) -> int:
        d = root / stage
        return len(list(d.glob("chapter_*.md"))) if d.exists() else 0

    return {
        "book_id": book_id,
        "root": str(root),
        "metadata": meta,
        "counts": {
            "raw_chinese": count("raw_chinese"),
            "raw_vietnamese": count("raw_vietnamese"),
            "edited_vietnamese": count("edited_vietnamese"),
        },
    }


SCHEMA = {
    "type": "function",
    "function": {
        "name": "book_info",
        "description": "Return a book's metadata (book.yaml) and how many chapters exist at each stage.",
        "parameters": {
            "type": "object",
            "properties": {"book_id": {"type": "string"}},
            "required": ["book_id"],
        },
    },
}
