# Joint maintenance of Reviewer and the ChatGPT plugin

**GitHub Reviewer is the source of truth.** The plugin is a versioned, self-contained
distribution of Reviewer plus an adapter for native ChatGPT Work subagents. It is
not a second review methodology and does not fetch `main` during a review.

**Current source version: `0.1.0-rc.1`.** This is a release candidate, not an approved
public-directory release. Publisher identity/policy approval, clean installed-cloud
acceptance and cross-task recovery remain pending. A prerelease tag uses the same
clean-source and CI checks as a final tag; it does not waive the publication gates.
The first complete staged-diff check also removed a trailing blank line in the
shared routing module. This has no Python/Reviewer behavior effect, but regeneration
changes its byte hash and therefore the runtime fingerprint. Existing cloud checkpoints
must continue using their retained original bundle; do not rewrite their seals.

For the current submission checklist, publisher-only steps and exact packet commands,
see [Public plugin submission and updates](plugin_publication.md). Passing GitHub CI
automatically prepares a candidate packet; a matching immutable tag prepares a release
packet. **Neither changes the public directory until a publisher submits, obtains
approval and explicitly publishes that version.**

## Living documentation: how we maintain both together

This is the single maintenance guide for the ordinary Reviewer and its plugin.
Keep it current as part of repository changes, not through a separate documentation
or plugin-porting project. [The repository instructions](../AGENTS.md) direct future
coding sessions to read this guide and update it when the maintenance contract changes.
This is a development rule, not an automatic background service: it does not monitor
GitHub, edit documentation between sessions, or publish releases by itself.

### Responsibilities for each change

1. **Edit the canonical source first.** Review methodology, prompts, roles, schemas
   and deterministic processing belong in the core files listed below. Do not patch
   generated runtime copies or introduce a second plugin-specific review contract.
2. **Assess both execution hosts.** Decide whether the change propagates through
   generation alone or changes an interface that the CLI and native-host adapter
   must both understand. Preserve CLI behavior unless the task explicitly changes it.
3. **Regenerate and verify.** For changes to bundled sources or packaging, rebuild
   the plugin, inspect the generated diff, and run the relevant regression tests and
   drift check. Follow the full development/release checks below before release.
4. **Update this guide in the same change** if source ownership, bundled resources,
   shared interfaces, host-specific exceptions, commands, tests, installation,
   release procedures or compatibility limits have changed. Ordinary prompt wording
   changes do not need a redundant entry here if the maintenance process is unchanged.
5. **Hand off accurately.** State which core and plugin files changed, what was
   tested, whether regeneration was needed, and whether the installed/published
   plugin is still an older snapshot. Never describe a local build as a release.

Keep this guide focused on maintenance; link to the canonical skill and templates
for reviewing methodology and to the installation/acceptance guides for host testing.
Do not copy those instructions here. Date verification records and distinguish
historical test results from checks performed for the current change.

### Shared-change checklist

- [ ] The core remains authoritative; any adapter-only change has a host-specific reason.
- [ ] Affected CLI and plugin interfaces have been considered and tested as appropriate.
- [ ] The generated bundle is current when its sources changed; no runtime copy was hand-edited.
- [ ] This guide and linked instructions reflect any changed maintenance steps or limitations.
- [ ] The handoff records checks and outstanding private-host testing or publication steps.
- [ ] Versioning, installation and publication remain deliberate, separately authorized actions.

## Architecture and audit findings

