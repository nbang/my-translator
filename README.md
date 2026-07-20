# 📚 my-translator

Chinese → Vietnamese web-novel translation toolkit, built as **provider-agnostic
skills** driven by a **deterministic workflow**.

Pipeline per chapter:

```
scrape → translate (LLM, fidelity) → edit (LLM, style + glossary) → QA → [auto-fix loop]
```

Translation is a direct LLM pass, so proper nouns come out as Sino-Vietnamese
(Hán Việt) from the start instead of pinyin. Which model runs each stage is a
**config choice**, not code — point any role at a local (vLLM/Ollama),
OpenAI-compatible, Gemini, or Anthropic endpoint.

---

## 1. Project setup

Prerequisites: **Python 3.10+** and access to at least one LLM endpoint (a local
server, or an API key for OpenAI/DeepSeek/Gemini/Anthropic).

```bash
git clone <this repo> && cd my-translator

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env         # then edit .env (see below)
```

### Configure your LLM endpoint

Secrets live in `.env`; routing lives in [config.yaml](config.yaml). Fill in
`.env` with an OpenAI-compatible endpoint:

```bash
# .env
LLM_API_BASE=http://localhost:8000/v1     # vLLM/Ollama/LM Studio/OpenAI/DeepSeek
LLM_API_KEY=sk-local                        # any non-empty string for local servers
LLM_MODEL=qwen2.5-72b-instruct
```

By default all four roles — `translator`, `editor`, `critic`, `glossary` — read
these values. To send a stage to a different model or a cloud provider, edit its
entry in [config.yaml](config.yaml) (and set `GEMINI_API_KEY` / `ANTHROPIC_API_KEY`
in `.env` if you point a role at Gemini or Anthropic). Roles:

| Role | Stage | Temp |
|------|-------|------|
| `translator` | faithful zh→vi | low (0.25) |
| `editor` | style / polish | higher (0.5) |
| `critic` | QA review (optional) | 0.3 |
| `glossary` | proper-noun extraction | 0.1 |

### Verify the install

```bash
python tests/smoke_test.py     # offline — no LLM/network needed
```

---

## 2. Translate a book — step by step

A **book id** is just a directory path from the repo root, e.g. `bqg/2013956118`
or `52shuku/bjXRF`. All of a book's files live under that directory:

```
<book_id>/
  book.yaml            metadata (title, author, source, translation info)
  glossary.yaml        fixed  chinese → hanviet  terms
  EDITOR.md            per-book prose style guide (fed as the editor prompt)
  raw_chinese/         chapter_0001.md ...   (scraped source)
  raw_vietnamese/      chapter_0001.md ...   (fidelity translation)
  edited_vietnamese/   chapter_0001.md ...   (final, polished)
```

### Step 1 — Scrape the source chapters

Point the scraper at the book's table-of-contents URL. Chapters land in
`<book_id>/raw_chinese/`. Already-downloaded chapters are skipped.

```bash
python -m translator.workflow.pipeline \
  --book bqg/mybook --stage scrape \
  --source-url "https://www.52shuku.net/.../toc.html"
```

> Selectors are per-site in `translator/skills/scrape_chapters.py` (`SITE_RULES`).
> `52shuku` is configured; add a rule for a new site if needed.

### Step 2 — Create the book metadata

Add a `book.yaml` in the book directory. Copy an existing one (e.g.
[bqg/2013956118/book.yaml](bqg/2013956118/book.yaml)) and edit the fields — title,
author, source URL, translated title, description, subjects.

### Step 3 — Seed the glossary

Extract proper nouns (names, places, sects, techniques) from the first few
chapters so they translate consistently as Hán Việt:

```bash
python -m translator.workflow.extract_glossary bqg/mybook --chapters 5
# --print for a dry run; merges into any existing glossary, keeping curated terms
```

Review `<book_id>/glossary.yaml` and fix any term by hand — the glossary is the
source of truth QA enforces. Add terms later with the `glossary_update` skill.

### Step 4 — Write the style guide (`EDITOR.md`)

