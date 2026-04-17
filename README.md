# Reviewer

A local, Windows-first Codex project for building and testing a multi-agent reviewer for academic economics papers.

This repo is both:
- a real workflow for paper review, and
- a learning project for using Codex in a disciplined, reproducible way.

The goal is not to build a polished product immediately. The goal is to learn a workflow with repo guidance, project-scoped config, custom agents, repo-scoped skills, `codex exec`, JSON schemas, deterministic preprocessing, validation, and editor synthesis.

Current status: `scripts/review_paper.py` is the default fresh-run entry point. The workflow has been smoke-tested across multiple papers with parser-quality preflight, dynamic reviewer selection, selected optional reviewers, editor synthesis, final report checking, and editor-only report refreshes from existing reviewer evidence.

For an external-facing explanation of the full workflow, design choices, artifacts, and prompt appendix, see `PROJECT_DOCUMENTATION.md`.

## Mental Model

The repo has several layers. They do different jobs.

- `AGENTS.md`: repo-wide guidance for Codex.
- `.codex/config.toml`: project-level Codex defaults.
- `.codex/agents/*.toml`: custom reviewer/editor definitions.
- `.agents/skills/paper-reviewer/SKILL.md`: reusable workflow playbook.
- `config/reviewers.json`: configured reviewer roster.
- `prompts/templates/*.txt`: reusable prompt templates.
- `schemas/*.json`: structured output contracts.
- `scripts/*.py`: deterministic machinery for preprocessing, validation, normalization, and orchestration.

A useful shorthand:
- agents = workers
- reviewer config = roster and run options
- skills = playbooks
- schemas = output contracts
- prompt templates = assignment patterns
- scripts = deterministic glue

## Why Preprocessing Comes First

For PDF-heavy review work, bad extraction is usually the largest source of downstream error.

The intended flow is:
1. preprocess the PDF into structured artifacts
2. render run-specific prompts
3. run the parser-quality preflight auditor
4. validate preflight JSON and fail only on high-confidence blocking parser defects
5. classify the paper and select optional reviewers, unless static mode is requested
6. write the run-specific selected reviewer roster
7. rerender prompts for the selected reviewer roster
8. run mandatory baseline reviewers and selected optional reviewers on parsed artifacts
9. validate reviewer JSON
10. normalize and deduplicate reviewer outputs
11. build editor input with a deterministic editor brief
12. run the editor
13. write the final markdown report
14. smoke-check the final report

For fresh runs, `scripts/review_paper.py` is the default entry point for this flow.

## Current Repo Layout

