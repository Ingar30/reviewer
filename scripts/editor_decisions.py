"""Validate accountable editorial decisions and render editor-authored prose.

Deterministic coverage is not semantic proof. The separately identified semantic
verdicts are assessor/model judgments, bound to this draft, and retained as such.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from strict_json import read_json

DISPOSITIONS = {"included", "merged", "rejected", "narrowed", "appendix_only"}
TRACEABILITY = "Appendix: Traceability Map"


def prose_errors(text: str) -> list[str]:
    """The renderer owns section boundaries; validate each authored fragment."""
    errors = []
    if re.search(r"(?m)^ {0,3}#{1,2}(?:\s|$)|^\S[^\n]*\n {0,3}(?:=+|-+)[ \t]*(?:\n|$)", text):
        errors.append("Authored prose cannot replace document/section boundaries")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip().startswith("|") or (index and lines[index-1].strip().startswith("|")):
            continue
        cells = re.split(r"(?<!\\)\|", line.strip().strip("|"))
        separator = lines[index+1].strip() if index+1 < len(lines) else ""
        delimiters = re.split(r"(?<!\\)\|", separator.strip("|"))
        if (not separator.startswith("|") or len(cells) != len(delimiters)
                or not all(re.fullmatch(r"\s*:?-{3,}:?\s*", c) for c in delimiters)):
            errors.append("Markdown table header needs a matching delimiter row in the same prose fragment")
    return errors


def material(finding: dict) -> bool:
    return finding.get("severity") in {"high", "medium"} and finding.get("issue_class") in {
        "manuscript_issue", "reference_integrity", "cannot_verify"}


def decision_errors(artifact: dict, bundle: dict, *, semantic_verdicts=None,
                    trusted_assessor: str = "editor_model") -> list[str]:
    errors = []
    if artifact.get("version") != 1 or artifact.get("paper_id") != bundle.get("paper_id"):
        errors.append("Editorial version or paper identity does not match")
    findings = {f["canonical_id"]: f for f in bundle["canonical_findings"]}
    blocks = {}
    for block in artifact.get("blocks", []):
        key = block.get("id")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,79}", key) or key in blocks:
            errors.append("Missing/duplicate/invalid report block ID")
        blocks[key] = block
        if (not str(block.get("section") or "").strip() or block["section"] == TRACEABILITY
                or re.search(r"[\r\n]", block["section"]) or block["section"].lstrip().startswith("#")):
            errors.append("Report blocks need a section other than the generated traceability appendix")
        errors.extend(prose_errors(block.get("markdown", "")))
    decisions = {}
    for decision in artifact.get("decisions", []):
        cid = decision.get("canonical_id")
        if cid not in findings or cid in decisions:
            errors.append("Unknown or duplicate editorial disposition: " + str(cid))
        decisions[cid] = decision
        errors.extend(prose_errors(decision.get("treatment", "")))
        disposition = decision.get("disposition")
        if disposition not in DISPOSITIONS:
            errors.append("Unknown editorial disposition")
        if not str(decision.get("reason") or "").strip():
            errors.append("Every disposition needs a finding-specific evidence-based reason")
        block_ids = decision.get("block_ids", [])
        if len(block_ids) != len(set(block_ids)) or any(b not in blocks for b in block_ids):
            errors.append("Disposition references missing/duplicate report blocks")
        if disposition in {"included", "narrowed", "appendix_only"}:
            if len(block_ids) != 1 or not str(decision.get("treatment") or "").strip():
                errors.append("Substantive disposition needs one rendered block and finding-specific treatment")
            if decision.get("destination") is not None:
                errors.append("Only merged dispositions may name a destination")
            if disposition == "appendix_only" and any(not blocks.get(b, {}).get("section", "").startswith("Appendix:") for b in block_ids):
                errors.append("Appendix-only disposition must name an actual appendix block")
            if disposition == "narrowed" and not str(decision.get("surviving_claim") or "").strip():
                errors.append("Narrowing requires the surviving claim")
        elif disposition == "rejected":
            if block_ids or decision.get("destination") is not None or decision.get("treatment"):
                errors.append("Rejected claims cannot masquerade as included report treatment")
        elif disposition == "merged":
            if block_ids or decision.get("destination") not in findings or decision.get("destination") == cid:
                errors.append("Merge needs an existing distinct destination, not a report-block claim")
            if not decision.get("retained_evidence") or not decision.get("qualifications"):
                errors.append("Merge must explicitly account for retained evidence and qualifications")
    for cid in findings.keys() - decisions.keys():
        errors.append("Missing terminal editorial disposition: " + cid)
    # Introductions are optional when a retained finding supplies the block's
    # rendered content. IDs, merges and rejected claims cannot fill an empty block.
    treated_blocks = {d["block_ids"][0] for cid, d in decisions.items()
                      if cid in findings and d.get("disposition") in {"included", "narrowed", "appendix_only"}
                      and len(d.get("block_ids", [])) == 1 and str(d.get("treatment") or "").strip()}
    for key, block in blocks.items():
        if not str(block.get("markdown") or "").strip() and key not in treated_blocks:
            errors.append("Report block has no rendered prose or finding treatment")
    for cid, decision in decisions.items():
        if decision.get("disposition") != "merged":
            continue
        seen, target = {cid}, decision.get("destination")
        while target in decisions and decisions[target].get("disposition") == "merged":
            if target in seen:
                errors.append("Cyclic editorial merge")
                break
            seen.add(target)
            target = decisions[target].get("destination")
        if target not in decisions or decisions[target].get("disposition") not in {"included", "narrowed", "appendix_only"}:
            errors.append("Merge has no substantively retained terminal destination")
    # No keyword/length heuristic substitutes for an assessor's semantic check.
    verdicts = artifact.get("semantic_checks", []) if semantic_verdicts is None else semantic_verdicts
    checked = {}
    for verdict in verdicts:
        cid = verdict.get("canonical_id")
        if cid in checked or cid not in findings:
            errors.append("Unknown or duplicate semantic assessment")
        checked[cid] = verdict
        # Model-authored claims never establish independent/human identity.
        # External verdicts, when supplied by a trusted caller, remain separate.
        if (trusted_assessor not in {"editor_model", "independent_model", "human"}
                or not verdict.get("reason") or verdict.get("assessor") != trusted_assessor):
            errors.append("Semantic check must identify its assessor and source-based reasoning")
        if verdict.get("verdict") != "faithful":
            errors.append("Semantic treatment is not accepted: " + str(cid))
    for cid, finding in findings.items():
        if material(finding) and cid not in checked:
            errors.append("Consequential finding lacks a semantic-fidelity assessment: " + cid)
    return errors


def cell(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def render(artifact: dict, bundle: dict) -> str:
    failures = decision_errors(artifact, bundle)
    if failures:
        raise ValueError("; ".join(failures))
    text = ["# Multi-Agent Paper Review Report\n"]
    section = None
    for block in artifact["blocks"]:
        if block["section"] != section:
            section = block["section"]
            text.append("## " + section + "\n")
        if block["markdown"].strip():
            text.append(block["markdown"].strip() + "\n")
        # Treatments are rendered, not merely asserted in an ID map.
        for decision in artifact["decisions"]:
            if block["id"] in decision["block_ids"] and decision["treatment"]:
                text.append(decision["treatment"].strip() + "\n")
    text.append("## " + TRACEABILITY + "\n")
    text.append("| Report section | Finding | Canonical ID | Source finding IDs | Disposition and evidence-based reason |\n"
                "| --- | --- | --- | --- | --- |")
    by_id = {d["canonical_id"]: d for d in artifact["decisions"]}
    blocks = {b["id"]: b for b in artifact["blocks"]}
    for finding in bundle["canonical_findings"]:
        cid = finding["canonical_id"]
        d = by_id[cid]
        target = d
        while target["disposition"] == "merged":
            target = by_id[target["destination"]]
        sections = "; ".join(blocks[b]["section"] for b in target["block_ids"])
        ids = "; ".join(f"{s['reviewer']}:{s['id']}" for s in finding["source_findings"])
        text.append("| " + " | ".join(map(cell, [sections or "Not included", finding["finding_summary"], cid, ids,
            d["disposition"] + ": " + d["reason"]])) + " |")
    if not bundle["canonical_findings"]:
        text.append("No findings were reported by the completed audits.")
    return "\n".join(text).rstrip() + "\n"


def assemble(candidate: Path, bundle_path: Path, report_path: Path, schema_path: Path) -> dict:
    from jsonschema import Draft202012Validator
    artifact = read_json(candidate)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = [e.message for e in Draft202012Validator(schema).iter_errors(artifact)]
    if errors:
        raise ValueError("Invalid editorial artifact: " + "; ".join(errors))
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    text = render(artifact, bundle)
    from check_final_report import report_failures
    errors = report_failures(text, bundle=bundle, min_chars=0)
    if errors:
        raise ValueError("Invalid rendered report: " + "; ".join(errors))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    pending = report_path.with_suffix(".md.pending")
    pending.write_text(text, encoding="utf-8")
    pending.replace(report_path)
    receipt = {"version": 1, "editor_decisions_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
               "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
               "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
               "semantic_assessor": "editor_model",
               "semantic_assessment": "assessor judgment, not a deterministic guarantee"}
    candidate.with_name("editor_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt
