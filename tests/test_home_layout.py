"""Static checks for the custom Jekyll homepage layout."""

import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


class HomeLayoutTests(unittest.TestCase):
    """Ensure the archive layout keeps using pagination and card previews."""

    def test_home_layout_uses_paginator_and_card_grid(self):
        """ 
        The layout must use paginator.posts when GitHub Pages supplies it;
        otherwise the default Minima page would keep growing as one long list. 
        """
        layout = (REPOSITORY_ROOT / "_layouts" / "home.html").read_text(encoding="utf-8")
        self.assertIn("paginator.posts", layout)
        self.assertIn("insight-grid", layout)
        self.assertIn("digest-pagination", layout)

    def test_styles_define_responsive_card_grid(self):
        """ 
        The CSS grid must collapse on small screens rather than leaving two
        unreadably narrow archive cards side by side.
        """
        styles = (REPOSITORY_ROOT / "assets" / "main.scss").read_text(encoding="utf-8")
        self.assertIn(".insight-grid", styles)
        self.assertIn("grid-template-columns: 1fr;", styles)


if __name__ == "__main__":
    unittest.main()
