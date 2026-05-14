# Contributing

Thanks for helping improve the reviewer pipeline.

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

When opening issues or pull requests, use synthetic examples or short non-sensitive snippets.

## Changing Reviewers

Reviewer changes usually involve:

1. updating `config/reviewers.json`
2. updating or adding a prompt in `prompts/templates/`
3. updating schemas or validators if the output contract changes
4. adding focused tests when behavior changes

Run `python -m unittest` before opening a pull request.
