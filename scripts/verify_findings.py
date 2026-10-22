"""Explicit CLI-only transport for bounded shadow verification."""
import argparse
import hashlib
import json
from pathlib import Path
from strict_json import read_json
from evidence_registry import sha256
from finding_verification import prepare, accept

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--ids", nargs="+", required=True)
    p.add_argument("--output", type=Path, required=True)
    for name in ("accept", "run"):
        p = sub.add_parser(name)
        p.add_argument("--packet", type=Path, required=True)
        p.add_argument("--candidate", type=Path, required=True)
        p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.command == "prepare":
        prepare(args.bundle, args.ids, args.output)
        return 0
    if args.command == "run":
        from review_paper import agent_exec_command, run_required
        from claude_backend import check_claude, save_claude_output
        from resume_review import runtime_snapshot
        packet = read_json(args.packet)
        work = repo / "work" / packet["paper_id"]
        manifest = read_json(work / "run_manifest.json")
        if manifest.get("status") != "complete":
            raise ValueError("Shadow run requires a completed main pipeline")
        if args.candidate.exists() or args.output.exists():
            raise ValueError("Shadow attempt already exists; preserve it, do not retry silently")
        frozen = {**runtime_snapshot(repo), **{str(p): sha256(p) for p in (work / "parsed").rglob("*") if p.is_file()}}
        backend = manifest.get("backend", "codex")
        if backend == "claude":
            check_claude(repo)
        schema = repo / "schemas/finding_verification.schema.json"
        prompt = (repo / "prompts/templates/finding_verifier.txt").read_text(encoding="utf-8")
        prompt += "\nFrozen packet SHA256 (canonical JSON): " + hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        prompt += "\n" + json.dumps(packet, ensure_ascii=False)
        args.candidate.parent.mkdir(parents=True, exist_ok=True)
        result = run_required("shadow-verifier", agent_exec_command(backend=backend,
            model=manifest["model"], reasoning_effort=manifest["reviewer_editor_reasoning_effort"],
            schema_path=schema, output_path=args.candidate), repo, args.candidate.parent,
            input_text=prompt, timeout_seconds=2700)
        if backend == "claude":
            save_claude_output(result.stdout_path, args.candidate, schema)
        if any(not (repo / name).is_file() or sha256(repo / name) != sha for name, sha in frozen.items()):
            raise ValueError("Shadow verifier changed evidence/runtime; output not accepted")
    accept(args.candidate, args.packet, args.output, repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
