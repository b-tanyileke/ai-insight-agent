"""
Synthesis stage -- turns new items into structured insights using Gemini.

Design principles (directly from earlier discussion):
1. Grounding: the model receives only structured evidence whose excerpts have
   been checked against the source article by ``evidence.py``.
2. Content sufficiency and evidence extraction are isolated in ``evidence.py``
   so this module focuses only on business interpretation.
3. Every insight keeps collector-supplied source metadata rather than trusting
   the model to echo a citation correctly.
"""

import json
import logging
import time

from pipeline.config import DATA_DIR
from pipeline.critique import critique_insight
from pipeline.evidence import extract_evidence
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


def build_user_prompt(item, evidence):
    """Build a business-analysis prompt using only pre-validated evidence."""
    claims = "\n".join(
        f"- Claim: {claim['claim']}\n  Supporting excerpt: {claim['excerpt']}"
        for claim in evidence["claims"]
    )
    return (
        f"Title: {item.get('title', '')}\n"
        f"Source: {item.get('source', '')}\n"
        f"Provider: {item.get('provider', '')}\n"
        f"Published: {item.get('published', 'unknown')}\n"
        f"URL: {item.get('url', '')}\n"
        f"Evidence summary: {evidence.get('summary', '')}\n"
        f"Verified claims:\n{claims}"
    )


def call_gemini(user_prompt):
    text = call_gemini_raw(SYSTEM_INSTRUCTION, user_prompt, temperature=0.2)
    return parse_json_response(text)


def build_revision_prompt(item, evidence, draft, feedback):
    """Ask the existing insight writer for one evidence-bound revision."""
    prompt = build_user_prompt(item, evidence)
    prior_draft = json.dumps(draft, ensure_ascii=False)
    return (
        f"{prompt}\n\nOriginal draft:\n{prior_draft}\n\n"
        f"Editor feedback: {feedback}\n"
        "Revise the draft once. Keep the required JSON schema and use only the verified evidence."
    )


def synthesize_item(item, retry_delay=4):
    """Synthesize one item into an insight dict, or return None if skipped/failed."""
    title_ok, title_reason = passes_title_filter(item)
    if not title_ok:
        logger.info("Skipping (title filter) [%s]: %s", title_reason, item.get("title", "")[:60])
        return None

    try:
        evidence = extract_evidence(item)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning("Could not parse evidence for '%s': %s", item.get("title", "")[:60], e)
        return None
    except requests.RequestException as e:
        logger.warning("Evidence request failed for '%s': %s", item.get("title", "")[:60], e)
        return None

    if not evidence:
        return None

    prompt = build_user_prompt(item, evidence)
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

    # The critic has no publishing authority, but a rejected or malformed
    # review blocks this draft before it reaches the existing publish gate.
    try:
        critique = critique_insight(result, evidence)
        if critique and critique["decision"] == "revise":
            revised = call_gemini(build_revision_prompt(item, evidence, result, critique["feedback"]))
            if not revised.get("significant"):
                logger.info("Revision no longer significant: %s", item.get("title", "")[:60])
                return None
            final_critique = critique_insight(revised, evidence)
            if not final_critique or final_critique["decision"] != "approve":
                logger.info("Revision not approved: %s", item.get("title", "")[:60])
                return None
            result = revised
            critique = {"initial": critique, "final": final_critique, "revision_applied": True}
        elif not critique or critique["decision"] != "approve":
            logger.info("Critic rejected insight: %s", item.get("title", "")[:60])
            return None
        else:
            critique = {"final": critique, "revision_applied": False}
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning("Could not parse critic response for '%s': %s", item.get("title", "")[:60], e)
        return None
    except requests.RequestException as e:
        logger.warning("Critic request failed for '%s': %s", item.get("title", "")[:60], e)
        return None

    # Splice in the REAL source data -- never trust the model to echo it back.
    result["source_url"] = item.get("url", "")
    result["source_name"] = item.get("source", "")
    result["provider"] = item.get("provider", "")
    result["published"] = item.get("published", "")
    result["title"] = item.get("title", "")
    result["content_enriched"] = evidence["content_enriched"]
    result["evidence"] = evidence
    result["critique"] = critique

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
