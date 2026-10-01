"""Score source-adjudicated benchmark findings offline; never infer correctness from text overlap."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def ratio(top, bottom):
    return top / bottom if bottom else None


def score(packet: Path, references: Path, key_path: Path) -> dict:
    samples = read(packet / "samples.json")
    key = read(key_path)
    reference_sha = hashlib.sha256(references.read_bytes()).hexdigest()
    metadata = read(packet / "packet.json") if (packet / "packet.json").exists() else {}
    if metadata.get("reference_sha256") and reference_sha != metadata["reference_sha256"]:
        raise ValueError("Reference ledger differs from the frozen benchmark packet")
    reference = read(references)["issues"]
    truth = [item for item in reference if item.get("status") == "confirmed"]
    seen = set()
    for item in truth:
        identity = (item["case"], item["issue_key"])
        if identity in seen or not item.get("source") or not item.get("roles"):
            raise ValueError("Reference issues need unique case/issue keys, role scope and checked source locations")
        if type(item.get("weight")) not in (int, float) or not 0 < item["weight"] <= 5:
            raise ValueError("Reference weights must be fixed in advance, greater than 0 and at most 5")
        seen.add(identity)
    with (packet / "ratings.csv").open(encoding="utf-8-sig", newline="") as stream:
        ratings = list(csv.DictReader(stream))
    expected = set()
    for sample in samples:
        if sample["status"] == "complete":
            expected.update((sample["sample_id"], f["id"]) for f in read(packet / f"{sample['sample_id']}.json")["findings"])
    supplied = [(r["sample_id"], r["finding_id"]) for r in ratings]
    if len(supplied) != len(set(supplied)) or set(supplied) != expected:
        raise ValueError("Every finding must have exactly one rating; missing, duplicate or extra rows are not scored")
    allowed = {"confirmed", "false_positive", "unresolved", "suggestion"}
    for row in ratings:
        if row["verdict"] not in allowed or not row["issue_key"].strip() or not row["source_check_notes"].strip():
            raise ValueError("Finish source checking: each rating needs verdict, deduplicated issue_key and source_check_notes")
        if row["evidence_correct"] not in ("true", "false", "unknown") or row["actionability"] not in ("0", "1", "2"):
            raise ValueError("Use evidence_correct=true/false/unknown and actionability=0/1/2")
    scored = []
    for sample in samples:
        sample_id = sample["sample_id"]
        job = key[sample_id]["job"]
        result = key[sample_id]["result"]
        record = {**sample, "profile": job["profile"], "repeat": job["repeat"],
                  "elapsed_seconds": result.get("elapsed_seconds"), "usage": result.get("usage"),
                  "cli_version": result.get("cli_version"),
                  "reported_settings": result.get("cli_reported_settings")}
        if sample["status"] != "complete":
            scored.append(record)
            continue
        rows = [r for r in ratings if r["sample_id"] == sample_id]
        unique = {}
        for row in rows:
            issue = row["issue_key"]
            if issue in unique and unique[issue]["verdict"] != row["verdict"]:
                raise ValueError("Conflicting verdicts for one issue cluster in one sample")
            unique.setdefault(issue, row)
        confirmed = {issue for issue, row in unique.items() if row["verdict"] == "confirmed"}
        false_positives = sum(r["verdict"] == "false_positive" for r in unique.values())
        unresolved = sum(r["verdict"] == "unresolved" for r in unique.values())
        scoped = [item for item in truth if item["case"] == sample["case"] and sample["role"] in item["roles"]]
        hits = [item for item in scoped if item["issue_key"] in confirmed]
        checked_evidence = [r for r in rows if r["evidence_correct"] != "unknown"]
        total_claims = len(confirmed) + false_positives + unresolved
        record.update(
            confirmed_unique=len(confirmed), false_positive_unique=false_positives, unresolved_unique=unresolved,
            duplicate_rows=len(rows) - len(unique),
            suggestion_unique=sum(r["verdict"] == "suggestion" for r in unique.values()),
            precision_resolved=ratio(len(confirmed), len(confirmed) + false_positives),
            precision_lower_bound=ratio(len(confirmed), total_claims),
            precision_upper_bound=ratio(len(confirmed) + unresolved, total_claims),
            reference_issue_count=len(scoped), reference_hits=len(hits),
            known_issue_recall=ratio(len(hits), len(scoped)),
            weighted_known_issue_recall=ratio(sum(i["weight"] for i in hits), sum(i["weight"] for i in scoped)),
            evidence_accuracy=ratio(sum(r["evidence_correct"] == "true" for r in checked_evidence), len(checked_evidence)),
            mean_actionability=statistics.mean(int(r["actionability"]) for r in rows) if rows else None,
        )
        scored.append(record)
    all_profiles = {row["profile"] for row in scored}
    cell_key = lambda row: (row["case"], row["role"], row["repeat"])
    paired = {cell_key(row) for row in scored if
              {r["profile"] for r in scored if cell_key(r) == cell_key(row) and r["status"] == "complete"} == all_profiles}
    profiles = {}
    for profile in sorted({row["profile"] for row in scored}):
        group = [r for r in scored if r["profile"] == profile]
        complete = [r for r in group if r["status"] == "complete"]
        attempted = [r for r in group if r["status"] != "not-run"]
        matched = [r for r in complete if cell_key(r) in paired]
        def macro(metric):
            values = [r[metric] for r in matched if r.get(metric) is not None]
            return {"mean": statistics.mean(values) if values else None, "defined_cells": len(values)}
        # Publish cells/replicates, not a spurious independent-finding significance test.
        profiles[profile] = {"planned": len(group), "attempted": len(attempted), "complete": len(complete),
                             "completion_rate_attempted": ratio(len(complete), len(attempted)),
                             "planned_coverage": ratio(len(complete), len(group)),
                             "matched_complete_cells": len(matched),
                             "precision_resolved_macro": macro("precision_resolved"),
                             "known_issue_recall_macro": macro("known_issue_recall"),
                             "weighted_known_issue_recall_macro": macro("weighted_known_issue_recall") }
    return {"profiles": profiles, "cells": scored,
            "references_sha256": reference_sha,
            "ratings_sha256": hashlib.sha256((packet / "ratings.csv").read_bytes()).hexdigest(),
            "confirmed_reference_issues": len(truth), "unconfirmed_reference_issues_excluded": len(reference) - len(truth),
            "interpretation": "Precision is adjudicated, recall is against known checked issues only. No automatic ranking; compare matched paper/role/repeat cells and failures. Novel valid issues count for precision, not an invented complete recall denominator."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output file; preserve earlier adjudication results")
    try:
        result = score(args.packet, args.references, args.key)
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["profiles"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
