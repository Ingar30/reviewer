"""Synthetic contract fixtures shared by offline process doubles only."""
import json
from pathlib import Path
import sys


def review_payload(root, paper_id, name, status="ok"):
    sys.path.insert(0, str(Path(root) / "scripts"))
    from review_coverage import assignments
    parsed = Path(root) / "work" / paper_id / "parsed"
    coverage = [{"item_id": i["id"], "source_object_ids": i["object_ids"], "claim": None,
        "check_performed": "MOCK: " + i["check"], "status": "checked_no_issue", "reason": "Synthetic exhaustive scope",
        "finding_ids": [], "attempted": True, "importance": "central", "scope": "exhaustive"}
        for i in assignments(name, parsed)]
    if name == "claim_evidence_auditor":
        registry = json.loads((parsed / "source_registry.json").read_text(encoding="utf-8"))
        oid = next(o["id"] for o in registry["objects"] if o["path"] == "pages/page_001.md")
        coverage.append({**coverage[0], "item_id": "claim:synthetic", "source_object_ids": [oid],
                         "claim": "Synthetic no-causal-claim control"})
    return {"reviewer": name, "paper_id": paper_id, "run_status": status,
            "summary": "MOCK audit, not scholarly validation", "findings": [], "notes": [],
            "completion": {"version": 1, "state": "complete", "scope_description": "Synthetic remit",
                           "checks_completed": ["Synthetic required checks"], "missing_checks": [],
                           "evidence_limitations": ["Web unavailable"] if status == "cannot_verify" else []},
            "coverage": coverage}


def editor_payload(bundle, lite=False):
    headings = ["Executive Summary", "Highest-Priority Cross-Agent Findings",
                "Suggested Revision Priorities", "Additional Findings", "Appendix: Review Scope and Limitations"]
    artifact = {"version": 1, "paper_id": bundle["paper_id"], "blocks": [
        {"id": f"block-{i}", "section": heading,
         "markdown": "MOCK report: synthetic workflow test, not scientific validation." + (" Lite mode." if lite else "")}
        for i, heading in enumerate(headings)], "decisions": [], "semantic_checks": []}
    for finding in bundle["canonical_findings"]:
        artifact["decisions"].append({"canonical_id": finding["canonical_id"], "disposition": "included",
            "block_ids": ["block-3"], "destination": None, "treatment": finding["finding_summary"],
            "reason": "Synthetic supplied evidence supports this narrow observation", "surviving_claim": None,
            "retained_evidence": ["Synthetic signed estimate"], "qualifications": ["Synthetic only"]})
        artifact["semantic_checks"].append({"canonical_id": finding["canonical_id"], "verdict": "faithful",
            "assessor": "editor_model", "reason": "MOCK semantic verdict, not an actual assessment"})
    return artifact
