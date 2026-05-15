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
4. optionally runs an experimental parser repair LLM agent when parser-quality preflight reports high- or medium-severity parser artifacts
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
- `scripts/pipeline_paths.py`: shared runtime path conventions for wrappers and forked workflows.
- `tests/`: focused unit tests for reviewer config, validation, normalization, editor brief behavior, and report checks.
- `.github/`: CI, issue templates, and pull request template.
- `.github/dependabot.yml`: weekly dependency checks for GitHub Actions and Python requirements.
- `setup.ps1` and `setup.sh`: local bootstrap helpers.
- `scripts/check_environment.py`: fast local readiness check for dependencies, project files, and Codex CLI.
- `scripts/check_tracked_sensitive_names.py`: pre-push scanner for unexpected sensitive variable names in shareable files.
- `docs/first_review_walkthrough.md`: step-by-step path for a new user running a first private review.
- `docs/extension_guide.md`: reviewer and wrapper extension points for forks.
- `docs/repository_settings.md`: recommended GitHub settings for public or private repository use.

Local/private runtime locations:

- `inputs/`: source PDFs.
- `work/<paper_id>/parsed/`: parsed page text, page images, inventories, tables, figures, citations, crossrefs, and manifest files.
- `work/<paper_id>/prompts/`: rendered run-specific prompts.
- `work/<paper_id>/repair/`: optional parser repair plan, reviewer-facing repair notes, repair manifest, and repaired overlay artifacts.
- `work/<paper_id>/selection/`: reviewer selector output and selected reviewer roster.
- `work/<paper_id>/reviews/`: reviewer JSON outputs.
- `work/<paper_id>/editor/`: normalized bundle and editor input.
- `outputs/<paper_id>/report.md`: final human-readable report.

Private papers and generated review artifacts are local by default. Do not commit source PDFs, `work/` artifacts, `outputs/` reports, logs, rendered prompts, reviewer JSON, or credentials. See `SECURITY.md` and `docs/public_release_checklist.md` for the full release checklist.

## Open Development

This project is intended to support reproducible AI-assisted paper-review workflows without publishing the papers being reviewed. Issues, pull requests, examples, and tests should use synthetic fixtures, public-domain examples, or short non-sensitive snippets rather than private manuscripts or generated review outputs.

Useful contributions include:

- better deterministic preprocessing and artifact inventories
- reviewer prompts, schemas, validators, and normalization rules that improve traceability
- tests that capture parser, reviewer-selection, editor, or privacy-hygiene failures
- documentation for running the workflow on new platforms or adapting it to related review settings

Forks can usually extend the workflow by adding reviewer entries in `config/reviewers.json`, prompt templates in `prompts/templates/`, and matching validation or normalization tests when the output contract changes. Shared runtime paths live in `scripts/pipeline_paths.py` so wrappers can reuse the same `inputs/`, `work/`, and `outputs/` layout.

See `docs/extension_guide.md` for the main reviewer, schema, prompt, normalization, and wrapper extension points.

See `CONTRIBUTING.md` for pull request expectations and local checks.

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

Experimental parser repair modes:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --parser-repair plan
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --parser-repair overlay
```

`plan` writes reviewer guidance only. `overlay` may also write narrow LLM-generated repaired artifacts under `work/<paper_id>/repair/repaired_artifacts/`, plus `repair_manifest.json`. Neither mode overwrites `work/<paper_id>/parsed/`.

Use an explicit paper id when needed:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --paper-id "my-custom-id"
```

## License

MIT License. See `LICENSE.md`.
