# AGENTS.md

## Project purpose
This repository builds and runs a reproducible multi-agent reviewer for academic economics papers.

The normal workflow is:
1. Put source PDFs in `inputs/`.
2. Preprocess each paper into structured artifacts under `work/<paper_id>/parsed/`.
3. Render run-specific prompts under `work/<paper_id>/prompts/`.
4. Run parser-quality preflight before substantive review.
5. Route substantive reviewers around parser-quality warnings using deterministic artifacts.
6. Run the single conservative applicability router. The 8 universal review-stage auditors always run; conditional specialists are skipped only when their entire remit is clearly absent. Mixed, unknown, or lower-confidence classifications expand to every conditional specialist.
7. Store applicability provenance and the active reviewer roster under `work/<paper_id>/selection/`.
8. Rerender prompts for the selected reviewer roster with parser-quality guidance.
9. Run the selected reviewer agents on the parsed artifacts.
10. Store and validate reviewer JSON outputs under `work/<paper_id>/reviews/`.
11. Conservatively normalize reviewer outputs into a precision-first, lossless editor bundle that preserves every source finding's details and avoids merging distinct concerns.
12. Build editor input from a deterministic brief, the lossless normalized bundle, and a compact provenance index for the validated reviewer JSON files. Do not duplicate raw reviewer JSON or truncate evidence.
13. Run the editor to write the final markdown report under `outputs/<paper_id>/report.md`.
14. Smoke-check the final report.

## Canonical file locations
- Source PDFs: `inputs/`
- Parsed artifacts: `work/<paper_id>/parsed/`
- Reviewer outputs: `work/<paper_id>/reviews/`
- Reviewer selection: `work/<paper_id>/selection/`
- Final reports: `outputs/<paper_id>/`

## Path conventions
- If the user refers to a bare source PDF filename, first resolve it under `inputs/`.
- Prefer project-relative paths over absolute paths when possible.
- Do not assume a file is outside the repo unless the user explicitly says so.

## Workflow rules
- Never run reviewer agents directly on a raw PDF if parsed artifacts do not exist.
- Preprocessing comes before review.
- Reviewer agents are configured through `config/reviewers.json`.
- Fresh wrapper runs use one conservative applicability workflow. Eight universal review-stage auditors always run. Eleven conditional specialists, including the theory-logic auditor, run whenever their remit is plausibly material; only high-confidence single-type classifications may skip clearly inapplicable roles. Mixed, unknown, medium-confidence, and low-confidence classifications run all 19 substantive reviewers.
- The quality-first default is `gpt-5.6-sol` with `xhigh` reasoning for substantive reviewers and the editor. Parser-quality preflight and applicability routing use `high`.
- Users may explicitly override the model and reasoning through wrapper flags. Documentation uses `gpt-5.6-terra` with `xhigh` reasoning as a lower-usage example, not a second recommended default. Other combinations are unbenchmarked and must remain explicit in the run manifest.
- Substantive reviewers must read the parser-quality output and route around unsafe deterministic artifacts. If no trustworthy deterministic fallback exists, use `cannot_verify`; never generate or infer repaired text, signs, cells, values, or formulas.
- Internal reviewer agents return structured JSON only.
- Only the editor writes the final markdown report.
- If preprocessing artifacts are missing or clearly poor, fail clearly instead of guessing.
- Editor-only refresh is allowed when parsed artifacts, all selected reviewer JSON files, and the selected reviewer config already exist. Revalidate the reviews, rebuild the precision-first lossless bundle and provenance-only editor input, rerun only the editor, and then smoke-check the final report.

## Preprocessing rules
- Preserve original page numbering.
- Normalize whitespace carefully.
- Never silently remove minus signs, decimal points, percent symbols, parentheses, or appendix labels.
- Save page-level outputs and inventories so downstream reviewers can cite locations precisely.
- The default workflow does not install or invoke OCR, an external document service, or an LLM-generated repair layer. When native extraction clearly fails or a page is scanned/image-only, retain the page image and mark OCR as recommended rather than inferring replacement content.

## Reviewer rules
- Literature and reference verification require web search when enabled.
- Never guess missing evidence; use `cannot_verify` or equivalent failure labels.
- Preserve exact source locations whenever possible.
- A reviewer whose remit is genuinely absent should return `run_status: ok` with no findings. Absence of an empirical design, formal model, dataset, experiment, or other scope element is not itself a defect.
- Keep reviewer outputs modular so failed reviewers can be rerun independently.
- Final reports should keep canonical/source finding identifiers in the traceability appendix rather than repeated body footers.

## Working style
- Prefer deterministic scripts for file handling, preprocessing, validation, and report assembly.
- Use Codex for judgment-heavy auditing and synthesis tasks.
- Keep the workflow reproducible, inspectable, and easy to rerun.
