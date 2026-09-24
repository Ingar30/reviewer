# Reviewer

A reproducible multi-agent reviewer for academic economics papers. The repository contains the preprocessing, reviewer prompts, validation, normalization, editor assembly, tests, and Codex project instructions. Papers and generated reports remain local and are not included.

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

The review itself is not fully local: parsed manuscript text is sent to OpenAI through the authenticated Codex CLI by default, or to Anthropic when you explicitly choose the optional Claude Code backend. Search-enabled reviewers may also send manuscript-derived queries to web search. Do not review a confidential paper unless its disclosure terms permit those transmissions.

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
- An up-to-date Codex CLI installed and authenticated
- access to GPT-6 Sol (or your selected override) and Codex web search

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

### 5. Add a Paper Locally

Put the source PDF in `inputs/`. The directory is ignored by Git.

```text
inputs/my-paper.pdf
```

### 6. Run the Review

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf"
```

macOS/Linux:

```bash
./.venv/bin/python scripts/review_paper.py --pdf "inputs/my-paper.pdf"
```

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

The Quick Start above remains the primary workflow; **uv is optional**. With
[uv installed](https://docs.astral.sh/uv/getting-started/installation/), Python
3.12+, Git, and Codex CLI on PATH authenticated through `codex login`, run from
the directory containing your PDF:

```text
uvx --from git+https://github.com/Ingar30/reviewer.git economics-paper-reviewer --pdf "paper.pdf"
```

This uses the same review pipeline and Codex account, consumes normal review
quota, and needs no new API key. Replace `--pdf "paper.pdf"` with `--help` or
`--check` for checks without a review; `--check` does not verify model access or
remaining quota. The manuscript-transmission notice above still applies.

Input paths resolve from your current directory, which need not be a Git repo.
Papers, intermediates and reports persist in `./reviewer-workspace/`, outside uv's
cache; choose another location with `--workspace "D:/Review work"`. The report is
at `outputs/<paper_id>/report.md` inside that workspace. Back it up; use distinct
paper IDs or workspaces for papers with the same filename stem.

Existing review flags still work. Resume with the same workspace, paper ID and
runtime: `--resume-after-preflight` reuses preflight but reruns substantive reviews;
`--refresh-editor --paper-id paper --run-editor` reuses completed reviewer outputs.
Keep the original wheel or pin a Git commit (`...reviewer.git@COMMIT`) for recovery.
Changed runtime resources and unrelated nonempty workspaces are not overwritten.
Codex sandbox, approval and trust rules are unchanged; no bypass is enabled.

Tested on Windows x64/Python 3.12, including live reviews. A sleep-interrupted
GPT-6 run required manual recovery; unattended recovery is not established.
Other platforms have not had live-review validation here. See
[validation and local-package testing](docs/uv_validation.md).

## Optional: Run with Claude Code (experimental)

Codex remains the default. An optional `--backend claude` uses the **same pipeline,
review prompts and validators**, through Claude Code subscription login (no API key).
It defaults to Opus 5.5 (`claude-opus-5-5`); install Claude Code 2.1.280+ and sign in
with `claude auth login`. Check prerequisites without a review:

```powershell
python scripts/check_environment.py --backend claude
```

Add `--backend claude` to the ordinary review command, or use the optional uv launcher:

```text
uvx --from git+https://github.com/Ingar30/reviewer.git economics-paper-reviewer --backend claude --pdf "paper.pdf"
```

Results persist in `./reviewer-workspace/`; `--workspace DIR` is optional. Use a
separate workspace for backend comparisons and repeat the backend flag on resume.
**Experimental: partial live Windows testing only; a complete live Claude pipeline
is not yet validated.**
Claude receives manuscript content and consumes your subscription allowance; a long
review can exhaust a session. Leave Usage credits / Extra usage OFF to avoid paid
overage. Ordinary resume reruns substantive reviewers, not just unfinished ones.
See [setup, recovery limitations and tester feedback](docs/claude_code.md).

## Quality Defaults

The default is **GPT-6 Sol** (`gpt-6-sol`), with `xhigh` reasoning for substantive reviewers and the editor and `high` for parser-quality preflight and applicability routing. [GPT-6 Sol supports these reasoning settings](https://developers.openai.com/api/docs/models/gpt-6-sol). After selected-reviewer tests on three papers, both GPT-6 models completed a full-pipeline comparison on one 71-page paper. Sol retained more consequential corrections; this is limited evidence, not a general accuracy benchmark.

For a lower-cost option, explicitly select **GPT-6 Luna** (`gpt-6-luna`):

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model gpt-6-luna --reasoning-effort xhigh
```

Luna was substantially cheaper in the recorded comparison but missed material corrections; do not assume Sol-equivalent coverage. It required manual continuation after a sleep-related timeout, and both reports needed human judgment. See [Model Overrides](docs/model_profiles.md) for measured tokens, estimated credits, and validation limits. Actual quota consumption was not measured. Both options use the same workflow and authenticated Codex CLI.

To deliberately use another combination:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model MODEL_ID --reasoning-effort EFFORT
```

Supported effort values are `none`, `low`, `medium`, `high`, `xhigh`, and `max`. Overrides apply only to that run and should be treated as unbenchmarked unless evaluated on representative papers. The run manifest records the effective model and reasoning settings.

The wrapper runs up to four reviewer agents concurrently and records the PDF hash, effective model, reasoning settings, active roster, Git state, and elapsed time in `work/<paper_id>/run_manifest.json`.

## Resume a Run

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

## License

MIT License. See `LICENSE.md`.
