"""
Orchestrates the full pipeline: collect -> dedup -> cluster -> screen -> synthesize ->
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

from pipeline.collect import run_collection
from pipeline.client_profiles import load_profile
from pipeline.clustering import cluster_items
from pipeline.config import CLIENT_PROFILE_ID, MAX_ITEMS_PER_RUN, MIN_SCREENING_SCORE
from pipeline.dedup import load_seen, normalize_url, save_seen, filter_new, mark_seen
from pipeline.screening import screen_candidates
from pipeline.synthesize import synthesize_items
from pipeline.publish_gate import select_for_publishing
from pipeline.generate_report import generate_reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_pipeline")


def cluster_members(items, representatives):
    """Return original items belonging to selected or low-relevance clusters."""
    member_urls = {
        normalize_url(source.get("url", ""))
        for representative in representatives
        for source in representative.get("related_sources", [])
        if source.get("url")
    }
    return [item for item in items if normalize_url(item.get("url", "")) in member_urls]


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

    # Stage 3: cluster all new items before selection so duplicate coverage
    # cannot consume several places in the limited weekly processing budget.
    clustered_items = cluster_items(new_items)
    logger.info("Clustered %d new item(s) into %d candidate(s).", len(new_items), len(clustered_items))

    # Stage 4: rank every representative for the selected profile. This is
    # deterministic and cheap; the expensive model stages see only selected
    # candidates, not whichever links happened to arrive first.
    profile = load_profile(CLIENT_PROFILE_ID)
    selected, held = screen_candidates(
        clustered_items, profile, MIN_SCREENING_SCORE, MAX_ITEMS_PER_RUN
    )
    low_relevance = [item for item in held if item["screening_status"] == "low_relevance"]
    overflow = [item for item in held if item["screening_status"] == "capacity_overflow"]
    logger.info(
        "Screened %d candidate(s) for %s: %d selected, %d low relevance, %d held for a later run.",
        len(clustered_items), profile["id"], len(selected), len(low_relevance), len(overflow),
    )
    for candidate in selected:
        logger.info(
            "Selected [%d]: %s (%s)",
            candidate["screening_score"],
            candidate.get("title", "")[:60],
            "; ".join(candidate["screening_reasons"]),
        )

    # Low-relevance clusters have completed their cheap review and should not
    # recur forever. Capacity overflow remains unseen for the next cycle.
    # Selected clusters are deliberately not marked yet: if an API/model stage
    # fails below, they must retry rather than silently disappear.
    low_relevance_items = cluster_members(new_items, low_relevance)
    updated_seen = mark_seen(low_relevance_items, seen, run_ts)
    save_seen(updated_seen)
    logger.info("Dedup state saved (%d total items tracked).", len(updated_seen))

    if not selected:
        logger.info("No candidates met the profile screening threshold.")
        return

    # Stage 5: synthesize (title filter, enrichment, evidence, and critique
    # happen inside this call, per representative).
    logger.info("Synthesizing %d selected candidate(s)...", len(selected))
    insights = synthesize_items(selected, profile=profile)
    logger.info("%d insight(s) judged significant out of %d selected candidate(s).", len(insights), len(selected))

    # Synthesis completed for the selected candidates, so their clusters can
    # now be marked as seen. This preserves the prior crash-retry behavior.
    selected_items = cluster_members(new_items, selected)
    updated_seen = mark_seen(selected_items, updated_seen, run_ts)
    save_seen(updated_seen)
    logger.info("Dedup state saved after synthesis (%d total items tracked).", len(updated_seen))

    if not insights:
        logger.info("No significant insights this cycle. No posts to publish.")
        return

    # Stage 6: publish gate
    to_publish, held_back = select_for_publishing(insights)
    logger.info("%d insight(s) selected for publishing, %d held back.", len(to_publish), len(held_back))

    if not to_publish:
        logger.info("Nothing cleared the publish gate this cycle.")
        return

    # Stage 7: generate reports
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
