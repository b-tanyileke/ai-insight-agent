"""Tests for source-health funnel reporting."""

import unittest

from pipeline.source_health import build_source_health


def item(source, **extra):
    """Build minimal pipeline records for source-health tests."""
    return {"source": source, "source_name": source, **extra}


class SourceHealthTests(unittest.TestCase):
    """Ensure source reports distinguish collection and quality outcomes."""

    def test_report_counts_the_full_funnel(self):
        # The report should show whether a weak source failed collection,
        # screening, synthesis, or publication rather than only total volume.
        all_items = [item("Official"), item("Research")]
        selected = [item("Official", related_sources=[{"source_name": "Official"}])]
        held = [item("Research", screening_status="low_relevance", related_sources=[{"source_name": "Research"}])]
        insights = [{"source_name": "Official"}]
        published = [{"source_name": "Official"}]
        report = build_source_health(
            all_items, all_items, all_items, selected, held, insights, published
        )
        self.assertEqual(report["Official"]["selected"], 1)
        self.assertEqual(report["Official"]["published"], 1)
        self.assertEqual(report["Research"]["low_relevance"], 1)


if __name__ == "__main__":
    unittest.main()
