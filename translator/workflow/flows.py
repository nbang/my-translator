#!/usr/bin/env python3
"""Prefect orchestration layer.

A thin, observable wrapper over the exact same skills the deterministic runner
uses (translator.workflow.pipeline). Prefect adds a monitoring UI, task-level
retries, and parallel translation — without changing any translation logic.

Parity with pipeline.py:
- **Idempotent**: the skills self-skip when a non-empty output already exists
  (unless force), so re-runs only redo missing work — visible in the UI as tasks
  returning ``status="skipped"``. (We rely on the skills' filesystem-truth skip
  rather than Prefect input-caching, which would not notice a deleted output.)
- **Option A concurrency**: translation fans out in parallel (independent per
  chapter); editing/re-terming run sequentially per book so each chapter can use
  the previous *edited* chapter as style context (see pipeline._prev_edited_text).

Stages: scrape | translate | edit | qa | reterm | all.

Run:
    prefect server start          # optional — for the live UI at :4200
    python -m translator.workflow.flows --book bqg/2013956118 --stage all --range 1-5
    python -m translator.workflow.flows --book mybook --stage scrape --source-url https://.../toc

Global rate limiting (optional, needs a Prefect server): all LLM tasks carry the
``llm`` tag, so a tag concurrency limit caps concurrent LLM calls across every
run:  ``prefect concurrency-limit create llm 4``.
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import List, Optional

from prefect import flow, get_run_logger, task
from prefect.task_runners import ThreadPoolTaskRunner

from translator.config import book_root, load_config
from translator.skills import call_tool

# Reuse the pipeline's chapter-selection and range helpers verbatim — no
# duplicated logic, and behavior stays identical to the deterministic runner.
from translator.workflow.pipeline import _chapter_files, _parse_range, _prev_edited_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Max chapters translated in parallel. Overridable via env or --concurrency.
DEFAULT_CONCURRENCY = int(os.getenv("TRANSLATE_CONCURRENCY", "4"))


# --- Tasks: one per skill call ------------------------------------------------


@task(retries=2, retry_delay_seconds=30, task_run_name="scrape:{book_id}")
def scrape_task(book_id: str, source_url: str, max_chapters: Optional[int] = None) -> dict:
    """Scrape raw Chinese chapters from a source TOC into raw_chinese/."""
    return call_tool(
        "scrape_chapters",
        {"book_id": book_id, "source_url": source_url, "max_chapters": max_chapters},
    )


@task(
    retries=2,
    retry_delay_seconds=[10, 30],
    tags=["llm"],
    task_run_name="translate:{chapter_file}",
)
def translate_task(book_id: str, chapter_file: str, force: bool) -> dict:
    """Fidelity LLM translation (raw_chinese -> raw_vietnamese)."""
    return call_tool("translate_chapter", {"book_id": book_id, "chapter_file": chapter_file, "force": force})


@task(
    retries=2,
    retry_delay_seconds=[10, 30],
    tags=["llm"],
    task_run_name="edit:{chapter_file}",
)
def edit_task(
    book_id: str,
    chapter_file: str,
    force: bool,
    previous_context: Optional[str] = None,
    fix_issues: Optional[List[str]] = None,
    input_stage: str = "raw_vietnamese",
) -> dict:
    """Editorial polish (-> edited_vietnamese), with optional fix hints.

    ``input_stage="edited_vietnamese"`` re-terms an already-polished chapter
    (preserve prose, only normalize glossary terms).
    """
    return call_tool(
        "edit_chapter",
        {
            "book_id": book_id,
            "chapter_file": chapter_file,
            "force": force,
            "previous_context": previous_context,
            "fix_issues": fix_issues,
            "input_stage": input_stage,
        },
    )


@task(task_run_name="qa:{chapter_file}")
def qa_task(book_id: str, chapter_file: str, use_critic: bool) -> dict:
    """Deterministic (+ optional critic) QA of an edited chapter."""
    return call_tool("qa_chapter", {"book_id": book_id, "chapter_file": chapter_file, "use_critic": use_critic})


# --- Per-chapter edit/reterm + QA auto-fix loops (sequential) -----------------


def _qa_fix_loop(book_id: str, chapter_file: str, use_critic: bool, max_fix: int, *, input_stage: str, prev: Optional[str]) -> dict:
    """QA the edited chapter, re-editing with fix hints until clean or capped.

    Shared by the edit and reterm paths; `input_stage` selects which base the
    re-edit reads from (raw_vietnamese for edit, edited_vietnamese for reterm).
    """
    logger = get_run_logger()
    qa = qa_task(book_id, chapter_file, use_critic)
    attempts = 0
    while not qa["ok"] and attempts < max_fix:
        attempts += 1
        logger.info("QA found %d issue(s) in %s; fix attempt %d", len(qa["issues"]), chapter_file, attempts)
        edit_task(book_id, chapter_file, True, previous_context=prev, fix_issues=qa["issues"], input_stage=input_stage)
        qa = qa_task(book_id, chapter_file, use_critic)
    return {"qa_ok": qa["ok"], "qa_issues": qa["issues"], "fix_attempts": attempts}


def _edit_and_qa(book_id: str, chapter_file: str, force: bool, use_critic: bool, max_fix: int) -> dict:
    """Edit one chapter then QA it. Uses the previous *edited* chapter as style
    context, so callers must invoke this in chapter order."""
    prev = _prev_edited_text(book_id, chapter_file)
    result = {"chapter_file": chapter_file}
    e = edit_task(book_id, chapter_file, force, previous_context=prev)
    result["edit"] = e["status"]
    if e["status"] == "error":
        return result
    result.update(_qa_fix_loop(book_id, chapter_file, use_critic, max_fix, input_stage="raw_vietnamese", prev=prev))
    return result


def _reterm_and_qa(book_id: str, chapter_file: str, use_critic: bool, max_fix: int) -> dict:
    """Re-apply the current glossary to an already-edited chapter, then QA.

    Skips chapters with no edited output. Independent of neighbours (prose is
    preserved), so no previous-chapter context is threaded.
    """
    if not (book_root(book_id) / "edited_vietnamese" / chapter_file).exists():
        return {"chapter_file": chapter_file, "status": "skipped (no edited output)"}
    e = edit_task(book_id, chapter_file, True, input_stage="edited_vietnamese")
    result = {"chapter_file": chapter_file, "reterm": e["status"]}
    result.update(_qa_fix_loop(book_id, chapter_file, use_critic, max_fix, input_stage="edited_vietnamese", prev=None))
    return result


# --- Book-level flow: fan-out over a chapter range ----------------------------


@flow(name="book", flow_run_name="{book_id} · {stage}", task_runner=ThreadPoolTaskRunner(max_workers=DEFAULT_CONCURRENCY))
def book_flow(
    book_id: str,
    *,
    stage: str = "all",
    rng: Optional[tuple[int, int]] = None,
    limit: Optional[int] = None,
    force: bool = False,
    use_critic: bool = False,
    source_url: Optional[str] = None,
) -> dict:
    """Orchestrate one stage across a book's chapters.

    Option A: `translate`/`qa` fan out in parallel (capped by the flow's task
    runner); `edit`/`reterm`/`all` process chapters sequentially so the
    style-context chain is preserved.
    """
    logger = get_run_logger()
    max_fix = int(load_config().get("pipeline", {}).get("max_fix_attempts", 2))

    # Stage 0: scrape once for the whole book (runs before chapters exist).
    if stage in ("scrape", "all") and source_url:
        logger.info("Scraping %s ...", book_id)
        res = scrape_task(book_id, source_url, limit if stage == "scrape" else None)
        logger.info("scrape: %s", res)
        if stage == "scrape":
            return {"scrape": res}

    files = _chapter_files(book_id, rng)
    if limit is not None:
        files = files[:limit]
    if not files:
        logger.warning("No chapters found for %s (range=%s)", book_id, rng)
        return {"processed": 0}
    logger.info("Book %s: %d chapter(s), stage=%s", book_id, len(files), stage)

    # Parallel fidelity translation (independent per chapter).
    if stage in ("translate", "all"):
        futures = [translate_task.submit(book_id, f, force) for f in files]
        for fut in futures:
            fut.result()
        if stage == "translate":
            return {"processed": len(files)}

    # QA-only: independent, so also parallel.
    if stage == "qa":
        results = [qa_task.submit(book_id, f, use_critic) for f in files]
        clean = sum(1 for fut in results if fut.result()["ok"])
        logger.info("QA done: %d/%d clean", clean, len(files))
        return {"processed": len(files), "clean": clean}

    # Sequential edit/reterm (+ QA auto-fix).
    per_chapter = _reterm_and_qa if stage == "reterm" else None
    clean = 0
    for f in files:
        r = per_chapter(book_id, f, use_critic, max_fix) if per_chapter else _edit_and_qa(book_id, f, force, use_critic, max_fix)
        if r.get("qa_ok"):
            clean += 1
        logger.info("%s", r)
    return {"processed": len(files), "clean": clean}


def main() -> None:
    ap = argparse.ArgumentParser(description="my-translator pipeline (Prefect)")
    ap.add_argument("--book", required=True, help="Book id, e.g. bqg/2013956118 or 52shuku/bjXRF")
    ap.add_argument("--stage", default="all", choices=["scrape", "translate", "edit", "qa", "reterm", "all"])
    ap.add_argument("--range", help="Chapter range, e.g. 1-10 or a single number")
    ap.add_argument("--limit", type=int, help="Max chapters to process this run")
    ap.add_argument("--force", action="store_true", help="Redo stages even if output exists")
    ap.add_argument("--critic", action="store_true", help="Use LLM critic in QA")
    ap.add_argument("--source-url", help="TOC URL for the scrape stage")
    ap.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Parallel translations (default 4)")
    args = ap.parse_args()

    runner = ThreadPoolTaskRunner(max_workers=args.concurrency)
    book_flow.with_options(task_runner=runner)(
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
