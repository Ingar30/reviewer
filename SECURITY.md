# Security Policy

## Sensitive Data

This repository is designed to keep private paper inputs and generated artifacts out of Git. The following should never be committed or posted in public issues:

- source PDFs and paper text
- parsed artifacts under `work/`
- final reports under `outputs/`
- logs that contain paper text or reviewer outputs
- real-paper identities, metadata, findings, measurements, comparisons and run histories, including pseudonymized tables
- API keys, tokens, passwords, credentials, or authenticated CLI files

The `.gitignore` rules protect against accidental Git publication; they do not make a review fully local. PDF preprocessing runs locally, but the Codex reviewer and editor prompts send parsed manuscript content to OpenAI. Reviewers with web search enabled may also send manuscript-derived queries to the search service. Confirm that the manuscript's confidentiality and data-use terms permit these transmissions before running a review.

## Reporting

For private security or data-exposure concerns, use GitHub private vulnerability reporting when it is enabled, or contact the repository owner directly instead of opening a public issue.

If private data is accidentally committed, preserve evidence privately and coordinate removal from the current tree and all affected history. A deletion commit does not erase old commits or PR diffs. Rotate credentials only if credentials were exposed. GitHub Support may be needed for cached views and PR references; existing clones and forks require separate coordination. Do not repeat exposed content in a public cleanup issue or PR.

Public examples and regression fixtures must be independently invented. Replacing
author names with sample labels does not make private evidence publishable.
Path/secret-name checks are not semantic privacy certification; inspect complete
files, commit history, PR diffs, comments and release assets before publication.
