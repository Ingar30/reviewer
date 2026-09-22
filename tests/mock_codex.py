"""Offline Codex process double. Never invokes Codex, a model, or the network."""
from pathlib import Path
import json
import os
import sys
import uuid


def main():
    args = sys.argv[1:]
    calls = Path(os.environ["REVIEWER_TEST_CALLS"])
    calls.mkdir(parents=True, exist_ok=True)
    (calls / f"{uuid.uuid4().hex}.json").write_text(
        json.dumps({"args": args, "cwd": str(Path.cwd())}), encoding="utf-8"
    )
    if args == ["login", "status"]:
        # Ensure launcher diagnostics never forward login output.
        print("SENSITIVE_TEST_LOGIN_OUTPUT")
        return int(os.environ.get("REVIEWER_TEST_LOGIN_FAILURE", "0"))
    assert "exec" in args, args
    prompt = sys.stdin.read()
    assert prompt.strip()
    output = Path(args[args.index("--output-last-message") + 1])
    config = json.loads(Path("config/reviewers.json").read_text(encoding="utf-8"))["reviewers"]
    paper_id = output.parent.parent.name
    if output.name == "reviewer_selection.json":
        if os.environ.get("REVIEWER_TEST_STOP") == "selection":
            print("Mock interruption after valid preflight", file=sys.stderr)
            return 73
        payload = {
            "paper_id": paper_id, "paper_type": "unknown", "selection_confidence": "low",
            "selection_mode": "applicability", "selected_optional_reviewers": [
                {"name": r["name"], "reason": "Synthetic uncertain paper: retain full coverage."}
                for r in config if r.get("selection_policy") == "optional" and r.get("enabled", True)
            ], "skipped_optional_reviewers": [], "notes": ["MOCK; no scholarly validation."],
        }
    elif output.suffix == ".json":
        reviewer = next(r for r in config if r["output"] == output.name)
        payload = {"reviewer": reviewer["name"], "paper_id": paper_id, "run_status": "ok",
                   "summary": "MOCK audit for launch testing only.", "findings": [], "notes": []}
    else:
        if os.environ.get("REVIEWER_TEST_STOP") == "editor":
            return 74
        headings = ["Executive Summary", "Highest-Priority Cross-Agent Findings",
                    "Suggested Revision Priorities", "Additional Findings",
                    "Appendix: Review Scope and Limitations", "Appendix: Traceability Map"]
        paragraph = ("This is a synthetic mocked pipeline test, not an academic review. "
                     "No scholarly claims or external references have been verified. "
                     "The empty fixture findings exercise deterministic assembly and persistence. ")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("# Multi-Agent Paper Review Report\n\nMOCK report: offline fixture only.\n\n" + "\n\n".join(
            "## " + heading + "\n\n" + paragraph * 3 for heading in headings
        ), encoding="utf-8")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
