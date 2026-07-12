"""
Collector functions -- one per source type.

Every collector returns a list of normalized item dicts:
    {
        "title": str,
        "url": str,
        "summary": str,       # short description/abstract, may be empty
        "source": str,        # human-readable source name, e.g. "OpenAI News"
        "provider": str,      # claude / openai / google / meta / ollama / other
        "published": str,     # ISO 8601 date string, best-effort
        "source_type": str,   # rss / github_releases / arxiv / hn
    }

Design principle: a broken source should never crash the whole run.
Each collect_* function catches its own exceptions, logs a warning,
and returns [] on failure so the pipeline just has one less source
that cycle instead of zero output.
"""

import logging
import xml.etree.ElementTree as ET

import feedparser
import requests
from dateutil import parser as dateparser

logger = logging.getLogger("collectors")

REQUEST_TIMEOUT = 15
USER_AGENT = "ai-insight-agent/0.1 (personal research project)"


def _safe_date(raw):
    """Best-effort ISO date parsing. Returns None if unparseable."""
    if not raw:
        return None
    try:
        return dateparser.parse(raw).isoformat()
    except (ValueError, TypeError):
        return None


def collect_rss(source):
    """Fetch and normalize an RSS/Atom feed."""
    try:
        resp = requests.get(
            source["url"], timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}
        )
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)

        if parsed.bozo and not parsed.entries:
            # bozo=True just means "not strictly well-formed XML" -- lots
            # of real-world feeds trip this. Only treat it as a failure
            # if we also got zero usable entries out of it.
            raise ValueError(f"feed did not parse: {parsed.bozo_exception}")

        items = []
        for entry in parsed.entries:
            items.append({
                "title": entry.get("title", "").strip(),
                "url": entry.get("link", "").strip(),
                "summary": entry.get("summary", "").strip(),
                "source": source["name"],
                "provider": source["provider"],
                "published": _safe_date(entry.get("published", entry.get("updated"))),
                "source_type": "rss",
            })
        logger.info("RSS [%s]: %d items", source["name"], len(items))
        return items

    except Exception as e:
        logger.warning("RSS [%s] failed: %s", source["name"], e)
        return []


def collect_github_releases(source):
    """Fetch recent releases for a GitHub repo (public API, no auth needed
    for low request volumes, but rate-limited to 60 req/hour unauthenticated)."""
    try:
        url = f"https://api.github.com/repos/{source['repo']}/releases"
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
            params={"per_page": 10},
        )
        resp.raise_for_status()
        releases = resp.json()

        items = []
        for r in releases:
            if r.get("draft"):
                continue
            items.append({
                "title": f"{source['repo']} {r.get('tag_name', '')}: {r.get('name') or r.get('tag_name', '')}".strip(),
                "url": r.get("html_url", ""),
                "summary": (r.get("body") or "")[:1000],
                "source": source["name"],
                "provider": source["provider"],
                "published": _safe_date(r.get("published_at")),
                "source_type": "github_releases",
            })
        logger.info("GitHub releases [%s]: %d items", source["name"], len(items))
        return items

    except Exception as e:
        logger.warning("GitHub releases [%s] failed: %s", source["name"], e)
        return []


def collect_arxiv(source):
    """Query the arXiv API for recent papers matching a category/search query."""
    try:
        url = "http://export.arxiv.org/api/query"
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            params={
                "search_query": source["query"],
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": source.get("max_results", 15),
            },
        )
        resp.raise_for_status()

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.content)

        items = []
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            id_el = entry.find("atom:id", ns)
            published_el = entry.find("atom:published", ns)

            items.append({
                "title": (title_el.text or "").strip().replace("\n", " ") if title_el is not None else "",
                "url": (id_el.text or "").strip() if id_el is not None else "",
                "summary": (summary_el.text or "").strip().replace("\n", " ")[:1000] if summary_el is not None else "",
                "source": source["name"],
                "provider": source["provider"],
                "published": _safe_date(published_el.text if published_el is not None else None),
                "source_type": "arxiv",
            })
        logger.info("arXiv [%s]: %d items", source["name"], len(items))
        return items

    except Exception as e:
        logger.warning("arXiv [%s] failed: %s", source["name"], e)
        return []


def collect_hn(source):
    """Query Hacker News (via Algolia API) for recent stories matching a query."""
    try:
        url = "https://hn.algolia.com/api/v1/search_by_date"
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            params={"query": source["query"], "tags": "story", "hitsPerPage": 20},
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])

        items = []
        for h in hits:
            # Skip low-signal stories -- require some discussion to have happened.
            if (h.get("points") or 0) < 20 and (h.get("num_comments") or 0) < 10:
                continue
            items.append({
                "title": h.get("title", "").strip(),
                "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                "summary": f"{h.get('points', 0)} points, {h.get('num_comments', 0)} comments on HN",
                "source": source["name"],
                "provider": source["provider"],
                "published": _safe_date(h.get("created_at")),
                "source_type": "hn",
            })
        logger.info("HN [%s]: %d items", source["name"], len(items))
        return items

    except Exception as e:
        logger.warning("HN [%s] failed: %s", source["name"], e)
        return []


COLLECTORS = {
    "rss": collect_rss,
    "github_releases": collect_github_releases,
    "arxiv": collect_arxiv,
    "hn": collect_hn,
}


def collect_source(source):
    """Dispatch a single source dict to its collector function."""
    collector = COLLECTORS.get(source["type"])
    if not collector:
        logger.warning("Unknown source type '%s' for %s -- skipping", source["type"], source["name"])
        return []
    return collector(source)
