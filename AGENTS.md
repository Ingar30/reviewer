# AGENTS.md

## Project purpose
This repository builds and runs a reproducible multi-agent reviewer for academic economics papers.

The normal workflow is:
1. Put source PDFs in `inputs/`.
2. Preprocess each paper into structured artifacts under `work/<paper_id>/parsed/`.
3. Render run-specific prompts under `work/<paper_id>/prompts/`.
4. Run the configured reviewer agents on the parsed artifacts.
5. Store and validate reviewer JSON outputs under `work/<paper_id>/reviews/`.
6. Normalize and deduplicate reviewer outputs into an editor bundle.
7. Build editor input from the normalized bundle and original reviewer JSON files.
8. Run the editor to write the final markdown report under `outputs/<paper_id>/report.md`.
9. Smoke-check the final report.

## Canonical file locations
- Source PDFs: `inputs/`
- Parsed artifacts: `work/<paper_id>/parsed/`
- Reviewer outputs: `work/<paper_id>/reviews/`
- Final reports: `outputs/<paper_id>/`

## Path conventions
- If the user refers to `example-paper.pdf`, first resolve it as `inputs/example-paper.pdf`.
- Prefer project-relative paths over absolute paths when possible.
- Do not assume a file is outside the repo unless the user explicitly says so.

## Workflow rules
- Never run reviewer agents directly on a raw PDF if parsed artifacts do not exist.
- Preprocessing comes before review.
- Reviewer agents are configured through `config/reviewers.json`.
- Internal reviewer agents return structured JSON only.
- Only the editor writes the final markdown report.
- If preprocessing artifacts are missing or clearly poor, fail clearly instead of guessing.

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

## Working style
- Prefer deterministic scripts for file handling, preprocessing, validation, and report assembly.
- Use Codex for judgment-heavy auditing and synthesis tasks.
- Keep the workflow reproducible, inspectable, and easy to rerun.
