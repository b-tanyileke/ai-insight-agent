"""Run fixture-based checks for deterministic candidate screening.

Usage: ``python -m pipeline.evaluate``. This command never contacts sources
or models; it validates expected screening outcomes for reviewed examples.
"""

import json
import sys
from pathlib import Path

from pipeline.client_profiles import load_profile
from pipeline.config import MIN_SCREENING_SCORE
from pipeline.screening import score_item


CASE_PATH = Path(__file__).resolve().parent.parent / "data" / "evaluation" / "screening_cases.json"


def evaluate_screening_cases(path=CASE_PATH, minimum_score=MIN_SCREENING_SCORE):
    """Return one result per fixture case and whether every expectation passed."""
    with open(path, "r", encoding="utf-8") as file:
        cases = json.load(file)

    results = []
    for case in cases:
        score, reasons = score_item(case["item"], load_profile(case["profile_id"]))
        expected_selected = case["expected_selected"]
        actual_selected = score >= minimum_score
        results.append({
            "id": case["id"],
            "expected_selected": expected_selected,
            "actual_selected": actual_selected,
            "score": score,
            "reasons": reasons,
            "passed": actual_selected == expected_selected,
        })
    return results, all(result["passed"] for result in results)


def main():
    """Print results and return a non-zero exit status for a failed baseline."""
    results, passed = evaluate_screening_cases()
    for result in results:
        outcome = "PASS" if result["passed"] else "FAIL"
        print(
            f"{outcome} {result['id']}: score={result['score']} "
            f"selected={result['actual_selected']} ({'; '.join(result['reasons'])})"
        )
    print(f"\nScreening evaluation: {sum(result['passed'] for result in results)}/{len(results)} passed")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
