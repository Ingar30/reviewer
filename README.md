# Reviewer

A reproducible multi-agent reviewer for academic economics papers. The repository contains the workflow machinery: preprocessing scripts, reviewer prompts, schemas, validation, normalization, editor assembly, tests, and Codex project instructions. It does not include papers or generated review outputs.

The main entry point is:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\<paper_id>.pdf"
```

On macOS/Linux, use `./.venv/bin/python` instead of `.\.venv\Scripts\python.exe`.

## What This Does

For a fresh paper, the wrapper:

1. preprocesses the PDF into structured artifacts under `work/<paper_id>/parsed/`
2. renders run-specific prompts under `work/<paper_id>/prompts/`
3. runs parser-quality preflight before substantive review
4. optionally runs a parser repair LLM agent when parser-quality preflight reports high- or medium-severity parser artifacts
5. dynamically selects optional reviewers while always running mandatory reviewers
6. validates every reviewer JSON output against schema and semantic checks
7. normalizes and deduplicates reviewer findings into an editor bundle
8. builds editor input from the normalized bundle and original reviewer JSON files
9. runs the editor to write `outputs/<paper_id>/report.md`
10. smoke-checks final report structure and traceability

Only the project machinery is meant to be shared on GitHub. Source PDFs, parsed artifacts, reviewer logs, and final reports are local/private by default.

## Quick Start

### 1. Get The Repository

```powershell
git clone https://github.com/Ingar30/reviewer.git
cd reviewer
```

Git is convenient for cloning and contributing, but it is not required to run the reviewer. You can also download the repository as a ZIP from GitHub and open a shell in the extracted folder.

### 2. Install Prerequisites

You need:

- Python 3.12 or newer
- Codex CLI installed and authenticated
- access to the model/search features needed by your reviewer configuration

### 3. Set Up Python

Windows PowerShell:

```powershell
.\setup.ps1
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
bash setup.sh
source .venv/bin/activate
```

Manual setup is also fine:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Check The Install

```powershell
.\.venv\Scripts\python.exe -m unittest
.\.venv\Scripts\python.exe scripts\check_environment.py
```

### 5. Add A Paper Locally

Put a source PDF in `inputs/`. Files in `inputs/` are ignored by Git.

```text
inputs/my-paper.pdf
```

### 6. Run A Review

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf"
```

The final report will be written to:

```text
outputs/my-paper/report.md
```

The intermediate parsed artifacts, prompts, logs, reviewer outputs, selection output, and editor bundle will be written to:

```text
work/my-paper/
```

## Repository Map

Tracked project machinery:

- `AGENTS.md`: Codex-facing workflow and safety instructions.
- `.codex/config.toml`: project-level Codex defaults.
- `.agents/skills/paper-reviewer/SKILL.md`: reusable workflow playbook.
- `config/reviewers.json`: enabled reviewer roster and reviewer metadata.
- `prompts/templates/*.txt`: reusable prompt templates.
- `schemas/*.json`: structured output contracts.
- `scripts/*.py`: deterministic preprocessing, validation, orchestration, normalization, and report checks.
- `scripts/run_parser_repair_agent.py`: opt-in post-preflight parser repair overlay generation.
- `scripts/evaluate_parser_repair.py`: scoring helper for parser repair plan experiments.
- `tests/`: focused unit tests for reviewer config, validation, normalization, editor brief behavior, and report checks.
- `.github/`: CI, issue templates, and pull request template.
- `.github/dependabot.yml`: weekly dependency checks for GitHub Actions and Python requirements.
- `setup.ps1` and `setup.sh`: local bootstrap helpers.
- `scripts/check_environment.py`: fast local readiness check for dependencies, project files, and Codex CLI.
- `scripts/check_tracked_sensitive_names.py`: pre-push scanner for unexpected sensitive variable names in shareable files.
- `docs/first_review_walkthrough.md`: step-by-step path for a new user running a first private review.
- `docs/repository_settings.md`: recommended GitHub settings for the private repository.

Local/private runtime locations:

