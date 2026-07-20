"""Skill: faithful LLM translation Chinese -> Vietnamese (fidelity pass).

Replaces the old Google-Translate step. Reads <book>/raw_chinese/<file>, strips
the markdown scaffolding, translates the title and body (paragraph-chunked) with
the book glossary injected, and writes <book>/raw_vietnamese/<file>.

Uses the "translator" role, so which model runs it is a config choice.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

from translator.config import book_root, load_config
from translator.llm.roles import chat_as
from translator.skills import glossary as glo
from translator.skills.chapters import chunk_paragraphs, read_chapter, render_chapter

logger = logging.getLogger(__name__)

BASE_RULES = """Bạn là một chuyên gia dịch thuật Trung-Việt, chuyên về tiểu thuyết mạng.
Dịch văn bản tiếng Trung sang tiếng Việt (bản dịch chính xác, trung thành).

QUY TẮC BẮT BUỘC:
1. Độ chính xác: Dịch sát nghĩa gốc. TUYỆT ĐỐI không tóm tắt, không cắt bớt, không thêm nội dung.
2. Tên riêng & thuật ngữ: Chuyển tên người/địa danh/chiêu thức/tông môn sang âm Hán Việt và VIẾT HOA chữ cái đầu (ví dụ: "Giang Thu Thu", "Mặc Tư"). KHÔNG dịch nghĩa đen tên riêng (không dịch "Lâm Phong" thành "Gió Rừng").
3. Cấu trúc: Giữ nguyên cách phân đoạn/xuống dòng như bản gốc.
4. CHỈ trả về bản dịch tiếng Việt, không kèm giải thích, không kèm bản gốc."""


def _load_translator_rules() -> str:
    """Base rules: repo TRANSLATOR.md if present, else the built-in default."""
    from translator.config import REPO_ROOT

    path = REPO_ROOT / "TRANSLATOR.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return BASE_RULES


def translate_chapter(args: Dict) -> Dict:
    """Translate one raw Chinese chapter to raw Vietnamese.

    args: {book_id, chapter_file, force?}
    """
    book_id = args["book_id"]
    chapter_file = args["chapter_file"]
    force = bool(args.get("force", False))

    root = book_root(book_id)
    in_path = root / "raw_chinese" / chapter_file
    out_path = root / "raw_vietnamese" / chapter_file
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and out_path.stat().st_size > 0 and not force:
        return {"chapter_file": chapter_file, "status": "skipped"}

    if not in_path.exists():
        return {"chapter_file": chapter_file, "status": "error", "error": "raw_chinese file missing"}

    doc = read_chapter(in_path)
    base_rules = _load_translator_rules()
    terms = glo.load_glossary(book_id)
    max_chars = int(load_config().get("pipeline", {}).get("chunk_chars", 4000))

    # Translate the title (usually short).
    title_vi = doc.title
    if doc.title and doc.title != "Untitled":
        title_terms = glo.relevant_terms(doc.title, terms)
        system = base_rules + ("\n\n" + glo.format_glossary_block(title_terms) if title_terms else "")
        title_vi = chat_as("translator", system, f"Dịch tiêu đề chương sau:\n{doc.title}").strip()

    # Translate the body chunk by chunk, injecting only relevant glossary terms.
    chunks = chunk_paragraphs(doc.body, max_chars=max_chars)
    translated = []
    for idx, chunk in enumerate(chunks, 1):
        chunk_terms = glo.relevant_terms(chunk, terms)
        system = base_rules + ("\n\n" + glo.format_glossary_block(chunk_terms) if chunk_terms else "")
        translated.append(chat_as("translator", system, chunk).strip())
        logger.info("translated chunk %d/%d of %s", idx, len(chunks), chapter_file)

    body_vi = "\n\n".join(translated)
    out_path.write_text(render_chapter(title_vi, body_vi), encoding="utf-8")
    return {"chapter_file": chapter_file, "status": "translated", "chunks": len(chunks)}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "translate_chapter",
        "description": "Faithfully translate one raw Chinese chapter to Vietnamese (fidelity pass) "
        "using an LLM and the book glossary. Writes <book>/raw_vietnamese/<chapter_file>.",
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string"},
                "chapter_file": {"type": "string", "description": "e.g. 'chapter_0001.md'."},
                "force": {"type": "boolean", "description": "Re-translate even if output exists."},
            },
            "required": ["book_id", "chapter_file"],
        },
    },
}
