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
5. records an exhaustive static roster by default, or runs the optional-reviewer selector only when dynamic mode is explicitly requested
6. rerenders prompts for the active roster and runs all 4 mandatory plus 14 optional review-stage agents by default
7. validates every reviewer JSON output against schema, semantic, identity, and provenance checks
8. conservatively normalizes findings into a precision-first, lossless editor bundle
9. builds editor input from a deterministic brief, the lossless bundle, and a compact provenance index for the validated reviewer files
10. runs the editor to write `outputs/<paper_id>/report.md`
11. smoke-checks final report structure and traceability

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

By default, every Codex stage uses `gpt-5.6-sol`. Substantive reviewers and the editor use `xhigh` reasoning, parser-quality preflight uses `high`, and the explicit dynamic selector uses `medium`. Override the model and substantive/editor reasoning effort at launch when comparing quality, latency, or cost:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --model gpt-5.6-terra --reasoning-effort high
```

Current GPT-5.6 reasoning values are `none`, `low`, `medium`, `high`, `xhigh`, and `max`. Omit `--model` to use `.codex/config.toml`. OpenAI's [current model guide](https://developers.openai.com/api/docs/guides/latest-model) identifies Sol as the flagship GPT-5.6 model and Terra as the lower-price quality/cost option.

Use Sol/xhigh for a quality-first full review. Sol/high is a reasonable measured alternative for routine editor refreshes or comparison runs when turnaround matters. Reserve `max` for unusually difficult mathematical, theoretical, or adversarial checks after benchmarking it on the relevant task; higher effort should not be assumed to improve every stage.

The following editor-only benchmark used the same 419,638-byte paper9 evidence bundle. Times are wall-clock seconds on one machine and token counts are those reported by Codex, so they are representative rather than billing or runtime guarantees.

| Model and effort | Seconds | Reported tokens | Report bytes | Result |
| --- | ---: | ---: | ---: | --- |
| `gpt-5.6-terra` / `high` | 119 | 112,150 | 25,326 | Valid; concise |
| `gpt-5.6-sol` / `high` | 297 | 123,191 | 34,199 | Valid; detailed |
| `gpt-5.6-sol` / `xhigh` | 386 | 125,629 | 30,885 | Valid; strongest prioritization |

A full paper run is substantially larger because preflight, each active reviewer, and the editor are separate model calls. Explicit dynamic mode adds a selector call. Reviewer count, web-search needs, paper length, cache state, service load, and reasoning effort all affect total time and token use.

A historical 12-page dynamic-mode acceptance run selected 12 substantive reviewers and used four-way reviewer concurrency. The complete wrapper took 2,737 seconds (45.6 minutes) and reported 1,718,231 tokens: about 573 seconds and 134,458 tokens for Sol/high parser preflight, 79 seconds and 45,729 tokens for Sol/medium selection, 1,840 wall-clock seconds and 1,386,595 aggregate tokens for the concurrent Sol/xhigh reviewer panel, and 212 seconds and 151,449 tokens for the final Sol/xhigh editor. This is useful as a scale example, but it is not a benchmark of the current 18-reviewer static default or a runtime or billing guarantee.

A fresh 8-page static-default acceptance ran parser preflight, all 18 substantive reviewers, normalization, and the Sol/xhigh editor with four-way reviewer concurrency. It took 4,893 seconds (81.5 minutes) and reported 2,794,498 tokens. The panel produced 145 source findings, conservatively normalized to 97 canonical findings, and a valid 6,622-word report. Treat these as quality-first scale data, not a runtime, billing, or output-length guarantee.

The wrapper runs at most four reviewer agents concurrently by default and records the PDF hash, effective model and stage-specific reasoning effort, workflow options, Git state, active roster, and elapsed time in `work/<paper_id>/run_manifest.json`. Parser preflight uses `high`, substantive reviewers plus the editor use `xhigh`, and the optional dynamic selector uses `medium`. Evidence-heavy stages fail after 45 minutes; dynamic selector routing fails after 15 minutes. These limits bound how long the wrapper waits and make stalls visible; descendant-process cleanup remains platform dependent. Use `--max-parallel-reviewers`, `--agent-timeout-minutes`, or `--selector-timeout-minutes` to tune constrained or rate-limited setups.

If a run stops after a valid parser-quality preflight, resume without paying for that stage again:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --paper-id "my-paper" --resume-after-preflight
```

Resume is allowed only when both the existing run manifest and deterministic parsed manifest record the same PDF SHA-256 hash, and every configured preflight output still passes reviewer identity, schema, semantic, provenance, and parser-gate checks.

