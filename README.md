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
4. routes reviewers around artifacts flagged by parser-quality preflight using retained deterministic evidence
5. dynamically selects optional reviewers while always running mandatory reviewers
6. validates every reviewer JSON output against schema and semantic checks
7. normalizes and deduplicates reviewer findings into an editor bundle
8. builds editor input from the normalized bundle and original reviewer JSON files
9. runs the editor to write `outputs/<paper_id>/report.md`
10. smoke-checks final report structure and traceability

Only the project machinery is meant to be shared on GitHub. Source PDFs, parsed artifacts, reviewer logs, and final reports are excluded from Git by default.

The deterministic PDF preprocessing step runs locally. The review itself is not fully local: rendered prompts contain parsed manuscript text and are sent through the authenticated Codex CLI to OpenAI. Reviewers configured with `search: true` may also send manuscript-derived search queries to the web-search service. Do not review a confidential manuscript unless its disclosure terms permit those transmissions.

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

By default, Codex agents use `gpt-5.6-sol` with `xhigh` reasoning for full review runs. Override the model and reasoning effort at launch when comparing quality, latency, or cost:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --model gpt-5.6-terra --reasoning-effort high
```

Current GPT-5.6 reasoning values are `none`, `low`, `medium`, `high`, `xhigh`, and `max`. The legacy `minimal` value remains accepted for older compatible models. Omit `--model` to use `.codex/config.toml`. OpenAI's [current model guide](https://developers.openai.com/api/docs/guides/latest-model.md) identifies Sol as the flagship GPT-5.6 model and Terra as the lower-price quality/cost option.

Use Sol/xhigh for a quality-first full review. Sol/high is a reasonable measured alternative for routine editor refreshes or comparison runs when turnaround matters. Reserve `max` for unusually difficult mathematical, theoretical, or adversarial checks after benchmarking it on the relevant task; higher effort should not be assumed to improve every stage.

The following editor-only benchmark used the same 419,638-byte paper9 evidence bundle. Times are wall-clock seconds on one machine and token counts are those reported by Codex, so they are representative rather than billing or runtime guarantees.

| Model and effort | Seconds | Reported tokens | Report bytes | Result |
| --- | ---: | ---: | ---: | --- |
| `gpt-5.6-terra` / `high` | 119 | 112,150 | 25,326 | Valid; concise |
| `gpt-5.6-sol` / `high` | 297 | 123,191 | 34,199 | Valid; detailed |
| `gpt-5.6-sol` / `xhigh` | 386 | 125,629 | 30,885 | Valid; strongest prioritization |

A full paper run is substantially larger because preflight, selection, each selected reviewer, and the editor are separate model calls. Reviewer count, web-search needs, paper length, cache state, service load, and reasoning effort all affect total time and token use.

A clean 12-page quality-first acceptance run selected 12 substantive reviewers and used four-way reviewer concurrency. The complete wrapper took 2,737 seconds (45.6 minutes) and reported 1,718,231 tokens: about 573 seconds and 134,458 tokens for Sol/high parser preflight, 79 seconds and 45,729 tokens for Sol/medium selection, 1,840 wall-clock seconds and 1,386,595 aggregate tokens for the concurrent Sol/xhigh reviewer panel, and 212 seconds and 151,449 tokens for the final Sol/xhigh editor. Treat these as scale examples, not estimates or billing guarantees.

The wrapper runs at most four reviewer agents concurrently by default and records the PDF hash, effective model and stage-specific reasoning effort, workflow options, Git state, selected roster, and elapsed time in `work/<paper_id>/run_manifest.json`. Parser preflight uses `high`, reviewer selection uses `medium`, and substantive reviewers plus the editor use `xhigh` by default. Evidence-heavy stages fail after 45 minutes and selector routing after 15 minutes. These limits bound how long the wrapper waits and make stalls visible; descendant-process cleanup remains platform dependent. Use `--max-parallel-reviewers`, `--agent-timeout-minutes`, or `--selector-timeout-minutes` to tune constrained or rate-limited setups.

If a run stops after a valid parser-quality preflight, resume without paying for that stage again:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --paper-id "my-paper" --resume-after-preflight
```

