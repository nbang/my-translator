#!/usr/bin/env python3
"""Build a book's glossary.yaml by reading its first few raw Chinese chapters.

The new-workflow way to seed a glossary: instead of scraping an existing
EDITOR.md, this sends the first N (default 5) raw Chinese chapters to the LLM and
asks it to extract proper nouns — character/place/sect/technique/item names — as
``chinese -> hanviet`` (Sino-Vietnamese / Hán Việt) pairs. The result is *merged*
into ``<book>/glossary.yaml``: existing (human-curated) terms are preserved.

Which model runs the extraction is a config choice — the "glossary" role in
config.yaml (low temperature by default). See translator/config.py.

Usage:
    python -m translator.workflow.extract_glossary <book_id> [--chapters N] [--print] [--force]

    <book_id>       e.g. bqg/biqu59096 or 52shuku/bjXRF
    --chapters N    how many leading chapters to read (default 5)
    --print         print the merged glossary instead of writing it (dry run)
    --force         overwrite the hanviet of terms already in glossary.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from typing import Dict, List

import yaml

from translator.config import book_root
from translator.llm.provider import LLMError
from translator.llm.roles import chat_as
from translator.skills.chapters import read_chapter
from translator.skills.glossary import glossary_path, load_glossary

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("extract_glossary")

# Cap total Chinese text sent in one call, to stay within smaller local models'
# context windows. First-chapters extraction rarely needs more.
MAX_INPUT_CHARS = 40000

SYSTEM_PROMPT = """Bạn là chuyên gia dịch thuật Trung-Việt, đang xây dựng bảng thuật ngữ (glossary) cho một bộ tiểu thuyết mạng.

Nhiệm vụ: Từ đoạn văn tiếng Trung được cung cấp, TRÍCH XUẤT các DANH TỪ RIÊNG cần thống nhất cách dịch, gồm:
- Tên nhân vật (người)
- Địa danh (nơi chốn, tinh cầu, quốc gia...)
- Tổ chức / thế lực / tông môn / gia tộc
- Chiêu thức / công pháp / kỹ năng
- Vật phẩm / bảo vật / danh hiệu / chức vị quan trọng

QUY TẮC:
1. Với mỗi thuật ngữ, cung cấp chữ Hán gốc và cách đọc ÂM HÁN VIỆT, VIẾT HOA chữ cái đầu mỗi âm tiết (ví dụ: 江秋秋 → "Giang Thu Thu", 星网 → "Tinh Võng").
2. TUYỆT ĐỐI không dịch nghĩa đen tên riêng (không dịch 林风 thành "Gió Rừng"; phải là "Lâm Phong").
3. Bỏ qua các danh từ chung, đại từ, từ thông dụng. CHỈ lấy danh từ riêng đáng đưa vào glossary.
4. Gộp các biến thể của cùng một thực thể thành một mục (dùng dạng đầy đủ nhất).

ĐỊNH DẠNG ĐẦU RA: CHỈ trả về một mảng JSON hợp lệ, không kèm giải thích, không kèm markdown. Mỗi phần tử:
{"chinese": "<chữ Hán>", "hanviet": "<âm Hán Việt>", "category": "<nhân vật|địa danh|tổ chức|chiêu thức|vật phẩm|khác>", "note": "<ghi chú ngắn, có thể để trống>"}"""


def _leading_chapters(book_id: str, count: int) -> List[str]:
    raw_dir = book_root(book_id) / "raw_chinese"
    if not raw_dir.exists():
        return []
    files = sorted(p.name for p in raw_dir.glob("chapter_*.md"))
    return files[:count]


def _gather_source(book_id: str, chapter_files: List[str]) -> str:
    """Concatenate the Chinese bodies of the given chapters, capped in length."""
    root = book_root(book_id)
    parts: List[str] = []
    total = 0
    for name in chapter_files:
        doc = read_chapter(root / "raw_chinese" / name)
        block = f"### {name}\n{doc.title}\n\n{doc.body}"
        if total + len(block) > MAX_INPUT_CHARS:
            block = block[: MAX_INPUT_CHARS - total]
            parts.append(block)
            logger.warning("Input truncated at %d chars (reached %s).", MAX_INPUT_CHARS, name)
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def _parse_terms(raw: str) -> List[Dict[str, str]]:
    """Pull the JSON array out of the model's reply, tolerant of code fences."""
    text = raw.strip()
    # Strip ```json ... ``` fences if present.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Fall back to the first [...] block.
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"could not parse glossary JSON from model reply: {e}")
    if not isinstance(data, list):
        raise LLMError("model reply was not a JSON array")
    return [d for d in data if isinstance(d, dict) and d.get("chinese") and d.get("hanviet")]


