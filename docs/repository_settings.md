# Repository Settings

Recommended GitHub settings for private development and public collaboration.

## Visibility

- Keep the repository private until `docs/public_release_checklist.md` is complete.
- When public, keep private manuscripts and generated artifacts out of issues, pull requests, discussions, releases, and wikis.
- Do not add source PDFs, generated reports, reviewer logs, or parsed artifacts to releases, issues, pull requests, or wikis.

## Branches

- Use `main` as the default branch.
- Require pull requests before merging once collaborators are added.
- Require the CI workflow to pass before merging.
- Consider requiring linear history after the project has more contributors.

## Actions

- Enable GitHub Actions for the repository.
- Let the `CI` workflow run on pushes and pull requests.
- Review Dependabot pull requests before merging dependency updates.

## Issues And Pull Requests

- Ask contributors to use synthetic examples or short non-sensitive snippets.
- Close or redact issues that accidentally include private paper text, generated reports, logs, or credentials.
- Keep reviewer changes small: config, prompt, schema, validator, and tests should move together when the output contract changes.
- Consider enabling Discussions for design proposals, reviewer ideas, and reproducibility questions.

## Security And Privacy Reporting

- Enable private vulnerability reporting if the repository is public.
- Direct data-exposure reports to a private channel rather than public issues.
- Treat accidental paper text, generated review outputs, logs, or credentials as sensitive and remove them before discussion continues.

## Before Public Release

Follow `docs/public_release_checklist.md` and verify the repository from a fresh clone.
