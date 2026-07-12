"""
Dedup stage -- filters out items already processed in a previous run.

"Seen" here means "already handed to synthesis", not "already published".
Whether a new item becomes a post is a separate decision made later by
publish_gate.py. Keeping these separate means: an item can be judged
"not concrete enough to publish" without being re-fetched and re-judged
every single cycle forever.

State lives in data/state/seen.json and is meant to be committed to
the repo -- losing it just means old items get reprocessed once, not
a real failure, but it's better to keep it.
"""

import json
import logging
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger("dedup")

STATE_PATH = Path(__file__).parent / "data" / "state" / "seen.json"


def normalize_url(url):
    """Strip fragments and common tracking params so trivially different
    URLs pointing at the same content dedupe correctly."""
    if not url:
        return url
    parts = urlsplit(url)
    # Drop query string entirely -- for our sources (blog posts, releases,
    # papers) the path alone identifies the content; query params here are
    # almost always tracking noise, not distinct content.
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def load_seen(path=STATE_PATH):
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read seen.json (%s) -- starting fresh", e)
        return {}


def save_seen(seen, path=STATE_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)


def filter_new(items, seen, run_timestamp):
    """Split items into (new_items, updated_seen_dict).

    updated_seen_dict is NOT written to disk here -- caller decides when
    to persist (typically only after the item has been fully processed,
    so a crash mid-pipeline doesn't silently mark things as seen without
    ever having produced output for them).
    """
    new_items = []
    updated_seen = dict(seen)

    for item in items:
        key = normalize_url(item.get("url", ""))
        if not key:
            # No URL to key on -- can't safely dedupe, treat as always-new
            # and log it, since silently dropping items is worse than an
            # occasional duplicate.
            logger.warning("Item with no URL, skipping dedup check: %s", item.get("title"))
            new_items.append(item)
            continue

        if key in seen:
            continue

        new_items.append(item)
        updated_seen[key] = {
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "first_seen": run_timestamp,
        }

    logger.info(
        "Dedup: %d incoming, %d new, %d already seen",
        len(items), len(new_items), len(items) - len(new_items),
    )
    return new_items, updated_seen


if __name__ == "__main__":
    # Standalone test run: dedupe against the most recent raw collection file.
    import sys
    from datetime import datetime, timezone

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    raw_dir = Path(__file__).parent / "data" / "raw"
    raw_files = sorted(raw_dir.glob("*.json"))
    if not raw_files:
        print("No raw collection files found -- run collect.py first.")
        sys.exit(1)

    latest = raw_files[-1]
    with open(latest, "r", encoding="utf-8") as f:
        items = json.load(f)

    seen = load_seen()
    run_ts = datetime.now(timezone.utc).isoformat()
    new_items, updated_seen = filter_new(items, seen, run_ts)

    print(f"\nFrom {latest.name}: {len(new_items)} new item(s) out of {len(items)} total.")
    for item in new_items[:5]:
        print(f"  - [{item['provider']}] {item['title'][:70]}")

    save_seen(updated_seen)
    print(f"\nUpdated seen.json now tracks {len(updated_seen)} items.")