def _to_entry(item: Dict[str, str]) -> Dict[str, str]:
    """Normalize an extracted item into a glossary term dict."""
    entry: Dict[str, str] = {"chinese": str(item["chinese"]).strip(), "hanviet": str(item["hanviet"]).strip()}
    category = (item.get("category") or "").strip()
    note = (item.get("note") or "").strip()
    if category and category not in ("khác", "nhân vật"):
        entry["role"] = category
    combined_note = note or (category if category == "nhân vật" else "")
    if combined_note:
        entry["note"] = combined_note
    return entry


def extract(book_id: str, chapters: int = 5, force: bool = False) -> Dict:
    """Extract terms from the first `chapters` chapters and merge into glossary.yaml.

    Returns a dict with the merged term list plus added/updated/skipped counts.
    Does not write to disk — the caller decides (see main()).
    """
    files = _leading_chapters(book_id, chapters)
    if not files:
        raise LLMError(f"no raw_chinese chapters found for '{book_id}'")
    logger.info("Reading %d chapter(s) for %s: %s", len(files), book_id, ", ".join(files))

    source = _gather_source(book_id, files)
    reply = chat_as("glossary", SYSTEM_PROMPT, f"Đây là {len(files)} chương đầu:\n\n{source}")
    extracted = _parse_terms(reply)
    logger.info("Model returned %d candidate term(s).", len(extracted))

    # Merge, preserving existing human-curated entries and order.
    existing = load_glossary(book_id)
    by_chinese: Dict[str, Dict[str, str]] = {t["chinese"]: t for t in existing}
    order: List[str] = [t["chinese"] for t in existing]

    added = updated = skipped = 0
    for item in extracted:
        entry = _to_entry(item)
        zh = entry["chinese"]
        if zh not in by_chinese:
            by_chinese[zh] = entry
            order.append(zh)
            added += 1
        elif force:
            # Keep an existing role/note if the model didn't supply richer info.
            merged = {**by_chinese[zh], **entry}
            by_chinese[zh] = merged
            updated += 1
        else:
            skipped += 1

    terms = [by_chinese[zh] for zh in order]
    return {
        "terms": terms,
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "chapters_read": files,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract a book glossary from its first N chapters using the LLM.")
    ap.add_argument("book_id", help="Book directory id, e.g. bqg/biqu59096")
    ap.add_argument("--chapters", type=int, default=5, help="Number of leading chapters to read (default 5).")
    ap.add_argument("--print", dest="print_only", action="store_true", help="Print the merged glossary; do not write.")
    ap.add_argument("--force", action="store_true", help="Overwrite hanviet of terms already in glossary.yaml.")
    args = ap.parse_args()

    try:
        result = extract(args.book_id, chapters=args.chapters, force=args.force)
    except LLMError as e:
        logger.error("%s", e)
        return 1

    doc = {"terms": result["terms"]}
    out = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)

    if args.print_only:
        print(out)
        logger.info(
            "Dry run: %d added, %d updated, %d skipped (%d total).",
            result["added"], result["updated"], result["skipped"], len(result["terms"]),
        )
        return 0

    path = glossary_path(args.book_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(out, encoding="utf-8")
    logger.info(
        "Wrote %d term(s) to %s (%d added, %d updated, %d skipped).",
        len(result["terms"]), path, result["added"], result["updated"], result["skipped"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
