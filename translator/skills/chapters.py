"""Chapter file helpers: lenient parsing, paragraph-aware chunking, CJK checks.

Chapter markdown files (across scrape versions) look roughly like:

    # 第1章 <title>            (optional H1)
    ## 标题 | Title            (or ### / "Tiêu đề")
    <title line>
    ---
    ## 内容 | Content          (or ### / "Nội dung")
    <body ...>
    ---
    *生成时间: ...*             (optional footer)

We parse leniently so both old and new files work, and so translated files
round-trip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

# Matches the "content" section heading in Chinese or Vietnamese.
_CONTENT_HEADING = re.compile(r"^#{1,6}\s*(内容|Content|Nội dung).*$", re.IGNORECASE)
_TITLE_HEADING = re.compile(r"^#{1,6}\s*(标题|Title|Tiêu đề).*$", re.IGNORECASE)
_TIMESTAMP_FOOTER = re.compile(r"^\*?\s*(生成时间|Thời gian tạo)", re.IGNORECASE)
_CJK = re.compile(r"[一-鿿㐀-䶿]")


@dataclass
class ChapterDoc:
    """A parsed chapter: a human title and the body prose, plus the original text."""

    title: str
    body: str
    raw: str

    def has_cjk_body(self) -> bool:
        return bool(_CJK.search(self.body))


def contains_cjk(text: str) -> bool:
    return bool(_CJK.search(text))


def read_chapter(path: Path) -> ChapterDoc:
    """Parse a chapter markdown file into title + body, tolerant of layout drift."""
    raw = Path(path).read_text(encoding="utf-8")
    lines = raw.splitlines()

    title = ""
    body_start = None
    # First pass: locate title and the content heading.
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if not title:
            if stripped.startswith("#") and not _TITLE_HEADING.match(stripped) and not _CONTENT_HEADING.match(stripped):
                title = stripped.lstrip("#").strip()
            elif _TITLE_HEADING.match(stripped):
                # Title text is the next non-empty, non-separator line.
                for j in range(i + 1, len(lines)):
                    t = lines[j].strip()
                    if t and t != "---" and not t.startswith("#"):
                        title = t
                        break
        if _CONTENT_HEADING.match(stripped):
            body_start = i + 1
            break

    if body_start is None:
        # No content heading: body is everything after the title line.
        body_lines = lines[1:] if title else lines
    else:
        body_lines = lines[body_start:]

    # Trim leading separators/blanks and the trailing footer/separators.
    body = "\n".join(body_lines).strip()
    body = re.sub(r"^(---\s*\n?)+", "", body).strip()
    cleaned: List[str] = []
    for line in body.splitlines():
        if _TIMESTAMP_FOOTER.match(line.strip()):
            break
        cleaned.append(line)
    body = "\n".join(cleaned).strip()
    # Drop a dangling trailing separator.
    body = re.sub(r"\n?-{3,}\s*$", "", body).strip()

    if not title:
        title = "Untitled"
    return ChapterDoc(title=title, body=body, raw=raw)


def chunk_paragraphs(text: str, max_chars: int = 4000) -> List[str]:
    """Split text into <=max_chars chunks on paragraph (blank-line) boundaries.

    A single paragraph longer than max_chars is emitted as its own chunk rather
    than being cut mid-sentence.
    """
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks


def render_chapter(title: str, body: str) -> str:
    """Render an edited/translated chapter to the canonical Vietnamese layout."""
    return f"# {title}\n\n## Nội dung\n\n{body.strip()}\n"
