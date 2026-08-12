"""Regression tests for the public client-profile loading contract."""

import unittest

from pipeline.client_profiles import (
    ClientProfileError,
    list_profiles,
    load_profile,
    validate_profile)


class ClientProfileTests(unittest.TestCase):
    def test_example_profiles_are_discoverable_and_valid(self):
        """
        The shipped examples are part of the feature contract: a future
        refactor must not silently make either profile unavailable.
        """
        self.assertEqual(list_profiles(), ["b2b-saas", "consulting-firm"])

        consulting = load_profile("consulting-firm")
        saas = load_profile("b2b-saas")

        self.assertEqual(consulting["industry"], "Professional services")
        self.assertEqual(saas["business_type"], "Software-as-a-service company")

    def test_invalid_maturity_is_rejected(self):
        """ 
        Constraining maturity gives later prompting/routing code a known,
        reviewable set of values rather than accepting arbitrary labels.
        """
        profile = {
            "id": "example",
            "name": "Example",
            "business_type": "Example",
            "industry": "Example",
            "geography": "Example",
            "ai_maturity": "advanced",
            "strategic_priorities": ["Priority"],
            "target_functions": ["Function"],
            "approved_vendors": ["Vendor"],
            "data_sensitivity": ["Data"],
            "regulatory_considerations": ["Rule"],
        }
        with self.assertRaises(ClientProfileError):
            validate_profile(profile)

    def test_profile_id_cannot_escape_profile_directory(self):
        """ 
        Profile identifiers come from configuration in future stages; reject
        path traversal so they can only resolve to files in profiles/.
        """
        with self.assertRaises(ClientProfileError):
            load_profile("../consulting-firm")


if __name__ == "__main__":
    unittest.main()
