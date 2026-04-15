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
- `prompts/templates/*.txt`: reusable prompt templates.
- `schemas/*.json`: structured output contracts.
- `scripts/*.py`: deterministic machinery for preprocessing, validation, normalization, and orchestration.

A useful shorthand:
- agents = workers
- skills = playbooks
- schemas = output contracts
- prompt templates = assignment patterns
- scripts = deterministic glue

## Why Preprocessing Comes First

For PDF-heavy review work, bad extraction is usually the largest source of downstream error.

The intended flow is:
1. preprocess the PDF into structured artifacts
2. render run-specific prompts
3. run reviewer agents on parsed artifacts
4. validate reviewer JSON
5. normalize and deduplicate reviewer outputs
6. build editor input
7. run the editor
8. smoke-check the final report
9. later, wrap the whole flow in one script

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

### `schemas/`

JSON schemas used for stable reviewer outputs.

### `scripts/`

Deterministic workflow steps.

Current scripts:
- `preprocess_pdf.py`
- `validate_review_json.py`
- `render_prompts.py`
- `normalize_review_outputs.py`
- `build_editor_input.py`
- `check_final_report.py`

Future script:
- `review_paper.py`

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

## Current Best-Practice Manual Workflow

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

The five reviewer agents are:
- `crossref_auditor`
- `numerical_auditor`
- `claim_evidence_auditor`
- `literature_auditor`
- `reference_auditor`

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

Repeat for all five reviewer outputs.

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

### 7. Run Editor

```powershell
Get-Content work\example-paper\editor\editor_input.md -Raw |
  codex exec --output-last-message outputs\example-paper\report.md -
```

The editor must write the actual final markdown report, not a note saying where the report was saved.

### 8. Check Final Report

```powershell
python scripts\check_final_report.py --input outputs\example-paper\report.md
```

## Git Hygiene

Usually track:
- `AGENTS.md`
- `.codex/config.toml`
- `.codex/agents/*.toml`
- `.agents/skills/paper-reviewer/SKILL.md`
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
