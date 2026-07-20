"""Deterministic pipeline runner — the primary, reliable batch path.

Flow per chapter:  translate -> edit -> qa -> [auto-fix re-edit loop]

- Idempotent: skips stages whose non-empty output already exists (unless --force).
- Resumable: safe to re-run; only missing/failed work is redone.
- Sequential: threads the previous edited chapter as style context.
- QA-gated: after editing, runs qa_chapter; if issues are found, re-edits with the
  issues as fix hints, up to pipeline.max_fix_attempts.

Scraping is stage 0 and runs once for the whole book (needs the source URL), not
per chapter.

CLI:
    python -m translator.workflow.pipeline --book biqu59096 --stage all --range 1-10
    python -m translator.workflow.pipeline --book biqu59096 --stage scrape --source-url ...
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import List, Optional

from translator.config import book_root, load_config
from translator.skills import call_tool
from translator.skills.chapters import read_chapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("pipeline")


def _chapter_files(book_id: str, rng: Optional[tuple[int, int]]) -> List[str]:
    raw_dir = book_root(book_id) / "raw_chinese"
    files = sorted(p.name for p in raw_dir.glob("chapter_*.md"))
    if rng:
        lo, hi = rng
        files = [f for f in files if lo <= int(f[len("chapter_"):-3]) <= hi]
    return files


def _prev_edited_text(book_id: str, chapter_file: str) -> Optional[str]:
    num = int(chapter_file[len("chapter_"):-3])
    if num <= 1:
        return None
    prev = book_root(book_id) / "edited_vietnamese" / f"chapter_{num - 1:04d}.md"
    if prev.exists() and prev.stat().st_size > 0:
        return read_chapter(prev).body
    return None


def process_chapter(
    book_id: str,
    chapter_file: str,
    *,
    force: bool = False,
    use_critic: bool = False,
    max_fix: int = 2,
) -> dict:
    """Run translate -> edit -> qa (+auto-fix) for one chapter."""
    result = {"chapter_file": chapter_file}

    t = call_tool("translate_chapter", {"book_id": book_id, "chapter_file": chapter_file, "force": force})
    result["translate"] = t["status"]
    if t["status"] == "error":
        return result

    prev = _prev_edited_text(book_id, chapter_file)
    e = call_tool(
        "edit_chapter",
        {"book_id": book_id, "chapter_file": chapter_file, "force": force, "previous_context": prev},
    )
    result["edit"] = e["status"]
    if e["status"] == "error":
        return result

    # QA + auto-fix loop.
    qa = call_tool("qa_chapter", {"book_id": book_id, "chapter_file": chapter_file, "use_critic": use_critic})
    attempts = 0
    while not qa["ok"] and attempts < max_fix:
        attempts += 1
        logger.info("QA found %d issue(s) in %s; fix attempt %d", len(qa["issues"]), chapter_file, attempts)
        call_tool(
            "edit_chapter",
            {
                "book_id": book_id,
                "chapter_file": chapter_file,
                "force": True,
                "previous_context": prev,
                "fix_issues": qa["issues"],
            },
        )
        qa = call_tool("qa_chapter", {"book_id": book_id, "chapter_file": chapter_file, "use_critic": use_critic})

    result["qa_ok"] = qa["ok"]
    result["qa_issues"] = qa["issues"]
    result["fix_attempts"] = attempts
    return result


def reterm_chapter(
    book_id: str,
    chapter_file: str,
    *,
    use_critic: bool = False,
    max_fix: int = 2,
) -> dict:
    """Re-apply the current glossary to an already-edited chapter, preserving prose.

    Reads the existing edited chapter as the base, normalizes terminology, then
    QA + auto-fix. Skips chapters that have no edited output yet.
    """
    root = book_root(book_id)
    if not (root / "edited_vietnamese" / chapter_file).exists():
        return {"chapter_file": chapter_file, "status": "skipped (no edited output)"}

    e = call_tool(
        "edit_chapter",
        {"book_id": book_id, "chapter_file": chapter_file, "force": True, "input_stage": "edited_vietnamese"},
    )
    result = {"chapter_file": chapter_file, "reterm": e["status"]}

    qa = call_tool("qa_chapter", {"book_id": book_id, "chapter_file": chapter_file, "use_critic": use_critic})
    attempts = 0
    while not qa["ok"] and attempts < max_fix:
        attempts += 1
        call_tool(
            "edit_chapter",
            {
                "book_id": book_id,
                "chapter_file": chapter_file,
                "force": True,
                "input_stage": "edited_vietnamese",
                "fix_issues": qa["issues"],
            },
        )
        qa = call_tool("qa_chapter", {"book_id": book_id, "chapter_file": chapter_file, "use_critic": use_critic})
    result["qa_ok"] = qa["ok"]
    result["qa_issues"] = qa["issues"]
    result["fix_attempts"] = attempts
    return result


def run(
    book_id: str,
    *,
    stage: str = "all",
    rng: Optional[tuple[int, int]] = None,
    limit: Optional[int] = None,
    force: bool = False,
    use_critic: bool = False,
    source_url: Optional[str] = None,
) -> None:
    cfg = load_config().get("pipeline", {})
    max_fix = int(cfg.get("max_fix_attempts", 2))
    delay = float(cfg.get("request_delay_s", 1.0))

    if stage in ("scrape", "all") and source_url:
        logger.info("Scraping %s ...", book_id)
        logger.info("%s", call_tool("scrape_chapters", {"book_id": book_id, "source_url": source_url}))
        if stage == "scrape":
            return

    files = _chapter_files(book_id, rng)
    if not files:
        logger.warning("No chapters found for %s (range=%s)", book_id, rng)
        return
    logger.info("Processing %d chapter(s) of %s [stage=%s]", len(files), book_id, stage)

    done = 0
    clean = 0
    for f in files:
        if limit is not None and done >= limit:
            logger.info("Reached limit of %d", limit)
            break
        if stage == "translate":
            r = call_tool("translate_chapter", {"book_id": book_id, "chapter_file": f, "force": force})
        elif stage == "edit":
            prev = _prev_edited_text(book_id, f)
            r = call_tool("edit_chapter", {"book_id": book_id, "chapter_file": f, "force": force, "previous_context": prev})
        elif stage == "qa":
            r = call_tool("qa_chapter", {"book_id": book_id, "chapter_file": f, "use_critic": use_critic})
        elif stage == "reterm":
            r = reterm_chapter(book_id, f, use_critic=use_critic, max_fix=max_fix)
            if r.get("qa_ok"):
                clean += 1
        else:  # all
            r = process_chapter(book_id, f, force=force, use_critic=use_critic, max_fix=max_fix)
            if r.get("qa_ok"):
                clean += 1
        logger.info("%s", r)
        done += 1
        time.sleep(delay)

    if stage in ("all", "reterm"):
        logger.info("Done. %d processed, %d passed QA clean.", done, clean)
    else:
        logger.info("Done. %d processed.", done)


def _parse_range(s: Optional[str]) -> Optional[tuple[int, int]]:
    if not s:
        return None
    if "-" in s:
        lo, hi = s.split("-", 1)
        return int(lo), int(hi)
    n = int(s)
    return n, n


def main() -> None:
    ap = argparse.ArgumentParser(description="my-translator pipeline")
    ap.add_argument("--book", required=True, help="Book id, e.g. biqu59096 or 52shuku/bjXRF")
    ap.add_argument("--stage", default="all", choices=["scrape", "translate", "edit", "qa", "reterm", "all"])
    ap.add_argument("--range", help="Chapter range, e.g. 1-10 or a single number")
    ap.add_argument("--limit", type=int, help="Max chapters to process this run")
    ap.add_argument("--force", action="store_true", help="Redo stages even if output exists")
    ap.add_argument("--critic", action="store_true", help="Use LLM critic in QA")
    ap.add_argument("--source-url", help="TOC URL for the scrape stage")
    args = ap.parse_args()

    run(
        args.book,
        stage=args.stage,
        rng=_parse_range(args.range),
        limit=args.limit,
        force=args.force,
        use_critic=args.critic,
        source_url=args.source_url,
    )


if __name__ == "__main__":
    main()