Create `<book_id>/EDITOR.md` — the prose style guide fed as the **editor** system
prompt: narrator role, pronoun rules, banned words, formatting, and a few-shot
example or two. Copy [bqg/2013956118/EDITOR.md](bqg/2013956118/EDITOR.md) as a
starting point. (An optional repo-level [TRANSLATOR.md](TRANSLATOR.md) overrides
the default *fidelity*-pass rules the same way.)

### Step 5 — Run the pipeline

Full flow (translate → edit → QA → auto-fix) for a range of chapters:

```bash
python -m translator.workflow.pipeline --book bqg/mybook --stage all --range 1-10
```

Run stages individually when iterating:

```bash
python -m translator.workflow.pipeline --book bqg/mybook --stage translate --range 1-50
python -m translator.workflow.pipeline --book bqg/mybook --stage edit      --range 1-50
python -m translator.workflow.pipeline --book bqg/mybook --stage qa        --range 1-50 --critic
```

Flags:

| Flag | Effect |
|------|--------|
| `--range 1-10` | chapter range (or a single number) |
| `--limit N` | cap chapters processed this run |
| `--force` | redo a stage even if its output exists |
| `--critic` | add an LLM critic to QA (else deterministic checks only) |

The pipeline is **idempotent and resumable** — re-running only redoes
missing/failed work, so it's safe to interrupt and restart.

### Step 6 — Review the output

Final chapters are in `<book_id>/edited_vietnamese/`. QA (`qa_chapter`) flags
residual Chinese, glossary violations, missing format markers, and dropped
content, and the pipeline re-edits with those issues as fix hints (up to
`pipeline.max_fix_attempts` in [config.yaml](config.yaml)).

### Step 7 (optional) — Re-apply an updated glossary

If you refine the glossary after chapters are already edited, re-term the
existing prose without a full re-translate:

```bash
python -m translator.workflow.pipeline --book bqg/mybook --stage reterm --range 1-50
```

---

## 3. Reference

### Layout

```
translator/
  llm/         provider.py (openai|google|anthropic client) + roles.py (role→model routing)
  skills/      scrape_chapters, translate_chapter, edit_chapter, qa_chapter, glossary, book
  workflow/    pipeline.py (runner + QA auto-fix loop), flows.py (Prefect),
               extract_glossary, validate_books, normalize_terms
  config.py    config.yaml + .env loading
config.yaml    endpoints + role→model routing
tests/         smoke_test.py (offline)
```

Skills are plain `fn(args) -> dict` functions with JSON-Schema tool definitions,
collected in `translator/skills/TOOL_REGISTRY` — a single source of truth for the
runner and any future agent-framework adapter. See
[translator/skills/SKILLS.md](translator/skills/SKILLS.md) for the full catalog.

### Utilities

```bash
python -m translator.workflow.validate_books      # check every book's yaml + glossary
python -m translator.workflow.normalize_terms <book_id> [--apply]   # safe no-LLM term replace
```

### Orchestration with Prefect (optional)

For a monitoring UI, task-level retries, and parallel translation, run the same
stages through [Prefect](https://prefect.io). It wraps the identical skills — no
change to translation behavior — and `pipeline.py` remains a zero-dependency
fallback.

```bash
pip install -r requirements-prefect.txt   # in addition to requirements.txt
prefect server start                      # optional — live UI at http://127.0.0.1:4200

python -m translator.workflow.flows --book bqg/mybook --stage all --range 1-10
python -m translator.workflow.flows --book bqg/mybook --stage translate --range 1-50 --concurrency 6
```

- **Concurrency:** translation fans out in parallel (`--concurrency` /
  `TRANSLATE_CONCURRENCY`); editing and re-terming stay sequential per book to
  preserve the previous-chapter style-context chain.
- **Global LLM rate limit** (needs the server): every LLM task carries the `llm`
  tag, so `prefect concurrency-limit create llm 4` caps concurrent LLM calls
  across all runs.

### GitHub Actions

Three manual (`workflow_dispatch`) workflows call the same pipeline module:
`scraper.yml` (scrape), `translator.yml` (translate), `editor.yml` (edit/qa).
Add an `LLM_API_KEY` repo secret; pass the base URL and model as inputs.

---

## License

For educational and personal use only.
