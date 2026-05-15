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

Parser repair overlay runs by default when parser-quality preflight reports high- or medium-severity parser artifacts. It adds reviewer-facing repair notes and narrow overlay artifacts before substantive review.

To write repair guidance without overlay artifacts, use:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --parser-repair plan
```

For a faster or cheaper run that skips parser repair, use:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --parser-repair off
```

Parser repair can improve auditability by routing reviewers away from unsafe parsed tables, figures, or captions and toward safer fallback artifacts. It adds runtime and token usage. When no high- or medium-severity parser artifact is reported, the repair planner is skipped.

## 5. Read The Report

The final report appears at:

```text
outputs/my-paper/report.md
```

Intermediate artifacts are under:

```text
work/my-paper/
```

Repair overlays, if enabled, appear under `work/my-paper/repair/`. In `overlay` mode, LLM-generated repaired files are written under `work/my-paper/repair/repaired_artifacts/`; the original `work/my-paper/parsed/` artifacts are not overwritten. The `work/` and `outputs/` directories are ignored by Git because they can contain paper text, quotes, reviewer findings, repair notes, and logs.

## 6. Before Sharing Changes

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest
.\.venv\Scripts\python.exe scripts\check_shareable_repo.py --include-untracked
git status --short
```

Only share project machinery, prompts, schemas, tests, and documentation. Do not share PDFs, generated prompts, reviewer JSON, logs, editor bundles, or final reports unless you have explicit permission to do so.
