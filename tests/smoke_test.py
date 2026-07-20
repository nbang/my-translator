#!/usr/bin/env python3
"""Offline smoke tests — no LLM/network required.

Run:  python tests/smoke_test.py
Exercises chapter parsing, paragraph chunking, glossary loading, the tool
registry, and QA's deterministic checks (good vs. bad chapter).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from translator.skills import TOOL_REGISTRY, tool_schemas  # noqa: E402
from translator.skills.chapters import chunk_paragraphs, read_chapter  # noqa: E402
from translator.skills.glossary import load_glossary  # noqa: E402
from translator.skills.qa_chapter import qa_chapter  # noqa: E402

BOOK = "bqg/biqu59096"
GOOD = "chapter_0001.md"

passed = 0
failed = 0


def check(name: str, cond: bool) -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name}")


def main() -> int:
    # Registry / schemas
    check("registry has 7 tools", len(TOOL_REGISTRY) == 7)
    check("all schemas are function defs", all(s.get("type") == "function" for s in tool_schemas()))

    # Chapter parsing
    zh = read_chapter(REPO_ROOT / BOOK / "raw_chinese" / GOOD)
    check("zh body has CJK", zh.has_cjk_body())
    vi = read_chapter(REPO_ROOT / BOOK / "edited_vietnamese" / GOOD)
    check("vi title starts with Chương", vi.title.startswith("Chương"))
    check("vi body has no CJK", not vi.has_cjk_body())

    # Chunking respects the limit
    chunks = chunk_paragraphs("a\n\n" * 50 + ("x" * 100), max_chars=120)
    check("chunking splits >max_chars", len(chunks) > 1)

    # Glossary
    check("biqu glossary loads terms", len(load_glossary(BOOK)) >= 1)

    # QA mechanics (corpus-independent): craft (source, output) pairs and run
    # the deterministic checks directly, so the test doesn't depend on whether a
    # historical chapter happens to match the current glossary.
    from translator.skills.qa_chapter import _deterministic_checks

    good = _deterministic_checks(
        BOOK,
        ref_zh="你好，江秋秋！“今天吃什么？”",
        edited_vi='"Hôm nay ăn gì?" Giang Thu Thu mỉm cười.',
        raw_vi="Giang Thu Thu cười.",
    )
    check("QA clean on compliant input", good == [])

    bad = _deterministic_checks(
        BOOK,
        ref_zh="你好，江秋秋！",
        edited_vi="Chào Jiang Qiuqiu.\n还有中文没翻译。",  # wrong name + residual CJK
        raw_vi="Chào Giang Thu Thu, một đoạn văn dài hơn nhiều để so sánh độ dài.",
    )
    check("QA flags residual CJK + glossary miss", len(bad) >= 2)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
