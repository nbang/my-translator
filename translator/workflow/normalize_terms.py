#!/usr/bin/env python3
"""Apply SAFE, distinctive term replacements to a book's edited chapters.

For normalizing an established glossary term across already-translated chapters
WITHOUT an LLM — only for renderings that are distinctive enough to replace
without collateral damage. Ambiguous terms (that collide with ordinary words)
must be handled by an LLM re-edit instead, not here.

Usage:
    python -m translator.workflow.normalize_terms <book_id> [--apply]
Without --apply it does a dry run (counts only).
"""

from __future__ import annotations

import argparse
import sys

from translator.config import book_root

# Per-book safe replacement maps: {book_id: {old_rendering: new_rendering}}.
# Only distinctive strings — never substrings that occur as ordinary words.
SAFE_MAPS = {
    "bqg/2013956118": {
        # 星网 -> Mạng liên tinh (both prior renderings are distinctive)
        "Mạng Tinh Tế": "Mạng liên tinh",
        "Tinh Võng": "Mạng liên tinh",
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_id")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = ap.parse_args()

    repl = SAFE_MAPS.get(args.book_id)
    if not repl:
        sys.exit(f"No safe replacement map defined for '{args.book_id}'")

    edited = book_root(args.book_id) / "edited_vietnamese"
    files = sorted(edited.glob("chapter_*.md"))
    total_files = 0
    total_hits = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        hits = sum(text.count(old) for old in repl)
        if not hits:
            continue
        total_files += 1
        total_hits += hits
        if args.apply:
            for old, new in repl.items():
                text = text.replace(old, new)
            f.write_text(text, encoding="utf-8")

    verb = "Replaced" if args.apply else "Would replace"
    print(f"{verb} {total_hits} occurrence(s) across {total_files} chapter(s).")
    for old, new in repl.items():
        print(f"  '{old}' -> '{new}'")
    if not args.apply:
        print("\n(dry run — re-run with --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
