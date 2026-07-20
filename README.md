# 📚 my-translator

Chinese → Vietnamese web-novel translation toolkit, built as **provider-agnostic
skills** driven by a **deterministic workflow**.

Pipeline per chapter:

```
scrape → translate (LLM, fidelity) → edit (LLM, style + glossary) → QA → [auto-fix loop]
```

The old free-Google-Translate raw pass has been replaced by a direct LLM
translation, so proper nouns come out as Sino-Vietnamese (Hán Việt) from the
start instead of pinyin. Which model runs each stage is a **config choice**, not
code — point any role at a local (vLLM/Ollama), OpenAI-compatible, Gemini, or
Anthropic endpoint.

> The skills are plain `fn(args) -> dict` functions with JSON-Schema tool
> definitions collected in `translator/skills/TOOL_REGISTRY`. This makes it
> straightforward to later expose them to an agent framework (e.g. **Hermes
> Agent**) — that integration is deliberately deferred; the deterministic
> pipeline is the primary runner.

## Layout

```
translator/
  llm/         provider.py (openai|google|anthropic client) + roles.py (role→model routing)
  skills/      scrape_chapters, translate_chapter, edit_chapter, qa_chapter, glossary, book
  workflow/    pipeline.py (deterministic runner + QA auto-fix loop)
  config.py    config.yaml + .env loading
config.yaml    endpoints + role→model routing
<book_id>/     raw_chinese/  raw_vietnamese/  edited_vietnamese/  EDITOR.md  glossary.yaml  book.yaml
```

A *book id* is just a directory path from the repo root — e.g. `bqg/biqu59096` or
`52shuku/bjXRF`. No migration needed.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # fill in your endpoint + key + model
```

Edit `config.yaml` to route the `translator`, `editor`, and `critic` roles at
whatever model you want. The defaults read `LLM_API_BASE` / `LLM_API_KEY` /
`LLM_MODEL` from `.env` (an OpenAI-compatible endpoint — local vLLM/Ollama,
OpenAI, DeepSeek, or Gemini's OpenAI-compatible URL).

### Run the pipeline

```bash
# Full flow for chapters 1–10 of a book:
python -m translator.workflow.pipeline --book bqg/biqu59096 --stage all --range 1-10

# Individual stages:
python -m translator.workflow.pipeline --book bqg/biqu59096 --stage translate --range 1-50
python -m translator.workflow.pipeline --book bqg/biqu59096 --stage edit --range 1-50
python -m translator.workflow.pipeline --book bqg/biqu59096 --stage qa --range 1-50 --critic

# Scrape a new book:
python -m translator.workflow.pipeline --book mybook --stage scrape --source-url "https://.../toc.html"
```

Flags: `--force` redo existing outputs · `--limit N` cap per run · `--critic`
add an LLM critic to QA. The pipeline is idempotent and resumable — re-running
only redoes missing/failed work.

## Quality controls

- **Glossary** (`<book>/glossary.yaml`): fixed `chinese → hanviet` terms, injected
  into prompts (only terms present in the chunk) and enforced by QA. Seed one from
  an existing `EDITOR.md`: `python scripts/extract_glossary.py <book_id>`; extend
  via the `glossary_update` skill.
- **EDITOR.md** (per book): the prose style guide (role, pronoun rules, banned
  words, formatting, few-shot) — fed as the editor system prompt.
- **QA** (`qa_chapter`): flags residual Chinese, glossary violations, missing
  format markers, and dropped-content; the pipeline re-edits with those issues as
  fix hints (up to `pipeline.max_fix_attempts`).

## GitHub Actions

Three manual (`workflow_dispatch`) workflows call the same pipeline module:
`scraper.yml` (scrape), `translator.yml` (translate), `editor.yml` (edit/qa).
Add an `LLM_API_KEY` repo secret; pass the base URL and model as inputs.

## License

For educational and personal use only.
