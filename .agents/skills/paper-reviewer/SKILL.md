---
name: paper-reviewer
description: Use this skill when the task is to review an academic paper PDF from the repo input folder, run specialized auditors, and compile a final report.
---

# Paper Reviewer Skill

This skill runs a reproducible multi-agent paper-review workflow for academic PDFs.

## Use this skill when
- the input is an academic paper PDF
- the task is review, auditing, or verification
- the user wants a structured report
- the task involves literature claims, references, numeric checks, or internal cross-references

## Do not use this skill when
- the user wants only a summary
- the user wants only proofreading
- the user wants only a rewrite
- parsed artifacts already exist and the request is unrelated to the review pipeline

## Default input convention
- If the user names a file like `example-paper.pdf`, first look for `inputs/example-paper.pdf`.
- If the user gives a repo-relative path, use it.
- If the user gives an absolute path, use it as provided.

## Workflow
For fresh runs, use `scripts/review_paper.py` as the primary entry point.

The pipeline stages are:
1. Resolve the input PDF path.
2. Derive `paper_id` from the filename stem unless explicitly provided.
3. Preprocess the PDF into `work/<paper_id>/parsed/`.
4. Render run-specific prompts into `work/<paper_id>/prompts/`.
5. Launch preflight reviewers from `config/reviewers.json`.
6. Validate preflight JSON and stop on blocking parser-quality failures.
7. Launch the configured review-stage reviewers from `config/reviewers.json`.
8. Validate each reviewer JSON output under `work/<paper_id>/reviews/`.
9. Normalize and deduplicate reviewer outputs into `work/<paper_id>/editor/normalized_bundle.json`.
10. Build editor input at `work/<paper_id>/editor/editor_input.md`.
11. Run the editor to write `outputs/<paper_id>/report.md`.
12. Smoke-check the final report with `scripts/check_final_report.py`.

## Critical rules
- Internal reviewers return JSON only.
- The editor is the only component that emits final markdown.
- Literature and reference verification require web search when enabled.
- Never guess missing evidence; use `cannot_verify`.
- Preserve exact source locations whenever possible.
- If parsed artifacts are poor, fix preprocessing before trusting reviewer outputs.
- Treat parser-quality preflight warnings as reportable caveats; treat high-confidence blocking parser findings as a reason to stop before substantive review.

## Output conventions
- Parsed artifacts: `work/<paper_id>/parsed/`
- Reviewer outputs: `work/<paper_id>/reviews/`
- Final report: `outputs/<paper_id>/report.md`
