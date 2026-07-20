#!/usr/bin/env python3
"""Prefect orchestration layer (Phase 1 spike).

A thin, observable wrapper over the exact same skills the deterministic runner
uses (translator.workflow.pipeline). Prefect adds a monitoring UI, task-level
retries, and parallel translation — without changing any translation logic.

Parity with pipeline.py:
- **Idempotent**: the skills self-skip when a non-empty output already exists
  (unless force), so re-runs only redo missing work — visible in the UI as tasks
  returning ``status="skipped"``. (Prefect-native result caching is a Phase-2
  enhancement.)
- **Option A concurrency**: translation fans out in parallel (independent per
  chapter); editing runs sequentially per book so each chapter can use the
  previous *edited* chapter as style context (see pipeline._prev_edited_text).

Phase 1 supports stages: translate | edit | qa | all.
(scrape and reterm are added in Phase 2.)

Run:
    prefect server start          # optional — for the live UI at :4200
    python -m translator.workflow.flows --book bqg/biqu59096 --stage all --range 1-5
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import List, Optional

from prefect import flow, get_run_logger, task
from prefect.task_runners import ThreadPoolTaskRunner

from translator.config import load_config
from translator.skills import call_tool

# Reuse the pipeline's chapter-selection and range helpers verbatim — no
# duplicated logic, and behavior stays identical to the deterministic runner.
from translator.workflow.pipeline import _chapter_files, _parse_range, _prev_edited_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Max chapters translated in parallel. Overridable via env or --concurrency.
DEFAULT_CONCURRENCY = int(os.getenv("TRANSLATE_CONCURRENCY", "4"))


# --- Tasks: one per skill call ------------------------------------------------


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
) -> dict:
    """Editorial polish (raw_vietnamese -> edited_vietnamese), with optional fix hints."""
    return call_tool(
        "edit_chapter",
        {
            "book_id": book_id,
            "chapter_file": chapter_file,
            "force": force,
            "previous_context": previous_context,
            "fix_issues": fix_issues,
        },
    )


@task(task_run_name="qa:{chapter_file}")
def qa_task(book_id: str, chapter_file: str, use_critic: bool) -> dict:
    """Deterministic (+ optional critic) QA of an edited chapter."""
    return call_tool("qa_chapter", {"book_id": book_id, "chapter_file": chapter_file, "use_critic": use_critic})


# --- Per-chapter edit + QA auto-fix loop (sequential, Option A) ----------------


def _edit_and_qa(book_id: str, chapter_file: str, force: bool, use_critic: bool, max_fix: int) -> dict:
    """Edit one chapter, then QA it, re-editing with fixes until clean or capped.

    Mirrors pipeline.process_chapter's edit/QA phase. Runs the previous *edited*
    chapter as style context, so callers must invoke this in chapter order.
    """
    logger = get_run_logger()
    prev = _prev_edited_text(book_id, chapter_file)
    result = {"chapter_file": chapter_file}

    e = edit_task(book_id, chapter_file, force, previous_context=prev)
    result["edit"] = e["status"]
    if e["status"] == "error":
        return result

    qa = qa_task(book_id, chapter_file, use_critic)
    attempts = 0
    while not qa["ok"] and attempts < max_fix:
        attempts += 1
        logger.info("QA found %d issue(s) in %s; fix attempt %d", len(qa["issues"]), chapter_file, attempts)
        edit_task(book_id, chapter_file, True, previous_context=prev, fix_issues=qa["issues"])
        qa = qa_task(book_id, chapter_file, use_critic)

    result["qa_ok"] = qa["ok"]
    result["qa_issues"] = qa["issues"]
    result["fix_attempts"] = attempts
    return result


# --- Book-level flow: fan-out over a chapter range ----------------------------


@flow(name="book", task_runner=ThreadPoolTaskRunner(max_workers=DEFAULT_CONCURRENCY))
def book_flow(
    book_id: str,
    *,
    stage: str = "all",
    rng: Optional[tuple[int, int]] = None,
    limit: Optional[int] = None,
    force: bool = False,
    use_critic: bool = False,
) -> dict:
    """Orchestrate one stage across a book's chapters.

    Option A: `translate` fans out in parallel (capped by the flow's task
    runner); `edit`/`all` process chapters sequentially so the style-context
    chain is preserved.
    """
    logger = get_run_logger()
    max_fix = int(load_config().get("pipeline", {}).get("max_fix_attempts", 2))

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

    # Sequential edit (+ QA auto-fix) to preserve the previous-chapter chain.
    clean = 0
    for f in files:
        r = _edit_and_qa(book_id, f, force, use_critic, max_fix)
        if r.get("qa_ok"):
            clean += 1
        logger.info("%s", r)
    return {"processed": len(files), "clean": clean}


def main() -> None:
    ap = argparse.ArgumentParser(description="my-translator pipeline (Prefect)")
    ap.add_argument("--book", required=True, help="Book id, e.g. bqg/biqu59096 or 52shuku/bjXRF")
    ap.add_argument("--stage", default="all", choices=["translate", "edit", "qa", "all"])
    ap.add_argument("--range", help="Chapter range, e.g. 1-10 or a single number")
    ap.add_argument("--limit", type=int, help="Max chapters to process this run")
    ap.add_argument("--force", action="store_true", help="Redo stages even if output exists")
    ap.add_argument("--critic", action="store_true", help="Use LLM critic in QA")
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
    )


if __name__ == "__main__":
    main()
