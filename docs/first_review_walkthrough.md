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

## 4. Run The Reviewer

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf"
```

Use an explicit ID if the filename is long or sensitive:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --paper-id "paper-a"
```

## 5. Read The Report

The final report appears at:

```text
outputs/my-paper/report.md
```

Intermediate artifacts are under:

```text
work/my-paper/
```

Both directories are ignored by Git because they can contain paper text, quotes, reviewer findings, and logs.

## 6. Before Sharing Changes

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest
.\.venv\Scripts\python.exe scripts\check_shareable_repo.py --include-untracked
git status --short
```

Only share project machinery, prompts, schemas, tests, and documentation. Do not share PDFs, generated prompts, reviewer JSON, logs, editor bundles, or final reports unless you have explicit permission to do so.
