"""Local, opt-in fixed-task benchmarking; preparation and collection never call models."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time

from build_cli_package import cli_payload
from claude_backend import check_claude, save_claude_output
from render_prompts import render_review_prompts
from review_paper import agent_exec_command, enforce_preflight_gate, run_command
from reviewer_config import load_reviewers_config
from validate_review_json import validate_review_output


REPO = Path(__file__).resolve().parents[1]


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def snapshot(folder: Path) -> dict[str, str]:
    files = {}
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlinked benchmark input is not supported: {path}")
        if path.is_file():
            files[path.relative_to(folder).as_posix()] = digest(path)
    if not files:
        raise ValueError(f"Empty input directory: {folder}")
    return files


def identifier(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", value):
        raise ValueError(f"Expected a short lowercase identifier, got {value!r}")
    return value


def runtime_hashes() -> dict[str, str]:
    return {name: hashlib.sha256(data).hexdigest() for name, data in cli_payload(REPO).items()}


def prepare(config_path: Path, output: Path) -> dict:
    config_path, output = config_path.resolve(), output.resolve()
    if output.exists():
        raise ValueError("Use a new --output directory; benchmark plans are not overwritten.")
    config = read(config_path)
    if config.get("format") != 1:
        raise ValueError("Expected benchmark config format 1")
    repeats = config.get("repeats", 1)
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError("repeats must be an integer from 1 to 10")
    profiles, cases = config.get("profiles", []), config.get("cases", [])
    if not profiles or not cases:
        raise ValueError("At least one profile and case is required")
    for group in (profiles, cases):
        names = [identifier(item["id"]) for item in group]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate profile/case IDs")
    for profile in profiles:
        if profile.get("backend") not in ("codex", "claude"):
            raise ValueError("backend must be codex or claude")
        if not isinstance(profile.get("model"), str) or not profile["model"].strip():
            raise ValueError("Pin a model for every profile")
        if profile.get("effort") not in ("low", "medium", "high", "xhigh", "max"):
            raise ValueError("Set an explicit supported effort for every profile")
    reviewers = load_reviewers_config(REPO / "config/reviewers.json")
    catalog = {r.name: r for r in reviewers}
    schema = read(REPO / "schemas/reviewer_output.schema.json")
    frozen_cases = []
    for case in cases:
        paper_id = identifier(case["paper_id"])
        source = (config_path.parent / case["workspace"]).resolve()
        parsed = source / "work" / paper_id / "parsed"
        preflight = source / "work" / paper_id / "reviews/parser_quality_auditor.json"
        pdf = (config_path.parent / case["pdf"]).resolve()
        pdf_hash = digest(pdf)
        parsed_manifest = read(parsed / "manifest.json")
        if parsed_manifest.get("source_pdf_sha256") != pdf_hash:
            raise ValueError(f"PDF/parsed hash mismatch for {case['id']}")
        if parsed_manifest.get("paper_id") != paper_id:
            raise ValueError("Parsed paper identity differs from benchmark case")
        roles = case.get("roles", [])
        if not roles or len(roles) != len(set(roles)) or any(
            role not in catalog or catalog[role].stage != "review" for role in roles
        ):
            raise ValueError("Each case needs unique canonical substantive reviewer roles")
        failures = validate_review_output(read(preflight), schema, reviewers, repo=source,
                                         expected_reviewer="parser_quality_auditor", paper_id=paper_id)
        if failures:
            raise ValueError("Invalid frozen preflight: " + "; ".join(failures))
        enforce_preflight_gate(catalog["parser_quality_auditor"], preflight)
        # Only parsed evidence and parser preflight are included, never old substantive reviews.
        frozen_cases.append({**case, "workspace": str(source), "pdf": str(pdf),
                             "pdf_sha256": pdf_hash, "parsed_files": snapshot(parsed),
                             "preflight_sha256": digest(preflight),
                             "page_count": parsed_manifest.get("summary", {}).get("page_count"),
                             "preflight_origin": "reused, source-validated prerequisite; not a candidate-model output"})
    jobs = [{"case": case["id"], "role": role, "profile": profile["id"], "repeat": repeat}
            for case in frozen_cases for role in case["roles"]
            for repeat in range(1, repeats + 1) for profile in profiles]
    seed = config.get("schedule_seed", 20260924)
    random.Random(seed).shuffle(jobs)
    for number, job in enumerate(jobs, 1):
        job["id"] = f"j{number:03d}"
    plan = {"format": 1, "kind": "fixed-reviewer-panel", "created_at": datetime.now(timezone.utc).isoformat(),
            "profiles": profiles, "cases": frozen_cases, "jobs": jobs, "repeats": repeats,
            "schedule_seed": seed, "planned_model_calls": len(jobs), "automatic_retries": 0,
            "timeout_minutes": config.get("timeout_minutes", 45), "runtime_files": runtime_hashes(),
            "runner_sha256": digest(Path(__file__)),
            "limitations": ["model plus execution host comparison, not identical tool capabilities",
                            "shared preflight/parser quality is held fixed, not benchmarked",
                            "live web results, caches and service load are not held fixed",
                            "historical model reports are not ground truth or matched fresh runs"]}
    if not isinstance(plan["timeout_minutes"], (int, float)) or not 0 < plan["timeout_minutes"] <= 120:
        raise ValueError("timeout_minutes must be greater than 0 and at most 120")
    if config.get("reference_issues"):
        references = (config_path.parent / config["reference_issues"]).resolve()
        issues = read(references)["issues"]
        plan["reference_issues"] = {"path": str(references), "sha256": digest(references),
                                    "confirmed": sum(i.get("status") == "confirmed" for i in issues),
                                    "provisional": sum(i.get("status") != "confirmed" for i in issues)}
    output.mkdir(parents=True)
    write(output / "plan.json", plan)
    (output / ".gitignore").write_text("*\n", encoding="utf-8")
    (output / "PLAN.md").write_text(
        f"# Fixed-task benchmark plan\n\n{len(jobs)} single-stage model calls; "
        f"{len(cases)} papers; {len(profiles)} profiles; {repeats} repetition(s).\n\n"
        "Prepared only: no model calls made. Review the protocol and source-check the reference ledger "
        "before authorizing execution. No editor, router or fresh parser-agent calls are included.\n\n"
        "Run one approved job at a time, in the plan's order. Never automatically retry a failure.\n",
        encoding="utf-8")
    return plan


def verify_case(case: dict) -> None:
    source = Path(case["workspace"]) / "work" / case["paper_id"]
    if (digest(Path(case["pdf"])) != case["pdf_sha256"]
            or snapshot(source / "parsed") != case["parsed_files"]
            or digest(source / "reviews/parser_quality_auditor.json") != case["preflight_sha256"]):
        raise ValueError("Frozen benchmark evidence changed; prepare a new plan instead of mixing inputs")


def usage_from_log(backend: str, stdout: Path) -> dict:
    """Missing/ambiguous counters remain unknown, never zero or a guessed bill."""
    unknown = {"status": "unavailable", "input_uncached": None, "input_cached": None,
               "input_cache_write": None, "output": None, "input_total": None}
    try:
        if backend == "codex":
            events = [json.loads(line) for line in stdout.read_text(encoding="utf-8").splitlines() if line.strip()]
            turns = [e["usage"] for e in events if e.get("type") == "turn.completed" and e.get("usage")]
            if len(turns) != 1:  # Fresh one-turn jobs; do not accidentally sum cumulative counters.
                return {**unknown, "status": "ambiguous-or-incomplete"}
            usage = turns[0]
            total, cached, out = (usage[k] for k in ("input_tokens", "cached_input_tokens", "output_tokens"))
            if any(type(n) is not int or n < 0 for n in (total, cached, out)) or cached > total:
                return unknown
            return {"status": "reported", "input_uncached": total - cached, "input_cached": cached,
                    "input_cache_write": None, "output": out, "input_total": total,
                    "reasoning_included_in_output": usage.get("reasoning_output_tokens"),
                    "source": "Codex turn.completed; includes only counters the CLI reports"}
        envelope = read(stdout)
        usage = envelope.get("usage", {})
        uncached, cached, created, out = (usage[k] for k in (
            "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))
        if any(type(n) is not int or n < 0 for n in (uncached, cached, created, out)):
            return unknown
        return {"status": "reported", "input_uncached": uncached, "input_cached": cached,
                "input_cache_write": created, "output": out, "input_total": uncached + cached + created,
                "source": "Claude result.usage; provider tokenization differs from Codex",
                "provider_cost_usd_estimate_not_subscription_bill": envelope.get("total_cost_usd"),
                "model_usage": envelope.get("modelUsage")}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return unknown


def run_job(plan_path: Path, job_id: str, *, allow_live: bool = False) -> dict:
    if not allow_live:
        raise ValueError("A model call consumes quota. Review the plan and obtain approval before using --allow-live.")
    plan_path = plan_path.resolve()
    plan = read(plan_path)
    if plan["runner_sha256"] != digest(Path(__file__)) or plan["runtime_files"] != runtime_hashes():
        raise ValueError("Benchmark/runtime changed since preparation; prepare a new plan")
    job = next((job for job in plan["jobs"] if job["id"] == job_id), None)
    if job is None:
        raise ValueError("Unknown job ID")
    case = next(c for c in plan["cases"] if c["id"] == job["case"])
    profile = next(p for p in plan["profiles"] if p["id"] == job["profile"])
    verify_case(case)
    if plan.get("reference_issues") and digest(Path(plan["reference_issues"]["path"])) != plan["reference_issues"]["sha256"]:
        raise ValueError("Reference ledger changed; prepare a new plan before running")
    workspace = plan_path.parent / "runs" / job_id
    if workspace.exists():
        raise ValueError("Job already attempted; retain its evidence. No automatic retries/overwrites.")
    if profile["backend"] == "claude":
        check_claude(plan_path.parent)
    workspace.mkdir(parents=True)
    for name, data in cli_payload(REPO).items():
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    paper = case["paper_id"]
    original = Path(case["workspace"]) / "work" / paper
    work = workspace / "work" / paper
    shutil.copytree(original / "parsed", work / "parsed")
    (work / "reviews").mkdir()
    shutil.copyfile(original / "reviews/parser_quality_auditor.json", work / "reviews/parser_quality_auditor.json")
    reviewers = load_reviewers_config(workspace / "config/reviewers.json")
    reviewer = next(r for r in reviewers if r.name == job["role"])
    values = {"paper_id": paper, "parsed_dir": f"work/{paper}/parsed",
              "reviews_dir": f"work/{paper}/reviews", "schema_path": "schemas/reviewer_output.schema.json",
              "editor_bundle_path": f"work/{paper}/editor/normalized_bundle.json"}
    render_review_prompts(workspace / "prompts/templates", work / "prompts", [reviewer], values)
    prompt = work / "prompts" / reviewer.prompt
    frozen = {**{f"work/{paper}/parsed/{name}": value for name, value in case["parsed_files"].items()},
              f"work/{paper}/reviews/parser_quality_auditor.json": case["preflight_sha256"],
              **plan["runtime_files"], f"work/{paper}/prompts/{reviewer.prompt}": digest(prompt)}
    output = work / "reviews" / reviewer.output
    schema_path = workspace / "schemas/reviewer_output.schema.json"
    command = agent_exec_command(backend=profile["backend"], model=profile["model"],
                                 reasoning_effort=profile["effort"], search=reviewer.search,
                                 schema_path=schema_path, output_path=output)
    if profile["backend"] == "codex":
        command.insert(command.index("exec") + 1, "--json")
        if "--skip-git-repo-check" not in command:
            command.insert(command.index("exec") + 1, "--skip-git-repo-check")
    record = {"job": job, "profile": profile, "status": "running", "search": reviewer.search,
              "prompt_sha256": digest(prompt), "started_at": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "platform": sys.platform,
              "permission_policy": "existing backend settings; no permission/sandbox bypass"}
    write(workspace / "result.json", record)
    started = time.monotonic()
    try:
        version = subprocess.run([command[0], "--version"], stdin=subprocess.DEVNULL,
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        record["cli_version"] = version.stdout.strip() if version.returncode == 0 else None
        started = time.monotonic()
        result = run_command("benchmark", command, workspace, work / "logs",
                             input_text=prompt.read_text(encoding="utf-8"),
                             timeout_seconds=plan["timeout_minutes"] * 60)
        record["returncode"] = result.returncode
        record["usage"] = usage_from_log(profile["backend"], result.stdout_path)
        if profile["backend"] == "codex":
            record["cli_reported_settings"] = dict(re.findall(
                r"^(model|reasoning effort|approval|sandbox): (.+)$",
                result.stderr_path.read_text(encoding="utf-8"), re.M))
        if result.returncode:
            raise ValueError(f"Agent failed (exit {result.returncode}); retain logs and check for remaining processes")
        if profile["backend"] == "claude":
            save_claude_output(result.stdout_path, output, schema_path)
        failures = validate_review_output(read(output), read(schema_path), reviewers, repo=workspace,
                                         expected_reviewer=reviewer.name, paper_id=paper)
        if failures:
            raise ValueError("Review validation failed: " + "; ".join(failures))
        if any(not (workspace / name).is_file() or digest(workspace / name) != sha for name, sha in frozen.items()):
            raise ValueError("Agent changed frozen evidence/runtime")
        verify_case(case)
        record.update(status="complete", output=str(output.relative_to(workspace)), output_sha256=digest(output))
    except (Exception, KeyboardInterrupt) as exc:
        record.update(status="failed", error=str(exc) or "Interrupted")
        raise
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 3)
        write(workspace / "result.json", record)
    return record


def collect(plan_path: Path, output: Path) -> dict:
    """Export a label-blinded rating packet; keep the model key outside it."""
    import csv

    if output.exists():
        raise ValueError("Use a new packet directory; do not overwrite human ratings")
    plan_path = plan_path.resolve()
    plan = read(plan_path)
    output.mkdir(parents=True)
    packet = output / "blind"
    packet.mkdir()
    shuffled = list(plan["jobs"])
    random.SystemRandom().shuffle(shuffled)
    mapping, rows, samples = {}, [], []
    for index, job in enumerate(shuffled, 1):
        sample = f"s{index:03d}"
        workspace = plan_path.parent / "runs" / job["id"]
        result = read(workspace / "result.json") if (workspace / "result.json").exists() else {"status": "not-run"}
        mapping[sample] = {"job": job, "result": result}
        metadata = {"sample_id": sample, "case": job["case"], "role": job["role"], "status": result["status"]}
        if result["status"] == "complete":
            review = (workspace / result["output"]).resolve()
            if not review.is_relative_to(workspace.resolve()):
                raise ValueError("Review path escapes its benchmark workspace")
            if digest(review) != result["output_sha256"]:
                raise ValueError("Completed review was modified; cannot export a valid benchmark packet")
            data = read(review)
            write(packet / f"{sample}.json", data)
            for finding in data["findings"]:
                rows.append({"sample_id": sample, "finding_id": finding["id"], "verdict": "",
                             "issue_key": "", "evidence_correct": "", "actionability": "",
                             "source_check_notes": ""})
            metadata["finding_count"] = len(data["findings"])
        samples.append(metadata)
    write(packet / "samples.json", samples)
    with (packet / "ratings.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["sample_id", "finding_id", "verdict", "issue_key",
                                                   "evidence_correct", "actionability", "source_check_notes"])
        writer.writeheader()
        writer.writerows(rows)
    write(output / "operator-key.json", mapping)
    references = plan.get("reference_issues")
    if references:
        source = Path(references["path"])
        if digest(source) != references["sha256"]:
            raise ValueError("Reference ledger changed since preparation")
        shutil.copyfile(source, packet / "reference-issues.json")
    else:
        write(packet / "reference-issues.template.json", {"issues": []})
    write(packet / "packet.json", {"reference_sha256": references["sha256"] if references else None,
                                  "plan_sha256": digest(plan_path)})
    return {"samples": len(samples), "complete": sum(s["status"] == "complete" for s in samples),
            "findings_to_rate": len(rows), "packet": str(packet),
            "warning": "Give assessors only blind/. Labels hidden, not guaranteed stylistic anonymity. No scores until source checking."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="Freeze a schedule and input hashes; zero model calls")
    prep.add_argument("--config", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="Run exactly one approved reviewer task")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--job", required=True)
    run.add_argument("--allow-live", action="store_true")
    export = commands.add_parser("collect", help="Create an offline blinded rating packet")
    export.add_argument("--plan", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            plan = prepare(args.config, args.output)
            result = {"plan": str(args.output / "plan.json"), "planned_model_calls": plan["planned_model_calls"],
                      "model_calls_made": 0}
        elif args.command == "run":
            result = run_job(args.plan, args.job, allow_live=args.allow_live)
        else:
            result = collect(args.plan, args.output)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