| Authoritative source | Ordinary Reviewer | Plugin |
| --- | --- | --- |
| `.agents/skills/paper-reviewer/SKILL.md` | Local workflow and review rules | Exact bundled copy; only CLI execution details are adapted |
| `config/reviewers.json` | Roles, preflight, applicability, search | Same configuration, including added preflight/conditional roles |
| `prompts/templates/`, `schemas/` | Review contracts and output schemas | Generated copies, never independently edited |
| `scripts/render_prompts.py` | CLI prompt rendering | Same renderer, contract and router prompt |
| `scripts/reviewer_routing.py` | Applicability and parser guardrails | Same functions |
| `scripts/validate_review_json.py` | Schema, semantics and provenance | Same validator plus host failure/coverage handling |
| `scripts/preprocess_pdf.py` | Deterministic PDF extraction | Same executable; no external parser or repair model |
| `scripts/normalize_review_outputs.py`, `build_editor_input.py`, `check_final_report.py` | Lossless editor evidence and report checking | Same functions |
| `scripts/render_report_pdf.py` | Optional offline export of an existing report | Same exporter, called after validated review completion |
| `scripts/review_paper.py` | Codex CLI process lifecycle | Excluded from the package |
| `scripts/work_plugin.py` | Not needed by the CLI | Native-host reservations, retries, checkpoints and handoff |
| `scripts/prepare_work_environment.py` | Optional, never part of the default CLI run | Permission-gated isolated host setup using the coordinator's doctor and canonical requirements |

The original package already generated core source copies and checked their hashes;
those were distribution snapshots, not independently maintained forks. The audit
nevertheless found and removed avoidable divergence:

- Separate reviewer/editor rendering and router-prompt assembly now call the core
  rendering functions. The extra plugin-only parser reminder is removed because the
  canonical reviewer contract already supplies the parser instructions.
- The CLI validator and adapter now share schema/identity/semantic/provenance
  validation. Only host-specific completion and unavailable-web handling differ.
- The adapter no longer assumes a single preflight task or a fixed coverage count.
  Every configured preflight runs; the parser-quality gate remains mandatory.
- The canonical skill is now bundled byte-for-byte as
  `runtime/reviewer-guidance/paper-reviewer.md`, with explicit adaptations for
  attachments, native execution and host-selected models. Renaming the packaged
  reference prevents discovery of a second CLI skill; it does not fork its content.
- The builder follows local imports instead of a second hand-maintained Python
  dependency list. It also includes new resources in the public source trees.
- A repository catalog and a tag-gated release build provide Git distribution and
  a reproducible ZIP with commit/file-hash provenance.

## Generated files are not another source of truth

Maintain the ordinary Reviewer sources above. **Do not edit
`plugins/economics-paper-reviewer/skills/review-paper/runtime/` by hand.** It is a
generated, LF-normalized snapshot committed so a Git-backed installation needs no
build on the researcher's machine. CI checks byte-for-byte drift. Packaged copies
are necessary for self-contained distribution, not another implementation to port.

Maintained plugin-specific files are the manifest, branding, UI/invocation metadata,
skill entry point, native-host procedure, coordinator and packaging/release tools. They
describe how to execute the canonical review on another host, not what to review.
Full/Lite remain scheduling, retry-budget and requested-effort profiles with the same
substantive coverage and validation. The CLI's flags and defaults remain unchanged.

### PDF presentation and host delivery

The editor still authors `report.md`; the shared `scripts/render_report_pdf.py`
converts it deterministically into a PDF without inference or new dependencies.
The ordinary CLI keeps its Markdown default and can use this optional command:

```text
python scripts/render_report_pdf.py --report outputs/PAPER_ID/report.md --output outputs/PAPER_ID/report.pdf
```

The plugin calls `work_plugin.py export-pdf --workspace RUN` after review completion,
then presents the PDF through the host's generated-file mechanism. This delivery step
is host-specific; PDF content/layout is maintained in the core exporter. The exporter
supports the report's heading, paragraph, emphasis, code, link and pipe-table subset;
tables become labelled rows for page-spanning evidence. Unknown Markdown/TeX remains
literal, not guessed. It checks text preservation and bounds, and embeds the exact
source Markdown. It is not a full Markdown/LaTeX engine or a new scientific validator.

