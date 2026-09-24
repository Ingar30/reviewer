"""Offline Claude process double. Never imports or contacts an AI client."""
import json
import os
from pathlib import Path
import re
import sys
import uuid


def main():
    args = sys.argv[1:]
    calls = Path(os.environ["REVIEWER_TEST_CALLS"])
    calls.mkdir(parents=True, exist_ok=True)
    (calls / f"{uuid.uuid4().hex}.json").write_text(
        json.dumps({"args": args, "cwd": str(Path.cwd())}), encoding="utf-8",
    )
    if args == ["--version"]:
        print("2.1.280 (MOCK Claude Code)")
        return 0
    if args == ["auth", "status", "--json"]:
        print(json.dumps({"loggedIn": True, "authMethod": "claude.ai",
                          "email": "SENSITIVE_TEST_LOGIN_OUTPUT"}))
        return 0
    assert "--print" in args, args
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert "Bash" not in args[args.index("--tools") + 1]
    prompt = sys.stdin.read()
    assert prompt.strip()
    role = re.search(r"Act as the (\w+) for this run", prompt).group(1)
    paper = re.search(r'paper_id\s*(?:=\s*)?"([^"]+)"', prompt).group(1)
    response = {"type": "result", "subtype": "success", "is_error": False,
                "permission_denials": [], "modelUsage": {"claude-opus-5-5": {"inputTokens": 1}}}
    if role == "reviewer_applicability_router":
        if os.environ.get("REVIEWER_TEST_STOP") == "selection":
            print("MOCK interruption after preflight", file=sys.stderr)
            return 73
        config = json.loads(Path("config/reviewers.json").read_text(encoding="utf-8"))["reviewers"]
        payload = {"paper_id": paper, "paper_type": "unknown", "selection_confidence": "low",
                   "selection_mode": "applicability", "selected_optional_reviewers": [
                       {"name": r["name"], "reason": "Synthetic uncertain paper: retain full coverage."}
                       for r in config if r.get("selection_policy") == "optional" and r.get("enabled", True)
                   ], "skipped_optional_reviewers": [], "notes": ["MOCK; no scholarly validation."]}
    elif role != "editor":
        payload = {"reviewer": role, "paper_id": paper, "run_status": "ok",
                   "summary": "MOCK audit for launch testing only.", "findings": [], "notes": []}
    else:
        if os.environ.get("REVIEWER_TEST_STOP") == "editor":
            return 74
        headings = ["Executive Summary", "Highest-Priority Cross-Agent Findings",
                    "Suggested Revision Priorities", "Additional Findings",
                    "Appendix: Review Scope and Limitations", "Appendix: Traceability Map"]
        paragraph = ("This is a synthetic mocked pipeline test, not an academic review. "
                     "No scholarly claims or external references have been verified. "
                     "Empty fixture findings exercise deterministic assembly and persistence. ")
        response["result"] = "# Multi-Agent Paper Review Report\n\nMOCK report: offline fixture only.\n\n" + "\n\n".join(
            "## " + heading + "\n\n" + paragraph * 3 for heading in headings)
    if role != "editor":
        # Exercise real argv round-tripping of both canonical schemas, including on Windows.
        from jsonschema import validate
        validate(payload, json.loads(args[args.index("--json-schema") + 1]))
        response["structured_output"] = payload
    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
