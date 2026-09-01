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
7. Route substantive reviewers around parser-quality warnings using the deterministic artifacts and parser-quality JSON.
8. Use static exhaustive selection by default and record all enabled reviewers in `work/<paper_id>/selection/reviewer_selection.json`. Only run the reviewer selector when `--reviewer-selection dynamic` is explicitly requested.
9. Write the active run roster and selection provenance to `work/<paper_id>/selection/selected_reviewers.json`.
10. Rerender prompts using the selected reviewer roster and parser-quality guidance.
11. Launch the 4 mandatory review-stage reviewers and every active optional reviewer. The static default activates all 14 optional reviewers, for 18 substantive reviewers in total.
12. Validate each reviewer JSON output under `work/<paper_id>/reviews/`.
13. Conservatively normalize reviewer outputs into a precision-first, lossless `work/<paper_id>/editor/normalized_bundle.json`. Preserve every source finding's details and do not merge findings merely because they share a quote or path.
14. Build `work/<paper_id>/editor/editor_input.md` from the deterministic editor brief, the lossless bundle, and a compact provenance index. Validate the source reviewer JSON files, but do not duplicate them in the editor input or truncate evidence.
15. Run the editor to write `outputs/<paper_id>/report.md`.
16. Smoke-check the final report with `scripts/check_final_report.py --bundle work/<paper_id>/editor/normalized_bundle.json`.

The quality-first defaults are `gpt-5.6-sol`, `xhigh` reasoning for substantive reviewers and the editor, `high` for parser-quality preflight, and static exhaustive reviewer selection. Current reasoning values are `none`, `low`, `medium`, `high`, `xhigh`, and `max`.

Use `--reviewer-selection dynamic` only when the user deliberately accepts a smaller roster as a cost or latency tradeoff. Dynamic mode selects 7 to 13 optional reviewers, for 11 to 17 substantive reviewers after the 4 mandatory review-stage agents.

## Editor-only refresh
If parsed artifacts, all selected reviewer JSON files, and `work/<paper_id>/selection/selected_reviewers.json` already exist, use `scripts/refresh_editor.py --paper-id <paper_id>` to resume synthesis without rerunning reviewers. The helper:
1. Validates every selected reviewer JSON against the schema, semantic rules, and provenance constraints.
2. Rebuilds the precision-first lossless `work/<paper_id>/editor/normalized_bundle.json` from the validated reviews.
3. Rerenders prompts and rebuilds the deterministic brief, lossless bundle, and provenance-only editor input using the active reviewer config.
4. With `--run-editor`, reruns the editor and smoke-checks the final report.

Do not use editor-only refresh when reviewer evidence, parser artifacts, or reviewer selection needs to change. Correct or rerun invalid reviewer output first; the helper will refuse to synthesize it.

Use editor-only refresh to test narrowly scoped editor prompt changes against the same evidence bundle before changing the full workflow. This is especially useful for checking whether report emphasis improved without changing reviewer evidence, such as when adjusting how parser/preprocessing caveats are surfaced in prose.

## Critical rules
- Internal reviewers return JSON only.
- The editor is the only component that emits final markdown.
- Literature and reference verification require web search when enabled.
- Never guess missing evidence; use `cannot_verify`.
- Preserve exact source locations whenever possible.
- If parsed artifacts are poor, fix preprocessing before trusting reviewer outputs.
- Treat parser-quality preflight warnings as reportable caveats; treat high-confidence blocking parser findings as a reason to stop before substantive review.
- Never generate or infer repaired parser content. Do not invoke an external parsing service or an LLM-generated repair layer. If deterministic artifacts do not support a reliable check, use `cannot_verify`.
- Keep final-report traceability in the traceability appendix. Do not reintroduce repeated traceability footers in the body.
- Literature and novelty critiques must be grounded in concrete studies or marked `cannot_verify`; do not assert lack of novelty from vague prior-work impressions.
- If the final report cites external studies, registry records, web pages, or other external evidence, include the external-sources appendix using only source details already present in reviewer evidence.
- Do not bury parser/preprocessing issues when they materially distort auditability of a central formula, table, figure, citation target, or quantitative claim. Keep them in the parser-caveats section, but mention them explicitly in prose and treat them as revision-priority material when the auditability risk is substantial.
- Treat `scripts/check_final_report.py` as a structure and traceability smoke check, not as independent verification that external sources are real or current.
- In explicit dynamic mode, treat data availability/replication, institutional context, power/multiple testing, design/randomization, and economic magnitude reviewers as optional pilots. Select at most 4 when the paper has distinct, concrete cues for those risks. Static mode runs all 5 pilots.
- If `codex exec --output-last-message` writes only a short acknowledgement for the editor, rely on the wrapper's recovery from the editor transcript and then rerun the final report checker.

## Output conventions
- Parsed artifacts: `work/<paper_id>/parsed/`
- Reviewer selection: `work/<paper_id>/selection/`
- Reviewer outputs: `work/<paper_id>/reviews/`
- Final report: `outputs/<paper_id>/report.md`

The expected final report shape is synthesis-first: executive summary, prose review configuration, roughly 3 to 8 high-confidence highest-priority findings when supported by the evidence, suggested revision priorities, additional findings, domain-specific sections, grammar appendix when needed, external-sources appendix when external evidence is cited, parser-caveat prose that keeps central auditability failures visible, and traceability map appendix.
