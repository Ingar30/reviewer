from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from render_prompts import render_template
from review_paper import codex_command, repo_root, require_fresh_file, run_required


DEFAULT_SCHEMA = "schemas/parser_repair_plan.schema.json"
DEFAULT_TEMPLATE = "prompts/templates/parser_repair_plan.txt"
PLAN_FILENAME = "parser_repair_plan.json"
NOTES_FILENAME = "parser_repair_notes.md"
MANIFEST_FILENAME = "repair_manifest.json"
REPAIRED_ARTIFACTS_DIR = "repaired_artifacts"

SAFE_ARTIFACT_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
NUL_CODEPOINT_RE = re.compile("\x00([0-9A-Fa-f]{2,6})")
MOJIBAKE_MARKERS = ("Ã", "Â", "â", "ï¿½", "\ufffd")
TEXT_SOURCE_SUFFIXES = {".csv", ".json", ".md", ".txt"}
MAX_SOURCE_CHARS = 200_000


def repo_relative(path: Path, repo: Path) -> str:
    try:
        return str(path.relative_to(repo))
    except ValueError:
        return str(path)


def validate_plan(plan: dict[str, Any], schema_path: Path, paper_id: str) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = [error.message for error in validator.iter_errors(plan)]
    if plan.get("paper_id") != paper_id:
        errors.append(f"paper_id={plan.get('paper_id')!r}, expected {paper_id!r}")
    return errors


