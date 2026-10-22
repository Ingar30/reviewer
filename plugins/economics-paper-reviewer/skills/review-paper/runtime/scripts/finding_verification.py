"""Opt-in, bounded shadow verification; never edits the scored main report.

prepare/accept are deterministic and usable by native hosts. Only the explicit
run command invokes a CLI, using the existing backend adapter and saved settings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from evidence_registry import check_source, REGISTRY, sha256
from strict_json import read_json

OUTCOMES = {"confirmed", "narrowed", "unsupported", "unresolved"}


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def prepare(bundle_path: Path, ids: list[str], output: Path) -> dict:
    if not 1 <= len(ids) <= 5 or len(set(ids)) != len(ids):
        raise ValueError("Preselect one to five distinct consequential finding IDs")
    bundle = read_json(bundle_path)
    findings = {f["canonical_id"]: f for f in bundle["canonical_findings"]}
    if any(cid not in findings for cid in ids):
        raise ValueError("Unknown candidate finding")
    if any(findings[cid].get("severity") not in {"high", "medium"} for cid in ids):
        raise ValueError("Shadow verification is scoped to consequential candidates")
    decisions_path = bundle_path.with_name("editor_decisions.json")
    decisions = read_json(decisions_path) if decisions_path.exists() else None
    packet = {"version": 1, "paper_id": bundle["paper_id"], "mode": "shadow",
              "bundle_sha256": sha256(bundle_path), "selected_ids": ids,
              "candidates": [findings[cid] for cid in ids],
              "editorial_artifact": decisions,
              "instruction": "These are allegations, not ground truth. Do not start a new review or alter the main report."}
    write_new(output, packet)  # selection exists before any verifier result
    return packet


def verification_errors(data: dict, packet: dict, repo: Path) -> list[str]:
    errors = []
    if data.get("version") != 1 or data.get("paper_id") != packet["paper_id"]:
        errors.append("Wrong verification version or paper")
    if data.get("packet_sha256") != hashlib.sha256(
            json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()).hexdigest():
        errors.append("Verification belongs to another frozen candidate packet")
    if data.get("status") != "complete":
        errors.append("Optional verifier did not finish; no allegation is confirmed or removed")
    results = data.get("results", [])
    ids = [r.get("canonical_id") for r in results]
    if len(ids) != len(set(ids)) or set(ids) != set(packet["selected_ids"]):
        errors.append("Missing, duplicate or contradictory candidate outcomes")
    parsed = repo / "work" / packet["paper_id"] / "parsed"
    registry = read_json(parsed / REGISTRY)
    objects = {o["id"]: o for o in registry["objects"]}
    for result in results:
        outcome = result.get("outcome")
        if outcome not in OUTCOMES:
            errors.append("Invalid verification outcome")
        for key in ("reason", "strongest_alternative", "observation", "diagnosis", "remedy"):
            if not str(result.get(key) or "").strip():
                errors.append("Verification must separate evidence, alternatives, diagnosis and remedy")
        if result.get("editor_fidelity") not in {"faithful", "not_faithful", "unresolved", "not_applicable"}:
            errors.append("Missing semantic-fidelity judgment")
        if not result.get("editor_reason"):
            errors.append("Editorial-fidelity judgment needs a reason")
        if outcome == "narrowed" and not result.get("surviving_claim"):
            errors.append("Narrowed outcome needs its surviving claim")
        evidence = result.get("evidence", [])
        if outcome != "unresolved" and not evidence:
            errors.append("A resolved outcome needs source evidence")
        for item in evidence:
            obj = objects.get(item.get("object_id"))
            if not obj:
                errors.append("Unknown verifier evidence object")
                continue
            source = {"id": obj["id"], "object_id": obj["id"], "type": "text",
                      "path": f"work/{packet['paper_id']}/parsed/{obj['path']}",
                      "page": item["page"], "text_quote": item["quote"],
                      "correspondence": item["correspondence"], "verification_note": item["note"]}
            errors.extend(check_source(source, parsed, registry, paper_id=packet["paper_id"])["errors"])
            if item["correspondence"] == "unresolved" and outcome != "unresolved":
                errors.append("Unavailable evidence cannot resolve a candidate")
    return errors


def accept(candidate: Path, packet_path: Path, output: Path, repo: Path) -> dict:
    from jsonschema import Draft202012Validator
    data, packet = read_json(candidate), read_json(packet_path)
    schema = read_json(repo / "schemas/finding_verification.schema.json")
    errors = [e.message for e in Draft202012Validator(schema).iter_errors(data)]
    if not errors:
        errors = verification_errors(data, packet, repo)
    if errors:
        raise ValueError("Shadow verification not accepted: " + "; ".join(errors))
    record = {"version": 1, "status": "complete", "mode": "shadow",
              "packet_file_sha256": sha256(packet_path), "candidate_sha256": sha256(candidate),
              "assessment": "model/assessor judgment, not ground truth", "verification": data}
    write_new(output, record)
    return record
