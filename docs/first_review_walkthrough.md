# First Review Walkthrough

This walkthrough assumes you have cloned the repository and run the setup steps in `README.md`.

## 1. Activate The Environment

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

## 2. Confirm The Local Checks Pass

```powershell
.\.venv\Scripts\python.exe -m unittest
.\.venv\Scripts\python.exe scripts\check_environment.py
.\.venv\Scripts\python.exe scripts\check_shareable_repo.py --include-untracked
```

## 3. Add A Private Paper PDF

Put your paper in `inputs/`:

```text
inputs/my-paper.pdf
```

Do not commit this file. The directory is ignored by Git except for `inputs/README.md`.

Preprocessing stays local, but the review prompts send parsed manuscript text to OpenAI through Codex. Search-enabled reviewers may also issue manuscript-derived web queries. Confirm that the manuscript's confidentiality terms permit this before continuing.

## 4. Run The Reviewer

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf"
```

Use an explicit ID if the filename is long or sensitive:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --paper-id "paper-a"
```

Substantive reviewers read the parser-quality output and route around deterministic artifacts marked unsafe. The workflow does not generate repaired parser content. If page text, coordinates, crops, and page images are insufficient for a reliable check, the reviewer returns `cannot_verify`.

## 5. Read The Report

The final report appears at:

```text
outputs/my-paper/report.md
```

Intermediate artifacts are under:

```text
work/my-paper/
```

The `work/` and `outputs/` directories are ignored by Git because they can contain paper text, quotes, reviewer findings, and logs.

## 6. Before Sharing Changes

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest
.\.venv\Scripts\python.exe scripts\check_shareable_repo.py --include-untracked
git status --short
```

Only share project machinery, prompts, schemas, tests, and documentation. Do not share PDFs, generated prompts, reviewer JSON, logs, editor bundles, or final reports unless you have explicit permission to do so.
