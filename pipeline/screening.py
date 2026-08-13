"""Cheap, deterministic profile-aware screening before model calls.

The screen ranks all collected candidates using reviewed profile terms and
source priority. It intentionally avoids embeddings and LLM calls so the run
budget is spent on the most promising items instead of collection order.
"""

import re


SOURCE_PRIORITY_SCORES = {"high": 3, "medium": 1, "low": 0}
SIGNAL_ONLY_PRIORITY = "signal"
TERM_MATCH_SCORE = 2


def normalize_text(text):
    """Lowercase and collapse whitespace for simple phrase matching."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def matching_terms(item, profile):
    """Return explicit profile terms found in an item's title or summary."""
    searchable_text = normalize_text(f"{item.get('title', '')} {item.get('summary', '')}")
    return [term for term in profile["screening_terms"] if normalize_text(term) in searchable_text]


def score_item(item, profile):
    """Return a score and audit-friendly reasons for one representative item."""
    priority = item.get("business_priority", "medium")
    if priority == SIGNAL_ONLY_PRIORITY:
        return 0, ["signal-only source"]

    matched_terms = matching_terms(item, profile)
    score = SOURCE_PRIORITY_SCORES.get(priority, SOURCE_PRIORITY_SCORES["medium"])
    reasons = [f"{priority}-priority source"]
    for term in matched_terms:
        score += TERM_MATCH_SCORE
        reasons.append(f"matched profile term: {term}")
    return score, reasons


def screen_candidates(items, profile, minimum_score, max_candidates):
    """Return ``(selected, held)`` after profile-aware deterministic ranking.

    ``selected`` contains the highest-scoring items meeting the threshold.
    Held items distinguish low relevance (safe to mark seen) from capacity
    overflow (leave unseen so a later run can still consider them).
    """
    eligible = []
    held = []
    for item in items:
        score, reasons = score_item(item, profile)
        screened_item = dict(item)
        screened_item["screening_score"] = score
        screened_item["screening_reasons"] = reasons
        if score < minimum_score:
            screened_item["screening_status"] = "low_relevance"
            held.append(screened_item)
        else:
            eligible.append(screened_item)

    eligible.sort(key=lambda item: (-item["screening_score"], item.get("title", "").lower()))
    selected = eligible[:max_candidates]
    for item in selected:
        item["screening_status"] = "selected"
    for item in eligible[max_candidates:]:
        item["screening_status"] = "capacity_overflow"
        held.append(item)
    return selected, held
