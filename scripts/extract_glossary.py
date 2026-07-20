#!/usr/bin/env python3
"""Seed a book's glossary.yaml from its EDITOR.md.

Extracts Chinese -> Hán Việt term pairs from two common patterns:
1. Markdown glossary tables:  |**中文**|Dịch cố định|Ghi chú|
2. Character rosters in prose:  Thẩm Thiển (沈浅) — ...   (HánViệt (中文))

The result is a starting point; refine by hand or via the glossary_update skill.

Usage:  python scripts/extract_glossary.py <book_id> [--print]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from translator.config import book_root  # noqa: E402

CJK = r"[一-鿿㐀-䶿]"
ROSTER_RE = re.compile(rf"([A-ZÀ-Ỹ][A-Za-zÀ-ỹ]*(?:\s+[A-ZÀ-Ỹ][A-Za-zÀ-ỹ]*)*)\s*[（(]\s*({CJK}+)\s*[）)]")


def _clean(cell: str) -> str:
    return cell.replace("*", "").strip()


def extract(editor_md: str) -> list[dict]:
    terms: dict[str, dict] = {}

    # Pattern 1: markdown table rows with a CJK first column.
    for line in editor_md.splitlines():
        if "|" not in line:
            continue
        cells = [c for c in line.split("|")]
        cells = [_clean(c) for c in cells if c.strip() != ""]
        if len(cells) < 2:
            continue
        chinese, hanviet = cells[0], cells[1]
        if re.search(CJK, chinese) and hanviet and not re.fullmatch(r"-{2,}", hanviet):
            terms.setdefault(chinese, {"chinese": chinese, "hanviet": hanviet})
            if len(cells) >= 3 and cells[2]:
                terms[chinese].setdefault("note", cells[2])

    # Pattern 2: prose rosters "HánViệt (中文)".
    for m in ROSTER_RE.finditer(editor_md):
        hanviet, chinese = m.group(1), m.group(2).strip()
        # The Vietnamese-uppercase Unicode range also matches some lowercase
        # letters, so a match can grab a trailing fragment of the previous word.
        # Keep only the last line and drop a stray leading lowercase token.
        hanviet = hanviet.split("\n")[-1].strip()
        hanviet = re.sub(r"^[a-zà-ỹ]+\s+", "", hanviet).strip()
        if hanviet:
            terms.setdefault(chinese, {"chinese": chinese, "hanviet": hanviet})

    return list(terms.values())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_id")
    ap.add_argument("--print", action="store_true", help="Print result instead of writing.")
    args = ap.parse_args()

    root = book_root(args.book_id)
    editor_path = root / "EDITOR.md"
    if not editor_path.exists():
        sys.exit(f"No EDITOR.md at {editor_path}")

    terms = extract(editor_path.read_text(encoding="utf-8"))
    doc = {"terms": terms}
    out = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)

    if args.print:
        print(out)
        return
    (root / "glossary.yaml").write_text(out, encoding="utf-8")
    print(f"Wrote {len(terms)} terms to {root / 'glossary.yaml'}")


if __name__ == "__main__":
    main()
