"""
Entry point for the collection stage.

Run standalone: python -m pipeline.collect
(module invocation, run from the repo root, needed now that this file
lives inside the pipeline/ package)
Writes one JSON file per run to data/raw/<timestamp>.json containing
every item pulled from every source that cycle (pre-dedup, pre-filter --
that happens in the next stage).
"""

import json
import logging
from datetime import datetime, timezone

from pipeline.config import SOURCES, DATA_DIR as BASE_DATA_DIR
from pipeline.collectors import collect_source

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("collect")

DATA_DIR = BASE_DATA_DIR / "raw"


def run_collection():
    all_items = []
    source_results = {}

    for source in SOURCES:
        items = collect_source(source)
        source_results[source["name"]] = len(items)
        all_items.extend(items)

    # Summary -- makes it obvious at a glance which sources are healthy
    logger.info("--- Collection summary ---")
    for name, count in source_results.items():
        status = "OK" if count > 0 else "EMPTY/FAILED"
        logger.info("  %-40s %3d items  [%s]", name, count, status)
    logger.info("Total raw items collected: %d", len(all_items))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = DATA_DIR / f"{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)

    logger.info("Wrote %s", out_path)
    return out_path, all_items


if __name__ == "__main__":
    run_collection()
