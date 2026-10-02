# Reviewer

A reproducible multi-agent reviewer for academic economics papers, using Codex or Claude Code. The repository contains the preprocessing, reviewer prompts, validation, normalization, editor assembly, and tests. Papers and generated reports remain local and are not included.

## What It Does

For each paper, the wrapper:

1. preprocesses the PDF locally into source-faithful text, coordinates, page images, tables, figures, citations, and cross-references
2. runs a parser-quality preflight before substantive review
3. selects every reviewer whose remit is plausibly relevant, with a full-roster fallback when applicability is uncertain
4. runs the reviewer panel and validates every structured JSON result
5. conservatively normalizes clear duplicates without discarding source evidence
6. asks the editor to lead with concrete correctness and auditability problems, followed by broader positioning and development suggestions
7. writes and smoke-checks the final report at `outputs/<paper_id>/report.md`

The PDF parser is deterministic and local. It does not use an external document service, hosted OCR, or an LLM repair layer, and it never invents missing signs, values, labels, cells, or formulas. Unsafe artifacts are flagged so reviewers can use page images or return `cannot_verify`.

The review itself is not fully local: parsed manuscript text is sent to OpenAI when using Codex, or to Anthropic when using Claude Code. Search-enabled reviewers may also send manuscript-derived queries to web search. Do not review a confidential paper unless its disclosure terms permit those transmissions.

## Quick Start

### 1. Get the Repository

```powershell
git clone https://github.com/Ingar30/reviewer.git
cd reviewer
```

Git is convenient but not required. You can also download the repository as a ZIP and open a shell in the extracted folder.

### 2. Install Prerequisites

You need:

- Python 3.12 or newer
- One authenticated CLI: **Codex or Claude Code** (you do not need both)
- Access to your chosen model and the CLI's web-search tools

| Backend | Sign in | Default model | Lower-cost option |
| --- | --- | --- | --- |
| Codex | `codex login` | GPT-6.1 Sol | GPT-6 Luna |
| Claude Code | `claude auth login` | Opus 5.5 | Sonnet 5.5 |

Use an up-to-date CLI. See [model options](docs/model_profiles.md) and
[Claude setup](docs/claude_code.md) for version requirements and lower-cost choices.

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

### 4. Check the Install

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest
.\.venv\Scripts\python.exe scripts\check_environment.py
```

macOS/Linux:

```bash
./.venv/bin/python -m unittest
./.venv/bin/python scripts/check_environment.py
```

For Claude, add `--backend claude` to the environment-check command. These checks
do not save a preference; choose your backend when starting your first review.

### 5. Add a Paper Locally

Put the source PDF in `inputs/`. The directory is ignored by Git.

```text
inputs/my-paper.pdf
```

### 6. Run the Review

Choose one command, using the Python environment activated above.

**Codex:**

```powershell
python scripts/review_paper.py --backend codex --pdf "inputs/my-paper.pdf"
```

**Claude Code:**

```powershell
python scripts/review_paper.py --backend claude --pdf "inputs/my-paper.pdf"
```

The backend choice is remembered for new papers in this workspace (the repository
folder for this workflow). You can omit `--backend` next time, or choose explicitly
for another new paper. Existing papers keep their original backend when resumed.
Commands with no saved choice still use Codex, so existing scripts keep working.
The selected backend and model are printed at startup; Reviewer never switches
providers automatically. `--help` and prerequisite checks do not change your preference.

The final report is written to:

```text
outputs/my-paper/report.md
```

Intermediate parsed artifacts, prompts, logs, reviewer outputs, routing decisions, and the editor bundle are written to:

```text
work/my-paper/
```

Use an explicit paper ID when needed:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --paper-id "my-custom-id"
```

## Optional: Run with uv

The Quick Start above remains the primary workflow; **uv is optional**. `uvx`
comes with uv and sets up Reviewer and its Python dependencies in an isolated
environment, so you do not need to clone this repository or create a virtual
environment yourself.

