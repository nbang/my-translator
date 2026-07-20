# Skills catalog

Each skill is a pure `fn(args: dict) -> dict` with a JSON-Schema tool definition.
`TOOL_REGISTRY` (in `__init__.py`) maps name → (schema, callable) and is the single
source of truth for the pipeline runner and any future agent-framework adapter.

| Skill | When to use | Key args | Returns |
|-------|-------------|----------|---------|
| `scrape_chapters` | Fetch raw Chinese chapters from a source TOC URL into `<book>/raw_chinese/`. Skips already-downloaded chapters. | `book_id`, `source_url`, `max_chapters?`, `delay_s?` | `{scraped, skipped, total_listed}` |
| `translate_chapter` | Faithful LLM zh→vi (fidelity pass). Reads `raw_chinese/<file>`, writes `raw_vietnamese/<file>`. Uses the `translator` role + glossary. | `book_id`, `chapter_file`, `force?` | `{status, chunks}` |
| `edit_chapter` | Editorial polish (style pass) using `EDITOR.md` + glossary + Chinese reference. Writes `edited_vietnamese/<file>`. Accepts `fix_issues` for QA re-edits. | `book_id`, `chapter_file`, `force?`, `previous_context?`, `fix_issues?` | `{status, fixed}` |
| `qa_chapter` | Validate an edited chapter (residual Chinese, glossary compliance, format markers, dropped content; optional LLM critic). | `book_id`, `chapter_file`, `use_critic?` | `{ok, issues}` |
| `glossary_lookup` | Read a book's fixed terms, optionally filtered to those appearing in a text. | `book_id`, `source_text?` | `{count, terms}` |
| `glossary_update` | Add/update one fixed `chinese → hanviet` term. | `book_id`, `chinese`, `hanviet`, `role?`, `note?` | `{action, term, total}` |
| `book_info` | Read book metadata (`book.yaml`) + per-stage chapter counts. | `book_id` | `{metadata, counts}` |

**Roles** (`config.yaml`): `translator` (fidelity, low temp), `editor` (style),
`critic` (QA). Swap any role's endpoint/model without touching skill code.
