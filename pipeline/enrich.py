"""
Enrichment stage -- fetches full article text for items whose feed-provided
summary is too thin to synthesize a grounded insight from.

Why this exists: several RSS sources (notably the Anthropic mirror feed)
only provide a one-sentence excerpt, not real content. Rather than lowering
the sufficiency bar and letting the LLM pad out thin input, we go get the
actual content directly from the source URL -- the same URL we're already
citing, so this doesn't introduce any new grounding risk.

Failure mode: if a fetch fails (paywall, JS-rendered page, blocked, etc.),
this returns None and the caller falls back to the original short summary,
which the sufficiency gate will then correctly skip. Never crashes the run.
"""

import logging

import requests
import trafilatura

logger = logging.getLogger("enrich")

REQUEST_TIMEOUT = 15
USER_AGENT = "ai-insight-agent/0.1 (personal research project)"
MAX_ENRICHED_CHARS = 4000


def fetch_article_text(url, max_chars=MAX_ENRICHED_CHARS):
    """Fetch a URL and extract its main article text. Returns None on any failure."""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()

        text = trafilatura.extract(resp.text, favor_recall=True)
        if not text or len(text.strip()) < 50:
            logger.info("Enrichment yielded too little text for %s", url)
            return None

        text = text.strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return text

    except Exception as e:
        logger.info("Enrichment failed for %s: %s", url, e)
        return None


def get_content_for_synthesis(item, min_summary_length):
    """Returns the best available text to synthesize from: the original
    summary if it's already long enough, otherwise an enrichment attempt,
    falling back to the original summary either way if enrichment fails.

    Only attempts enrichment for rss/github_releases/arxiv sources --
    HN is intentionally excluded here too (see synthesize.py docstring),
    since enriching HN would mean fetching arbitrary third-party pages
    with no consistent structure.
    """
    summary = item.get("summary", "") or ""
    if len(summary) >= min_summary_length:
        return summary, False  # already sufficient, no enrichment needed

    if item.get("source_type") == "hn":
        return summary, False  # never enrich HN, handled by synthesize.py gate

    enriched = fetch_article_text(item.get("url", ""))
    if enriched:
        logger.info("Enriched '%s': %d -> %d chars", item.get("title", "")[:50], len(summary), len(enriched))
        return enriched, True

    return summary, False  # enrichment failed, fall back to thin original
