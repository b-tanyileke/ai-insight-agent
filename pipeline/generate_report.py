"""
Report generation stage -- turns a publishable insight dict into an actual
markdown file in _posts/, using Jekyll's front-matter + filename convention
(YYYY-MM-DD-slug.md) so the repo is a working blog the moment GitHub Pages
gets enabled, no restructuring needed.
"""

import logging
import re
from datetime import date
from pathlib import Path

from pipeline.config import POSTS_DIR, DATA_DIR

logger = logging.getLogger("generate_report")


def slugify(title, max_words=10):
    """Turn a title into a URL-safe slug, e.g. 'Claude gains tool use!'
    -> 'claude-gains-tool-use'."""
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s-]", "", title)
    words = title.split()[:max_words]
    return "-".join(words) or "untitled"


def render_post(insight, post_date=None):
    """Renders one insight as a full markdown post (front matter + body)."""
    post_date = post_date or date.today()
    tags = [insight.get("provider", "other"), "business-ai"]
    profile_id = insight.get("client_profile_id", "")
    if profile_id:
        tags.append(profile_id)

    front_matter = (
        "---\n"
        f"title: \"{insight.get('title', 'Untitled').replace(chr(34), chr(39))}\"\n"
        f"date: {post_date.isoformat()}\n"
        f"tool: {insight.get('provider', 'other')}\n"
        f"tags: [{', '.join(tags)}]\n"
        f"confidence: {insight.get('confidence', 'unknown')}\n"
        f"client_profile: {profile_id}\n"
        "---\n"
    )

    body = (
        f"\n*Tailored for: {insight.get('client_profile_name', 'a general business audience')}*\n"
        f"\n## What it is\n{insight.get('what_it_is', '').strip()}\n"
        f"\n## Business use case\n{insight.get('business_use_case', '').strip()}\n"
        f"\n## Estimated value\n{insight.get('estimated_value', '').strip()}\n"
        f"\n## Implementation\n{insight.get('implementation', '').strip()}\n"
        f"\n## Sources\n"
        f"- [{insight.get('source_name', 'source')}]({insight.get('source_url', '')})"
        f" -- published {insight.get('published', 'date unknown')}\n"
    )

    related_sources = insight.get("related_sources", [])
    # Related coverage is not used as evidence for this post's claims yet;
    # label it clearly so readers can distinguish it from the primary source.
    if len(related_sources) > 1:
        body += "\n## Related coverage\n"
        for source in related_sources:
            if source.get("url") == insight.get("source_url"):
                continue
            body += (
                f"- [{source.get('source_name', 'source')}]({source.get('url', '')})"
                f" -- {source.get('title', 'untitled')}\n"
            )

    return front_matter + body


def generate_reports(insights, output_dir=None, post_date=None):
    """Writes one markdown file per insight. Returns list of written paths.
    If two insights would produce the same filename (same date + similar
    title), a numeric suffix is appended so nothing gets silently overwritten."""
    output_dir = output_dir or POSTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    post_date = post_date or date.today()

    written = []
    used_names = set()

    for insight in insights:
        slug = slugify(insight.get("title", "untitled"))
        base_filename = f"{post_date.isoformat()}-{slug}.md"
        filename = base_filename
        n = 2
        while filename in used_names or (output_dir / filename).exists():
            filename = f"{post_date.isoformat()}-{slug}-{n}.md"
            n += 1
        used_names.add(filename)

        content = render_post(insight, post_date)
        path = output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("Wrote post: %s", path)
        written.append(path)

    return written


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    from publish_gate import select_for_publishing

    test_file = DATA_DIR / "processed" / "test_insights.json"
    if not test_file.exists():
        print("No test_insights.json found -- run synthesize.py first.")
    else:
        with open(test_file, "r", encoding="utf-8") as f:
            insights = json.load(f)

        to_publish, held_back = select_for_publishing(insights)
        print(f"{len(to_publish)} insight(s) to publish, {len(held_back)} held back.\n")

        written = generate_reports(to_publish)
        print(f"\nWrote {len(written)} post(s):")
        for p in written:
            print(f"  - {p}")
