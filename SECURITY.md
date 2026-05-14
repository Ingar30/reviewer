# Security Policy

## Sensitive Data

This repository is designed to keep private paper inputs and generated artifacts out of Git. The following should never be committed or posted in public issues:

- source PDFs and paper text
- parsed artifacts under `work/`
- final reports under `outputs/`
- logs that contain paper text or reviewer outputs
- API keys, tokens, passwords, credentials, or authenticated CLI files

## Reporting

For private security or data-exposure concerns, use GitHub private vulnerability reporting when it is enabled, or contact the repository owner directly instead of opening a public issue.

If private data is accidentally committed, rotate any exposed credentials, remove the file from the current branch, and consider history cleanup before making the repository public.
