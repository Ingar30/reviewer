# Reviewer

A local, Windows-first Codex project for building and testing a **multi-agent reviewer for academic economics papers**.

This repo is partly a real tool and partly a learning project. The goal is not to build a polished product immediately. The goal is to learn how to use Codex well with:

- repo guidance
- project-scoped config
- custom agents
- repo-scoped skills
- `codex exec` workflows
- JSON schemas and validation
- a preprocessing-first pipeline

The current design is:

1. Put a paper PDF in `inputs/`
2. Preprocess it into structured artifacts under `work/<paper_id>/parsed/`
3. Run several specialized reviewer agents
4. Validate each reviewer JSON output against a shared schema
5. Run an editor that synthesizes a final Markdown report
6. Later, wrap the full pipeline in one script

---

## Mental model

This repo has four different layers. They are not the same thing.

### 1. `AGENTS.md`
This is the **repo-wide guidance** for Codex.

Think:
- overall project purpose
- default workflow rules
- folder conventions
- how Codex should behave in this repo

### 2. `.codex/config.toml`
This is the **project-level Codex configuration**.

Think:
- model defaults
- reasoning effort defaults
- sandbox / approvals
- project-root behavior

### 3. `.codex/agents/*.toml`
These are the **custom subagent definitions**.

Think:
- who the workers are
- their role descriptions
- their default behavior

Examples:
- `literature_auditor.toml`
- `numerical_auditor.toml`
- `reference_auditor.toml`
- `crossref_auditor.toml`
- `claim_evidence_auditor.toml`
- `editor.toml`

### 4. `.agents/skills/paper-reviewer/SKILL.md`
This is the **repo skill**.

Think:
- the workflow playbook
- when the workflow should be used
- how the pieces fit together

A useful shorthand is:

- **agents = workers**
- **skills = playbooks**
- **schema = output contract**
- **prompt file = this run’s assignment memo**

---

## Why the project is structured this way

The repo uses a **preprocessing-first** design.

That is deliberate.

For PDF-heavy review work, the biggest source of downstream error is usually not the model prompt. It is bad PDF extraction. If the parsed artifacts are poor, all reviewer agents become less reliable.

So the pipeline is:

- deterministic Python preprocessing first
- then reviewer agents
- then schema validation
- then editor synthesis

This also makes the workflow easier to debug.

---

## Current repo layout

```text
reviewer/
├─ AGENTS.md
├─ README.md
├─ REPO_AUDIT.md
├─ .gitignore
├─ requirements.txt
├─ .codex/
│  ├─ config.toml
│  └─ agents/
│     ├─ literature_auditor.toml
│     ├─ numerical_auditor.toml
│     ├─ reference_auditor.toml
│     ├─ crossref_auditor.toml
│     ├─ claim_evidence_auditor.toml
│     └─ editor.toml
├─ .agents/
│  └─ skills/
│     └─ paper-reviewer/
│        ├─ SKILL.md
│        ├─ agents/
│        │  └─ openai.yaml
│        └─ references/
├─ inputs/
├─ outputs/
├─ prompts/
├─ schemas/
├─ scripts/
├─ tests/
└─ work/
```

---

## What lives where

### `inputs/`
Source PDFs go here.

Typical usage:
- `inputs/example-paper.pdf`

These files are usually **not committed to Git**.

### `work/`
Intermediate artifacts go here.

Typical usage:
- parsed text
- page images
- extracted tables
- reviewer JSON outputs

These files are usually **not committed to Git**.

### `outputs/`
Final human-readable reports go here.

These files are usually **not committed to Git**.

### `prompts/`
Run-specific prompt files live here.

These are not the same as custom-agent definitions.

Think:
- agent TOML = the reviewer’s job description
- prompt file = today’s assignment

### `schemas/`
JSON schemas live here.

These define the required output shape for reviewer runs.

### `scripts/`
Python scripts for deterministic workflow steps.

Current examples:
- `preprocess_pdf.py`
- `validate_review_json.py`

---

## Environment assumptions

This repo currently assumes:

- Windows
- PowerShell
- local Git
- a local Python virtual environment at `.venv`
- Codex CLI available in the shell

Repo path used during setup:

```text
C:\Users\s11378\Dropbox\reviewer
```

---

## Starting a session

Open PowerShell in the repo root, then activate the local Python environment.

```powershell
cd C:\Users\s11378\Dropbox\reviewer
.\.venv\Scripts\Activate.ps1
```

If your terminal already opens in the repo root, you can skip the `cd` line.

You know the environment is active when the prompt starts with:

```text
(.venv)
```

To stop using the virtual environment in the current shell:

```powershell
deactivate
```

---

## Why `.venv` exists

`.venv` is the project’s **private Python environment**.

It is not unique to this repo. It is standard Python project hygiene.

Purpose:
- keep project dependencies isolated
- avoid polluting global Python
- avoid package/version conflicts between projects

You usually:
- **commit** `requirements.txt`
- **ignore** `.venv/`

---

## Git hygiene

Track the workflow logic.
Do not track generated artifacts or private paper inputs.

Usually commit:
- `AGENTS.md`
- `.codex/config.toml`
- `.codex/agents/*.toml`
- `.agents/skills/paper-reviewer/SKILL.md`
- `prompts/*.txt`
- `schemas/*.json`
- `scripts/*.py`
- `requirements.txt`
- `.gitignore`
- `REPO_AUDIT.md`

