# Private GitHub Repository Setup

Use this when you are ready to publish the project machinery to GitHub as a private repository.

## Before Publishing

Run:

```powershell
python -m unittest
python scripts\check_shareable_repo.py --include-untracked
python scripts\check_tracked_sensitive_names.py
git status --short
git ls-files -o --exclude-standard inputs work outputs
```

The last command should list only:

```text
inputs/README.md
outputs/README.md
work/README.md
```

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
git add .gitignore .gitattributes .env.example README.md CONTRIBUTING.md SECURITY.md LICENSE.md setup.ps1 setup.sh .github docs inputs/README.md work/README.md outputs/README.md scripts/check_shareable_repo.py
git commit -m "Prepare reviewer project for GitHub"
git push -u origin main
```

Do not stage local paper inputs, generated review artifacts, or unrelated working-tree changes such as draft slide edits unless you intentionally want them in the repository.

Before making the repository public later, follow `docs/public_release_checklist.md`.
