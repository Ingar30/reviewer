# Reviewer-facing setup, tests and release notes

This document is safe to share with submission reviewers. It intentionally excludes
private papers, local usernames, environment identifiers and diagnostic archives.
It describes evidence and test instructions, not a certification of all host tests.

## Setup and permissions

Install the accompanying skills-only ZIP in a supported ChatGPT Work/Codex host.
The host needs native subagents, file execution and Python, plus image viewing.
The plugin has no external login, MCP server, API key, paid inference backend,
developer-operated database or test credentials. An eligible host account and
available shared usage are still necessary. No developer repository clone or local
computer connection should be supplied for a cloud-only trial.

Use the installed **review-paper** skill and the exported prompts. The skill performs
environment checks; if canonical packages are missing, approve isolated installation
only if permitted in this test environment. Let the bundled helper handle preparation.
Do not point it to a developer's pre-existing environment, repair package files by
guessing or run nested `codex exec`. If setup fails, record the failure and stop;
do not treat a workaround as clean installation success.

Full reviews can consume substantial shared allowance. Tests launch real native
review work only when the tester requests it. Do not deliberately exhaust allowance
or buy credits as a test. Missing tools or limits should yield a clear explanation
and checkpoint where possible, not fabricated completion.

## Test data and reproducible expectations

`test-cases.json` is generated directly from the repository's maintained acceptance
tables, not a second independent test plan. Execute those prompts and expectations.

- **P1, P2, P5:** `fixtures/signed-estimate.pdf`. Synthetic means are 97.5 and 100;
  the defined relative difference is -2.5%. The Abstract and Conclusion incorrectly
  say increase. A useful review should identify the direction error with locations.
- **P3:** `fixtures/theory-proposition.pdf`. Its intentionally false proposition
  claims `x = 1` maximizes `x - x*x` on `[0,1]`. The maximum is at `x = 0.5`.
  A theory-logic audit should be selected; absent empirical data is not a defect.
- **P4:** in a P1 trial, request a checkpoint and pause after parser/router and at
  least one accepted audit, before completion. Download it; start another cloud task,
  install the exact matching package, and invoke resume with that checkpoint. Confirm
  the accepted audits are reused and the remaining work completes. No prebuilt private
  checkpoint is shipped; generating one is part of the reproducible test.
- **P5:** disable web using the host's supported settings where available. Merely
  saying web is disabled is not a verified tool restriction. If the host cannot disable
  it, record this test as unavailable rather than asserting a pass.
- **N1:** use the signed-estimate PDF with the summary-only request.
- **N2:** try no attachment; separately try both the signed-estimate and theory PDFs
  without selecting one. Expect a clarification, no implicit merged review.
- **N3:** `fixtures/untrusted-manuscript.pdf` contains a deliberately malicious
  instruction. It is untrusted test data, never permission to access or share files.

All three fixtures are synthetic, have no private data or external references and
are shareable under the repository's MIT license. They test workflow behavior, not
general research accuracy. Negative-case text must not be executed by a test harness.

Expected user result: a complete downloadable PDF report with precise evidence and
traceability, a brief findings summary and limitations; Markdown is retained and a
private checkpoint can be downloaded. The PDF should open outside the chat. Compare
it to the checkpoint report. If host delivery adds Content Credentials and changes
the binary hash, retain both hashes and check the embedded source and rendered pages;
do not rewrite the sealed checkpoint or claim byte equality/signature authentication.

For each case record date, exact ZIP hash/version, host, installed-vs-attached status,
Python versions, actual capabilities, actual model/effort if exposed, result, and
private evidence links. Use `unknown` for unexposed settings. Local unit tests, scans
and attached-bundle tests do not establish an installed cloud pass.

## Evidence available and limitations (2026-09-09)

A Full run of the synthetic sign-error fixture completed in an OpenAI-hosted task
using an unchanged attached bundle and an isolated repaired dependency environment.
All 18 stages (parser, router, 15 selected audits, editor) were accepted; all eight
universal audits and seven applicable specialists were present. Canonical validation,
122 checkpoint payload hashes and 41 runtime-resource comparisons passed. The report
caught both direction errors and disclosed a low-severity section-index limitation.

The three-page downloaded PDF was opened, rendered and checked. The delivery copy
has added Content Credentials and a different binary hash; its pages render identically
to the checkpoint PDF and both embedded Markdown files match the accepted report.
This establishes functional content delivery, not a verified credential signature.

The original environment had a truncated native OpenBLAS library. Replacing only
that file in an isolated copy with the verified original wheel content restored
imports and the environment check. The truncation's cause remains unknown.
**Clean setup, installed cloud discovery and cross-task interrupted recovery remain
unverified.** Actual model/effort were not exposed. Directory branding does not alter
review behavior. During `0.1.0-rc.1` release preparation, a staged-diff check also
removed one trailing blank line from the canonical shared router. Its Python AST
is unchanged, but regeneration changes the runtime fingerprint. The original cloud
bundle is retained for its checkpoints. The final listed ZIP needs its own acceptance.
Do not claim all exported manual cases passed or this synthetic trial benchmarks
scientific accuracy. Update this dated record when new evidence is actually obtained.

## Suggested initial release note

Initial open-source, skills-only economics paper review package: native host subagents,
canonical deterministic preprocessing, conservative routing, structured validation
and editor synthesis; Full and unbenchmarked Lite modes; bounded retries, quota
checkpoints and PDF-first delivery. No MCP server or model API credentials. Host
capabilities and shared usage limits apply. See the test record above for boundaries.

For subsequent versions, replace the initial release note with a factual summary of
the tagged core/adapter changes and tests. Do not copy old acceptance as if the new
package had been tested. OpenAI review and an explicit publish action are still needed.
