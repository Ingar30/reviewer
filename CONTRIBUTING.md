# Contributing

Thanks for helping improve the reviewer pipeline. The project is open to changes that make AI-assisted paper review more reproducible, inspectable, and safe to adapt without exposing private manuscripts or generated review artifacts.

## Development Setup

1. Clone the repository.
2. Run `.\setup.ps1` on Windows PowerShell or `bash setup.sh` on macOS/Linux.
3. Activate the virtual environment.
4. Run `python -m unittest`.

## Privacy Rules

Do not commit or paste:

- source PDFs or other copyrighted/private papers
- `work/` artifacts, logs, rendered prompts, or reviewer JSON
- `outputs/` reports
- API keys, tokens, passwords, credentials, or authenticated CLI config

When opening issues or pull requests, use synthetic fixtures, public-domain examples, or short non-sensitive snippets. Do not paste private manuscript text into public discussion threads.

## Good First Contribution Areas

- preprocessing reliability and artifact inventories
- reviewer prompts, reviewer metadata, and selection rules
- output validation, normalization, and final-report checks
- documentation for clean setup, local privacy hygiene, and fork-specific adaptations

## Changing Reviewers

Reviewer changes usually involve:

1. updating `config/reviewers.json`
2. updating or adding a prompt in `prompts/templates/`
3. updating schemas or validators if the output contract changes
4. adding focused tests when behavior changes

Run `python -m unittest` before opening a pull request.

## Pull Request Checklist

- Keep changes focused and explain the workflow effect in the pull request summary.
- Add or update tests for behavior changes.
- Update README or docs when commands, reviewer behavior, or privacy expectations change.
- Run `python -m unittest`.
- Run `python scripts/check_shareable_repo.py --include-untracked` before sharing local changes that might include new files.