**One-time setup:** you still need Git, Python 3.12+, and your chosen CLI installed
and authenticated (see [prerequisites](#2-install-prerequisites)). Install uv on
Windows using PowerShell:

```powershell
winget install --id astral-sh.uv -e
```

For macOS/Linux or other installation methods, see the
[uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).
Open a new terminal after installation and run `uvx --version` to check that it
is available.

**Start a review:** open a terminal in the folder containing `paper.pdf` and
choose one command below. Replace `"paper.pdf"` with your PDF's filename or its
full quoted path; the folder does not need to contain the Reviewer repository.

**Codex:**

```text
uvx --from git+https://github.com/Ingar30/reviewer.git economics-paper-reviewer --backend codex --pdf "paper.pdf"
```

**Claude Code:**

```text
uvx --from git+https://github.com/Ingar30/reviewer.git economics-paper-reviewer --backend claude --pdf "paper.pdf"
```

For lower-cost models, see [model options](docs/model_profiles.md) or
[Claude model choices](docs/claude_code.md#choose-a-model).

This uses the same review pipeline and your chosen CLI account, consumes normal review
quota, and needs no new API key. Replace `--pdf "paper.pdf"` with `--help` or
`--check` for checks without a review; `--check` does not verify model access or
remaining quota. The manuscript-transmission notice above still applies.

Input paths resolve from your current directory, which need not be a Git repo.
Papers, intermediates and reports persist in `./reviewer-workspace/`, outside uv's
cache; choose another location with `--workspace "D:/Review work"`. The report is
at `outputs/<paper_id>/report.md` inside that workspace. Back it up; use distinct
paper IDs or workspaces for papers with the same filename stem.
The backend choice is remembered in that workspace, so later commands can omit
`--backend`. The original command without this flag still works and uses Codex
when no choice has been saved.

Existing review flags still work. Resume with the same workspace, paper ID and
runtime: new runs support `--resume-incomplete` to reuse validated completed
reviewers after preflight/routing; `--resume-after-preflight` reuses preflight but reruns substantive reviews;
`--refresh-editor --paper-id paper --run-editor` reuses completed reviewer outputs.
Keep the original wheel or pin a Git commit (`...reviewer.git@COMMIT`) for recovery.
Changed runtime resources and unrelated nonempty workspaces are not overwritten.
Codex sandbox, approval and trust rules are unchanged; no bypass is enabled.

Tested on Windows x64/Python 3.12, including live reviews. A sleep-interrupted
GPT-6 run required manual recovery; unattended recovery is not established.
Other platforms have not had live-review validation here. See
[validation and local-package testing](docs/uv_validation.md).

## Claude Code setup

`--backend claude` uses the **same pipeline, review prompts and validators**,
through Claude Code subscription login (no API key).
It defaults to Opus 5.5 (`claude-opus-5-5`); install Claude Code 2.1.280+ and sign in
with `claude auth login`. Check prerequisites without a review:

```powershell
python scripts/check_environment.py --backend claude
```

Add `--backend claude` to the ordinary review command, or use the optional uv launcher:

```text
uvx --from git+https://github.com/Ingar30/reviewer.git economics-paper-reviewer --backend claude --pdf "paper.pdf"
```

With uv, results persist in `./reviewer-workspace/`; `--workspace DIR` is optional.
Use a new paper ID or workspace for backend comparisons. Resumes reuse the saved backend.

For a lower-cost Claude option, choose **Sonnet 5.5** with `--model`:

```powershell
python scripts/review_paper.py --backend claude --model claude-sonnet-5-5 --pdf "inputs/my-paper.pdf"
```

Or with the optional uv launcher:

```text
uvx --from git+https://github.com/Ingar30/reviewer.git economics-paper-reviewer --backend claude --model claude-sonnet-5-5 --pdf "paper.pdf"
```

Sonnet 5.5 needs Claude Code **2.1.284+**; run `claude update` if needed.
It generally uses less subscription allowance than Opus, but its review quality has not yet
been benchmarked here. Opus remains the default.
Reviews send your paper to Claude and use your subscription allowance. Keep
Usage credits / Extra usage off to stay within your subscription.
See [model choices, setup and resuming a review](docs/claude_code.md).

## Quality Defaults

Each backend has its own default: **GPT-6.1 Sol** (`gpt-6.1-sol`) for Codex and **Opus 5.5** (`claude-opus-5-5`) for Claude. Both use `xhigh` reasoning for substantive reviewers and the editor and `high` for parser-quality preflight and applicability routing. The [model notes](docs/model_profiles.md) describe the available comparisons. The GPT-6.1 Sol live test used Codex CLI 0.159.0; update an older CLI if the model is unavailable.

For a lower-cost Codex option, explicitly select **GPT-6 Luna** (`gpt-6-luna`):

```powershell
python scripts/review_paper.py --backend codex --pdf "inputs/my-paper.pdf" --model gpt-6-luna --reasoning-effort xhigh
```

Luna is the lowest-cost tested Codex option, but not an equivalent-coverage replacement.
In a small three-reviewer comparison, Luna at `xhigh` used about 19 times fewer
estimated Standard credits than GPT-6.1 Sol at `high`, but missed more source-checked
issues. For broader coverage with less reasoning than the default, try Sol with
`--reasoning-effort high`. See [model comparisons](docs/model_profiles.md#luna-xhigh-versus-sol-61-high---2026-10-02)
for the limited evidence; this was not a full-pipeline comparison.

To deliberately use another combination:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model MODEL_ID --reasoning-effort EFFORT
```

Supported effort values are `none`, `low`, `medium`, `high`, `xhigh`, and `max`. Overrides apply only to that run and should be treated as unbenchmarked unless evaluated on representative papers. The run manifest records the effective model and reasoning settings.

The wrapper runs up to four reviewer agents concurrently and records the PDF hash, effective model, reasoning settings, active roster, Git state, and elapsed time in `work/<paper_id>/run_manifest.json`.

## Resume a Run

For a run started with this version that completed preflight and routing, reuse
validated completed reviewers and retry only unfinished stages:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --paper-id "my-paper" --resume-incomplete
```

Keep the original runtime, PDF, model, effort settings and workspace. Changed
inputs or accepted outputs are refused; this does not upgrade older checkpoints.
The backend is recovered from the saved run. There is no automatic quota retry or
paid fallback. If preflight itself did not finish, repeat the original command.

If a run stops after a valid parser-quality preflight, resume without rerunning that stage:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --paper-id "my-paper" --resume-after-preflight
```

If all selected reviewer JSON files already exist, rebuild the editor inputs and rerun only the editor:

```powershell
python scripts/refresh_editor.py --paper-id "my-paper" --run-editor
```

Both helpers validate the saved PDF hash and existing artifacts before reuse.

## Reviewer Coverage

Parser-quality preflight runs first. Eight universal reviewers then cover:

- cross-references
- source consistency
- claim-evidence alignment
- literature and positioning
- reference integrity
- grammar and copyediting
- abstract/conclusion consistency
- models, equations, notation, and estimands

Eleven conditional specialists cover numerical checks, identification, robustness, sample construction, limitations and external validity, theory logic, data availability and replication, institutional context, power and multiple testing, design and randomization, and economic magnitude.

A specialist is skipped only when a high-confidence classification shows that its entire remit is absent. Mixed, unknown, or lower-confidence papers use the full 19-reviewer substantive roster. Literature and reference verification use web search and return `cannot_verify` when evidence is unavailable.

Reviewers are configured in `config/reviewers.json`.

## Repository Map

Tracked project machinery:

- `.codex/config.toml`: project model and reasoning defaults
- `.agents/skills/paper-reviewer/SKILL.md`: reusable workflow playbook
- `config/reviewers.json`: reviewer roster and metadata
- `prompts/templates/`: reviewer, routing, and editor prompts
- `schemas/`: structured output contracts
- `scripts/`: preprocessing, orchestration, validation, normalization, and report checks
- `tests/`: focused regression tests
- `docs/first_review_walkthrough.md`: step-by-step first-run guide
- `docs/extension_guide.md`: extension points for forks

Local/private runtime locations:

- `inputs/`: source PDFs
- `work/<paper_id>/parsed/`: deterministic parsed artifacts
- `work/<paper_id>/selection/`: applicability decision and active roster
- `work/<paper_id>/reviews/`: reviewer JSON
- `work/<paper_id>/editor/`: normalized bundle and editor input
- `outputs/<paper_id>/report.md`: final report

Do not commit PDFs, generated prompts, reviewer JSON, logs, editor bundles, reports, credentials, or local Codex runtime state. See `SECURITY.md` and `docs/public_release_checklist.md`.

## Development

Useful contributions include deterministic preprocessing improvements, reviewer prompts and validators, conservative normalization, tests, and cross-platform documentation. Use synthetic fixtures, public-domain examples, or short non-sensitive snippets in issues and pull requests.

Before sharing changes, run:

```powershell
python -m unittest
python scripts/check_shareable_repo.py --include-untracked
python scripts/check_tracked_sensitive_names.py
git diff --check
```

See `CONTRIBUTING.md` and `docs/extension_guide.md`.

For optional, source-adjudicated model comparisons, see the [benchmark exercise](docs/model_benchmark.md). Preparation and scoring are offline; model runs require explicit opt-in.

## License

MIT License. See `LICENSE.md`.
