# AGENTS.md

## Project purpose
This repository builds and runs a reproducible multi-agent reviewer for academic economics papers.

The normal workflow is:
1. Put source PDFs in `inputs/`.
2. Preprocess each paper into structured artifacts under `work/<paper_id>/parsed/`.
3. Render run-specific prompts under `work/<paper_id>/prompts/`.
4. Run parser-quality preflight before substantive review.
5. Optionally run experimental parser repair planning or overlay repair when parser-quality preflight reports high- or medium-severity parser artifacts.
6. Use dynamic reviewer selection by default to choose optional reviewers while mandatory reviewers always run.
7. Store the selector decision under `work/<paper_id>/selection/` and use the selected reviewer roster for downstream stages.
8. Rerender prompts for the selected reviewer roster, including parser repair notes when present.
9. Run the selected reviewer agents on the parsed artifacts.
10. Store and validate reviewer JSON outputs under `work/<paper_id>/reviews/`.
11. Normalize and deduplicate reviewer outputs into an editor bundle.
12. Build editor input from the normalized bundle and original reviewer JSON files.
13. Run the editor to write the final markdown report under `outputs/<paper_id>/report.md`.
14. Smoke-check the final report.

## Canonical file locations
- Source PDFs: `inputs/`
- Parsed artifacts: `work/<paper_id>/parsed/`
- Parser repair overlays: `work/<paper_id>/repair/`
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
- Dynamic reviewer selection is the default for fresh wrapper runs; static mode is available when all enabled reviewers should run.
- Parser repair is opt-in. When enabled with `--parser-repair plan` or `--parser-repair overlay`, run it only after parser-quality preflight and only when high- or medium-severity `parser_artifact` findings are reported.
- Parser repair overlays route reviewers to safer existing artifacts. In `overlay` mode, they may also create narrow LLM-generated repaired artifacts under `work/<paper_id>/repair/repaired_artifacts/`, but they must not overwrite `work/<paper_id>/parsed/` or replace OCR, table reconstruction, figure crop regeneration, or deterministic preprocessing fixes.
- Internal reviewer agents return structured JSON only.
- Only the editor writes the final markdown report.
- If preprocessing artifacts are missing or clearly poor, fail clearly instead of guessing.
- Editor-only refresh is allowed when parsed artifacts, reviewer JSON, selected reviewer config, and the normalized editor bundle already exist. Rerender prompts, rebuild editor input, rerun only the editor, and then smoke-check the final report.

## Preprocessing rules
- Preserve original page numbering.
- Normalize whitespace carefully.
- Never silently remove minus signs, decimal points, percent symbols, parentheses, or appendix labels.
- Save page-level outputs and inventories so downstream reviewers can cite locations precisely.
- Use OCR only when text extraction clearly fails or the PDF is scanned/image-only.

## Reviewer rules
- Literature and reference verification require web search when enabled.
- Never guess missing evidence; use `cannot_verify` or equivalent failure labels.
- Preserve exact source locations whenever possible.
- Keep reviewer outputs modular so failed reviewers can be rerun independently.
- Final reports should keep canonical/source finding identifiers in the traceability appendix rather than repeated body footers.

## Working style
- Prefer deterministic scripts for file handling, preprocessing, validation, and report assembly.
- Use Codex for judgment-heavy auditing and synthesis tasks.
- Keep the workflow reproducible, inspectable, and easy to rerun.
