"""Tests that client profiles change drafting and critique context."""

import unittest

from pipeline.client_profiles import load_profile
from pipeline.critique import build_critic_prompt
from pipeline.synthesize import build_user_prompt


ITEM = {"title": "Example release", "source": "Example", "provider": "other", "url": "https://example.com"}
EVIDENCE = {
    "summary": "A release was announced.",
    "claims": [{"claim": "A capability is available.", "excerpt": "A capability is available now."}],
}
INSIGHT = {
    "what_it_is": "A capability.",
    "business_use_case": "A workflow.",
    "estimated_value": "Uncertain.",
    "implementation": "Pilot it.",
    "reasoning": "Relevant.",
}


class ProfilePromptIntegrationTests(unittest.TestCase):
    """Ensure profile selection materially changes the existing model prompts."""

    def test_writer_prompt_contains_selected_profile_context(self):
        # Profile priorities and target functions let the writer reject a
        # development that is interesting generally but irrelevant to a client.
        profile = load_profile("consulting-firm")
        prompt = build_user_prompt(ITEM, EVIDENCE, profile)
        self.assertIn("Mid-market professional services consulting firm", prompt)
        self.assertIn("Business development and proposal management", prompt)

    def test_critic_prompt_changes_between_profiles(self):
        # The same draft is evaluated differently for different business
        # contexts, without any new model call or separate critic framework.
        consulting = build_critic_prompt(INSIGHT, EVIDENCE, load_profile("consulting-firm"))
        saas = build_critic_prompt(INSIGHT, EVIDENCE, load_profile("b2b-saas"))
        self.assertIn("Professional services", consulting)
        self.assertIn("B2B software", saas)
        self.assertNotEqual(consulting, saas)


if __name__ == "__main__":
    unittest.main()
