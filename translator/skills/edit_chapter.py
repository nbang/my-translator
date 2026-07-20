"""Skill: editorial polish of a raw Vietnamese chapter (style pass).

Refactored from step3_edited_translate.py. Reads the rough Vietnamese plus the
Chinese source as reference, applies the per-book EDITOR.md style guide and
glossary, and writes <book>/edited_vietnamese/<file>.

Supports an optional `fix_issues` list so the QA auto-fix loop can re-run the
editor with concrete problems to correct. Uses the "editor" role.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from translator.config import book_root
from translator.llm.roles import chat_as
from translator.skills import glossary as glo
from translator.skills.chapters import read_chapter, render_chapter

logger = logging.getLogger(__name__)

DEFAULT_RULES = "Biên tập lại thành tiếng Việt tự nhiên, mượt mà, đúng văn phong tiểu thuyết."


def _load_editor_rules(book_id: str) -> str:
    path = book_root(book_id) / "EDITOR.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("EDITOR.md not found for %s, using default rules", book_id)
    return DEFAULT_RULES


def _build_user_content(
    ref_zh: str,
    raw_vi: str,
    previous_context: Optional[str],
    fix_issues: Optional[List[str]],
    reterm: bool = False,
) -> str:
    parts = []
    if previous_context:
        # Only a tail of the previous chapter, to keep tokens bounded.
        parts.append(f"## Nội dung chương trước (tham khảo văn phong):\n{previous_context[-1500:]}")
    parts.append(f"## Bản gốc (tiếng Trung):\n{ref_zh}")
    if reterm:
        parts.append(
            "## Bản dịch đã biên tập:\n" + raw_vi + "\n\n"
            "YÊU CẦU: Bản dịch trên đã hoàn chỉnh. CHỈ chuẩn hóa lại thuật ngữ/tên riêng cho "
            "đúng với glossary bắt buộc ở trên và sửa chữ Hán còn sót; GIỮ NGUYÊN câu chữ, "
            "văn phong, cách xuống dòng. Không viết lại, không diễn giải thêm."
        )
    else:
        parts.append(f"## Bản dịch thô (cần biên tập):\n{raw_vi}")
    if fix_issues:
        issues = "\n".join(f"- {i}" for i in fix_issues)
        parts.append(
            "## LỖI CẦN SỬA (bắt buộc khắc phục trong bản biên tập):\n" + issues
        )
    parts.append("Hãy trả về BẢN BIÊN TẬP HOÀN CHỈNH cuối cùng (chỉ nội dung tiếng Việt).")
    return "\n\n".join(parts)


def edit_chapter(args: Dict) -> Dict:
    """Polish one rough Vietnamese chapter into the edited version.

    args: {book_id, chapter_file, force?, previous_context?, fix_issues?}
    """
    book_id = args["book_id"]
    chapter_file = args["chapter_file"]
    force = bool(args.get("force", False))
    previous_context = args.get("previous_context")
    fix_issues = args.get("fix_issues")
    # Which stage to read the base text from. "edited_vietnamese" = re-term an
    # already-polished chapter (preserve prose, only normalize glossary terms).
    input_stage = args.get("input_stage", "raw_vietnamese")
    reterm = input_stage == "edited_vietnamese"

    root = book_root(book_id)
    in_path = root / input_stage / chapter_file
    ref_path = root / "raw_chinese" / chapter_file
    out_path = root / "edited_vietnamese" / chapter_file
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and out_path.stat().st_size > 0 and not force and not fix_issues:
        return {"chapter_file": chapter_file, "status": "skipped"}

    if not in_path.exists():
        return {"chapter_file": chapter_file, "status": "error", "error": f"{input_stage} file missing"}

    raw_doc = read_chapter(in_path)
    ref_zh = read_chapter(ref_path).body if ref_path.exists() else "(không có bản gốc)"

    rules = _load_editor_rules(book_id)
    terms = glo.relevant_terms(ref_zh, glo.load_glossary(book_id))
    system = rules + ("\n\n" + glo.format_glossary_block(terms) if terms else "")

    user = _build_user_content(ref_zh, raw_doc.body, previous_context, fix_issues, reterm=reterm)
    edited_body = chat_as("editor", system, user).strip()

    out_path.write_text(render_chapter(raw_doc.title, edited_body), encoding="utf-8")
    return {"chapter_file": chapter_file, "status": "edited", "fixed": bool(fix_issues)}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "edit_chapter",
        "description": "Editorially polish one rough Vietnamese chapter into publishable prose using "
        "the book's EDITOR.md style guide, glossary, and the Chinese source as reference. "
        "Writes <book>/edited_vietnamese/<chapter_file>.",
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string"},
                "chapter_file": {"type": "string", "description": "e.g. 'chapter_0001.md'."},
                "force": {"type": "boolean"},
                "previous_context": {"type": "string", "description": "Prior edited chapter text for style continuity."},
                "fix_issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "QA issues to correct in a re-edit pass.",
                },
            },
            "required": ["book_id", "chapter_file"],
        },
    },
}
