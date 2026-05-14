# Public Release Checklist

Use this before changing the GitHub repository from private to public, and again before tagging public releases.

- Confirm `git ls-files` contains only project machinery, documentation, tests, schemas, prompts, and placeholder README files for private runtime directories.
- Confirm no PDFs, paper text, reviewer JSON, generated prompts, logs, editor bundles, or final reports are tracked.
- Confirm internal slides, talks, and paper-specific notes are ignored or removed from Git tracking.
- Run `python scripts/check_shareable_repo.py --include-untracked`.
- Run `python scripts/check_tracked_sensitive_names.py` and manually inspect any flagged files.
- Confirm `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, and GitHub templates describe public collaboration without asking contributors to share private manuscripts.
- Confirm reviewer, selector, parser-repair, and editor workflow docs match the current wrapper behavior.
- Run `python -m unittest` from a fresh clone or clean virtual environment.
- Confirm `README.md` setup instructions work on a new machine.
- Confirm GitHub Actions CI is green.
- Review issue and pull request templates for any project-specific contact details you want to add.
