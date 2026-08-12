"""Tests for critic response validation without calling an LLM."""

import unittest

from pipeline.critique import validate_critique


class CritiqueTests(unittest.TestCase):
    """Keep the critic's small, machine-readable contract stable."""

    def test_complete_critique_is_accepted(self):
        # All four scores are required so publishing cannot accidentally rely
        # on a partial review response.
        result = {
            "decision": "approve",
            "scores": {
                "grounding": 5,
                "specificity": 4,
                "actionability": 4,
                "value_claim_safety": 5,
            },
            "feedback": "Specific, grounded, and ready to publish.",
        }
        self.assertEqual(validate_critique(result), result)

    def test_invalid_score_is_rejected(self):
        # Scores outside the documented range would make quality decisions
        # inconsistent, so malformed model output is never trusted.
        result = {
            "decision": "approve",
            "scores": {
                "grounding": 6,
                "specificity": 4,
                "actionability": 4,
                "value_claim_safety": 5,
            },
            "feedback": "Ready.",
        }
        self.assertIsNone(validate_critique(result))

    def test_missing_score_is_rejected(self):
        # The exact score set protects against prompts or models omitting one
        # of the review dimensions without the pipeline noticing.
        result = {
            "decision": "reject",
            "scores": {"grounding": 1, "specificity": 1, "actionability": 1},
            "feedback": "Too generic.",
        }
        self.assertIsNone(validate_critique(result))


if __name__ == "__main__":
    unittest.main()
