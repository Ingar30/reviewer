# Reviewer

A local, Windows-first Codex project for building and testing a multi-agent reviewer for academic economics papers.

This repo is both:
- a real workflow for paper review, and
- a learning project for using Codex in a disciplined, reproducible way.

The goal is not to build a polished product immediately. The goal is to learn a workflow with repo guidance, project-scoped config, custom agents, repo-scoped skills, `codex exec`, JSON schemas, deterministic preprocessing, validation, and editor synthesis.

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
5. run reviewer agents on parsed artifacts
6. validate reviewer JSON
7. normalize and deduplicate reviewer outputs
8. build editor input
9. run the editor
10. write the final markdown report
11. smoke-check the final report

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
inputs/example-paper.pdf
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

Reusable prompt templates tracked in Git. They should not hardcode `example-paper`.

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
python scripts\review_paper.py --pdf inputs\example-paper.pdf
```

This derives `paper_id` from the PDF filename, writes intermediate artifacts under `work/<paper_id>/`, writes the final report to `outputs/<paper_id>/report.md`, and stores subprocess logs under `work/<paper_id>/logs/`. By default, the wrapper uses dynamic reviewer selection: parser preflight runs first, mandatory baseline reviewers always run, and optional reviewers are selected for the paper type.

Use an explicit paper ID when needed:

```powershell
python scripts\review_paper.py --pdf inputs\example-paper.pdf --paper-id example-paper
```

Use static mode to run all enabled reviewers without selector filtering:

```powershell
python scripts\review_paper.py --pdf inputs\example-paper.pdf --reviewer-selection static
```

### 1. Preprocess

```powershell
python scripts\preprocess_pdf.py --pdf inputs\example-paper.pdf
```

This writes parsed artifacts under:

```text
work/example-paper/parsed/
```

### 2. Render Prompts

```powershell
python scripts\render_prompts.py `
  --paper-id example-paper `
  --parsed-dir work\example-paper\parsed `
  --reviews-dir work\example-paper\reviews `
  --schema-path schemas\reviewer_output.schema.json `
  --output-dir work\example-paper\prompts
```

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
Get-Content work\example-paper\prompts\crossref_audit.txt -Raw |
  codex exec --output-schema schemas\reviewer_output.schema.json `
    --output-last-message work\example-paper\reviews\crossref_auditor.json `
    -
```

For search-enabled reviewers, use the CLI search form supported by the installed Codex version, for example:

```powershell
codex --search exec ...
```

### 4. Validate Reviewer JSON

```powershell
python scripts\validate_review_json.py --schema schemas\reviewer_output.schema.json --input work\example-paper\reviews\crossref_auditor.json
```

Repeat for all configured reviewer outputs.

### 5. Normalize and Deduplicate

```powershell
python scripts\normalize_review_outputs.py `
  --paper-id example-paper `
  --reviews-dir work\example-paper\reviews `
  --output work\example-paper\editor\normalized_bundle.json
```

The normalized bundle groups overlapping findings, separates parser artifacts from manuscript issues, and removes process notes from editor-facing synthesis.

### 6. Build Editor Input

```powershell
python scripts\build_editor_input.py `
  --paper-id example-paper `
  --editor-prompt work\example-paper\prompts\editor_report.txt `
  --bundle work\example-paper\editor\normalized_bundle.json `
  --reviews-dir work\example-paper\reviews `
  --output work\example-paper\editor\editor_input.md
```

This writes a deterministic editor brief before the raw JSON inputs. The brief gives the editor internal guidance on optional reviewer selection, the top five high-priority synthesis candidates, additional-finding candidates, section routing, and traceability-map rows. The brief is not intended to be reproduced as report text.

### 7. Run Editor

```powershell
Get-Content work\example-paper\editor\editor_input.md -Raw |
  codex exec --output-last-message outputs\example-paper\report.md -
```

The editor must write the actual final markdown report, not a note saying where the report was saved.
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
- domain-specific sections for literature, references, parser caveats, cannot-verify items, and grammar appendix when applicable
- `## Appendix: Traceability Map`

The highest-priority section should stay selective. Lower-priority substantive issues and cannot-verify items should use compact tables where possible.

### 8. Check Final Report

```powershell
python scripts\check_final_report.py `
  --input outputs\example-paper\report.md `
  --bundle work\example-paper\editor\normalized_bundle.json
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
