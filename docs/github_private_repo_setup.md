# Historical Private GitHub Repository Setup

This records the original private-repository bootstrap path. For ongoing public-release checks, use `docs/public_release_checklist.md` and `docs/repository_settings.md`.

## Before Publishing

Run:

```powershell
python -m unittest
python scripts\check_shareable_repo.py --include-untracked
python scripts\check_tracked_sensitive_names.py
git status --short
git ls-files inputs work outputs Slides
git ls-files -o --exclude-standard inputs work outputs Slides
```

The tracked-files command should list only:

```text
inputs/README.md
outputs/README.md
work/README.md
```

The untracked-files command should be empty after ignored local artifacts are excluded.

Review the diff before committing:

```powershell
git diff
```

## Create A Private Repository

From GitHub.com:

1. Create a new private repository.
2. Do not initialize it with a README, license, or `.gitignore`; this repository already has those files.
3. Add the new repository as `origin`.

```powershell
git remote add origin https://github.com/Ingar30/reviewer.git
git branch -M main
```

Or with GitHub CLI:

```powershell
gh repo create Ingar30/reviewer --private --source . --remote origin
git branch -M main
```

## Commit And Push

Stage only the shareable setup files and intentional project machinery. Avoid `git add -A` if unrelated local edits are present.

```powershell
git add .gitignore .env.example README.md CONTRIBUTING.md SECURITY.md LICENSE.md setup.ps1 setup.sh .github docs inputs/README.md work/README.md outputs/README.md config prompts schemas scripts tests requirements.txt AGENTS.md
git commit -m "Prepare reviewer project for GitHub"
git push -u origin main
```

Do not stage local paper inputs, generated review artifacts, or unrelated working-tree changes such as draft slide edits unless you intentionally want them in the repository.

Before making the repository public, follow `docs/public_release_checklist.md`.
