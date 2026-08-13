"""Tests for deterministic profile-aware candidate screening."""

import unittest

from pipeline.client_profiles import load_profile
from pipeline.screening import screen_candidates, score_item


def item(title, summary, priority="medium"):
    """Build a minimal clustered representative for screening tests."""
    return {"title": title, "summary": summary, "business_priority": priority}


class ScreeningTests(unittest.TestCase):
    """Protect cost-saving candidate selection from collection-order regressions."""

    def test_profile_terms_and_source_priority_raise_score(self):
        # A consulting-relevant official release earns source points plus one
        # score increment per reviewed term present in title or summary.
        profile = load_profile("consulting-firm")
        candidate = item("New proposal workflow tools", "Improves client delivery", "high")
        score, reasons = score_item(candidate, profile)
        self.assertEqual(score, 7)
        self.assertIn("matched profile term: proposal", reasons)
        self.assertIn("matched profile term: client delivery", reasons)

    def test_signal_only_sources_do_not_consume_model_budget(self):
        # HN remains a collection signal, but direct synthesis needs a source
        # with reviewable content and an editorially configured priority.
        profile = load_profile("b2b-saas")
        score, reasons = score_item(item("New API feature", "Customer support", "signal"), profile)
        self.assertEqual(score, 0)
        self.assertEqual(reasons, ["signal-only source"])

    def test_highest_qualifying_candidates_are_selected(self):
        # The cap is applied after every item has been scored, so arrival order
        # cannot crowd out a later, more relevant source.
        profile = load_profile("b2b-saas")
        low = item("Model research", "General findings", "high")
        medium = item("New API controls", "Developer API improvements", "medium")
        strong = item("Customer support usage analytics", "New spend controls", "high")
        selected, held = screen_candidates([low, medium, strong], profile, minimum_score=4, max_candidates=1)
        self.assertEqual([candidate["title"] for candidate in selected], ["Customer support usage analytics"])
        self.assertEqual(len([candidate for candidate in held if candidate["screening_status"] == "low_relevance"]), 1)
        self.assertEqual(len([candidate for candidate in held if candidate["screening_status"] == "capacity_overflow"]), 1)


if __name__ == "__main__":
    unittest.main()
