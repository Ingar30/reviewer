# Public Release Checklist

Use this before changing the GitHub repository from private to public.

- Confirm `git ls-files` contains only project machinery, documentation, tests, schemas, prompts, and intentional teaching materials.
- Confirm no PDFs, paper text, reviewer JSON, generated prompts, logs, editor bundles, or final reports are tracked.
- Run `python scripts/check_shareable_repo.py --include-untracked` before the first GitHub commit.
- Run `python scripts/check_tracked_sensitive_names.py` and manually inspect any flagged files.
- Decide on a real public license and replace `LICENSE.md`.
- Run `python -m unittest` from a fresh clone or clean virtual environment.
- Confirm `README.md` setup instructions work on a new machine.
- Confirm GitHub Actions CI is green.
- Review issue and pull request templates for any project-specific contact details you want to add.
