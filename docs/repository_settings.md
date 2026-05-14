# Repository Settings

Recommended GitHub settings for the first private repository.

## Initial Visibility

- Create the repository as private.
- Keep it private until `docs/public_release_checklist.md` is complete.
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

## Before Public Release

Follow `docs/public_release_checklist.md`, choose a real license, and verify the repository from a fresh clone.
