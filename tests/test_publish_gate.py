"""Tests for deterministic publication selection without external services."""

import unittest

from pipeline.publish_gate import evaluate_for_publication, select_for_publishing


def insight(title, scores, decision="approve"):
    """Build a minimal critic-reviewed insight for the gate tests."""
    return {
        "title": title,
        "business_use_case": "A concrete workflow.",
        "critique": {"final": {"decision": decision, "scores": scores, "feedback": "Test review."}},
    }


class PublishGateTests(unittest.TestCase):
    """Ensure the rubric is predictable and does not depend on model calls."""

    def test_strong_approved_insight_meets_rubric(self):
        # The gate trusts critic scores only after a final approve decision.
        candidate = insight("Strong", {"grounding": 5, "specificity": 4, "actionability": 4, "value_claim_safety": 5})
        self.assertEqual(evaluate_for_publication(candidate), (True, "meets publication rubric"))

    def test_low_grounding_is_held_even_when_approved(self):
        # An approval alone is insufficient: high-confidence publishing needs
        # evidence strong enough for a reader to audit.
        candidate = insight("Weak evidence", {"grounding": 3, "specificity": 5, "actionability": 5, "value_claim_safety": 5})
        self.assertEqual(evaluate_for_publication(candidate), (False, "grounding score below 4"))

    def test_cap_retains_best_scores_and_explains_overflow(self):
        # Ranking uses the rubric scores, not the writer's confidence label or
        # prose length, and overflow remains available for later inspection.
        best = insight("Best", {"grounding": 5, "specificity": 5, "actionability": 5, "value_claim_safety": 5})
        good = insight("Good", {"grounding": 4, "specificity": 4, "actionability": 4, "value_claim_safety": 4})
        selected, held = select_for_publishing([good, best], max_posts=1)
        self.assertEqual([item["title"] for item in selected], ["Best"])
        self.assertEqual(held[0]["publication_reason"], "cycle cap of 1 reached")


if __name__ == "__main__":
    unittest.main()
