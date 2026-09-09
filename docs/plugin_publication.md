# Public plugin submission and updates

**Status: prepared for release work, not submitted or published.** Last checked:
2026-09-09. GitHub Reviewer is the product and source of truth. The plugin packages
that source; it does not run a maintainer-paid inference backend or fetch `main`
during a review. See [joint maintenance](plugin_maintenance.md).

The current source is **`0.1.0-rc.1`**, a release candidate. A matching prerelease
Git tag may archive the tested source before public acceptance/publisher approval;
it is not an assertion that those gates passed. Use a new final version/tag when
they do, and never move a candidate tag or relabel it as an approved publication.

## What is already prepared

- A skills-only package with native host subagents, the canonical PDF processor,
  routing, prompts, schemas, validation and editor synthesis. The CLI is preserved.
- Full/Lite entry points, quota warnings, explicit capability failures, bounded
  retries, checkpoint recovery and PDF-first report delivery with Markdown retained.
- Directory-length listing text, three starter prompts, a square SVG logo/composer
  icon, website and draft privacy/terms links. There is no MCP/app configuration.
- One packet builder exporting listing text from `plugin.json`, five positive and
  three negative tests from the [acceptance document](chatgpt_work_plugin_acceptance.md),
  three shareable synthetic PDFs, review notes and file-hash provenance.
- CI drift checks and candidate artifacts; an explicit, clean tagged-source release
  workflow. Neither workflow submits or publishes anything.

## Actual readiness, not just successful packaging

The 2026-09-09 attached-bundle cloud test completed a Full synthetic review in a
repaired environment: all 15 selected audits and editor synthesis passed the
canonical checks. The downloaded PDF was readable and its content verified.
This is not proof of a clean installation, installed-plugin discovery, or scientific
review quality. See the sanitized [review notes](plugin_submission_review_notes.md).

Before public submission, complete and retain evidence for:

- [ ] **Clean installed cloud trial:** the final package is discoverable in the
  intended host; run its environment check/setup in a new hosted environment with
  only the package and synthetic fixtures. Confirm working native children, images,
  validation and actual PDF download. Do not reuse the repaired test environment
  or connect to the developer's computer. If installation is only available through
  the portal's review flow, disclose that limitation and seek a supported private
  test path; do not label an attached bundle an installed-plugin pass.
- [ ] **Cross-task recovery:** save an interrupted stage checkpoint and restore in
  another cloud task with the matching runtime; reuse accepted work and finish the
  remaining stages. Reopening a final ZIP is not this test.
- [ ] Run the exported positive/negative cases on the candidate, including Lite,
  theory routing, missing/ambiguous input and prompt injection. Record actual host
  capabilities and model/effort when exposed; `unknown` is valid, guessed settings
  are not. Add a non-sensitive representative-paper trial before promising general
  research quality. Unit tests use scripted outputs, not real review judgments.
- [ ] Resolve the verified publisher identity. Currently both manifest identity
  fields say `Ingar30`; this GitHub handle is **not evidence of identity verification**.
  If the verified name differs, edit `author.name` and `interface.developerName`
  together, rebuild, and retest the final package.
- [ ] Owner reviews [privacy](plugin_privacy.md) and [terms](plugin_terms.md) drafts,
  removes their draft notices when approved, and confirms the named support route.
  Publish the reviewed source docs to GitHub and check their HTTPS links while
  signed out. Newly prepared local files are not already live web pages.
- [ ] Choose available countries, approve all portal declarations, inspect the diff,
  commit the complete source/generated snapshot and pass GitHub CI. Create a new
  immutable matching tag and retain the tested ZIP, receipts and private evidence.

The truncated NumPy/OpenBLAS library was repaired only in an isolated copy. The
original cause remains unknown. Do not add an automatic binary repair to production,
claim clean setup is proven, or silently install/upgrade packages to pass this gate.
The helper requests permission for an isolated dependency installation when needed.

## Generate the packet locally

From the repository root, with its existing Python environment (`python` below):

```text
python scripts/build_work_plugin.py
python -m unittest
python scripts/build_work_plugin.py --check
python scripts/check_shareable_repo.py --include-untracked
python scripts/check_tracked_sensitive_names.py
python scripts/prepare_plugin_submission.py --output output/submission-candidate-UNIQUE
```

The destination must be new. The packet contains:

