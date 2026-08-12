"""Tests for deterministic evidence validation without calling an LLM."""

import unittest

from pipeline.evidence import source_quality, validate_evidence


class EvidenceTests(unittest.TestCase):
    """Keep the evidence gate strict as later pipeline stages evolve."""

    def test_verbatim_excerpt_is_accepted(self):
        """Whitespace changes are harmless; the underlying source words must
        still appear exactly so an editor can audit the claim quickly."""
        content = "The platform now supports audit logs for enterprise users."
        result = {
            "summary": "Audit logging was introduced.",
            "claims": [{
                "claim": "The platform supports audit logs for enterprise users.",
                "excerpt": "now supports audit logs for enterprise users",
            }],
        }
        evidence = validate_evidence(result, content)
        self.assertEqual(evidence["claims"], result["claims"])

    def test_non_verbatim_excerpt_is_rejected(self):
        """A plausible paraphrase is not evidence: it could conceal a model
        hallucination, so it must not reach business insight generation."""
        content = "The platform now supports audit logs for enterprise users."
        result = {
            "summary": "Audit logging was introduced.",
            "claims": [{
                "claim": "The platform improves compliance.",
                "excerpt": "The platform improves compliance significantly",
            }],
        }
        self.assertIsNone(validate_evidence(result, content))

    def test_source_quality_is_deterministic(self):
        """Quality labels describe provenance class rather than asking an LLM
        to make an un-auditable judgment about source reliability."""
        self.assertEqual(source_quality({"source_type": "github_releases"}), "primary")
        self.assertEqual(source_quality({"source_type": "rss"}), "source-published")
        self.assertEqual(source_quality({"source_type": "hn"}), "community-signal")


if __name__ == "__main__":
    unittest.main()