def repaired_artifacts(plan: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    artifacts: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for repair in plan.get("repairs", []):
        if not isinstance(repair, dict):
            continue
        for artifact in repair.get("repaired_artifacts") or []:
            if isinstance(artifact, dict):
                artifacts.append((repair, artifact))
    return artifacts


def validate_artifact_filenames(plan: dict[str, Any]) -> list[str]:
    errors = []
    filenames: list[str] = []
    for _repair, artifact in repaired_artifacts(plan):
        filename = artifact.get("filename")
        if not isinstance(filename, str) or not SAFE_ARTIFACT_FILENAME_RE.fullmatch(filename):
            errors.append(f"invalid repaired artifact filename: {filename!r}")
            continue
        filenames.append(filename)
    duplicates = sorted({filename for filename in filenames if filenames.count(filename) > 1})
    for filename in duplicates:
        errors.append(f"duplicate repaired artifact filename: {filename}")
    return errors


def mojibake_score(text: str) -> int:
    return sum(text.count(marker) for marker in MOJIBAKE_MARKERS)


def repair_mojibake_text(text: str) -> tuple[str, bool]:
    fixed_lines: list[str] = []
    changed = False
    for line in text.splitlines(keepends=True):
        try:
            candidate = line.encode("cp1252").decode("utf-8")
        except UnicodeError:
            fixed_lines.append(line)
            continue
        if mojibake_score(candidate) < mojibake_score(line) and "\ufffd" not in candidate:
            fixed_lines.append(candidate)
            changed = changed or candidate != line
        else:
            fixed_lines.append(line)
    return "".join(fixed_lines), changed


def control_char_score(text: str) -> int:
    return sum(1 for char in text if ord(char) < 32 and char not in "\n\r\t")


def repair_nul_codepoints(text: str) -> tuple[str, bool]:
    def replace(match: re.Match[str]) -> str:
        value = int(match.group(1), 16)
        return chr(value) if 32 <= value <= 0x10FFFF else match.group(0)

    fixed = NUL_CODEPOINT_RE.sub(replace, text)
    return fixed, fixed != text


def source_mojibake_score(source_paths: list[str], repo: Path) -> int | None:
    scores = []
    for source_path in source_paths:
        path = Path(source_path)
        if not path.is_absolute():
            path = repo / path
        if path.suffix.lower() not in TEXT_SOURCE_SUFFIXES or not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")[:MAX_SOURCE_CHARS]
        except UnicodeError:
            continue
        scores.append(mojibake_score(text))
    if not scores:
        return None
    return sum(scores)


def write_repaired_artifacts(plan: dict[str, Any], output_dir: Path, repo: Path) -> dict[str, Any]:
    artifacts_dir = output_dir / REPAIRED_ARTIFACTS_DIR
    manifest_path = output_dir / MANIFEST_FILENAME
    manifest: dict[str, Any] = {
        "paper_id": plan.get("paper_id"),
        "repair_mode": plan.get("repair_mode", "plan"),
        "artifact_count": 0,
        "quality_warnings": [],
        "artifacts": [],
    }
    artifact_items = repaired_artifacts(plan)
    if artifact_items:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
    for repair, artifact in artifact_items:
        filename = artifact["filename"]
        output_path = artifacts_dir / filename
        raw_content = str(artifact["content"])
        raw_score = mojibake_score(raw_content)
        raw_control_score = control_char_score(raw_content)
        content, normalized_mojibake = repair_mojibake_text(raw_content)
        content, normalized_control_codepoints = repair_nul_codepoints(content)
        repaired_score = mojibake_score(content)
        repaired_control_score = control_char_score(content)
        artifact["content"] = content.rstrip()
        if normalized_mojibake:
            caveats = artifact.setdefault("caveats", [])
            normalization_note = "Common UTF-8/CP1252 mojibake was normalized deterministically before writing."
            if normalization_note not in caveats:
                caveats.append(normalization_note)
        if normalized_control_codepoints:
            caveats = artifact.setdefault("caveats", [])
            normalization_note = "NUL-prefixed Unicode codepoints were normalized deterministically before writing."
            if normalization_note not in caveats:
                caveats.append(normalization_note)
        source_score = source_mojibake_score(artifact.get("source_paths", []), repo)
        warnings = []
        if repaired_score and (source_score is None or repaired_score > source_score):
            warnings.append("suspicious_mojibake_remaining")
            manifest["quality_warnings"].append(
                {
                    "path": repo_relative(output_path, repo),
                    "warning": "suspicious_mojibake_remaining",
                    "mojibake_score": repaired_score,
                    "source_mojibake_score": source_score,
                }
            )
        if repaired_control_score:
            warnings.append("control_characters_remaining")
            manifest["quality_warnings"].append(
                {
                    "path": repo_relative(output_path, repo),
                    "warning": "control_characters_remaining",
                    "control_char_score": repaired_control_score,
                }
            )
        output_path.write_text(content.rstrip() + "\n", encoding="utf-8")
        digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
        manifest["artifacts"].append(
            {
                "parser_finding_id": repair.get("parser_finding_id"),
                "path": repo_relative(output_path, repo),
                "artifact_type": artifact.get("artifact_type"),
                "description": artifact.get("description"),
                "source_paths": artifact.get("source_paths", []),
                "confidence": artifact.get("confidence"),
                "caveats": artifact.get("caveats", []),
                "quality": {
                    "mojibake_score_before": raw_score,
                    "mojibake_score_after": repaired_score,
                    "source_mojibake_score": source_score,
                    "normalized_mojibake": normalized_mojibake,
                    "control_char_score_before": raw_control_score,
                    "control_char_score_after": repaired_control_score,
                    "normalized_control_codepoints": normalized_control_codepoints,
                    "warnings": warnings,
                },
                "sha256": digest,
                "bytes": output_path.stat().st_size,
            }
        )
    manifest["artifact_count"] = len(manifest["artifacts"])
    manifest["quality_summary"] = {
        "normalized_mojibake_artifact_count": sum(
            1 for artifact in manifest["artifacts"] if artifact["quality"]["normalized_mojibake"]
        ),
        "normalized_control_codepoint_artifact_count": sum(
            1 for artifact in manifest["artifacts"] if artifact["quality"]["normalized_control_codepoints"]
        ),
        "warning_count": len(manifest["quality_warnings"]),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def repair_notes_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Parser Repair Notes",
        "",
        f"Paper: `{plan.get('paper_id', 'unknown')}`",
        "",
        str(plan.get("reviewer_brief", "")).strip(),
        "",
        "## Repairs",
        "",
    ]
    for repair in plan.get("repairs", []):
        generated = repair.get("repaired_artifacts") or []
        lines.extend(
            [
                f"### {repair.get('parser_finding_id', 'unknown finding')}",
                "",
                f"- Status: `{repair.get('status', 'unknown')}`",
                f"- Action: `{repair.get('action', 'unknown')}`",
                f"- Guidance: {repair.get('reviewer_guidance', '')}",
                f"- Residual risk: {repair.get('residual_risk', '')}",
            ]
        )
        if generated:
            lines.append("- Repaired overlay artifacts:")
            for artifact in generated:
                filename = artifact.get("filename", "unknown")
                lines.append(
                    "  - `{}` ({}, confidence: {}): {}".format(
                        filename,
                        artifact.get("artifact_type", "unknown"),
                        artifact.get("confidence", "unknown"),
                        artifact.get("description", ""),
                    )
                )
                caveats = artifact.get("caveats") or []
                if caveats:
                    lines.append("    Caveats: " + "; ".join(str(item) for item in caveats))
        preferred = repair.get("preferred_source_paths") or []
        if preferred:
            lines.append("- Prefer these artifacts:")
            lines.extend(f"  - `{path}`" for path in preferred)
        avoid = repair.get("avoid_source_paths") or []
        if avoid:
            lines.append("- Do not rely on these as primary evidence:")
            lines.extend(f"  - `{path}`" for path in avoid)
        verification_steps = repair.get("verification_steps") or []
        if verification_steps:
            lines.append("- Verification steps:")
            lines.extend(f"  - {step}" for step in verification_steps)
        lines.append("")

    limitations = plan.get("limitations") or []
    if limitations:
        lines.extend(["## Remaining Limitations", ""])
        lines.extend(f"- {item}" for item in limitations)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_repair_prompt(
    template_path: Path,
    *,
    repo: Path,
    paper_id: str,
    parsed_dir: Path,
    parser_quality_output: Path,
    schema_path: Path,
    repair_plan_output: Path,
    repair_notes_output: Path,
    repair_mode: str,
    repaired_artifacts_dir: Path,
    repair_manifest_output: Path,
) -> str:
    template = template_path.read_text(encoding="utf-8")
    return render_template(
        template,
        {
            "paper_id": paper_id,
            "parsed_dir": repo_relative(parsed_dir, repo),
            "parser_quality_output": repo_relative(parser_quality_output, repo),
            "schema_path": repo_relative(schema_path, repo),
            "repair_plan_output": repo_relative(repair_plan_output, repo),
            "repair_notes_output": repo_relative(repair_notes_output, repo),
            "repair_mode": repair_mode,
            "repaired_artifacts_dir": repo_relative(repaired_artifacts_dir, repo),
            "repair_manifest_output": repo_relative(repair_manifest_output, repo),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a post-preflight parser repair-planning agent.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--parsed-dir", required=True)
    parser.add_argument("--parser-quality-output", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--schema-path", default=DEFAULT_SCHEMA)
    parser.add_argument("--prompt-template", default=DEFAULT_TEMPLATE)
    parser.add_argument("--notes-output", default=None)
    parser.add_argument(
        "--repair-mode",
        choices=["plan", "overlay"],
        default="plan",
        help="plan writes guidance only; overlay also asks for narrow repaired overlay artifacts.",
    )
    parser.add_argument(
        "--plan-input",
        default=None,
        help="Use an existing plan JSON and only validate/write notes; useful for deterministic tests.",
    )
    args = parser.parse_args()

    repo = repo_root()
    parsed_dir = Path(args.parsed_dir)
    if not parsed_dir.is_absolute():
        parsed_dir = repo / parsed_dir
    parser_quality_output = Path(args.parser_quality_output)
    if not parser_quality_output.is_absolute():
        parser_quality_output = repo / parser_quality_output
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo / output_dir
    log_dir = Path(args.log_dir) if args.log_dir else output_dir / "logs"
    if not log_dir.is_absolute():
        log_dir = repo / log_dir
    schema_path = Path(args.schema_path)
    if not schema_path.is_absolute():
        schema_path = repo / schema_path
    template_path = Path(args.prompt_template)
    if not template_path.is_absolute():
        template_path = repo / template_path
    notes_output = Path(args.notes_output) if args.notes_output else output_dir / NOTES_FILENAME
    if not notes_output.is_absolute():
        notes_output = repo / notes_output

    output_dir.mkdir(parents=True, exist_ok=True)
    notes_output.parent.mkdir(parents=True, exist_ok=True)
    plan_output = output_dir / PLAN_FILENAME
    repaired_artifacts_dir = output_dir / REPAIRED_ARTIFACTS_DIR
    repair_manifest_output = output_dir / MANIFEST_FILENAME

    if args.plan_input:
        plan_input = Path(args.plan_input)
        if not plan_input.is_absolute():
            plan_input = repo / plan_input
        plan = json.loads(plan_input.read_text(encoding="utf-8"))
        plan_output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    else:
        prompt = render_repair_prompt(
            template_path,
            repo=repo,
            paper_id=args.paper_id,
            parsed_dir=parsed_dir,
            parser_quality_output=parser_quality_output,
            schema_path=schema_path,
            repair_plan_output=plan_output,
            repair_notes_output=notes_output,
            repair_mode=args.repair_mode,
            repaired_artifacts_dir=repaired_artifacts_dir,
            repair_manifest_output=repair_manifest_output,
        )
        started_at = time.time() - 1.0
        run_required(
            "parser-repair-planner",
            [
                codex_command(),
                "exec",
                "--output-schema",
                repo_relative(schema_path, repo),
                "--output-last-message",
                repo_relative(plan_output, repo),
                "-",
            ],
            repo,
            log_dir,
            input_text=prompt,
        )
        require_fresh_file(plan_output, started_at, "parser repair plan")
        plan = json.loads(plan_output.read_text(encoding="utf-8"))

    if "repair_mode" not in plan:
        plan["repair_mode"] = args.repair_mode
        plan_output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    errors = validate_plan(plan, schema_path, args.paper_id)
    errors.extend(validate_artifact_filenames(plan))
    if errors:
        raise RuntimeError("Parser repair plan failed validation: " + "; ".join(errors))

    manifest = write_repaired_artifacts(plan, output_dir, repo)
    if (
        manifest["quality_summary"]["normalized_mojibake_artifact_count"]
        or manifest["quality_summary"]["normalized_control_codepoint_artifact_count"]
    ):
        plan_output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    notes_output.write_text(repair_notes_markdown(plan), encoding="utf-8")
    print(
        json.dumps(
            {
                "paper_id": args.paper_id,
                "repair_count": len(plan.get("repairs", [])),
                "repaired_artifact_count": manifest["artifact_count"],
                "plan": repo_relative(plan_output, repo),
                "notes": repo_relative(notes_output, repo),
                "manifest": repo_relative(repair_manifest_output, repo),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