If all selected reviewer JSON files already exist, resume synthesis without rerunning the panel. The helper validates every selected review, rebuilds the normalized bundle, rerenders prompts, and rebuilds editor input before optionally running the editor:

```powershell
.\.venv\Scripts\python.exe scripts\refresh_editor.py --paper-id "my-paper" --run-editor --model gpt-5.6-sol --reasoning-effort xhigh
```

PDF preprocessing remains local and deterministic. Native PDF text, word/block coordinates, page images, and visual crops are retained as the source artifacts. A two-column page uses native content-stream order only when its block sequence verifies a left-column-then-right-column layout; otherwise the coordinate-sorted text remains in use and the page is flagged for review. Repeated running headers are filtered only after matching across pages. Font-glyph substitutions require a verified font/code mapping and are applied only at source-aligned positions; spacing accents are composed only when font, size, baseline, and bounding-box overlap agree. Unknown math-font glyphs are preserved and flagged rather than guessed. When coordinate-sorted text cannot retain every verified glyph repair, the parser uses repaired native text for that page and records a reading-order fallback for preflight review.

Caption extraction uses native positioned lines so adjacent columns are not merged. A label-only figure caption is accepted only when a same-page source note supports the exhibit; the parser retains the exact label and never invents a title. Wrapped caption continuations require conservative block, font, baseline, and alignment evidence. Figure and table crops may be anchored to nearby native raster/vector or text bounds, including the common case where content appears above its caption, and landscape captions use the full page width. Native table candidates substantially contained in a positively anchored figure region are suppressed, and semantic table headers are promoted only when they exactly match the observed data shape. Reference inventories use positioned hanging indents, merge source-aligned fragments split artificially within one reference line, filter repeated headers and narrow footnote contamination, and stop at explicit bibliography boundaries such as standalone `Figures` or `Tables` headings. All caption-derived table cells remain marked for visual verification.

The page index and manifest also flag image-heavy pages where OCR may be needed, unresolved two-column or landscape reading order, and heuristic table outputs that require visual verification. The default setup does not install or run a separate ML document parser, OCR engine, external parsing service, or LLM-generated repair layer, and it never silently replaces native text with inferred text.

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

Parser-quality preflight runs first and separately:

- `parser_quality_auditor`: preflight check for parser artifacts that could poison downstream review

Four mandatory review-stage reviewers always run:

- `crossref_auditor`: internal reference, numbering, and appendix-label checks
- `source_consistency_auditor`: high-precision checks that central prose descriptions match their cited deterministic tables, figures, equations, and sample artifacts
- `reference_auditor`: bibliography and cited-reference verification
- `grammar_auditor`: copyediting and grammar issues

Fourteen optional reviewers also run in the default static mode:

- core substantive reviewers: `numerical_auditor`, `claim_evidence_auditor`, `literature_auditor`, `identification_auditor`, `robustness_auditor`, `sample_construction_auditor`, `abstract_conclusion_consistency_auditor`, `limitations_external_validity_auditor`, and `model_equation_auditor`
- narrower pilot reviewers: `data_availability_replication_auditor`, `institutional_context_auditor`, `power_multiple_testing_auditor`, `design_randomization_auditor`, and `economic_magnitude_auditor`

The default static mode runs all 4 mandatory and all 14 optional review-stage agents, for 18 substantive reviewers after parser-quality preflight. This is the quality-first default because control runs showed that apparently overlapping specialists can still find distinct material issues. Static mode writes the exhaustive roster and its provenance without making a selector model call.

Dynamic mode is an explicit cost and latency tradeoff. Its selector normally chooses 7 to 13 optional reviewers, never more than 13, and at most 4 pilots. Together with the 4 mandatory review-stage agents, a dynamic run therefore uses 11 to 17 substantive reviewers. Pilots are specialized reviewers, not lower-quality agents: in dynamic mode they run only when the parsed paper contains a distinct central cue for their narrower audit.

Substantive reviewers read the parser-quality output and avoid unsafe deterministic artifacts. The workflow has no LLM-generated preprocessing or repair layer. When deterministic page text, coordinates, crops, or images cannot support a reliable check, reviewers must return `cannot_verify` rather than reconstructing content.

Use the ordinary command for the exhaustive static default. To accept some risk of missing a specialist issue in exchange for fewer reviewer calls, opt into dynamic selection explicitly.

Search-enabled reviewers require Codex search mode. Literature and reference verification should not be guessed; use `cannot_verify` when evidence is missing.

Run with dynamic optional-reviewer selection:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --reviewer-selection dynamic
```

Use an explicit paper id when needed:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --paper-id "my-custom-id"
```

## License

MIT License. See `LICENSE.md`.
