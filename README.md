# Reviewer

A local, Windows-first Codex project for running a reproducible multi-agent reviewer on academic economics papers.

The default path is the single wrapper:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\<paper_id>.pdf"
```

If the project virtual environment is already activated, `python scripts\review_paper.py ...` is equivalent. The wrapper preprocesses the PDF, renders prompts, runs parser-quality preflight, dynamically selects optional reviewers, runs the selected reviewer roster, validates reviewer JSON, normalizes and deduplicates findings, builds editor input, writes `outputs/<paper_id>/report.md`, and smoke-checks the final report.

Documentation is intentionally simple: `README.md` is the human-facing source of truth, and `AGENTS.md` is the Codex-facing workflow contract.

## Project Map

Tracked project machinery:

- `AGENTS.md`: Codex-facing workflow and safety instructions.
- `.codex/config.toml`: project-level Codex defaults.
- `.agents/skills/paper-reviewer/SKILL.md`: reusable workflow playbook.
- `config/reviewers.json`: enabled reviewer roster and reviewer metadata.
- `prompts/templates/*.txt`: reusable prompt templates.
- `schemas/*.json`: structured output contracts.
- `scripts/*.py`: deterministic preprocessing, validation, orchestration, normalization, and report checks.
- `tests/`: focused unit tests for reviewer config, validation, normalization, editor brief behavior, and report checks.
- `Slides/reviewer_slides.pdf`: teaching deck for explaining this project as an agentic research-pipeline case study.

Run-specific artifacts:

- `inputs/`: source PDFs, usually ignored by Git.
- `work/<paper_id>/parsed/`: parsed page text, page images, inventories, tables, figures, citations, crossrefs, and manifest files.
- `work/<paper_id>/prompts/`: rendered run-specific prompts.
- `work/<paper_id>/selection/`: reviewer selector output and selected reviewer roster.
- `work/<paper_id>/reviews/`: reviewer JSON outputs.
- `work/<paper_id>/editor/`: normalized bundle and editor input.
- `outputs/<paper_id>/report.md`: final human-readable report.

## Workflow

The fresh-run sequence is:

1. Preprocess the PDF into structured artifacts.
2. Render prompts for preflight and review stages.
3. Run `parser_quality_auditor` first.
4. Block only on high-severity, high-confidence parser artifacts that make review unsafe.
5. Dynamically classify the paper and select optional reviewers, unless static mode is requested.
6. Write `work/<paper_id>/selection/reviewer_selection.json`.
7. Write `work/<paper_id>/selection/selected_reviewers.json`.
8. Rerender prompts for the selected roster.
9. Run mandatory and selected optional reviewers in parallel.
10. Validate reviewer JSON with the schema and semantic checks.
11. Normalize and deduplicate reviewer outputs into `normalized_bundle.json`.
12. Build editor input with deterministic guidance and traceability rows.
13. Run the editor to write the final markdown report.
14. Smoke-check the report structure and traceability identifiers.

Use an explicit paper id when needed:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\<paper_id>.pdf" --paper-id "<paper_id>"
```

Run all enabled review-stage reviewers without selector filtering:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\<paper_id>.pdf" --reviewer-selection static
```

## Reviewer Roster

Reviewers are configured in `config/reviewers.json`. Each entry declares:

- reviewer name
- prompt template
- output filename
- finding ID prefix
- whether search is required
- normalization role
- stage: `preflight` or `review`
- selection policy: `mandatory` or `optional`

Reviewer roles are carried by the prompt templates and reviewer config; the wrapper does not require separate `.codex/agents` definitions.

Mandatory reviewers currently include parser preflight plus baseline cross-reference, reference, and grammar/copyediting checks. Optional reviewers cover numerical claims, claim-evidence alignment, literature positioning, identification, robustness, sample construction, front/back consistency, external validity, model/equation checks, replication/data availability, institutional context, power/multiple testing, design/randomization, and economic magnitude.

Search-enabled reviewers need the Codex CLI search mode available. Literature and reference verification should not be guessed; use `cannot_verify` when evidence is missing.

## Editor-Only Refresh

Use editor-only refresh when parsed artifacts, reviewer JSON, selected reviewer config, and `work/<paper_id>/editor/normalized_bundle.json` already exist, and the change only affects editor presentation or report shape.

```powershell
$paperId = "<paper_id>"

.\.venv\Scripts\python.exe scripts\render_prompts.py `
  --paper-id $paperId `
  --parsed-dir "work\${paperId}\parsed" `
  --reviews-dir "work\${paperId}\reviews" `
  --schema-path schemas\reviewer_output.schema.json `
  --output-dir "work\${paperId}\prompts" `
  --editor-bundle-path "work\${paperId}\editor\normalized_bundle.json" `
  --reviewers-config "work\${paperId}\selection\selected_reviewers.json"

.\.venv\Scripts\python.exe scripts\build_editor_input.py `
  --paper-id $paperId `
  --editor-prompt "work\${paperId}\prompts\editor_report.txt" `
  --bundle "work\${paperId}\editor\normalized_bundle.json" `
  --reviews-dir "work\${paperId}\reviews" `
  --output "work\${paperId}\editor\editor_input.md" `
  --reviewers-config "work\${paperId}\selection\selected_reviewers.json"

Get-Content "work\${paperId}\editor\editor_input.md" -Raw |
  codex exec --output-last-message "outputs\${paperId}\report.md" -

.\.venv\Scripts\python.exe scripts\check_final_report.py `
  --input "outputs\${paperId}\report.md" `
  --bundle "work\${paperId}\editor\normalized_bundle.json"
```

Do not use editor-only refresh when reviewer evidence, parsing, reviewer selection, or normalized findings need to change.

## Output Contracts

Reviewer outputs must conform to `schemas/reviewer_output.schema.json` and semantic checks in `scripts/validate_review_json.py`.

Important reviewer-output expectations:

- stable IDs such as `NUM-001` matching each reviewer `id_prefix`
- explicit `issue_type`, `severity`, and `confidence`
- precise locations when possible
- `source_objects` for verifiable findings
- `cannot_verify_reason` for cannot-verify findings
- `numeric_check` for verifiable numerical-auditor findings
- `claim_evidence_links` when comparing claims with source evidence
- copyediting findings routed as `copyedit_issue`

The final report should be readable prose first, with canonical IDs and source finding IDs collected in `## Appendix: Traceability Map` rather than repeated in body footers. `scripts/check_final_report.py` is a smoke check for structure and traceability coverage; it is not a full semantic audit of every claim or external source.

## Development

Set up locally on Windows/PowerShell:

```powershell
cd C:\Users\s11378\Dropbox\reviewer
.\.venv\Scripts\Activate.ps1
python -m unittest tests.test_reviewer_config
```

Add a reviewer by adding:

1. `prompts/templates/<prompt>.txt`
2. one enabled entry in `config/reviewers.json`
3. focused tests when the reviewer changes validation, normalization, routing, or report structure

## Git Hygiene

Usually track:

- project instructions and README: `AGENTS.md`, `README.md`
- project config, skills, reviewer config, prompts, schemas, scripts, tests
- slide teaching material under `Slides/` when intentionally kept

Usually do not track:

- `inputs/*.pdf`
- `work/`
- `outputs/`
- `.venv/`
- generated documentation exports
- LaTeX slide build byproducts

Track the machinery that produces review results, not temporary run products.
