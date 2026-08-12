"""Select high-quality, critic-approved insights for publication.

This is a deterministic editorial gate. It does not call an LLM or rewrite
content; it applies the stored critic scores consistently and limits volume.
"""

import logging

from pipeline.config import MAX_POSTS_PER_CYCLE, DATA_DIR

logger = logging.getLogger("publish_gate")

# These thresholds intentionally favor reliable and safe claims. A useful
# early-signal can still publish, but it cannot be vague or poorly grounded.
MINIMUM_SCORES = {
    "grounding": 4,
    "specificity": 3,
    "actionability": 3,
    "value_claim_safety": 4,
}
MINIMUM_TOTAL_SCORE = 14


def final_critique(insight):
    """Return the final critic record from either review path, if present."""
    critique = insight.get("critique", {})
    if not isinstance(critique, dict):
        return None
    return critique.get("final")


def evaluate_for_publication(insight):
    """Return ``(eligible, reason)`` from the explicit editorial rubric."""
    critique = final_critique(insight)
    if not isinstance(critique, dict) or critique.get("decision") != "approve":
        return False, "no final critic approval"

    scores = critique.get("scores")
    if not isinstance(scores, dict):
        return False, "critic scores are missing"

    for score_name, minimum in MINIMUM_SCORES.items():
        score = scores.get(score_name)
        if not isinstance(score, int) or score < minimum:
            return False, f"{score_name} score below {minimum}"

    total_score = sum(scores[name] for name in MINIMUM_SCORES)
    if total_score < MINIMUM_TOTAL_SCORE:
        return False, f"total critic score below {MINIMUM_TOTAL_SCORE}"
    return True, "meets publication rubric"


def _rank_key(insight):
    """Rank eligible insights by critic quality, then by business usefulness."""
    critique = final_critique(insight)
    scores = critique["scores"]
    total_score = sum(scores[name] for name in MINIMUM_SCORES)
    return (
        -total_score,
        -scores["grounding"],
        -scores["specificity"],
        -scores["actionability"],
        insight.get("title", "").lower(),
    )


def _hold(insight, reason):
    """Copy a held insight and preserve the reason for logs or future review."""
    held_insight = dict(insight)
    held_insight["publication_status"] = "held"
    held_insight["publication_reason"] = reason
    return held_insight


def select_for_publishing(insights, max_posts=None):
    """Return ``(to_publish, held_back)`` using the deterministic rubric.

    Held records include a human-readable reason, which keeps rejection and
    volume-cap decisions inspectable without modifying the original insight.
    """
    max_posts = MAX_POSTS_PER_CYCLE if max_posts is None else max_posts
    eligible = []
    held_back = []
    for insight in insights:
        passes, reason = evaluate_for_publication(insight)
        if passes:
            eligible.append(insight)
        else:
            held_back.append(_hold(insight, reason))

    eligible.sort(key=_rank_key)
    to_publish = eligible[:max_posts]
    held_back.extend(_hold(insight, f"cycle cap of {max_posts} reached") for insight in eligible[max_posts:])

    logger.info(
        "Publish gate: %d insight(s) in -> %d meet rubric, %d selected (cap=%d), %d held",
        len(insights), len(eligible), len(to_publish), max_posts, len(held_back),
    )
    return to_publish, held_back


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    test_file = DATA_DIR / "processed" / "test_insights.json"
    if not test_file.exists():
        print("No test_insights.json found -- run synthesize.py first.")
    else:
        with open(test_file, "r", encoding="utf-8") as file:
            insights = json.load(file)

        to_publish, held_back = select_for_publishing(insights)
        print(f"\n{len(to_publish)} to publish:")
        for insight in to_publish:
            print(f"  - {insight['title'][:70]}")

        print(f"\n{len(held_back)} held back:")
        for insight in held_back:
            print(f"  - {insight['title'][:70]} ({insight['publication_reason']})")
