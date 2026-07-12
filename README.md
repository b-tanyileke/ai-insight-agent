# AI insight agent

Autonomous, free-tools-only pipeline that checks for new AI capability
developments on a schedule, filters for genuine business relevance, and
publishes citation-grounded write-ups as a Jekyll-ready blog via GitHub Pages.

## Pipeline stages

```
collect.py -> dedup.py -> synthesize.py -> publish_gate.py -> generate_report.py
```

All wired together by `run_pipeline.py`, the single entry point the
GitHub Actions workflow calls on a schedule. Each stage is also runnable
standalone for testing (see each file's `if __name__ == "__main__"` block).

## Local setup

```
pip install -r requirements.txt
export GEMINI_API_KEY="your-key-here"     # free tier: aistudio.google.com/apikey
python run_pipeline.py
```

Optional overrides (see config.py for details):
```
export GEMINI_MODEL=gemini-2.5-flash-lite   # swap models to manage quota
export TITLE_FILTER_METHOD=llm              # "keyword" (default) | "llm" | "none"
export MAX_POSTS_PER_CYCLE=3                # default 5
```

## GitHub Actions (automated weekly runs)

1. Push this repo to GitHub.
2. Add your Gemini key as a repo secret: Settings -> Secrets and variables
   -> Actions -> New repository secret -> name it `GEMINI_API_KEY`.
3. The workflow in `.github/workflows/weekly_run.yml` runs every Monday
   09:00 UTC, and can also be triggered manually from the Actions tab
   ("Run workflow" button, via `workflow_dispatch`).
4. To publish as an actual blog: Settings -> Pages -> deploy from branch
   -> select your default branch. `_config.yml` and `_posts/` are already
   set up for Jekyll, no restructuring needed.

Note: GitHub disables scheduled workflows on repos with no commits for
60 days. Push anything to reactivate it if that happens.

## Design notes

- Every source fails independently (collectors.py) -- a broken feed logs
  a warning and is skipped, never crashes the run.
- Dedup state (data/state/seen.json) is only saved AFTER synthesis
  completes for a run's new items, so a mid-run crash doesn't silently
  mark unsent items as seen.
- Synthesis is grounded strictly in each item's own content (title +
  enriched article text where needed) -- the model is told not to add
  outside facts, and every insight has the real source URL spliced back
  in after the fact rather than trusting model-echoed citations.
- Title filter (title_filter.py) runs BEFORE enrichment/synthesis so
  irrelevant items (funding, hiring, legal news) never cost a network
  fetch or an LLM call.
- Publish gate caps output at MAX_POSTS_PER_CYCLE, ranked by confidence,
  so a heavy week doesn't dump too much content at once.

## Known limitations / next steps

- Source list (config.py) is currently thin, especially for
  Google/DeepMind and Meta -- expand once the pipeline is stable.
- HN items are signal-only (not synthesized directly) -- full-text
  fetching for HN-linked pages is a possible v2 addition.
- No cross-referencing between sources yet (e.g. detecting when Claude
  and Gemini ship similar capabilities in the same window).
