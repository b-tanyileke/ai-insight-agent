"""Summarize each source's contribution through a pipeline run.

The report is intentionally based on existing item metadata and stage outputs.
It adds observability without changing any selection or publishing decision.
"""

import json
from collections import defaultdict

from pipeline.config import DATA_DIR


REPORT_DIR = DATA_DIR / "processed"


def _source_names(items):
    """Return source names represented by raw items or clustered coverage."""
    names = set()
    for item in items:
        if item.get("source"):
            names.add(item["source"])
        for related in item.get("related_sources", []):
            if related.get("source_name"):
                names.add(related["source_name"])
    return names


def build_source_health(all_items, new_items, clustered_items, selected, held, insights, published):
    """Return source-level funnel counts for one complete or partial run."""
    report = defaultdict(lambda: {
        "collected": 0,
        "new": 0,
        "cluster_representatives": 0,
        "selected": 0,
        "low_relevance": 0,
        "capacity_overflow": 0,
        "insights": 0,
        "published": 0,
    })

    for item in all_items:
        report[item.get("source", "Unknown source")]["collected"] += 1
    for item in new_items:
        report[item.get("source", "Unknown source")]["new"] += 1
    for item in clustered_items:
        report[item.get("source", "Unknown source")]["cluster_representatives"] += 1
    for item in selected:
        for name in _source_names([item]):
            report[name]["selected"] += 1
    for item in held:
        status = item.get("screening_status")
        if status in {"low_relevance", "capacity_overflow"}:
            for name in _source_names([item]):
                report[name][status] += 1
    for insight in insights:
        report[insight.get("source_name", "Unknown source")]["insights"] += 1
    for insight in published:
        report[insight.get("source_name", "Unknown source")]["published"] += 1

    return {name: report[name] for name in sorted(report)}


def log_source_health(logger, report):
    """Write compact source-health funnel counts to the normal run log."""
    logger.info("--- Source health ---")
    for name, counts in report.items():
        logger.info(
            "%s: collected=%d new=%d clustered=%d selected=%d low=%d overflow=%d insights=%d published=%d",
            name,
            counts["collected"],
            counts["new"],
            counts["cluster_representatives"],
            counts["selected"],
            counts["low_relevance"],
            counts["capacity_overflow"],
            counts["insights"],
            counts["published"],
        )


def save_source_health(report, timestamp):
    """Save a regenerable JSON report beside other local processed artifacts."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"source_health_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
    return path
