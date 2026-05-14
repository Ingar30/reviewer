# Extension Guide

The workflow is meant to be forkable without changing the privacy boundary: source papers stay in `inputs/`, runtime artifacts stay in `work/`, and final reports stay in `outputs/`.

## Main Extension Points

- `config/reviewers.json`: reviewer roster, metadata, search needs, stage, and selection policy.
- `prompts/templates/`: reusable prompts for reviewers, reviewer selection, parser repair, and the editor.
- `schemas/`: JSON output contracts for reviewer outputs, reviewer selection, and parser repair plans.
- `scripts/validate_review_json.py`: semantic checks beyond JSON Schema.
- `scripts/normalize_review_outputs.py`: canonicalization and deduplication of reviewer findings.
- `scripts/build_editor_input.py`: editor bundle presentation and section routing.
- `scripts/pipeline_paths.py`: shared path conventions for wrappers that reuse the same paper workspace layout.
- `tests/`: synthetic fixtures and regression tests for reviewer, selector, parser, editor, and privacy behavior.

## Adding A Reviewer

1. Add the prompt template under `prompts/templates/`.
2. Add one enabled reviewer entry in `config/reviewers.json`.
3. Choose `selection_policy`: use `mandatory` only for reviewers that should always run; otherwise use `optional`.
4. Choose `normalization_role` so downstream routing knows whether findings are manuscript issues, reference issues, cross-reference issues, copyedits, or parser artifacts.
5. Update `schemas/reviewer_output.schema.json` and `scripts/validate_review_json.py` only if the output contract changes.
6. Add focused tests with synthetic inputs.

Search-enabled reviewers should declare `"search": true` and should return `cannot_verify` rather than guessing when evidence is unavailable.

## Adding A Wrapper Or Forked Workflow

Use `scripts/pipeline_paths.py` for paper-specific runtime paths instead of recreating `work/<paper_id>/...` and `outputs/<paper_id>/...` strings. This keeps editor refresh, full pipeline runs, parser repair, and forked wrappers aligned.

Forked workflows should preserve the same shareability rule: only project machinery, docs, tests, schemas, prompts, and placeholder README files are tracked. Run:

```powershell
python -m unittest
python scripts\check_shareable_repo.py --include-untracked
python scripts\check_tracked_sensitive_names.py
```