```text
reviewer/
|-- AGENTS.md
|-- README.md
|-- CODEX_REVIEW_PROMPT.md
|-- PIPELINE_STATUS.md
|-- .gitignore
|-- requirements.txt
|-- .codex/
|   |-- config.toml
|   `-- agents/
|-- .agents/
|   `-- skills/
|-- inputs/
|-- outputs/
|-- config/
|   `-- reviewers.json
|-- prompts/
|   `-- templates/
|-- schemas/
|-- scripts/
|-- tests/
`-- work/
```

## What Lives Where

### `inputs/`

Source PDFs. Usually not committed to Git.

Example:

```text
inputs/<paper_id>.pdf
```

### `work/`

Intermediate artifacts. Usually not committed to Git.

Examples:
- parsed page text and images
- extracted tables and figures
- rendered prompts
- reviewer JSON outputs
- normalized editor bundles
- generated editor input

### `outputs/`

Final human-readable reports. Usually not committed to Git.

### `prompts/templates/`

Reusable prompt templates tracked in Git. They should not hardcode any run-specific paper ID.

Run-specific prompt files are generated under:

```text
work/<paper_id>/prompts/
```

### `config/reviewers.json`

The enabled reviewer roster. Each reviewer entry declares the Codex agent name, prompt template, output filename, stable finding-ID prefix, whether web search is required, the normalizer role used during editor-bundle construction, the run stage, and the selection policy used by the dynamic wrapper.

Valid `normalization_role` values are:
- `manuscript`: default substantive manuscript findings
- `crossref`: cross-reference findings, including parser-artifact classification for parser/false-positive categories
- `reference`: reference-integrity findings, including bibliography-maintenance classification for outdated or metadata-typo categories
- `copyedit`: grammar and copyediting findings routed to the report appendix

Valid `stage` values are:
- `preflight`: run after preprocessing and before other reviewers; currently used by `parser_quality_auditor`
- `review`: normal reviewer stage; this is the default for older config entries without `stage`

Valid `selection_policy` values are:
- `mandatory`: always run when enabled; used for parser preflight and baseline reviewers
- `optional`: available to the selector for paper-type-dependent review

### `schemas/`

JSON schemas used for stable reviewer outputs.

Reviewer outputs use `schemas/reviewer_output.schema.json` plus semantic checks in `scripts/validate_review_json.py`. New reviewer findings must include:
- stable IDs matching the configured `id_prefix`, such as `NUM-001`
- explicit `issue_type`, `severity`, and `confidence`
- `location.precision` as `exact`, `partial`, or `missing`
- `source_objects` for verifiable findings
- `cannot_verify_reason` for cannot-verify findings
- `numeric_check` for verifiable numerical-auditor findings
- `claim_evidence_links` when a claim is compared with source evidence
- `copyedit_issue` for grammar/copyediting findings intended for the appendix table

Reviewer selection uses `schemas/reviewer_selection.schema.json`. In dynamic mode, the selector writes its decision to:

```text
work/<paper_id>/selection/reviewer_selection.json
```

The wrapper then writes the run-specific selected roster to:

```text
work/<paper_id>/selection/selected_reviewers.json
```

### `scripts/`

Deterministic workflow steps.

Current scripts:
- `preprocess_pdf.py`
- `validate_review_json.py`
- `render_prompts.py`
- `normalize_review_outputs.py`
- `build_editor_input.py`
- `check_final_report.py`
- `review_paper.py`

To add another reviewer, add `.codex/agents/<name>.toml`, add a matching prompt template under `prompts/templates/`, and add one enabled entry to `config/reviewers.json`.

## Environment Assumptions

This repo currently assumes:
- Windows
- PowerShell
- local Git
- local Python virtual environment at `.venv`
- Codex CLI available in the shell

Typical start:

```powershell
cd C:\Users\s11378\Dropbox\reviewer
.\.venv\Scripts\Activate.ps1
git status
```

## Current Best-Practice Workflow

For a fully automated fresh run, use:

```powershell
$paperId = "your-paper-id"
python scripts\review_paper.py --pdf "inputs\${paperId}.pdf"
```

This derives `paper_id` from the PDF filename, writes intermediate artifacts under `work/<paper_id>/`, writes the final report to `outputs/<paper_id>/report.md`, and stores subprocess logs under `work/<paper_id>/logs/`. By default, the wrapper uses dynamic reviewer selection: parser preflight runs first, mandatory baseline reviewers always run, and optional reviewers are selected for the paper type.

Use an explicit paper ID when needed:

```powershell
$paperId = "your-paper-id"
python scripts\review_paper.py --pdf "inputs\${paperId}.pdf" --paper-id $paperId
```

Use static mode to run all enabled reviewers without selector filtering:

```powershell
$paperId = "your-paper-id"
python scripts\review_paper.py --pdf "inputs\${paperId}.pdf" --reviewer-selection static
```

The wrapper runs a fresh pipeline, executes preflight reviewers first, selects or preserves review-stage reviewers, rerenders prompts for the selected roster, and then executes the active review-stage reviewers in parallel. The manual steps below remain useful for debugging or rerunning one stage by hand.

### Editor-Only Refresh

If preprocessing, reviewer JSON, `work/<paper_id>/selection/selected_reviewers.json`, and `work/<paper_id>/editor/normalized_bundle.json` already exist, rerun only the editor when prompt/report-shape changes do not require new reviewer evidence:

```powershell
$paperId = "your-paper-id"

