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
1. Resolve the input PDF path.
2. Derive `paper_id` from the filename stem unless explicitly provided.
3. Ensure parsed artifacts exist under `work/<paper_id>/parsed/`.
4. If not, run `scripts/preprocess_pdf.py`.
5. Launch the five reviewers:
   - literature_auditor
   - numerical_auditor
   - reference_auditor
   - crossref_auditor
   - claim_evidence_auditor
6. Validate each reviewer JSON output.
7. Launch `editor` on the validated reviewer outputs.
8. Write the final report to `outputs/<paper_id>/report.md`.

## Critical rules
- Internal reviewers return JSON only.
- The editor is the only component that emits final markdown.
- Literature and reference verification require web search when enabled.
- Never guess missing evidence; use `cannot_verify`.
- Preserve exact source locations whenever possible.
- If parsed artifacts are poor, fix preprocessing before trusting reviewer outputs.

## Output conventions
- Parsed artifacts: `work/<paper_id>/parsed/`
- Reviewer outputs: `work/<paper_id>/reviews/`
- Final report: `outputs/<paper_id>/report.md`