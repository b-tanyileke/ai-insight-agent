"""
Source configuration for the AI insight agent.

Add/remove/edit sources here without touching collector code.
Each source is a dict with at minimum: name, type, provider.
`provider` is used for the ~40% Claude / 60% others weighting later
on — tag it accurately (claude, openai, google, meta, ollama, other).

type must be one of: "rss", "github_releases", "arxiv", "hn"
"""

SOURCES = [
    # --- RSS feeds (official blogs / news) ---
    # RSS URLs for AI companies change often. If one breaks, the
    # collector will log a warning and skip it rather than crash --
    # just fix the URL here when that happens.
    {
        # Anthropic doesn't publish an official RSS feed (confirmed
        # July 2026), so this uses a well-maintained unofficial mirror
        # that scrapes anthropic.com/news. Verified working. If it ever
        # goes stale, search "anthropic rss feed unofficial" for a
        # current replacement -- this is the source that keeps your
        # ~40% Claude coverage target honest, so don't let it silently die.
        "name": "Anthropic News (unofficial mirror)",
        "type": "rss",
        "provider": "claude",
        "url": "https://raw.githubusercontent.com/taobojlen/anthropic-rss-feed/main/anthropic_news_rss.xml",
    },
    {
        "name": "OpenAI News",
        "type": "rss",
        "provider": "openai",
        "url": "https://openai.com/news/rss.xml",
    },
    {
        "name": "Hugging Face Blog",
        "type": "rss",
        "provider": "other",
        "url": "https://huggingface.co/blog/feed.xml",
    },
    {
        "name": "Berkeley AI Research (BAIR)",
        "type": "rss",
        "provider": "other",
        "url": "https://bair.berkeley.edu/blog/feed.xml",
    },

    # --- GitHub releases (very stable, official, great for tool
    # capability tracking like Ollama, llama.cpp, etc.) ---
    {
        "name": "Ollama releases",
        "type": "github_releases",
        "provider": "ollama",
        "repo": "ollama/ollama",
    },
    {
        "name": "llama.cpp releases",
        "type": "github_releases",
        "provider": "other",
        "repo": "ggml-org/llama.cpp",
    },

    # --- arXiv (stable official API, good for research-driven capabilities) ---
    {
        "name": "arXiv cs.AI recent",
        "type": "arxiv",
        "provider": "other",
        "query": "cat:cs.AI",
        "max_results": 15,
    },

    # --- Hacker News (Algolia API, stable, good signal on what's
    # actually getting attention/discussion) ---
    {
        "name": "Hacker News AI discussions",
        "type": "hn",
        "provider": "other",
        "query": "AI OR LLM OR Claude OR GPT OR Gemini",
    },
]

# Rough target weighting for the synthesis stage later -- not enforced
# at collection time, just documented here for reference.
PROVIDER_WEIGHT_TARGET = {
    "claude": 0.40,
    "other": 0.60,  # openai, google, meta, ollama, open-source, etc.
}

# --- Synthesis stage config ---
# Read from environment, never hardcode a key in this file.
# Set it with: export GEMINI_API_KEY="your-key-here"
import os
from pathlib import Path

# config.py now lives in pipeline/, so the repo root is one level up.
# Every other module should import these rather than computing its own
# Path(__file__).parent -- that would now incorrectly resolve to pipeline/
# instead of the repo root where data/ and _posts/ actually live.
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
POSTS_DIR = BASE_DIR / "_posts"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Selects the reviewed business context for a run. Override per scheduled
# deployment or manual run, for example: CLIENT_PROFILE_ID=b2b-saas.
CLIENT_PROFILE_ID = os.environ.get("CLIENT_PROFILE_ID", "consulting-firm")

# "gemini-flash-latest" is an alias Google keeps pointed at their current
# recommended free-tier-eligible Flash model. Override with an env var if
# you want a specific model (e.g. during testing, to conserve quota):
#   export GEMINI_MODEL=gemini-2.5-flash-lite
# Verify free-tier quota for your key in aistudio.google.com if synthesis
# calls start failing with 429s.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Minimum summary length (characters) for an item to be considered to have
# enough real content to synthesize an insight from, rather than just a
# title. HN items are excluded from synthesis entirely (see synthesize.py)
# since their "summary" field is just points/comments metadata, not content.
MIN_SUMMARY_LENGTH = 100

# Title relevance pre-filter method, runs before enrichment/synthesis so an
# irrelevant item never costs a network fetch or LLM call. "keyword" (free,
# blunter) or "llm" (small quota cost, more nuanced) or "none" (disabled).
# Override to compare methods on real data:
#   export TITLE_FILTER_METHOD=llm
TITLE_FILTER_METHOD = os.environ.get("TITLE_FILTER_METHOD", "keyword")

# Cap on how many NEW items get processed (title-filtered/enriched/
# synthesized) in a single run, regardless of how many were found. This
# bounds each run's duration and quota use -- a large backlog (e.g. the
# very first run, or after a gap) drains gradually across several
# scheduled runs instead of one run trying to do everything and either
# taking hours or never finishing at all. Unprocessed overflow items are
# NOT marked as seen, so they're picked up again next run.
MAX_ITEMS_PER_RUN = int(os.environ.get("MAX_ITEMS_PER_RUN", "10"))

# Even among insights that clear all gates, only publish this many per
# cycle, ranked by confidence (see publish_gate.py). Keeps output volume
# manageable and avoids burning through quota publishing everything at once.
MAX_POSTS_PER_CYCLE = int(os.environ.get("MAX_POSTS_PER_CYCLE", "5"))