python scripts\render_prompts.py `
  --paper-id $paperId `
  --parsed-dir "work\${paperId}\parsed" `
  --reviews-dir "work\${paperId}\reviews" `
  --schema-path schemas\reviewer_output.schema.json `
  --output-dir "work\${paperId}\prompts" `
  --editor-bundle-path "work\${paperId}\editor\normalized_bundle.json" `
  --reviewers-config "work\${paperId}\selection\selected_reviewers.json"

python scripts\build_editor_input.py `
  --paper-id $paperId `
  --editor-prompt "work\${paperId}\prompts\editor_report.txt" `
  --bundle "work\${paperId}\editor\normalized_bundle.json" `
  --reviews-dir "work\${paperId}\reviews" `
  --output "work\${paperId}\editor\editor_input.md" `
  --reviewers-config "work\${paperId}\selection\selected_reviewers.json"

Get-Content "work\${paperId}\editor\editor_input.md" -Raw |
  codex exec --output-last-message "outputs\${paperId}\report.md" -

python scripts\check_final_report.py `
  --input "outputs\${paperId}\report.md" `
  --bundle "work\${paperId}\editor\normalized_bundle.json"
```

### 1. Preprocess

```powershell
$paperId = "your-paper-id"
python scripts\preprocess_pdf.py --pdf "inputs\${paperId}.pdf"
```

This writes parsed artifacts under:

```text
work/<paper_id>/parsed/
```

### 2. Render Prompts

```powershell
$paperId = "your-paper-id"

python scripts\render_prompts.py `
  --paper-id $paperId `
  --parsed-dir "work\${paperId}\parsed" `
  --reviews-dir "work\${paperId}\reviews" `
  --schema-path schemas\reviewer_output.schema.json `
  --output-dir "work\${paperId}\prompts"
```

In dynamic wrapper runs, prompts are rendered once before preflight and then rendered again after selection with:

```powershell
$paperId = "your-paper-id"

python scripts\render_prompts.py `
  --paper-id $paperId `
  --parsed-dir "work\${paperId}\parsed" `
  --reviews-dir "work\${paperId}\reviews" `
  --schema-path schemas\reviewer_output.schema.json `
  --output-dir "work\${paperId}\prompts" `
  --reviewers-config "work\${paperId}\selection\selected_reviewers.json"
```

If you are debugging a static run rather than a dynamic selected run, use `config/reviewers.json` anywhere these manual examples pass `work\<paper_id>\selection\selected_reviewers.json`.

### 3. Run Reviewers

The default reviewer agents are configured in `config/reviewers.json`:
- `parser_quality_auditor` (preflight, mandatory)
- `crossref_auditor` (mandatory)
- `reference_auditor` (mandatory)
- `grammar_auditor` (mandatory)
- `numerical_auditor` (optional)
- `claim_evidence_auditor` (optional)
- `literature_auditor` (optional)
- `identification_auditor` (optional)
- `robustness_auditor` (optional)
- `sample_construction_auditor` (optional)
- `abstract_conclusion_consistency_auditor` (optional)
- `limitations_external_validity_auditor` (optional)
- `model_equation_auditor` (optional)
- `data_availability_replication_auditor` (optional)

Each reviewer reads from `work/<paper_id>/parsed/` and writes one JSON file under `work/<paper_id>/reviews/`.

The basic command shape is:

```powershell
$paperId = "your-paper-id"

Get-Content "work\${paperId}\prompts\crossref_audit.txt" -Raw |
  codex exec --output-schema schemas\reviewer_output.schema.json `
    --output-last-message "work\${paperId}\reviews\crossref_auditor.json" `
    -
```

For search-enabled reviewers, use the CLI search form supported by the installed Codex version, for example:

```powershell
codex --search exec ...
```

### 4. Validate Reviewer JSON

```powershell
$paperId = "your-paper-id"
python scripts\validate_review_json.py --schema schemas\reviewer_output.schema.json --input "work\${paperId}\reviews\crossref_auditor.json" --reviewers-config "work\${paperId}\selection\selected_reviewers.json"
```

Repeat for all configured reviewer outputs.

### 5. Normalize and Deduplicate

```powershell
$paperId = "your-paper-id"

