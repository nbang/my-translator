"""Skill: scrape raw Chinese chapters from a source site into <book>/raw_chinese/.

Refactored from the original step1_chapter_scraper.py: same SITE_RULES selectors
and output format, now a callable skill with a JSON schema.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from translator.config import book_root

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

SITE_RULES = [
    {
        "domain_keyword": "52shuku",
        "main_selector": "div.content",
        "title_selector": "h1#nr_title",
        "content_selector": "div#text",
    },
    # Default fallback rule (matches everything).
    {
        "domain_keyword": "",
        "main_selector": "html",
        "title_selector": None,
        "content_selector": "div#text",
    },
]


def _match_rule(url: str) -> dict:
    for rule in SITE_RULES:
        if rule["domain_keyword"] in url:
            return rule
    return SITE_RULES[-1]


def _fetch_chapter_list(url: str) -> List[Dict]:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    ul = soup.find("ul", class_="list clearfix")
    if not ul:
        logger.error("Could not find <ul class='list clearfix'> at %s", url)
        return []

    chapters: List[Dict] = []
    for link in ul.find_all("a"):
        href = link.get("href", "")
        text = link.get_text(strip=True)
        m = re.match(r"第(\d+)[页章]\s*(.*)", text)
        if not m:
            continue
        chapters.append(
            {
                "number": int(m.group(1)),
                "title": m.group(2).strip() or text,
                "url": urljoin(url, href),
            }
        )
    chapters.sort(key=lambda c: c["number"])
    return chapters


def _fetch_chapter_content(url: str) -> Tuple[str, Optional[str]]:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    rule = _match_rule(url)

    scope = soup
    if rule["main_selector"] and rule["main_selector"] != "html":
        scope = soup.select_one(rule["main_selector"])
    if not scope:
        return "", None

    title = None
    if rule["title_selector"]:
        el = scope.select_one(rule["title_selector"])
        if el:
            title = el.get_text(strip=True)

    content = ""
    if rule["content_selector"]:
        div = scope.select_one(rule["content_selector"])
        if div:
            for br in div.find_all("br"):
                br.replace_with("\n")
            for p in div.find_all("p"):
                p.insert_after("\n")
            content = div.get_text()
            content = re.sub(r"\r\n", "\n", content)
            content = re.sub(r"[ \t]+\n", "\n", content)
            content = re.sub(r"\n{3,}", "\n\n", content)
            content = content.strip()
    return content, title


def _save_chapter(raw_dir: Path, number: int, title: str, content: str) -> Path:
    path = raw_dir / f"chapter_{number:04d}.md"
    md = (
        f"### 标题 | Title\n\n第{number}章 {title}\n\n---\n\n"
        f"### 内容 | Content\n\n{content}\n\n---\n"
        f"*生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n"
    )
    path.write_text(md, encoding="utf-8")
    return path


def scrape_chapters(args: Dict) -> Dict:
    """Scrape chapters from a source URL into <book>/raw_chinese/.

    args: {book_id, source_url, max_chapters?, delay_s?}
    """
    book_id = args["book_id"]
    source_url = args["source_url"]
    max_chapters = args.get("max_chapters")
    delay = float(args.get("delay_s", 1.0))

    raw_dir = book_root(book_id) / "raw_chinese"
    raw_dir.mkdir(parents=True, exist_ok=True)

    chapters = _fetch_chapter_list(source_url)
    if not chapters:
        return {"book_id": book_id, "scraped": 0, "skipped": 0, "error": "no chapters found"}
    if max_chapters:
        chapters = chapters[:max_chapters]

    scraped = skipped = 0
    for ch in chapters:
        path = raw_dir / f"chapter_{ch['number']:04d}.md"
        if path.exists():
            skipped += 1
            continue
        content, extracted = _fetch_chapter_content(ch["url"])
        if not content:
            logger.warning("No content for chapter %s", ch["number"])
            continue
        _save_chapter(raw_dir, ch["number"], extracted or ch["title"], content)
        scraped += 1
        time.sleep(delay)

    return {"book_id": book_id, "scraped": scraped, "skipped": skipped, "total_listed": len(chapters)}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "scrape_chapters",
        "description": "Scrape raw Chinese chapters from a source website's table-of-contents "
        "URL into <book>/raw_chinese/. Skips chapters already downloaded.",
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "Book directory id, e.g. 'biqu59096'."},
                "source_url": {"type": "string", "description": "Chapter-list (TOC) page URL."},
                "max_chapters": {"type": "integer", "description": "Optional cap on chapters to fetch."},
                "delay_s": {"type": "number", "description": "Politeness delay between requests (default 1.0)."},
            },
            "required": ["book_id", "source_url"],
        },
    },
}
