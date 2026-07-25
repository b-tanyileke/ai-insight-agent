"""
Title relevance filter -- runs BEFORE enrichment and synthesis, so an
irrelevant item never costs a network fetch or an LLM call.

Two strategies, switchable via config.TITLE_FILTER_METHOD (env var
TITLE_FILTER_METHOD=keyword|llm|none) so you can compare them on real
data before committing to one:

- "keyword": free, instant, no API call. Blunter -- a blocklist of terms
  that reliably signal "not a capability/feature story" (funding, hiring,
  legal, events). Can false-negative on cleverly-worded titles.
- "llm": one cheap classification call per item (short prompt, short
  output -- much smaller than a full synthesis call, but not free).
  Should catch nuance the keyword list misses, at a small quota cost.
- "none": disables the filter entirely, everything proceeds to enrichment.
"""

import logging

from pipeline.config import TITLE_FILTER_METHOD
from pipeline.llm_client import call_gemini_raw, parse_json_response

logger = logging.getLogger("title_filter")

# Terms that reliably indicate "not a capability/feature story" for our
# purposes -- corporate/personnel/legal/event news rather than something
# with a concrete business implementation angle.
IRRELEVANT_KEYWORDS = [
    "raises $", "series a", "series b", "series c", "series d",
    "funding round", "seed round", "valuation",
    "ipo", "acquires", "acquisition of", "merger",
    "lawsuit", "sues ", "sued", "settlement", "class action",
    "appoints", "joins as ceo", "joins as cfo", "joins as coo",
    "steps down", "resigns", "layoffs", "job cuts",
    "hiring", "internship", "scholarship", "obituary",
    "keynote schedule", "conference agenda", "call for papers",
]

LLM_FILTER_SYSTEM_INSTRUCTION = """You are a fast triage classifier for a business-AI \
insight pipeline. You'll see a title and a short excerpt. Decide if this LIKELY \
describes a specific AI tool, model, or feature capability that a business could \
plausibly apply to a real practice or workflow.

Say NOT relevant for: funding rounds, hiring/personnel moves, lawsuits/legal news, \
event schedules, vague opinion pieces, or anything that isn't actually about a \
capability someone could use.

When genuinely unsure, lean relevant=true -- a downstream step will fact-check \
against full article content anyway, so this is just a cheap first pass, not the \
final word.

Respond with ONLY a JSON object, no markdown fences:
{"relevant": true or false, "reason": "one short phrase"}"""


def _keyword_filter(item):
    title = (item.get("title") or "").lower()
    for kw in IRRELEVANT_KEYWORDS:
        if kw in title:
            return False, f"keyword filter: matched '{kw}'"
    return True, "keyword filter: no blocklist match"


def _llm_filter(item):
    prompt = (
        f"Title: {item.get('title', '')}\n"
        f"Source: {item.get('source', '')}\n"
        f"Short excerpt: {(item.get('summary') or '')[:200]}"
    )
    try:
        text = call_gemini_raw(LLM_FILTER_SYSTEM_INSTRUCTION, prompt, temperature=0.0)
        result = parse_json_response(text)
        return bool(result.get("relevant", True)), f"llm filter: {result.get('reason', '')}"
    except Exception as e:
        # Fail open -- a filter failure should never silently drop data,
        # it should let later, stricter stages judge it instead.
        logger.warning("LLM title filter failed (%s) -- defaulting to relevant", e)
        return True, "llm filter: error, defaulted to relevant"


def passes_title_filter(item, method=None):
    method = method or TITLE_FILTER_METHOD
    if method == "none":
        return True, "title filter disabled"
    if method == "llm":
        return _llm_filter(item)
    if method == "keyword":
        return _keyword_filter(item)
    logger.warning("Unknown TITLE_FILTER_METHOD '%s', defaulting to keyword", method)
    return _keyword_filter(item)
