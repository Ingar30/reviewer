"""A compact assignment/check ledger. Opening a file never establishes coverage."""
from __future__ import annotations

import json
from pathlib import Path


def assignments(reviewer: str, parsed: Path) -> list[dict]:
    items = [{"id": "assigned_remit", "required": True,
              "check": "Complete the role-specific checks in the supplied reviewer prompt", "object_ids": []}]
    registry_path = parsed / "source_registry.json"
    if not registry_path.is_file():
        return items
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    # Keep display assignments bounded at the display, not every duplicate cell.
    if reviewer in {"source_consistency_auditor", "numerical_auditor", "parser_quality_auditor"}:
        for obj in registry["objects"]:
            display = ((obj["path"].startswith("tables/") and obj["path"].endswith(".md"))
                       or (obj["path"].startswith("figures/") and obj["path"].endswith(".txt")))
            if obj["kind"] == "text_span" and display:
                items.append({"id": "display:" + obj["id"], "required": True,
                    "check": "Check this retained display within the assigned remit, including matching appendix context",
                    "object_ids": [obj["id"]]})
    if reviewer in {"model_equation_auditor", "theory_logic_auditor"}:
        crossrefs = parsed / "crossrefs.json"
        if crossrefs.exists():
            seen = set()
            for ref in json.loads(crossrefs.read_text(encoding="utf-8")):
                if str(ref.get("kind", "")).lower().rstrip(".") not in {"equation", "eq"}:
                    continue
                page = ref.get("page") or ref.get("pdf_page_number")
                label = str(ref.get("label") or ref.get("target") or "equation")
                key = f"equation:{page}:{label}"
                if key not in seen:
                    seen.add(key)
                    objects = [o["id"] for o in registry["objects"] if o["page"] == page and o["path"].startswith("pages/")]
                    items.append({"id": key, "required": True, "check": "Check the cited equation and surrounding assumptions", "object_ids": objects})
    return items


def coverage_errors(data: dict, parsed: Path) -> list[str]:
    records = data.get("coverage")
    if not isinstance(records, list) or not records:
        return ["Coverage ledger is missing; empty findings do not prove completed review"]
    errors, seen = [], set()
    required = {i["id"]: i for i in assignments(data["reviewer"], parsed)}
    registry_path = parsed / "source_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {"objects": []}
    objects = {o["id"] for o in registry["objects"]}
    findings = {f["id"] for f in data["findings"]}
    complete = (data.get("completion") or {}).get("state") in {"complete", "not_applicable"}
    for record in records:
        key = record.get("item_id")
        if key in seen:
            errors.append("Duplicate coverage item: " + str(key))
        seen.add(key)
        # An attempted scope check may establish that no manuscript claim exists.
        # Do not force the reviewer to invent claim text for that honest absence.
        # Source links, attempted work and a reason are still required below.
        absent_claim = (record.get("status") == "not_applicable"
                        and record.get("claim") is None)
        if key not in required and not (isinstance(key, str) and key.startswith("claim:")
                                       and (record.get("claim") or absent_claim)):
            errors.append("Unknown coverage item; new source-linked claims need claim: IDs")
        ids = record.get("source_object_ids", [])
        if set(ids) - objects:
            errors.append("Coverage references unknown source objects")
        if key in required and not set(required[key]["object_ids"]).issubset(ids):
            errors.append("Coverage omits its assigned source objects")
        if isinstance(key, str) and key.startswith("claim:") and not ids:
            errors.append("Added central/peripheral claims must link manuscript evidence")
        status = record.get("status")
        if status in {"cannot_verify", "not_applicable", "not_checked"} and not record.get("reason"):
            errors.append("Coverage exclusions and limitations need an explicit reason")
        if status not in {"not_checked"} and (record.get("attempted") is not True or not record.get("check_performed")):
            errors.append("Claimed coverage needs the actual attempted check, not file access")
        if complete and (key in required or record.get("importance") == "central") and status == "not_checked":
            errors.append("Required/central unattempted work contradicts completion")
        if set(record.get("finding_ids", [])) - findings:
            errors.append("Coverage references unknown findings")
        if (status == "linked_finding") != bool(record.get("finding_ids")):
            errors.append("Linked-finding coverage must agree with its finding IDs")
        if record.get("scope") == "sampled" and not record.get("reason"):
            errors.append("Sampled coverage must state its scope and limitations")
    for key in required.keys() - seen:
        errors.append("Unaddressed required coverage item: " + key)
    if (data["reviewer"] == "claim_evidence_auditor" and complete
            and (data.get("completion") or {}).get("state") != "not_applicable"
            and not any(r.get("importance") == "central" and str(r.get("item_id")).startswith("claim:")
                        and r.get("claim") and r.get("status") != "not_applicable" for r in records)):
        errors.append("Claim-evidence audit must identify and check source-linked central claims")
    return errors


def ledger(reviews: dict) -> dict:
    return {"version": 1, "coverage_is": "reviewer-recorded checks, not access logs or independent proof",
            "reviewers": [{"reviewer": name, "completion": data.get("completion"),
                           "items": data.get("coverage", [])} for name, data in reviews.items()]}
