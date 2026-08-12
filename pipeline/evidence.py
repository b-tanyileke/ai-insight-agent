"""Extract and validate source-grounded evidence before insight synthesis.

This module owns evidence selection only. It reuses ``enrich.py`` for article
retrieval and leaves business interpretation to ``synthesize.py`` so the two
responsibilities do not overlap.
"""

import logging
import re

from pipeline.config import MIN_SUMMARY_LENGTH
from pipeline.llm_client import call_gemini_raw, parse_json_response

logger = logging.getLogger("evidence")

EVIDENCE_SYSTEM_INSTRUCTION = """You extract evidence from one source article.

Use ONLY the provided content. Return one to three concrete claims relevant to
an AI capability, product change, or deployment. For every claim, provide a
short supporting excerpt copied VERBATIM from the content. Do not paraphrase
the excerpt. Exclude opinions, predictions, and claims with no support.

Return ONLY one JSON object with exactly this schema:
{
  "summary": "one-sentence factual summary of the development",
  "claims": [
    {"claim": "a factual claim supported by the excerpt", "excerpt": "exact words from the content"}
  ]
}

If the content has no concrete, source-supported AI development, return an
empty claims array and an empty summary."""


def _normalize_text(text):
    """Normalize whitespace so copied excerpts can be checked reliably."""
    return re.sub(r"\s+", " ", (text or "").strip())


def source_quality(item):
    """Return a transparent, deterministic quality label for this source type."""
    source_type = item.get("source_type")
    if source_type in {"github_releases", "arxiv"}:
        return "primary"
    if source_type == "rss":
        # RSS feeds can be official, mirrored, or editorial; their exact
        # provenance is captured by source_name rather than guessed here.
        return "source-published"
    if source_type == "hn":
        return "community-signal"
    return "unknown"


def content_for_evidence(item):
    """Return source content or a reason it cannot support an evidence record."""
    if item.get("source_type") == "hn":
        return "", False, "HN items are signals, not source evidence"

    # Keep validation-only commands lightweight: trafilatura is needed only
    # when a real pipeline run may have to fetch an article.
    from pipeline.enrich import get_content_for_synthesis

    content, was_enriched = get_content_for_synthesis(item, MIN_SUMMARY_LENGTH)
    if len(content) < MIN_SUMMARY_LENGTH:
        return "", was_enriched, "source content is too short for reliable evidence extraction"
    return content, was_enriched, ""


def validate_evidence(result, content):
    """Return a safe evidence record, or None when model output is unsupported."""
    if not isinstance(result, dict) or not isinstance(result.get("claims"), list):
        return None

    verified_claims = []
    normalized_content = _normalize_text(content)
    for claim in result["claims"][:3]:
        if not isinstance(claim, dict):
            return None
        claim_text = (claim.get("claim") or "").strip()
        excerpt = (claim.get("excerpt") or "").strip()
        # A verbatim excerpt is a simple, auditable grounding check. A claim
        # without one does not advance to the business-interpretation stage.
        if not claim_text or len(excerpt) < 20:
            return None
        if _normalize_text(excerpt) not in normalized_content:
            logger.info("Rejected evidence because an excerpt was not verbatim source text")
            return None
        verified_claims.append({"claim": claim_text, "excerpt": excerpt})

    if not verified_claims:
        return None
    return {
        "summary": (result.get("summary") or "").strip(),
        "claims": verified_claims,
    }


def extract_evidence(item):
    """Create a validated evidence record for one item, or return None if weak."""
    content, was_enriched, reason = content_for_evidence(item)
    if not content:
        logger.info("Skipping evidence [%s]: %s", reason, item.get("title", "")[:60])
        return None

    prompt = (
        f"Title: {item.get('title', '')}\n"
        f"Source: {item.get('source', '')}\n"
        f"Published: {item.get('published', 'unknown')}\n"
        f"Content:\n{content}"
    )
    result = parse_json_response(call_gemini_raw(EVIDENCE_SYSTEM_INSTRUCTION, prompt, temperature=0.0))
    evidence = validate_evidence(result, content)
    if not evidence:
        logger.info("No validated evidence extracted: %s", item.get("title", "")[:60])
        return None

    # Source metadata comes from the collector, not the model response.
    evidence.update({
        "source_url": item.get("url", ""),
        "source_name": item.get("source", ""),
        "source_quality": source_quality(item),
        "content_enriched": was_enriched,
    })
    return evidence