python scripts\normalize_review_outputs.py `
  --paper-id $paperId `
  --reviews-dir "work\${paperId}\reviews" `
  --output "work\${paperId}\editor\normalized_bundle.json" `
  --reviewers-config "work\${paperId}\selection\selected_reviewers.json"
```

The normalized bundle groups overlapping findings, separates parser artifacts from manuscript issues, and removes process notes from editor-facing synthesis.

### 6. Build Editor Input

```powershell
$paperId = "your-paper-id"

python scripts\build_editor_input.py `
  --paper-id $paperId `
  --editor-prompt "work\${paperId}\prompts\editor_report.txt" `
  --bundle "work\${paperId}\editor\normalized_bundle.json" `
  --reviews-dir "work\${paperId}\reviews" `
  --output "work\${paperId}\editor\editor_input.md" `
  --reviewers-config "work\${paperId}\selection\selected_reviewers.json"
```

This writes a deterministic editor brief before the raw JSON inputs. The brief gives the editor internal guidance on optional reviewer selection, the top five high-priority synthesis candidates, additional-finding candidates, section routing, and traceability-map rows. The brief is not intended to be reproduced as report text.

### 7. Run Editor

```powershell
$paperId = "your-paper-id"
Get-Content "work\${paperId}\editor\editor_input.md" -Raw |
  codex exec --output-last-message "outputs\${paperId}\report.md" -
```

The editor must write the actual final markdown report, not a note saying where the report was saved.
The wrapper rejects implausibly short editor outputs and can recover a complete report from the editor transcript if `codex exec --output-last-message` captures a short acknowledgement after a delegated editor response.
The report should keep canonical and source finding IDs out of the main prose and collect them in a final traceability appendix, such as:

```markdown
| Report section | Finding | Canonical ID | Source finding IDs |
| --- | --- | --- | --- |
| Highest-Priority Cross-Agent Findings | Mechanism language is too strong | CANON-001 | claim_evidence_auditor:CEA-005 |
```

The intended report structure starts with synthesis and keeps audit metadata compact:
- `## Executive Summary`
- `## Review Configuration`
- `## Highest-Priority Cross-Agent Findings`
- `## Suggested Revision Priorities`
- `## Additional Findings`
- domain-specific sections for literature, references, parser caveats, and cannot-verify items
- `## Appendix: Grammar and Copyediting Issues` when copyedit findings exist
- `## Appendix: Traceability Map`

The highest-priority section is capped at five synthesis findings by `scripts/build_editor_input.py`. Lower-priority substantive issues go to `Additional Findings`, cannot-verify items should use a compact table, and all canonical/source IDs should appear in the traceability appendix rather than repeated body footers.

### 8. Check Final Report

```powershell
$paperId = "your-paper-id"

python scripts\check_final_report.py `
  --input "outputs\${paperId}\report.md" `
  --bundle "work\${paperId}\editor\normalized_bundle.json"
```

The final report checker rejects reports that are too short, look like run-status notes, omit required headings, omit the grammar appendix when copyedit findings exist, omit the traceability appendix when a normalized bundle is supplied, or omit canonical/source finding identifiers.

## Git Hygiene

Usually track:
- `AGENTS.md`
- `.codex/config.toml`
- `.codex/agents/*.toml`
- `.agents/skills/paper-reviewer/SKILL.md`
- `config/reviewers.json`
- `prompts/templates/*.txt`
- `schemas/*.json`
- `scripts/*.py`
- `requirements.txt`
- `.gitignore`
- `README.md`
- `CODEX_REVIEW_PROMPT.md`
- `PIPELINE_STATUS.md`

Usually do not track:
- `inputs/*.pdf`
- `work/`
- `outputs/`
- `.venv/`

The rule of thumb is: track the machine that produces the results, not the temporary products.
