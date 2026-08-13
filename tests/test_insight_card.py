"""Tests for the generated post decision card."""

import unittest

from pipeline.generate_report import render_insight_card, render_post


INSIGHT = {
    "title": "Example insight",
    "client_profile_name": "Growth-stage B2B SaaS company",
    "business_use_case": "Support teams can pilot ticket triage.",
    "implementation": "Run a small, measured pilot.",
    "screening": {"score": 7, "reasons": ["high-priority source"]},
    "critique": {"final": {"scores": {"grounding": 5, "specificity": 4, "actionability": 4, "value_claim_safety": 5}}},
    "related_sources": [{"url": "https://example.com"}, {"url": "https://coverage.example"}],
}


class InsightCardTests(unittest.TestCase):
    """Ensure the visual summary remains based on existing insight metadata."""

    def test_card_includes_existing_quality_and_action_data(self):
        # The card is only a presentation layer: it must display the stored
        # values rather than inventing scores or recommendations.
        card = render_insight_card(INSIGHT)
        self.assertIn("Growth-stage B2B SaaS company", card)
        self.assertIn("7", card)
        self.assertIn("18/20", card)
        self.assertIn("2", card)
        self.assertIn("Run a small, measured pilot.", card)

    def test_card_escapes_generated_text(self):
        # LLM-produced prose is rendered inside HTML, so escaping prevents it
        # from being interpreted as site markup or script.
        unsafe = {**INSIGHT, "business_use_case": "Use <script>alert(1)</script>."}
        card = render_insight_card(unsafe)
        self.assertIn("&lt;script&gt;", card)
        self.assertNotIn("<script>", card)

    def test_full_post_contains_the_card(self):
        # A future template change should not accidentally omit the summary
        # from generated posts even if the detailed sections remain present.
        post = render_post(INSIGHT)
        self.assertIn('class="insight-card"', post)
        self.assertIn("## Business use case", post)


if __name__ == "__main__":
    unittest.main()