- `inputs/`: source PDFs.
- `work/<paper_id>/parsed/`: parsed page text, page images, inventories, tables, figures, citations, crossrefs, and manifest files.
- `work/<paper_id>/prompts/`: rendered run-specific prompts.
- `work/<paper_id>/repair/`: optional parser repair plan and reviewer-facing repair notes.
- `work/<paper_id>/selection/`: reviewer selector output and selected reviewer roster.
- `work/<paper_id>/reviews/`: reviewer JSON outputs.
- `work/<paper_id>/editor/`: normalized bundle and editor input.
- `outputs/<paper_id>/report.md`: final human-readable report.

## Privacy And Git Hygiene

Do not commit:

- source PDFs or other paper files
- parsed artifacts under `work/`
- rendered prompts or logs from real papers
- reviewer JSON outputs
- editor bundles
- final reports
- API keys, tokens, passwords, credentials, or authenticated CLI config

The `.gitignore` file is configured to keep `inputs/`, `work/`, and `outputs/` contents local while retaining README placeholders for those directories. Before pushing or making the repository public, inspect tracked files:

```powershell
git ls-files
git status --short
.\.venv\Scripts\python.exe scripts\check_shareable_repo.py --include-untracked
.\.venv\Scripts\python.exe scripts\check_tracked_sensitive_names.py
```

See `docs/public_release_checklist.md` before switching the GitHub repository from private to public.

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

Mandatory reviewers always run:

- `parser_quality_auditor`: preflight check for parser artifacts that could poison downstream review
- `crossref_auditor`: internal reference, numbering, and appendix-label checks
- `reference_auditor`: bibliography and cited-reference verification
- `grammar_auditor`: copyediting and grammar issues

Optional reviewers are selected dynamically by default:

- core substantive reviewers: `numerical_auditor`, `claim_evidence_auditor`, `literature_auditor`, `identification_auditor`, `robustness_auditor`, `sample_construction_auditor`, `abstract_conclusion_consistency_auditor`, `limitations_external_validity_auditor`, `model_equation_auditor`, and `data_availability_replication_auditor`
- narrower pilot reviewers: `institutional_context_auditor`, `power_multiple_testing_auditor`, `design_randomization_auditor`, and `economic_magnitude_auditor`

Use dynamic selection for normal runs. Use static mode only when all enabled review-stage reviewers should run.

Search-enabled reviewers require Codex search mode. Literature and reference verification should not be guessed; use `cannot_verify` when evidence is missing.

Run all enabled review-stage reviewers without selector filtering:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --reviewer-selection static
```

Use an explicit paper id when needed:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --paper-id "my-custom-id"
```

## Parser Repair Overlay

An experimental post-preflight parser repair planner can be enabled after parser-quality preflight and before substantive review:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --parser-repair plan
```

The repair planner writes:

- `work/<paper_id>/repair/parser_repair_plan.json`
- `work/<paper_id>/repair/parser_repair_notes.md`

Substantive reviewer prompts then include the repair-notes path so reviewers know which parsed artifacts to trust, which fallback artifacts to prefer, and which artifacts should not be used as primary evidence. This is an overlay and triage mechanism, not a replacement for deterministic preprocessing fixes: it does not run OCR, regenerate crops, reconstruct tables, or modify raw PDFs.

The wrapper invokes the repair planner only when parser-quality preflight reports high- or medium-severity `parser_artifact` findings. If no such issue is reported, `--parser-repair plan` is skipped and the run proceeds without an LLM repair call.

## Editor-Only Refresh

Use editor-only refresh when parsed artifacts, reviewer JSON, selected reviewer config, and `work/<paper_id>/editor/normalized_bundle.json` already exist, and the change only affects editor presentation or report shape.

Build refreshed editor input without making a new Codex call:

```powershell
.\.venv\Scripts\python.exe scripts\refresh_editor.py --paper-id "my-paper"
```

Run the editor and smoke-check the refreshed report:

```powershell
.\.venv\Scripts\python.exe scripts\refresh_editor.py --paper-id "my-paper" --run-editor
```

The lower-level commands are:

```powershell
$paperId = "my-paper"

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

Run the test suite:

```powershell
python -m unittest
```

Add a reviewer by adding:

1. `prompts/templates/<prompt>.txt`
2. one enabled entry in `config/reviewers.json`
3. focused tests when the reviewer changes validation, normalization, routing, or report structure

GitHub Actions runs `python -m unittest` on pushes and pull requests to `main` or `master`.

## License

No public open-source license has been selected yet. See `LICENSE.md`. Choose a real license before making the repository public.