PDF failures preserve the completed review and do not consume model retries. Successful
exports are sealed and included in subsequent checkpoints. A local filesystem link is
not proof of app downloadability: private acceptance must test the actual PDF preview
and download, not only the checkpoint ZIP. Older checkpoints need their original runtime
for resume; exporting their verified Markdown separately does not upgrade them.

When changing the report format, exercise `tests/test_report_pdf.py` alongside report
checks and plugin tests. Extend the single core exporter if new formatting needs it;
never maintain a plugin-only converter. See OpenAI's current
[file preview and download documentation](https://learn.chatgpt.com/codex/artifacts-viewer)
for the distinction between app, web and CLI surfaces.

The builder includes JSON under `config/` and `schemas/`, text templates under
`prompts/templates/`, and Markdown/text/JSON under the canonical skill. Static local
Python imports under `scripts/` follow the coordinator and PDF processor automatically,
including function-local imports. Keep these public resource trees free of private
data. New pinned dependencies flow from `requirements.txt` into the environment check.
Runtime-loaded assets outside these trees, non-flat Python packages, dynamic imports,
unusual dependency formats, or a new stage protocol still need explicit packaging/compatibility
work and tests. Never bundle private inputs or CLI launchers to fix a missing import.

Changing a prompt, role, schema or shared validator should require **no plugin logic
edit**. Implement a new host-independent stage once in the core, then connect it to
both execution adapters. CLI process-launching changes cannot automatically become
native-agent scheduling changes; that intentional boundary remains compatibility
glue. No architecture can infer arbitrary new host APIs or stages from a Git commit.

## Development: change once, regenerate, test

From the repository root, using the existing environment:

```powershell
.venv/Scripts/python.exe scripts/build_work_plugin.py
.venv/Scripts/python.exe -m unittest
.venv/Scripts/python.exe scripts/build_work_plugin.py --check
git diff --check
```

On macOS/Linux use `.venv/bin/python`. Review and commit the core and generated diffs
together through the ordinary Git workflow. No manual prompt/schema port is needed.
The builder never installs dependencies, publishes, or updates an installed plugin.
It retires only unmodified files recorded in the previous generated manifest; locally
edited retired files and unexpected files require inspection.

Regression tests cover core-to-bundle propagation, new imports/resources, CLI/native
prompt parity, added preflight tasks, excluded CLI dependencies, release gates,
reproducible ZIPs, retries, validation, and checkpoints.

For a private trial, use `--private-marketplace` and `--zip` with fresh output names,
then follow the [installation guide](chatgpt_work_plugin.md). Never overwrite the
only bundle that can resume an old checkpoint. Local cache troubleshooting uses
Plugin Creator's supported cachebuster/reinstall flow; cachebusters are not releases.

## GitHub distribution with pinned versions

`.agents/plugins/marketplace.json` exposes this repository's generated plugin as
the `reviewer` catalog. After a tested tag exists on GitHub, a maintainer or technical
tester can install that exact source, for example:

```text
codex plugin marketplace add Ingar30/reviewer --ref v0.2.0
codex plugin add economics-paper-reviewer@reviewer
```

`v0.2.0` is an **example future version**, not a claim that it exists. Private GitHub
repos require the installer's access. These are maintainer commands, not the public
directory end-user workflow.

For an existing catalog pinned to an older tag, inspect its configured source,
explicitly re-register it against the chosen new tag using the marketplace commands,
and reinstall/update the plugin. Use a new chat. Refreshing a pinned source does not
select a newer tag for you. Do not point production users at `main` or move old tags.

OpenAI documents [Git sources, ref pinning and marketplace refresh](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli).
Installed plugins are cached snapshots, not live views of source edits. Catalog
distribution and public-directory publication are distinct paths.

## Production: tests, tag, artifact, explicit publication

1. Choose a new version in `plugins/economics-paper-reviewer/.codex-plugin/plugin.json`.
   Use the same `vX.Y.Z` tag for the corresponding Reviewer release. Local
   `+codex...` cachebusters cannot pass the production release gate.
   Use a prerelease such as `0.1.0-rc.1` while public acceptance/publisher gates are
   incomplete. The matching `v0.1.0-rc.1` tag archives a candidate, not a directory
   publication. Never move it; final approval requires a new final version/tag.
2. Regenerate and run the tests above. Privately test the installed package in a
   supported Work environment using the [acceptance cases](chatgpt_work_plugin_acceptance.md).
   Record the actual host/model/capabilities. Commit the reviewed source and generated
   snapshot, then wait for CI.
3. Tag the tested commit `vX.Y.Z` and push the tag when ready. An experimental commit
   to `main` does not replace an installed or published plugin.
4. **Build versioned Reviewer plugin** in GitHub Actions runs the full tests and
   drift/hygiene checks, then uploads a build artifact containing the installable ZIP
   and `release.json`, plus generated listing/test references, synthetic fixtures,
   review notes, policy drafts and a `submission.json` packet receipt. It also supports
   a manual run against an existing tag. It has
   read-only repository permission and does not publish anything.
5. Retain the ZIP, receipt and acceptance record in your release archive before the
   Actions artifact expires. Upload the exact tested ZIP as a skills-only plugin
   update in OpenAI's submission portal, complete review, and explicitly publish
   the approved version. This repository does not automate public publication.

The complete packet build works locally from a **clean tagged checkout**:

```text
python scripts/prepare_plugin_submission.py --release-tag vX.Y.Z --output output/release-vX.Y.Z
```

The gate requires the matching version tag at HEAD, a clean working tree, tracked
canonical/package files and a current generated snapshot. `release.json` records
the Git commit/tag, plugin version, runtime fingerprint, ZIP SHA-256 and every
packaged file hash. A sidecar avoids a circular Git commit hash inside committed
generated files. The older `build_work_plugin.py --release-tag ... --release-dir ...`
remains available for just the ZIP and source receipt. Ordinary `--zip` development builds remain available but cannot
masquerade as a clean tagged release through this command.

See OpenAI's [submission and publishing flow](https://developers.openai.com/plugins/deploy/submission).
The portal may evolve; the repo does not invent a public release API or claim Git
push publishes a plugin. Publisher identity, listing/policy materials and real
installed-host acceptance remain maintainer responsibilities.

## End-user and compatibility boundaries

Researchers should install the released plugin, attach a PDF and request a review;
they should not clone GitHub or operate a CLI. No inference backend or API credentials
are introduced. The host supplies native agents and the user's usage entitlement;
the plugin cannot guarantee quota, included-only billing, account access, subagents,
Python execution, dependencies, image viewing or storage lifetime.

On a prepared host there is no dependency setup for the researcher. On an unprepared
host, the skill can run the bundled `prepare_work_environment.py` with permission.
It checks only by default. `--venv NEW_ENV --allow-install` creates a fresh isolated
environment, installs wheels for the canonical requirements from PyPI and rechecks
with the same coordinator doctor. Existing environments and the installed plugin
are never overwritten. Failed setup is retained; use a new destination for an
authorized retry. The helper neither installs Python nor enables host/network tools.
It must run on the cloud host for a cloud-only request, never on the user's computer.
Skills-only packaging cannot guarantee zero-setup execution on every host.

The exact direct requirements are pinned; their transitive dependencies are resolved
by pip and recorded in the environment's install receipt, not fully locked across
platforms. No Python environment or downloaded wheel is included in a plugin ZIP or
review checkpoint. Native agents, image access, package access and file downloads
remain host capabilities. Missing capabilities stop without lowering audit quality.

### Cloud acceptance is separate from local acceptance

Keep the installed local plugin intact while preparing a cloud candidate. Build a
non-sensitive private test kit after regenerating the ordinary plugin:

```text
python scripts/build_work_plugin.py
python scripts/build_cloud_test_kit.py --output output/cloud-test-NEW-VERSION
python -m unittest tests.test_work_environment tests.test_plugin_architecture tests.test_work_plugin tests.test_report_pdf
```

The kit contains the exact installable plugin ZIP, a one-page synthetic PDF, a
maintained cloud task prompt and SHA-256 receipts. The kit builder does not upload,
install or publish. It is development tooling, not another runtime or methodology.
See [the cloud test prompt](cloud_test_prompt.md) and
[installed-host acceptance](chatgpt_work_plugin_acceptance.md#cloud-only-acceptance).
An attached-bundle developer test can establish hosted execution when permitted,
but does not establish plugin installation or discovery. Verify both separately.

OpenAI documents local/Git catalogs separately from
[workspace-only publishing](https://developers.openai.com/plugins/build/plugins#publish-a-local-plugin-to-your-workspace)
(workspace admin required) and public Directory submission. Do not assume a personal
account has workspace publishing or that local installation syncs to Work Cloud.
Inspect actual account controls. Do not submit publicly to work around private-test
access without separate authorization.

Old reviews remain pinned to exact runtime hashes. Keep the original bundle to
resume them; never rewrite checkpoint hashes to force an upgrade. This architecture
change does not replace your installed private plugin, alter existing reviews,
commit/push a tag, or submit/publish a plugin.

## Architecture verification — 2026-09-08

- Full offline regression suite: **159 tests passed**. Tests use synthetic papers
  and local fixtures; no model API calls or paid inference were used.
- Bundle drift, plugin manifest, skill format, repository hygiene and diff checks
  passed. Ordinary review and editor-refresh CLI help entry points also ran.
- The development ZIP was built successfully. The canonical skill reference is
  byte-identical to its source, and the package exposes exactly one discoverable
  skill. A separate read-only instruction-following check found no blocking ambiguity.
- Release gates and reproducibility were tested with controlled Git-state fixtures;
  the release workflow was parsed but not executed on GitHub. No production tag,
  installed-host paper rerun, installed-plugin update or public submission was made.

## PDF-first delivery verification - 2026-09-08

- **167 offline regression tests passed**, including eight PDF tests covering long
  tables, Unicode/signed values, source embedding, unsafe markup, failed/limited
  exports, completion gates, retry isolation, sealed reuse and checkpoint restoration.
- A user-provided completed checkpoint passed its recorded artifact hashes, reviewer
  validation and report structure/traceability checks. Its accepted Markdown was
  exported without agent reruns; the complete 25-page PDF passed text verification,
  page bounds and visual inspection. Private artifacts remain in ignored folders.
- Bundle drift, plugin/skill validators, repository hygiene and diff checks passed;
  an updated development plugin ZIP was built. The existing CLI remains Markdown-first.
- These checks do not establish scientific correctness or successful app downloading.
  The installed private plugin was not refreshed; PDF preview/download acceptance in
  the user's app and any release/publication remain separate steps.

## Local private installation refresh - 2026-09-08

With user approval, `economics-paper-reviewer@reviewer-private` was refreshed to
`0.1.0+codex.20260908154926` using the supported cachebuster and CLI reinstall flow.
The registered local catalog now points to `output/work-plugin-private-pdf-2026-09-08/`.
This is a generated test snapshot; the canonical repository manifest remains `0.1.0`.
The CLI confirmed the new version is installed and enabled. All 41 bundled runtime
files matched the canonical payload, and the installed PDF-export command loaded.

The installer removed the old cached installation. Its original source bundle in
`output/work-plugin-private-fixed/` was retained unchanged for checkpoint recovery.
Use a new app chat to test the updated skill. First test PDF-only export of an existing
final checkpoint and actual PDF downloading; this refresh did not rerun any review,
verify app download behavior, or publish a public release.

## Cloud preparation verification - 2026-09-08

- Added the optional permission-gated environment helper and generated it from core
  sources into the plugin. Reviewing methodology, CLI defaults and model orchestration
  are unchanged. The installed private local snapshot was deliberately not refreshed.
- Focused regression run: 61 tests passed; after adding two kit tests, all 11 setup/kit
  tests passed again (63 distinct relevant tests in total). Plugin/skill validators,
  bundle drift, sensitive-name/shareable-file checks and diff checks passed.
- A genuinely empty disposable local Python environment reported all five dependencies
  missing and refused unapproved installation. An approved fresh venv installation
  then downloaded the pinned wheels and passed the common doctor with no differences.
  This is a local cold-start test, not a Work Cloud result.
- Built `output/cloud-test-2026-09-08/` with the tested plugin ZIP, synthetic one-page
  PDF, task prompt and hashes. Fixture text/signs and rendered layout were checked.
  The kit is a development snapshot, not a tagged release or installed cloud plugin.
- The in-app browser connection failed because its service referenced a removed
  cached version. The isolated browser fallback reached ChatGPT's sign-in form.
  Authentication and account-specific private/cloud installation remain unverified.
  No papers were uploaded and no plugin was submitted or published.

Adding a runtime helper changes the bundle fingerprint even when review methodology
is unchanged. Existing checkpoints still require their original installed bundle;
do not rewrite hashes or replace the local installation merely to test this candidate.

## Cloud diagnostic follow-up - 2026-09-09

The attached-bundle trial returned cloud-host metadata, but setup failed before any
review stage. Follow-up evidence strongly implicates a truncated NumPy OpenBLAS file,
not a demonstrated need to change pandas versions or review methodology. No repair
had been tested at that diagnostic stage. See the [acceptance record](chatgpt_work_plugin_acceptance.md#verification-record-2026-09-09)
and dated [development handoff](cloud_handoff_2026-09-09.md) for evidence and next steps.

Any future setup hardening belongs in the shared preparation/checking code, followed
by regeneration and relevant CLI/plugin tests, not a patched generated runtime or a
cloud-only dependency fork. Preserve the failed environment and exact original kit.
This diagnostic/documentation update changed no runtime sources or installation and
therefore needs no bundle regeneration. Public/private installation, full cloud
review and cross-task recovery are still separate outstanding acceptance gates.

Later the same day, the user supplied a successful isolated repair trial. Its copied
environment passed imports, doctor and RECORD integrity checks after replacement of
the one incomplete library from the verified original wheel. All 49 diagnostic payload
hashes match; original environment/plugin/artifact inventories remain unchanged.
The user now requests the Full synthetic cloud review in that repaired environment.
This is permission to execute the unchanged bundle, not to edit canonical sources
inside the cloud test. Clean installation reliability and full cloud acceptance
remain unproven; see the later acceptance entry and handoff update.

## Full cloud execution and artifact audit - 2026-09-09

The repaired-cloud Full synthetic review subsequently completed. Its downloaded
checkpoint passed all 122 sealed hashes, canonical runtime comparison, selected-roster
validation and reviewer/report checks. Fifteen applicable audits and three other
stages were accepted first attempt. The downloaded three-page report preserves the
accepted Markdown and renders identically to the checkpoint PDF.

The standalone PDF has an added `Content Credentials` attachment and a different
whole-file hash. Keep checkpoint seals unchanged and record source versus delivered
artifact hashes separately; this audit did not authenticate the credential or amend
the strict byte-equality acceptance criterion. See the
[full-run acceptance record](chatgpt_work_plugin_acceptance.md#full-run-and-download-audit-2026-09-09)
for evidence. This is functional cloud execution/delivery, not proven clean setup,
installed-plugin discovery, cross-task recovery or representative scientific quality.
Documentation only changed; no bundle regeneration or local plugin update was needed.

## Public submission preparation - 2026-09-09

Submission preparation now lives in `scripts/prepare_plugin_submission.py`, not in
the review runtime. It validates directory metadata and the allowlisted static SVG,
exports listing text from the manifest and the eight tests from the maintained
acceptance tables, and packages synthetic fixtures through the existing cloud-kit
renderer. Test definitions and core methodology are not maintained twice. The
shareable review notes intentionally omit the private diagnostic archives/handoff.

CI prepares a candidate packet after the ordinary tests and drift/hygiene checks;
passing branch pushes retain it for 30 days. A matching tag builds a full release
packet with the existing clean/tracked/tag gate and 90-day artifact retention.
Neither workflow commits generated files or publishes to GitHub/OpenAI. Source
changes still require one regeneration and a reviewed commit; publication requires
a verified publisher and an explicitly approved public snapshot. The current package
has not been submitted. See [the release checklist](plugin_publication.md).

Plugin-specific ownership now includes `assets/logo.svg`, public listing/policy
documents and submission tools/tests. Reviewer behavior/runtime remains unchanged
by this packaging work; clean installation, discovery and interrupted cross-task
cloud recovery still need direct host evidence. Owner approval of the policy drafts
and verified publisher identity are deliberately not inferred from a GitHub handle.

Verification for this preparation:

- All **187 offline regression tests passed**. The nine submission-specific tests
  also passed separately after the final metadata/link refinements. The initial
  sandboxed attempt failed on Windows temporary-folder permissions; the approved
  reruns used isolated test folders without installations or model calls.
- Plugin Creator's manifest/package validator, canonical drift check, tracked/addable
  artifact and sensitive-name checks, and `git diff --check` passed. Both workflow
  YAML files parsed; GitHub Actions itself was not run from these uncommitted changes.
- The generated candidate ZIP contains 47 allowlisted files (130,710 bytes). Relative
  to the successful attached cloud-test ZIP, only the listing manifest changed and
  `assets/logo.svg` was added; the complete runtime manifest is byte-identical.
- All 11 candidate packet hashes and ZIP CRCs passed. The three synthetic PDFs and
  logo were rendered and visually checked. The final fixture pages are pixel-identical
  to the inspected QA pages. This is artifact QA, not new native-agent/cloud acceptance.
- The candidate is under `output/pdf/plugin-submission-2026-09-09/`, labelled
  `development-candidate` with a dirty source tree, unverified publisher declarations,
  and no submission/publication. No dependency install, local plugin refresh, Git
  commit/push/tag, or portal action was performed. Policy URLs are not live merely
  because their source documents now exist locally.

## Authorized GitHub release-candidate preparation - 2026-09-09

The user subsequently authorized the Git release steps. The initial source commit
[`7a71ba0`](https://github.com/Ingar30/reviewer/commit/7a71ba064594a133c68ec939c8b856dba83ad0f3)
is public on `main`. Its [GitHub CI run](https://github.com/Ingar30/reviewer/actions/runs/34350950452)
passed all **187 tests** from a fresh Ubuntu checkout, plus bundle drift, hygiene
and candidate-packet generation. This establishes Linux CI preparation, not clean
ChatGPT Work installation or native-agent acceptance in that host.

The public privacy, terms and publication URLs returned HTTP 200 without authentication;
privacy and terms remain drafts awaiting publisher approval. Machine-specific paths
and the cloud environment identifier were removed from the public handoff after
preserving its original in an ignored private folder. Private inputs, outputs,
Downloads evidence and old runtime bundles remain outside Git.

CI reported a deprecated Node.js runtime in the old artifact uploader. Both workflows
now pin GitHub's official `actions/upload-artifact` v7.0.1 commit
`043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`, whose action definition uses Node.js 24.
`archive: true` explicitly preserves the complete packet as one Actions artifact.
This changes release tooling only. Candidate artifacts expire after 30 days and tag
artifacts after 90 days; archive the exact ZIP and receipts before expiry.

The current source/version is `0.1.0-rc.1`; tag only a passing commit and never move
the tag. Git tags and green Actions runs do not mean OpenAI has approved or published
the plugin. Keep publisher declarations and the remaining host-acceptance gates
pending until their evidence exists. Check Actions for the actual tagged-build result.
