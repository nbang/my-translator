#!/usr/bin/env python3
"""Validate every book's book.yaml and glossary.yaml.

Checks required fields, valid UTF-8 YAML, and that glossary terms are well-formed
Chinese -> Hán Việt pairs. Run: python -m translator.workflow.validate_books
"""

from __future__ import annotations

import re

import yaml

from translator.config import REPO_ROOT

CJK = re.compile(r"[一-鿿]")

BOOKS = [
    "bqg/2013956118",
    "52shuku/bjM9n",
    "52shuku/bjRVf",
    "52shuku/bjVQW",
    "52shuku/bjXRF",
    "52shuku/bjYhv",
    "52shuku/bkadd",
    "52shuku/bkbRR",
    "52shuku/bkbmS",
]

REQUIRED = ["identifier", "source", "title", "creator", "translation", "status", "description", "subjects"]


def _first(meta):
    return meta[0] if isinstance(meta, list) else meta


def check_book(book: str) -> list[str]:
    errs: list[str] = []
    root = REPO_ROOT / book

    by = root / "book.yaml"
    if not by.exists():
        errs.append("book.yaml missing")
    else:
        try:
            m = _first(yaml.safe_load(by.read_text(encoding="utf-8")))
            for f in REQUIRED:
                if not m.get(f):
                    errs.append(f"book.yaml: empty/missing '{f}'")
            tr = m.get("translation", {}) or {}
            if not tr.get("translated_title"):
                errs.append("book.yaml: missing translated_title")
        except Exception as e:  # noqa: BLE001
            errs.append(f"book.yaml: YAML error {e}")

    gy = root / "glossary.yaml"
    if not gy.exists():
        errs.append("glossary.yaml missing")
    else:
        try:
            data = yaml.safe_load(gy.read_text(encoding="utf-8")) or {}
            terms = data.get("terms", [])
            if not terms:
                errs.append("glossary.yaml: no terms")
            for t in terms:
                if not t.get("chinese") or not CJK.search(t["chinese"]):
                    errs.append(f"glossary: term missing/non-CJK chinese: {t}")
                if not t.get("hanviet") or CJK.search(t.get("hanviet", "")):
                    errs.append(f"glossary: bad hanviet: {t}")
        except Exception as e:  # noqa: BLE001
            errs.append(f"glossary.yaml: YAML error {e}")
    return errs


def main() -> int:
    total_err = 0
    for book in BOOKS:
        errs = check_book(book)
        if errs:
            total_err += len(errs)
            print(f"✗ {book}")
            for e in errs:
                print(f"    - {e}")
        else:
            gy = yaml.safe_load((REPO_ROOT / book / "glossary.yaml").read_text(encoding="utf-8"))
            print(f"✓ {book}  ({len(gy.get('terms', []))} glossary terms)")
    print(f"\n{'ALL VALID' if total_err == 0 else f'{total_err} problem(s)'}")
    return 1 if total_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
