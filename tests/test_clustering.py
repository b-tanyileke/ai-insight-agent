"""Tests for deterministic, conservative source clustering."""

import unittest

from pipeline.clustering import cluster_items, items_match


def item(title, url, source="Source", source_type="rss", summary="Short summary"):
    """Build a minimal collected item for clustering tests."""
    return {
        "title": title,
        "url": url,
        "source": source,
        "provider": "other",
        "published": "2026-08-12T00:00:00+00:00",
        "source_type": source_type,
        "summary": summary,
    }


class ClusteringTests(unittest.TestCase):
    """Protect the narrow matching policy from becoming over-aggressive."""

    def test_same_normalized_url_clusters(self):
        # URL query strings are tracking noise, so coverage links to the same
        # article should never produce separate synthesis calls.
        first = item("First headline", "https://example.com/article?utm=one")
        second = item("Different headline", "https://example.com/article?utm=two", source="Mirror")
        self.assertTrue(items_match(first, second))
        clusters = cluster_items([first, second])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]["related_sources"]), 2)

    def test_near_identical_substantive_titles_cluster(self):
        # Removing only generic release words lets closely worded copies join
        # while preserving meaningful product/model tokens.
        first = item("OpenAI introduces GPT 5 Codex for enterprise teams", "https://one.example/article")
        second = item("OpenAI GPT 5 Codex for enterprise teams", "https://two.example/article", source="Coverage")
        self.assertTrue(items_match(first, second))

    def test_related_but_distinct_titles_do_not_cluster(self):
        # The high threshold avoids merging separate releases merely because
        # they mention the same vendor and broad topic.
        first = item("OpenAI releases new coding agent controls", "https://one.example/article")
        second = item("OpenAI expands enterprise usage analytics", "https://two.example/article")
        self.assertFalse(items_match(first, second))
        self.assertEqual(len(cluster_items([first, second])), 2)


if __name__ == "__main__":
    unittest.main()
