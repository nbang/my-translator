"""Skill: validate an edited chapter and return actionable issues.

Deterministic checks (fast, no LLM):
- residual Chinese characters in the output,
- glossary compliance: every source term present in Chinese must have its
  mandated Hán Việt appear in the output,
- required format markers present when the source implies them,
- gross length shortfall vs. the rough translation (dropped-content guard).

Optional LLM critic pass adds qualitative issues (pronoun rules, machine-y phrasing).

The returned `issues` feed the pipeline's auto-fix loop (re-edit with fixes).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from translator.config import book_root
from translator.llm.roles import chat_as
from translator.skills import glossary as glo
from translator.skills.chapters import contains_cjk, read_chapter

_CJK = re.compile(r"[一-鿿㐀-䶿]+")

CRITIC_SYSTEM = """Bạn là biên tập viên kiểm định chất lượng bản dịch Trung-Việt.
So sánh bản gốc tiếng Trung và bản dịch tiếng Việt. Chỉ liệt kê các LỖI cụ thể cần sửa
(sai nghĩa, bỏ sót nội dung, sai đại từ nhân vật, văn dịch máy sượng, sai thuật ngữ).
Mỗi lỗi một dòng, bắt đầu bằng "- ". Nếu không có lỗi nghiêm trọng, trả về đúng chữ "OK"."""


def _deterministic_checks(book_id: str, ref_zh: str, edited_vi: str, raw_vi: str) -> List[str]:
    issues: List[str] = []

    # 1. Residual Chinese.
    leftover = _CJK.findall(edited_vi)
    if leftover:
        sample = ", ".join(dict.fromkeys(leftover))[:120]
        issues.append(f"Còn sót chữ Hán chưa dịch trong bản biên tập: {sample}")

    # 2. Glossary compliance (case-insensitive: a term at sentence start is
    #    capitalized, e.g. "Liên tinh" vs the glossary's "liên tinh").
    edited_lower = edited_vi.lower()
    for term in glo.relevant_terms(ref_zh, glo.load_glossary(book_id)):
        if term["hanviet"].lower() not in edited_lower:
            issues.append(
                f"Thuật ngữ '{term['chinese']}' phải được dịch là '{term['hanviet']}' nhưng không xuất hiện."
            )

    # 3. Format markers implied by the source. Dialogue/system lines may render
    #    as quotes ("...") OR brackets ([...] for system/chat messages), so accept
    #    either. Require several source quotes (>=3 opening marks) so a lone stray
    #    quote / slogan doesn't cause a false positive.
    source_quote_count = ref_zh.count("“") + ref_zh.count('"')
    output_has_markers = any(ch in edited_vi for ch in ('"', "“", "["))
    if source_quote_count >= 3 and not output_has_markers:
        issues.append("Bản gốc có nhiều hội thoại/tin nhắn nhưng bản dịch thiếu dấu ngoặc kép hoặc ngoặc vuông.")

    # 4. Length shortfall vs the rough translation (possible dropped content).
    if raw_vi and len(edited_vi) < 0.55 * len(raw_vi):
        issues.append(
            f"Bản biên tập ngắn bất thường ({len(edited_vi)} ký tự so với bản thô {len(raw_vi)}), "
            "có thể đã bỏ sót nội dung."
        )
    return issues


def qa_chapter(args: Dict) -> Dict:
    """Validate one edited chapter.

    args: {book_id, chapter_file, use_critic?}
    returns: {chapter_file, ok, issues}
    """
    book_id = args["book_id"]
    chapter_file = args["chapter_file"]
    use_critic = bool(args.get("use_critic", False))

    root = book_root(book_id)
    edited_path = root / "edited_vietnamese" / chapter_file
    if not edited_path.exists():
        return {"chapter_file": chapter_file, "ok": False, "issues": ["edited file missing"]}

    edited_vi = read_chapter(edited_path).body
    ref_path = root / "raw_chinese" / chapter_file
    raw_path = root / "raw_vietnamese" / chapter_file
    ref_zh = read_chapter(ref_path).body if ref_path.exists() else ""
    raw_vi = read_chapter(raw_path).body if raw_path.exists() else ""

    issues = _deterministic_checks(book_id, ref_zh, edited_vi, raw_vi)

    if use_critic and ref_zh:
        user = f"## Bản gốc:\n{ref_zh}\n\n## Bản dịch:\n{edited_vi}"
        verdict = chat_as("critic", CRITIC_SYSTEM, user).strip()
        if verdict and verdict.upper() != "OK":
            for line in verdict.splitlines():
                line = line.strip().lstrip("-").strip()
                if line and not contains_cjk(line[:2]):
                    issues.append(line)

    return {"chapter_file": chapter_file, "ok": len(issues) == 0, "issues": issues}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "qa_chapter",
        "description": "Validate an edited chapter: residual Chinese, glossary compliance, format "
        "markers, dropped-content, and (optionally) an LLM critic pass. Returns {ok, issues}.",
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string"},
                "chapter_file": {"type": "string"},
                "use_critic": {"type": "boolean", "description": "Also run an LLM critic pass."},
            },
            "required": ["book_id", "chapter_file"],
        },
    },
}
