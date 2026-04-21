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
- If the user names a bare PDF filename, first look for it under `inputs/`.
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
7. In dynamic mode, run the reviewer selector and write `work/<paper_id>/selection/reviewer_selection.json`.
8. Write the active run roster to `work/<paper_id>/selection/selected_reviewers.json`.
9. Rerender prompts using the selected reviewer roster.
10. Launch mandatory review-stage reviewers and selected optional reviewers.
11. Validate each reviewer JSON output under `work/<paper_id>/reviews/`.
12. Normalize and deduplicate reviewer outputs into `work/<paper_id>/editor/normalized_bundle.json`.
13. Build editor input at `work/<paper_id>/editor/editor_input.md`.
14. Run the editor to write `outputs/<paper_id>/report.md`.
15. Smoke-check the final report with `scripts/check_final_report.py --bundle work/<paper_id>/editor/normalized_bundle.json`.

Use `--reviewer-selection static` only when all enabled review-stage reviewers should run.

## Editor-only refresh
If parsed artifacts, reviewer JSON files, `work/<paper_id>/selection/selected_reviewers.json`, and `work/<paper_id>/editor/normalized_bundle.json` already exist, rerun only the editor when the change is limited to editor prompt/report presentation:
1. Rerender prompts with `scripts/render_prompts.py`, passing `--reviewers-config work/<paper_id>/selection/selected_reviewers.json`.
2. Rebuild editor input with `scripts/build_editor_input.py`, passing the same selected reviewer config.
3. Run the editor with `codex exec --output-last-message outputs/<paper_id>/report.md -`.
4. Smoke-check with `scripts/check_final_report.py --input outputs/<paper_id>/report.md --bundle work/<paper_id>/editor/normalized_bundle.json`.

Do not use editor-only refresh when reviewer evidence, parser artifacts, reviewer selection, or normalized findings need to change.

Use editor-only refresh to test narrowly scoped editor prompt changes against the same evidence bundle before changing the full workflow. This is especially useful for checking whether report emphasis improved without changing reviewer evidence, such as when adjusting how parser/preprocessing caveats are surfaced in prose.

## Critical rules
- Internal reviewers return JSON only.
- The editor is the only component that emits final markdown.
- Literature and reference verification require web search when enabled.
- Never guess missing evidence; use `cannot_verify`.
- Preserve exact source locations whenever possible.
- If parsed artifacts are poor, fix preprocessing before trusting reviewer outputs.
- Treat parser-quality preflight warnings as reportable caveats; treat high-confidence blocking parser findings as a reason to stop before substantive review.
- Keep final-report traceability in the traceability appendix. Do not reintroduce repeated traceability footers in the body.
- Literature and novelty critiques must be grounded in concrete studies or marked `cannot_verify`; do not assert lack of novelty from vague prior-work impressions.
- If the final report cites external studies, registry records, web pages, or other external evidence, include the external-sources appendix using only source details already present in reviewer evidence.
- Do not bury parser/preprocessing issues when they materially distort auditability of a central formula, table, figure, citation target, or quantitative claim. Keep them in the parser-caveats section, but mention them explicitly in prose and treat them as revision-priority material when the auditability risk is substantial.
- Treat `scripts/check_final_report.py` as a structure and traceability smoke check, not as independent verification that external sources are real or current.
- Treat institutional context, power/multiple testing, design/randomization, and economic magnitude reviewers as narrow optional pilots. They should run only when the selected paper has strong cues for those risks.
- If `codex exec --output-last-message` writes only a short acknowledgement for the editor, rely on the wrapper's recovery from the editor transcript and then rerun the final report checker.

## Output conventions
- Parsed artifacts: `work/<paper_id>/parsed/`
- Reviewer selection: `work/<paper_id>/selection/`
- Reviewer outputs: `work/<paper_id>/reviews/`
- Final report: `outputs/<paper_id>/report.md`

The expected final report shape is synthesis-first: executive summary, prose review configuration, roughly 3 to 8 high-confidence highest-priority findings when supported by the evidence, suggested revision priorities, additional findings, domain-specific sections, grammar appendix when needed, external-sources appendix when external evidence is cited, parser-caveat prose that keeps central auditability failures visible, and traceability map appendix.
