"""
Orchestrates the full pipeline: collect -> dedup -> synthesize ->
publish_gate -> generate_report. This is the single entry point the
GitHub Actions cron job calls.

State (seen.json) is only persisted to disk AFTER synthesis completes for
this run's new items -- if the run crashes before that point, seen.json
is left untouched, so those items get retried next cycle rather than
silently vanishing. Some wasted quota on a retry is an acceptable cost;
silently losing items is not.
"""

import logging
import sys
from datetime import datetime, timezone

from collect import run_collection
from config import MAX_ITEMS_PER_RUN
from dedup import load_seen, save_seen, filter_new, mark_seen
from synthesize import synthesize_items
from publish_gate import select_for_publishing
from generate_report import generate_reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_pipeline")


def run():
    run_ts = datetime.now(timezone.utc).isoformat()
    logger.info("=== Pipeline run started: %s ===", run_ts)

    # Stage 1: collect
    _, all_items = run_collection()
    if not all_items:
        logger.warning("No items collected this cycle -- check source health above. Nothing to do.")
        return

    # Stage 2: dedup
    seen = load_seen()
    new_items, _ = filter_new(all_items, seen, run_ts)
    if not new_items:
        logger.info("No new items since last run. Nothing to synthesize.")
        return

    # Cap how many we actually process this run -- bounds runtime/quota and
    # guarantees forward progress even on a large backlog. Overflow items
    # are simply left un-marked, so they reappear as "new" next run.
    batch = new_items[:MAX_ITEMS_PER_RUN]
    overflow = len(new_items) - len(batch)
    if overflow > 0:
        logger.info(
            "%d new item(s) found -- processing %d this run (cap=%d), %d left for future run(s).",
            len(new_items), len(batch), MAX_ITEMS_PER_RUN, overflow,
        )

    # Stage 3: synthesize (title filter + enrichment + sufficiency gate all
    # happen inside this call, per-item)
    logger.info("Synthesizing %d item(s)...", len(batch))
    insights = synthesize_items(batch)
    logger.info("%d insight(s) judged significant out of %d processed.", len(insights), len(batch))

    # Persist dedup state now, for exactly the batch we processed -- not
    # the full new_items list. If the run were to crash before this point,
    # nothing gets marked seen and the whole batch retries next run; if it
    # crashes after, only the un-processed overflow remains for next run.
    updated_seen = mark_seen(batch, seen, run_ts)
    save_seen(updated_seen)
    logger.info("Dedup state saved (%d total items tracked).", len(updated_seen))

    if not insights:
        logger.info("No significant insights this cycle. No posts to publish.")
        return

    # Stage 4: publish gate
    to_publish, held_back = select_for_publishing(insights)
    logger.info("%d insight(s) selected for publishing, %d held back.", len(to_publish), len(held_back))

    if not to_publish:
        logger.info("Nothing cleared the publish gate this cycle.")
        return

    # Stage 5: generate reports
    written = generate_reports(to_publish)
    logger.info("=== Pipeline run complete: %d post(s) written ===", len(written))
    for p in written:
        logger.info("  - %s", p)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception(
            "Pipeline run failed with an unhandled exception. "
            "seen.json was not updated for this run if the crash happened before the synthesis stage completed."
        )
        sys.exit(1)
