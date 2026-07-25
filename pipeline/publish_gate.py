"""
Publish gate -- decides which synthesized insights actually become posts.

Two-stage filter:
1. Confidence gate: drop "speculative" insights from publishing (still
   returned separately so the caller can log them for trend-tracking,
   just not published as posts).
2. Cap: even among publishable insights, only the top MAX_POSTS_PER_CYCLE
   get published per cycle, ranked by confidence (confirmed before
   early-signal) and, as a tiebreaker, how substantive the business_use_case
   write-up is -- a rough proxy for how much real signal Gemini had to
   work with.
"""

import logging

from pipeline.config import MAX_POSTS_PER_CYCLE, DATA_DIR

logger = logging.getLogger("publish_gate")

PUBLISHABLE_CONFIDENCE = {"confirmed", "early-signal"}
CONFIDENCE_RANK = {"confirmed": 0, "early-signal": 1, "speculative": 2}


def _rank_key(insight):
    return (
        CONFIDENCE_RANK.get(insight.get("confidence"), 99),
        -len(insight.get("business_use_case", "") or ""),
    )


def select_for_publishing(insights, max_posts=None):
    """Returns (to_publish, held_back) -- held_back includes both
    speculative insights and anything that overflowed the cap."""
    max_posts = MAX_POSTS_PER_CYCLE if max_posts is None else max_posts

    publishable = [i for i in insights if i.get("confidence") in PUBLISHABLE_CONFIDENCE]
    speculative = [i for i in insights if i.get("confidence") not in PUBLISHABLE_CONFIDENCE]

    publishable.sort(key=_rank_key)
    to_publish = publishable[:max_posts]
    overflow = publishable[max_posts:]
    held_back = speculative + overflow

    logger.info(
        "Publish gate: %d insight(s) in -> %d publishable, %d selected (cap=%d), "
        "%d held (speculative), %d held (overflow)",
        len(insights), len(publishable), len(to_publish), max_posts,
        len(speculative), len(overflow),
    )
    return to_publish, held_back


if __name__ == "__main__":
    import json
    from pathlib import Path

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    test_file = DATA_DIR / "processed" / "test_insights.json"
    if not test_file.exists():
        print("No test_insights.json found -- run synthesize.py first.")
    else:
        with open(test_file, "r", encoding="utf-8") as f:
            insights = json.load(f)

        to_publish, held_back = select_for_publishing(insights)

        print(f"\n{len(to_publish)} to publish:")
        for i in to_publish:
            print(f"  - [{i['confidence']}] {i['title'][:70]}")

        print(f"\n{len(held_back)} held back:")
        for i in held_back:
            print(f"  - [{i['confidence']}] {i['title'][:70]}")
