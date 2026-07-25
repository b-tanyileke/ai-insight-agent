"""
Synthesis stage -- turns new items into structured insights using Gemini.

Design principles (directly from earlier discussion):
1. Grounding: the model is given ONLY this item's own title/summary/url/
   source and explicitly told not to add outside facts or numbers it
   can't support from that text. No web browsing, no "as I recall".
2. Content-sufficiency gate: items without enough real information don't
   get sent to the LLM at all -- garbage in, garbage out, and it wastes
   free-tier quota. HN items are skipped entirely for direct synthesis
   (see MIN_SUMMARY_LENGTH and the source_type check below) since their
   summary field is HN metadata (points/comments), not article content.
3. Every insight keeps the ORIGINAL item's real url/source/provider
   attached after the fact -- never trust the model to echo these back
   correctly, always splice in the real values we already know.
"""

import json
import logging
import time

from pipeline.config import MIN_SUMMARY_LENGTH, DATA_DIR
from pipeline.enrich import get_content_for_synthesis
from pipeline.llm_client import call_gemini_raw, parse_json_response
from pipeline.title_filter import passes_title_filter
import requests

logger = logging.getLogger("synthesize")

SYSTEM_INSTRUCTION = """You are a careful business-technology analyst. You will be given \
details about ONE specific AI-related development (a blog post, paper, or release). \
Your job is to assess it and, if genuinely significant, explain its business relevance.

STRICT RULES:
- Use ONLY the information provided below. Do not add facts, statistics, dates, or \
capabilities you were not given. If you don't know something, say so rather than \
guessing.
- Do not invent cost or value figures. If you can't estimate honestly from the given \
information, say the estimate is uncertain and explain the reasoning qualitatively \
instead of making up a number.
- Respond with ONLY a single JSON object, no markdown fences, no preamble, matching \
exactly this schema:

{
  "significant": true or false,
  "confidence": "confirmed" | "early-signal" | "speculative",
  "what_it_is": "plain description, 1-3 sentences",
  "business_use_case": "specific practice/role this affects and how, 1-3 sentences",
  "estimated_value": "qualitative or rough-range value framing, honest about uncertainty",
  "implementation": "what it would actually take to try this: effort, prerequisites",
  "reasoning": "why you judged it significant or not, 1 sentence"
}

If the item is NOT significant (e.g. too minor, too vague, not actually business-relevant, \
or you don't have enough information to say anything substantive), set "significant": false \
and keep the other fields short/empty -- do not pad them out with speculation."""


def get_synthesizable_content(item):
    """Returns (content, was_enriched, sufficient, reason)."""
    if item.get("source_type") == "hn":
        return "", False, False, "HN items are signal-only, not synthesized directly (see docstring)"

    content, was_enriched = get_content_for_synthesis(item, MIN_SUMMARY_LENGTH)
    if len(content) < MIN_SUMMARY_LENGTH:
        return content, was_enriched, False, f"content still too short after enrichment attempt ({len(content)} chars < {MIN_SUMMARY_LENGTH})"
    return content, was_enriched, True, ""


def build_user_prompt(item, content):
    return (
        f"Title: {item.get('title', '')}\n"
        f"Source: {item.get('source', '')}\n"
        f"Provider: {item.get('provider', '')}\n"
        f"Published: {item.get('published', 'unknown')}\n"
        f"URL: {item.get('url', '')}\n"
        f"Content:\n{content}"
    )


def call_gemini(user_prompt):
    text = call_gemini_raw(SYSTEM_INSTRUCTION, user_prompt, temperature=0.2)
    return parse_json_response(text)


def synthesize_item(item, retry_delay=4):
    """Synthesize one item into an insight dict, or return None if skipped/failed."""
    title_ok, title_reason = passes_title_filter(item)
    if not title_ok:
        logger.info("Skipping (title filter) [%s]: %s", title_reason, item.get("title", "")[:60])
        return None

    content, was_enriched, ok, reason = get_synthesizable_content(item)
    if not ok:
        logger.info("Skipping (insufficient content) [%s]: %s", reason, item.get("title", "")[:60])
        return None

    prompt = build_user_prompt(item, content)
    try:
        result = call_gemini(prompt)
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            logger.warning("Rate limited, waiting %ds and retrying once...", retry_delay * 2)
            time.sleep(retry_delay * 2)
            try:
                result = call_gemini(prompt)
            except Exception as e2:
                logger.warning("Retry failed for '%s': %s", item.get("title", "")[:60], e2)
                return None
        else:
            logger.warning("Gemini call failed for '%s': %s", item.get("title", "")[:60], e)
            return None
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning("Could not parse Gemini response for '%s': %s", item.get("title", "")[:60], e)
        return None

    if not result.get("significant"):
        logger.info("Not significant: %s", item.get("title", "")[:60])
        return None

    # Splice in the REAL source data -- never trust the model to echo it back.
    result["source_url"] = item.get("url", "")
    result["source_name"] = item.get("source", "")
    result["provider"] = item.get("provider", "")
    result["published"] = item.get("published", "")
    result["title"] = item.get("title", "")
    result["content_enriched"] = was_enriched

    logger.info("Insight generated [%s/%s]: %s", result["provider"], result["confidence"], result["title"][:60])
    return result


def synthesize_items(items, delay_between_calls=4):
    """Synthesize a list of new items. Sleeps between calls to stay safely
    under Gemini free-tier RPM limits (~15/min as of mid-2026 -- check
    aistudio.google.com for your key's current limit)."""
    insights = []
    for i, item in enumerate(items):
        insight = synthesize_item(item)
        if insight:
            insights.append(insight)
        if i < len(items) - 1:
            time.sleep(delay_between_calls)
    return insights


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from .config import GEMINI_API_KEY

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not GEMINI_API_KEY:
        print('GEMINI_API_KEY not set. Run: export GEMINI_API_KEY="your-key-here"')
        sys.exit(1)

    raw_dir = DATA_DIR / "raw"
    raw_files = sorted(raw_dir.glob("*.json"))
    if not raw_files:
        print("No raw collection files found -- run collect.py first.")
        sys.exit(1)

    with open(raw_files[-1], "r", encoding="utf-8") as f:
        items = json.load(f)

    print(f"Testing synthesis on {min(3, len(items))} items from {raw_files[-1].name} (capped for a quick test)...")
    insights = synthesize_items(items[:3])

    out_dir = DATA_DIR / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "test_insights.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2, ensure_ascii=False)

    print(f"\n{len(insights)} insight(s) generated. Written to {out_path}")
    for insight in insights:
        print(f"\n--- {insight['title'][:70]}")
        print(f"    confidence: {insight['confidence']}")
        print(f"    use case: {insight['business_use_case'][:100]}")