| File | Use |
| --- | --- |
| `economics-paper-reviewer-VERSION.zip` | The **only** ZIP to upload as the plugin; manifest at archive root |
| `listing.json` | Generated portal-entry reference, not an API request; identity/countries/approval remain unset |
| `test-cases.json`, `fixtures/*.pdf` | Canonical test definitions and synthetic test inputs |
| `plugin_submission_review_notes.md` | Setup, fixture mapping, result shape, test evidence and limitations |
| `plugin_privacy.md`, `plugin_terms.md` | Owner-review policy drafts, later public GitHub pages |
| `submission.json` | Package/packet hashes, runtime fingerprint, Git commit and candidate/release status |
| `release.json` | Tagged source provenance, present only in release mode |

The packet is allowlisted; it does not copy `Downloads`, private PDFs, diagnostics,
checkpoints, Python environments or credentials. Do not manually add them. Supply
only separately inspected, consented test evidence to reviewers. Never upload the
whole packet folder as the plugin ZIP.

For an authorized, clean checkout at the immutable tag matching the manifest:

```text
python scripts/prepare_plugin_submission.py --release-tag vX.Y.Z --output output/submission-vX.Y.Z
```

Replace `X.Y.Z` with the real version. The command refuses dirty/untracked release
sources, missing/mismatched tags and local cachebuster versions. It does not run
host tests or certify public readiness. CI's tag workflow runs regression tests
before calling it. Do not retroactively change a published tag or an old resume bundle.

## Portal steps requiring the publisher

Open [OpenAI Platform's plugin portal](https://platform.openai.com/plugins) in the
intended organization/project. A ChatGPT subscription alone does not establish
publisher permissions. Current requirements include verified individual/business
identity and **Apps Management Write**, or organization-owner permission.

1. Start a **skills-only** plugin submission; upload the tested tagged-source ZIP.
   No MCP server, API credentials or developer-funded model backend is needed.
2. Review the manifest-derived listing against `listing.json`. The canonical
   manifest has the actual three starter prompts. Supply the support URL from the
   listing reference if requested. Skills-only uploads do not accept screenshots;
   do not add MCP/app configuration or fabricated authentication credentials.
3. Supply the test definitions, synthetic fixtures and reviewer setup/limitations
   notes through the available form fields. For resume testing, a reviewer creates
   a checkpoint in their own P1 run; no private checkpoint is supplied.
4. Review name/identity, URLs, country availability, release notes and declarations.
   If the portal normalizes or changes the package, inspect those changes and retest
   the exact final package. Do not attest to gates still marked unverified.
5. Submit for review. Skill scanning/review can reject or request changes; there is
   no promised approval time. **Submission is not publication.** After approval,
   explicitly publish the approved snapshot to the directory.

The portal's current validation rules take precedence. Website/support/privacy/terms
URLs are optional for skills-only ZIP uploads under the current error reference,
but we prepare them for transparency and support. A syntactically valid URL is not
a check that its page is live. Public logo and composer icon assets are required.

## Future updates: one source, controlled public releases

1. Improve the ordinary Reviewer in its canonical files.
2. Run `build_work_plugin.py` once. Inspect and commit core + generated changes
   together; update joint-maintenance docs only if the maintenance contract changed.
3. Tests and the byte-for-byte drift check run in CI. A passing `main`/`master` push
   produces a **candidate submission packet** automatically. CI fails on a forgotten
   regeneration; it does not silently change or commit your source.
4. When ready, bump the manifest version, test, commit, and tag the tested Reviewer
   commit `vX.Y.Z`. The tag workflow generates the complete versioned packet.
5. Download the Actions artifact, retain it beyond the 90-day artifact retention,
   and update the existing plugin in the portal with its exact ZIP, honest release
   notes and current test evidence. Review and publish the new approved version.

**GitHub-to-package synchronization is automated; public directory updates are not
live GitHub synchronization.** No prompt/schema/methodology port is required, but
each public update has an explicit version/review/publication step. Installed copies
are cached snapshots; a Git catalog pinned to an old tag stays pinned until updated.
Compatibility changes to host orchestration still require adapter tests. Preserve
old packages for old checkpoints; never combine runtime versions within a review.

## Official references checked 2026-09-09

- [Submission, testing and publication](https://developers.openai.com/plugins/deploy/submission)
- [Current ZIP, listing, identity and asset validation](https://developers.openai.com/plugins/deploy/submission-errors)
- [Git marketplaces and pinned versions](https://developers.openai.com/plugins/build/plugins)

Recheck these before every public release. This runbook and local validators are
preparation aids, not a guarantee of account eligibility, platform capabilities,
review approval, unlimited usage or availability on every ChatGPT surface.
