# GitHub Readiness Audit

This audit maps the repository-sharing goal to concrete local evidence.

## Objective

Make the reviewer setup easy for other researchers to clone and run, start from a private GitHub repository, keep the path open for a later public release, and avoid sharing papers or generated review artifacts.

## Checklist

| Requirement | Evidence | Status |
| --- | --- | --- |
| Clear README for cloning, setup, and first run | `README.md` includes prerequisites, setup commands, tests, adding a PDF to `inputs/`, and running `scripts/review_paper.py` | Complete locally |
| Smooth setup experience | `setup.ps1`, `setup.sh`, `requirements.txt`, and README manual setup instructions | Complete locally |
| Local readiness check | `scripts/check_environment.py` verifies required Python modules, core project files, and Codex CLI availability | Complete locally |
| First-run walkthrough | `docs/first_review_walkthrough.md` shows activation, checks, adding a private PDF, running the reviewer, and reading outputs | Complete locally |
| GitHub project scaffolding | `.github/workflows/ci.yml`, `.github/dependabot.yml`, `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/` | Complete locally |
| Suggested private repo settings | `docs/repository_settings.md` covers visibility, branch protection, Actions, issues, and public-release preparation | Complete locally |
| Keep papers off GitHub | `.gitignore` ignores `inputs/*`, `work/*`, and `outputs/*` except README placeholders | Complete locally |
| Keep generated artifacts off GitHub | `.gitignore` ignores generated work/output directories and common build/cache files | Complete locally |
| Enforce shareability in CI | `scripts/check_shareable_repo.py` and CI job `Check shareable tracked files` | Complete locally |
| Check first-commit safety | `scripts/check_shareable_repo.py --include-untracked` checks tracked plus addable untracked files | Complete locally |
| Check sensitive-name hygiene | `scripts/check_tracked_sensitive_names.py` scans tracked/addable text files for unexpected secret-like names without printing values | Complete locally |
| Tests cover the privacy guard | `tests/test_reviewer_config.py` covers allowed placeholders and rejected private artifacts | Complete locally |
| Private-to-public release path | `docs/public_release_checklist.md` and `LICENSE.md` placeholder | Complete locally |
| Private GitHub repo exists | No `origin` remote is currently configured | Blocked on owner/repo name and approval |
| Initial commit pushed | Not done; no commit or push was requested/approved yet | Blocked on approval |

## Last Verified Commands

```powershell
.\.venv\Scripts\python.exe -m unittest
.\.venv\Scripts\python.exe scripts\check_environment.py
.\.venv\Scripts\python.exe scripts\check_shareable_repo.py
.\.venv\Scripts\python.exe scripts\check_shareable_repo.py --include-untracked
.\.venv\Scripts\python.exe scripts\check_tracked_sensitive_names.py
.\.venv\Scripts\python.exe -m py_compile scripts\check_shareable_repo.py scripts\check_environment.py scripts\check_tracked_sensitive_names.py
git diff --check
git ls-files -o --exclude-standard inputs work outputs
```

Expected `git ls-files -o --exclude-standard inputs work outputs` output before the first commit:

```text
inputs/README.md
outputs/README.md
work/README.md
```

## Remaining External Step

After the repository owner/name is chosen and the user approves the external action, create the private GitHub repo, stage only shareable files, commit, and push. See `docs/github_private_repo_setup.md`.