Resume is allowed only when both the existing run manifest and deterministic parsed manifest record the same PDF SHA-256 hash, and every configured preflight output still passes reviewer identity, schema, semantic, provenance, and parser-gate checks.

If all selected reviewer JSON files already exist, resume synthesis without rerunning the panel. The helper validates every selected review, rebuilds the normalized bundle, rerenders prompts, and rebuilds editor input before optionally running the editor:

```powershell
.\.venv\Scripts\python.exe scripts\refresh_editor.py --paper-id "my-paper" --run-editor --model gpt-5.6-sol --reasoning-effort xhigh
```

PDF preprocessing remains local and deterministic. Native PDF text, word/block coordinates, page images, and visual crops are retained as the source artifacts. A two-column page uses native content-stream order only when its block sequence verifies a left-column-then-right-column layout; otherwise the coordinate-sorted text remains in use and the page is flagged for review. Font-glyph substitutions require a verified font/code mapping and are applied only at source-aligned positions; spacing accents are composed only when font, size, baseline, and bounding-box overlap agree. Unknown math-font glyphs are preserved and flagged rather than guessed. When coordinate-sorted text cannot retain every verified glyph repair, the parser uses repaired native text for that page and records a reading-order fallback for preflight review. Caption extraction uses native positioned lines so adjacent columns are not merged. Figure and table crops may be anchored to nearby native raster/vector or text bounds, including the common case where content appears above its caption. Native table candidates substantially contained in a positively anchored figure region are suppressed, and semantic table headers are promoted only when they exactly match the observed data shape. Reference inventories use positioned hanging indents and explicit bibliography boundaries. All caption-derived table cells remain marked for visual verification. Recent local checks took about 23 seconds for 12 pages and 116 seconds for 91 pages.

The page index and manifest also flag image-heavy pages where OCR may be needed, unresolved two-column or landscape reading order, and heuristic table outputs that require visual verification. The default setup does not install or run a separate ML document parser or OCR engine, and it never silently replaces native text with inferred text.

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
- `work/<paper_id>/selection/`: reviewer selector output and selected reviewer roster.
- `work/<paper_id>/reviews/`: reviewer JSON outputs.
- `work/<paper_id>/editor/`: normalized bundle and editor input.
- `outputs/<paper_id>/report.md`: final human-readable report.

Private papers and generated review artifacts are excluded from Git by default, but review prompts are sent to OpenAI and search-enabled reviewers may issue manuscript-derived web queries. Do not commit source PDFs, `work/` artifacts, `outputs/` reports, logs, rendered prompts, reviewer JSON, or credentials. See `SECURITY.md` and `docs/public_release_checklist.md` for the full release checklist.

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

- core substantive reviewers: `numerical_auditor`, `claim_evidence_auditor`, `literature_auditor`, `identification_auditor`, `robustness_auditor`, `sample_construction_auditor`, `abstract_conclusion_consistency_auditor`, `limitations_external_validity_auditor`, and `model_equation_auditor`
- narrower pilot reviewers: `data_availability_replication_auditor`, `institutional_context_auditor`, `power_multiple_testing_auditor`, `design_randomization_auditor`, and `economic_magnitude_auditor`

The selector normally chooses 5 to 9 optional reviewers, never more than 9, and at most 2 pilots. Pilots are specialized reviewers, not lower-quality agents: they run only when the parsed paper contains a distinct central cue for their narrower audit. Together with the three mandatory review-stage agents, a normal run therefore uses 8 to 12 substantive reviewers; parser-quality preflight runs separately.

Substantive reviewers read the parser-quality output and avoid unsafe deterministic artifacts. The workflow has no LLM-generated preprocessing or repair layer. When deterministic page text, coordinates, crops, or images cannot support a reliable check, reviewers must return `cannot_verify` rather than reconstructing content.

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

## License

MIT License. See `LICENSE.md`.
