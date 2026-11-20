# GitHub Readiness Audit

This audit maps the repository-sharing goal to concrete local evidence.

Path and secret-name checks are limited mechanical guards, not certification that
documentation or fixtures contain no confidential derived evidence. Follow the
full-file and history review in `docs/public_release_checklist.md` before publishing.

## Objective

Make the reviewer setup easy for other researchers to clone, run, fork, and improve while keeping papers and generated review artifacts out of GitHub.

## Checklist

| Requirement | Evidence | Status |
| --- | --- | --- |
| Clear README for cloning, setup, and first run | `README.md` includes prerequisites, setup commands, tests, adding a PDF to `inputs/`, and running `scripts/review_paper.py` | Complete locally |
| Smooth setup experience | `setup.ps1`, `setup.sh`, `requirements.txt`, and README manual setup instructions | Complete locally |
| Local readiness check | `scripts/check_environment.py` verifies required Python modules, core project files, and Codex CLI availability | Complete locally |
| First-run walkthrough | `docs/first_review_walkthrough.md` shows activation, checks, adding a private PDF, running the reviewer, and reading outputs | Complete locally |
| GitHub project scaffolding | `.github/workflows/ci.yml`, `.github/dependabot.yml`, `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/` | Complete locally |
| Suggested repository settings | `docs/repository_settings.md` covers visibility, branch protection, Actions, issues, security reporting, and public-release hygiene | Complete locally |
| Keep papers off GitHub | `.gitignore` ignores `inputs/*`, `work/*`, and `outputs/*` except README placeholders | Complete locally |
| Keep generated artifacts off GitHub | `.gitignore` ignores generated work/output directories and common build/cache files | Complete locally |
| Keep internal slides off GitHub | `.gitignore` ignores `Slides/`; `git ls-files Slides` is empty | Complete locally |
| Enforce shareability in CI | `scripts/check_shareable_repo.py` and CI job `Check shareable tracked files` | Complete locally |
| Check first-commit safety | `scripts/check_shareable_repo.py --include-untracked` checks tracked plus addable untracked files | Complete locally |
| Check sensitive-name hygiene | `scripts/check_tracked_sensitive_names.py` scans tracked/addable text files for unexpected secret-like names without printing values | Complete locally |
| Tests cover the privacy guard | `tests/test_reviewer_config.py` covers allowed placeholders and rejected private artifacts | Complete locally |
| Public license | `LICENSE.md` contains the MIT License and README points to it | Complete locally |
| Open contribution path | `README.md`, `CONTRIBUTING.md`, and `.github/` templates ask for synthetic examples and reproducible workflow changes | Complete locally |
| GitHub repo exists | `origin` points to `https://github.com/Ingar30/reviewer.git` | Complete |
| Main branch pushed | `main` is synchronized with `origin/main` when `git status --short --branch` is clean | Verify before release |

## Last Verified Commands

```powershell
.\.venv\Scripts\python.exe -m unittest
.\.venv\Scripts\python.exe scripts\check_environment.py
.\.venv\Scripts\python.exe scripts\check_shareable_repo.py
.\.venv\Scripts\python.exe scripts\check_shareable_repo.py --include-untracked
.\.venv\Scripts\python.exe scripts\check_tracked_sensitive_names.py
.\.venv\Scripts\python.exe -m py_compile scripts\check_shareable_repo.py scripts\check_environment.py scripts\check_tracked_sensitive_names.py
git diff --check
git ls-files inputs work outputs Slides
git ls-files -o --exclude-standard inputs work outputs Slides
```

Expected `git ls-files inputs work outputs Slides` output:

```text
inputs/README.md
outputs/README.md
work/README.md
```

Expected `git ls-files -o --exclude-standard inputs work outputs Slides` output is empty after ignored local artifacts are excluded.

## Remaining External Step

Before switching visibility to public, rerun the checks above, inspect `git ls-files`, confirm CI is green on `main`, and follow `docs/public_release_checklist.md`.
