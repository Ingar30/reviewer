# Extension Guide

The workflow is meant to be forkable without changing the privacy boundary: source papers stay in `inputs/`, runtime artifacts stay in `work/`, and final reports stay in `outputs/`.

## Main Extension Points

- `config/reviewers.json`: reviewer roster, metadata, search needs, stage, and selection policy.
- `prompts/templates/`: reusable prompts for reviewers, reviewer selection, and the editor.
- `schemas/`: JSON output contracts for reviewer outputs and reviewer selection.
- `scripts/validate_review_json.py`: semantic checks beyond JSON Schema.
- `scripts/normalize_review_outputs.py`: precision-first canonicalization that preserves every source finding's details while conservatively grouping clear cross-reviewer duplicates.
- `scripts/build_editor_input.py`: deterministic editor brief, lossless bundle presentation, compact reviewer provenance, and section routing.
- `scripts/pipeline_paths.py`: shared path conventions for wrappers that reuse the same paper workspace layout.
- `tests/`: synthetic fixtures and regression tests for reviewer, selector, parser, editor, and privacy behavior.

The default wrapper uses static exhaustive selection: 4 mandatory and 14 optional review-stage agents, for 18 substantive reviewers after parser-quality preflight. Dynamic selection is an explicit opt-in that selects 7 to 13 optional reviewers, for 11 to 17 substantive reviewers in total.

## Adding A Reviewer

1. Add the prompt template under `prompts/templates/`.
2. Add one enabled reviewer entry in `config/reviewers.json`.
3. Choose `selection_policy`: use `mandatory` only for reviewers that must run in both static and dynamic modes; otherwise use `optional`. Static mode still runs every enabled optional reviewer.
4. Choose `normalization_role` so downstream routing knows whether findings are manuscript issues, reference issues, cross-reference issues, copyedits, or parser artifacts.
5. Update `schemas/reviewer_output.schema.json` and `scripts/validate_review_json.py` only if the output contract changes.
6. Add focused tests with synthetic inputs.

Search-enabled reviewers should declare `"search": true` and should return `cannot_verify` rather than guessing when evidence is unavailable.

Parser extensions must preserve the local deterministic evidence boundary. Do not make an external document service, OCR engine, or LLM-generated repair layer part of the default path, and never infer missing signs, values, labels, cells, or formulas.

## Preserving The Editor Input Contract

The editor input contains a deterministic routing brief, one lossless normalized bundle, and a compact provenance index for the validated reviewer JSON files. The raw JSON files are validated before normalization but are not duplicated into the editor input.

Keep normalization precision-first: a shared quote, page, or path is not sufficient reason to merge distinct findings. Preserve per-source-finding summaries, claims, evidence, locations, assessments, confidence, numeric checks, source objects, and suggested fixes. If the editor input approaches its byte budget, minify the bundle losslessly; fail clearly rather than truncating evidence.

## Adding A Wrapper Or Forked Workflow

Use `scripts/pipeline_paths.py` for paper-specific runtime paths instead of recreating `work/<paper_id>/...` and `outputs/<paper_id>/...` strings. This keeps editor refresh, full pipeline runs, and forked wrappers aligned.

Forked workflows should preserve the same shareability rule: only project machinery, docs, tests, schemas, prompts, and placeholder README files are tracked. Run:

```powershell
python -m unittest
python scripts\check_shareable_repo.py --include-untracked
python scripts\check_tracked_sensitive_names.py
```
