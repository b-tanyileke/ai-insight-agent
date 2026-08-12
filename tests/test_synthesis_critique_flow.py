"""Tests for the synthesis-to-critic control flow without external services."""

import unittest
from unittest.mock import patch

from pipeline.synthesize import synthesize_item


ITEM = {
    "title": "Example capability",
    "url": "https://example.com/release",
    "source": "Example source",
    "provider": "other",
    "published": "2026-08-12T00:00:00+00:00",
}
EVIDENCE = {
    "summary": "A capability was released.",
    "claims": [{"claim": "The capability is available.", "excerpt": "The capability is available now."}],
    "source_url": ITEM["url"],
    "source_name": ITEM["source"],
    "source_quality": "primary",
    "content_enriched": False,
}
DRAFT = {
    "significant": True,
    "confidence": "confirmed",
    "what_it_is": "A new capability.",
    "business_use_case": "Support teams can test it for ticket triage.",
    "estimated_value": "Value is uncertain until tested.",
    "implementation": "Run a small pilot.",
    "reasoning": "It affects a clear workflow.",
}


class SynthesisCritiqueFlowTests(unittest.TestCase):
    """Verify critic decisions affect drafts before the existing publish gate."""

    @patch("pipeline.synthesize.critique_insight")
    @patch("pipeline.synthesize.call_gemini")
    @patch("pipeline.synthesize.extract_evidence", return_value=EVIDENCE)
    @patch("pipeline.synthesize.passes_title_filter", return_value=(True, "test"))
    def test_rejected_draft_does_not_continue(self, _filter, _evidence, draft_call, critic_call):
        # A clear reject prevents the draft from reaching metadata attachment
        # or the later publish gate.
        draft_call.return_value = DRAFT
        critic_call.return_value = {
            "decision": "reject",
            "scores": {"grounding": 2, "specificity": 1, "actionability": 1, "value_claim_safety": 4},
            "feedback": "Too generic.",
        }

        self.assertIsNone(synthesize_item(ITEM))
        self.assertEqual(draft_call.call_count, 1)

    @patch("pipeline.synthesize.critique_insight")
    @patch("pipeline.synthesize.call_gemini")
    @patch("pipeline.synthesize.extract_evidence", return_value=EVIDENCE)
    @patch("pipeline.synthesize.passes_title_filter", return_value=(True, "test"))
    def test_one_revision_then_approval_is_retained(self, _filter, _evidence, draft_call, critic_call):
        # The critic may request exactly one revision. A second non-approval
        # would be held back by the implementation rather than looping.
        revised_draft = {**DRAFT, "business_use_case": "Support leads can pilot ticket triage for one queue."}
        draft_call.side_effect = [DRAFT, revised_draft]
        critic_call.side_effect = [
            {
                "decision": "revise",
                "scores": {"grounding": 5, "specificity": 2, "actionability": 3, "value_claim_safety": 5},
                "feedback": "Name a pilot workflow.",
            },
            {
                "decision": "approve",
                "scores": {"grounding": 5, "specificity": 4, "actionability": 4, "value_claim_safety": 5},
                "feedback": "Ready to publish.",
            },
        ]

        insight = synthesize_item(ITEM)
        self.assertTrue(insight["critique"]["revision_applied"])
        self.assertEqual(insight["critique"]["final"]["decision"], "approve")
        self.assertEqual(draft_call.call_count, 2)
        self.assertEqual(critic_call.call_count, 2)


if __name__ == "__main__":
    unittest.main()
