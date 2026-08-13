"""Group obviously duplicate source items before expensive synthesis calls.

This intentionally uses conservative title matching rather than embeddings or
an LLM. It prevents repeat posts for the same announcement while preserving
every original source link for inspection and future multi-source analysis.
"""

import re
from urllib.parse import urlsplit, urlunsplit


# These words add little meaning when comparing release/news headlines. The
# short list avoids making unrelated items look alike through over-normalizing.
TITLE_STOP_WORDS = {
    "a", "an", "and", "announces", "for", "from", "in", "introducing",
    "new", "of", "on", "the", "to", "with",
}
MIN_SHARED_TOKENS = 3
MIN_TITLE_SIMILARITY = 0.8


def normalize_url(url):
    """Normalize URLs for same-run matching without importing dedup internals."""
    if not url:
        return ""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def title_tokens(title):
    """Return meaningful, lowercase title tokens for conservative comparison."""
    tokens = re.findall(r"[a-z0-9]+", (title or "").lower())
    return {token for token in tokens if token not in TITLE_STOP_WORDS}


def items_match(first, second):
    """Return True only for identical URLs or very similar, substantive titles."""
    first_url = normalize_url(first.get("url", ""))
    second_url = normalize_url(second.get("url", ""))
    if first_url and first_url == second_url:
        return True

    first_tokens = title_tokens(first.get("title", ""))
    second_tokens = title_tokens(second.get("title", ""))
    shared = first_tokens & second_tokens
    if len(shared) < MIN_SHARED_TOKENS:
        return False
    similarity = len(shared) / len(first_tokens | second_tokens)
    return similarity >= MIN_TITLE_SIMILARITY


def source_record(item):
    """Keep only public collector metadata for related-coverage display."""
    return {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "source_name": item.get("source", ""),
        "provider": item.get("provider", ""),
        "published": item.get("published", ""),
        "source_type": item.get("source_type", ""),
    }


def representative_key(item):
    """Prefer primary material, then fuller collector summaries, for synthesis."""
    source_type_rank = {"github_releases": 0, "rss": 1, "arxiv": 2, "hn": 3}
    return (
        source_type_rank.get(item.get("source_type"), 99),
        -len(item.get("summary", "") or ""),
        item.get("title", "").lower(),
    )


def cluster_items(items):
    """Return one representative per conservative cluster.

    Each returned item receives ``related_sources`` containing the full cluster,
    including its own source. Only the representative is synthesized today;
    the retained links make the aggregation transparent and ready for a later
    multi-source evidence pass.
    """
    clusters = []
    for item in items:
        for cluster in clusters:
            if any(items_match(item, member) for member in cluster):
                cluster.append(item)
                break
        else:
            clusters.append([item])

    representatives = []
    for cluster in clusters:
        representative = dict(min(cluster, key=representative_key))
        representative["related_sources"] = [source_record(member) for member in cluster]
        representatives.append(representative)
    return representatives