Usually do not commit:
- `inputs/*.pdf`
- `work/`
- `outputs/`
- `.venv/`

Common Git pattern:

```powershell
git status
git add <files>
git commit -m "Describe what changed"
```

Reminder:
- `git add` stages changes
- `git commit -m "..."` saves a snapshot with a message

---

## Preprocessing

The first real script in this repo is:

```text
scripts/preprocess_pdf.py
```

It takes a source PDF and builds structured artifacts under:

```text
work/<paper_id>/parsed/
```

Current outputs include:

- `full_text.md`
- page-by-page text
- page index metadata
- section detection
- in-text citation candidates
- reference list extraction
- numeric claim candidates
- cross-reference candidates
- table inventories
- figure inventories
- page images
- manifest metadata

### Example

```powershell
python scripts\preprocess_pdf.py --pdf inputs\example-paper.pdf
```

If successful, the script prints a JSON summary and writes artifacts under:

```text
work/example-paper/parsed/
```

---

## Shared reviewer schema

Reviewer outputs must conform to:

```text
schemas/reviewer_output.schema.json
```

That schema is the output contract for the reviewer stage.

Why this matters:
- downstream automation becomes easier
- reviewer outputs become more stable
- the editor can rely on consistent structure
- validation becomes objective rather than impressionistic

---

## Validator

The JSON validation script is:

```text
scripts/validate_review_json.py
```

Usage:

```powershell
python scripts\validate_review_json.py --schema schemas\reviewer_output.schema.json --input work\example-paper\reviews\crossref_auditor.json
```

If everything is fine, it prints:

```text
VALID
```

---

## Why prompt files still exist when there is already a schema

Because the schema and the prompt do different things.

The schema says:
- what shape the output must have

The prompt says:
- what this particular run is supposed to do
- which paper is being audited
- which reviewer name should appear
- which parsed artifacts should be used

So:
- **schema = output contract**
- **prompt file = run-specific assignment**

---

## Important Windows lesson

Do **not** use PowerShell `>` redirection for reviewer JSON outputs.

That can produce encoding problems on Windows and cause validation failures.

Prefer Codex’s own output flag instead.

Also, for this machine, the practical sandbox setting is:

```toml
[windows]
sandbox = "unelevated"
```

That avoids repeated admin/UAC friction on a managed Windows machine.

---

## Example reviewer run

A typical reviewer run now looks like this:

```powershell
Get-Content prompts\crossref_audit_paper1.txt -Raw |
  codex exec --output-schema schemas\reviewer_output.schema.json `
    --output-last-message work\example-paper\reviews\crossref_auditor.json `
    -

python scripts\validate_review_json.py --schema schemas\reviewer_output.schema.json --input work\example-paper\reviews\crossref_auditor.json
```

Search-enabled reviewers use:

```powershell
codex --search exec ...
```

not:

```powershell
codex exec --search ...
```

---

## Next step: editor synthesis

The next stage is to add the **editor**.

The editor should:
- read the five validated reviewer JSON files
- synthesize one Markdown report
- preserve uncertainty
- preserve exact locations when available
- prioritize substantive findings over parser/process notes

The editor should not invent findings.

This is the next major smoke test before the wrapper script.

---

## After the editor: full wrapper script

After the editor works, the final pedagogical milestone is a wrapper such as:

```text
scripts/review_paper.py
```

The long-run behavior should be:

1. take a PDF path or filename
2. derive `paper_id`
3. run preprocessing if needed
4. run all internal reviewers
5. validate all reviewer JSON outputs
6. run the editor
7. write the final report under `outputs/<paper_id>/report.md`

That wrapper should eventually also support:
- flexible prompts or prompt templates
- optional reruns of only one reviewer
- optional skipping of already-existing parsed artifacts
- optional single-threaded vs parallel reviewer execution

But that is the next layer. It does not need to be perfect immediately.

---

## Pedagogical reminder

This repo is not trying to become a universal product overnight.

It is a learning project for understanding how to work effectively with Codex in a real research workflow.

So the right standard is not:
- maximum sophistication now

The right standard is:
- understandable structure
- reproducible behavior
- clear mental models
- easy debugging
- incremental improvement

If the repo stays simple enough that future-you can read it and remember why each piece exists, then it is doing its job.

---

## Short checklist when you come back later

If you return to this repo after a break, the order to remember is:

1. activate `.venv`
2. check `git status`
3. confirm the source PDF is in `inputs/`
4. run preprocessing if needed
5. run reviewers with `codex exec`
6. validate reviewer JSON
7. run editor
8. inspect final report
9. commit only the workflow logic, not generated artifacts

---

## Common commands

Activate environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Run preprocessing:

```powershell
python scripts\preprocess_pdf.py --pdf inputs\example-paper.pdf
```

Validate one reviewer output:

```powershell
python scripts\validate_review_json.py --schema schemas\reviewer_output.schema.json --input work\example-paper\reviews\crossref_auditor.json
```

Check status:

```powershell
git status
```

Commit workflow changes:

```powershell
git add <files>
git commit -m "Describe what changed"
```

---

