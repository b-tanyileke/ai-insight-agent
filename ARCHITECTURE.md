# Architecture

This is the conceptual reference for the project -- what each stage actually
does, what data looks like as it moves through the pipeline, and where to
look when something's wrong.

## Mental model

The pipeline turns "everything currently in a handful of RSS/API feeds"
into "a small number of grounded, business-focused blog posts," through
five stages that each narrow or transform the data for a different reason:

```text
collect -> dedup -> title_filter -> enrich (conditional) -> synthesize -> publish_gate -> generate_report
```

`title_filter` and `enrich` happen *inside* `synthesize.py`, per item, not
as separate top-level stages -- see the synthesize section below.

## What the data looks like at each stage

**1. Raw item** (`collect.py` / `collectors.py`) -- one dict per item found
in any source, before any judgment is applied:

```json
{"title": "...", "url": "...", "summary": "...", "source": "...",
 "provider": "claude|openai|other|...", "published": "ISO date",
 "source_type": "rss|github_releases|arxiv|hn"}
```

Every source (`config.SOURCES`) fails independently -- one broken feed
logs a warning and is skipped, it never crashes the run.

**2. Deduped + batched** (`dedup.py`, then capped in `run_pipeline.py`) --
same shape, just filtered down to items whose URL isn't in `seen.json`,
then capped to `MAX_ITEMS_PER_RUN` (default 15) so one run can't spiral
into hours of work. Overflow items simply aren't marked seen, so they
reappear as "new" next run -- the backlog drains gradually.

**3. Title-filtered** (`title_filter.py`) -- runs first inside
`synthesize_item()`, before anything costs money or a network call.
Two swappable strategies (`config.TITLE_FILTER_METHOD`):

- `keyword` (default): free, instant, blocklist of terms like
  "raises $", "appoints", "lawsuit" that likely mean "not a relevant story."

- `llm`: one cheap Gemini call per item, more nuanced, small quota cost.

**4. Enriched** (`enrich.py`) -- only triggered if the item's `summary`
is shorter than `config.MIN_SUMMARY_LENGTH`. Fetches the real article at
`url` and extracts the main text (via trafilatura), replacing the thin
feed excerpt with real content. Falls back silently to the original
summary if the fetch fails -- never crashes, just likely gets filtered
out next by the sufficiency gate.

**5. Synthesized insight** (`synthesize.py` + `llm_client.py`) -- the
core transformation. Whatever content survived steps 3-4 gets sent to
Gemini with a system prompt that explicitly forbids adding facts beyond
what's given. Gemini returns:

```json
{"significant": true, "confidence": "confirmed|early-signal|speculative",
 "what_it_is": "...", "business_use_case": "...",
 "estimated_value": "...", "implementation": "...", "reasoning": "..."}
```

Immediately after, the REAL `source_url`, `source_name`, `provider`, and
`published` from the original item are spliced back in -- the model's
own citation claims are never trusted directly.

**6. Publish-gated** (`publish_gate.py`) -- drops anything with
`confidence: speculative`, ranks the rest (confirmed before early-signal,
longer `business_use_case` as tiebreaker), and caps at
`MAX_POSTS_PER_CYCLE` (default 5).

**7. Rendered post** (`generate_report.py`) -- insight fields mapped onto
a markdown template with Jekyll front matter, written to
`_posts/YYYY-MM-DD-slug.md`.

## Troubleshooting map

Start from the symptom, not the file list -- work top to bottom:

| Symptom | Likely cause | Check |
|---|---|---|
| Posts feel generic/vague | Source article was thin and enrichment failed | `enrich.py` logs; `content_enriched` flag on the insight |
| Wrong/irrelevant topics getting through | Title filter too permissive | `title_filter.py`, try switching `TITLE_FILTER_METHOD` |
| Good topics getting skipped | Filter too aggressive, or `MIN_SUMMARY_LENGTH` too high | `title_filter.py` keyword list, `config.py` |
| Value/cost claims feel made up | Prompt issue, or genuinely thin source data | `synthesize.py`'s `SYSTEM_INSTRUCTION` |
| Posts structurally shallow | Output schema too narrow | `synthesize.py`'s JSON schema in the system instruction |
| Right insight, bad formatting | Rendering only, not a data problem | `generate_report.py` |
| Same source dominating every week | Source list imbalance | `config.py`'s `SOURCES` |
| Run takes too long / few posts despite big backlog | Working through backlog, working as intended | `run_pipeline.py`, `MAX_ITEMS_PER_RUN` |

## Suggested file reading order

Read in execution order, not alphabetical -- each file only makes sense
once you know what feeds it.

1. `config.py` -- the control panel, every tunable knob with reasoning
2. `collectors.py` -> `collect.py` -- raw item shape, per-source fault tolerance
3. `dedup.py` -- `seen.json` shape; "seen" means processed, not published
4. `title_filter.py` -- the two strategies, why keyword is the default
5. `enrich.py` -- when it triggers, how it fails safely
6. `llm_client.py` -> `synthesize.py` -- the core stage: prompt, schema, citation splicing
7. `publish_gate.py` -- confidence ranking and the cap
8. `generate_report.py` -- insight fields to markdown template
9. `run_pipeline.py` -- wiring and execution order, read last

## Key config knobs (`config.py`)

- `MAX_ITEMS_PER_RUN` -- how many new items get processed per run (bounds runtime/quota)
- `MAX_POSTS_PER_CYCLE` -- how many insights become posts per run
- `MIN_SUMMARY_LENGTH` -- threshold for triggering enrichment
- `TITLE_FILTER_METHOD` -- `keyword` | `llm` | `none`
- `GEMINI_MODEL` -- overridable without code changes, e.g. for quota management
