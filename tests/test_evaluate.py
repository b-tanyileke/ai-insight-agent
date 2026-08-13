"""Tests for the no-cost deterministic screening evaluation command."""

import unittest

from pipeline.evaluate import evaluate_screening_cases


class EvaluationTests(unittest.TestCase):
    """Ensure the reviewed fixture baseline remains valid as rules evolve."""

    def test_screening_fixture_baseline_passes(self):
        # A failed fixture tells us a profile or screening-rule change altered
        # an expected decision before that change reaches scheduled runs.
        results, passed = evaluate_screening_cases()
        self.assertTrue(passed)
        self.assertEqual(len(results), 4)


if __name__ == "__main__":
    unittest.main()
