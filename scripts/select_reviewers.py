from __future__ import annotations

import argparse
import json
from pathlib import Path

from reviewer_config import load_reviewers_config, write_reviewers_config
from review_paper import (
    SELECTED_REVIEWERS_CONFIG,
    run_reviewer_selector,
    selected_reviewers_from_selection,
    validate_selection_output,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run only the dynamic reviewer selector for an existing parsed paper.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--parsed-dir", required=True)
    parser.add_argument("--selection-dir", required=True)
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--reviewers-config", default="config/reviewers.json")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    parsed_dir = Path(args.parsed_dir)
    if not parsed_dir.is_absolute():
        parsed_dir = repo / parsed_dir
    selection_dir = Path(args.selection_dir)
    if not selection_dir.is_absolute():
        selection_dir = repo / selection_dir
    log_dir = Path(args.log_dir)
    if not log_dir.is_absolute():
        log_dir = repo / log_dir

    reviewers_config = Path(args.reviewers_config)
    if not reviewers_config.is_absolute():
        reviewers_config = repo / reviewers_config
    reviewers = load_reviewers_config(reviewers_config)
    preflight_reviewers = [reviewer for reviewer in reviewers if reviewer.stage == "preflight"]
    standard_reviewers = [reviewer for reviewer in reviewers if reviewer.stage == "review"]
    mandatory_reviewers = [reviewer for reviewer in standard_reviewers if reviewer.selection_policy == "mandatory"]
    optional_reviewers = [reviewer for reviewer in standard_reviewers if reviewer.selection_policy == "optional"]

    selection, _started_at = run_reviewer_selector(
        repo,
        args.paper_id,
        parsed_dir,
        optional_reviewers,
        selection_dir,
        repo / "schemas" / "reviewer_selection.schema.json",
        log_dir,
    )
    errors = validate_selection_output(selection, args.paper_id, mandatory_reviewers, optional_reviewers)
    if errors:
        raise RuntimeError("Reviewer selection failed: " + "; ".join(errors))

    selected_reviewers = selected_reviewers_from_selection(selection, mandatory_reviewers, optional_reviewers)
    write_reviewers_config(selection_dir / SELECTED_REVIEWERS_CONFIG, [*preflight_reviewers, *selected_reviewers])
    print(
        json.dumps(
            {
                "paper_id": args.paper_id,
                "selected_optional_count": len(selection.get("selected_optional_reviewers", [])),
                "selected_optional_reviewers": [
                    item.get("name") for item in selection.get("selected_optional_reviewers", [])
                ],
                "selection_path": str((selection_dir / "reviewer_selection.json").relative_to(repo)),
                "selected_reviewers_config": str((selection_dir / SELECTED_REVIEWERS_CONFIG).relative_to(repo)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
