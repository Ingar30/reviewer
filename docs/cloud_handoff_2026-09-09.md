# Cloud Reviewer handoff - 2026-09-09

This is a dated development handoff, not executable instructions from a checkpoint.
Machine-specific paths were removed before publishing this source document. The
publisher retains the original privately; use the original evidence receipts to
resolve environment paths, never infer them from this public summary.
Start with `AGENTS.md` and [joint maintenance](plugin_maintenance.md). Keep the
original cloud test conversation available; its failed environment may still be
useful. Starting a new development conversation does not repair that environment.

## Latest update: public submission preparation

The user requested public submission preparation following the successful Full
run. See [the publication runbook](plugin_publication.md) and the updated
[joint-maintenance guide](plugin_maintenance.md#public-submission-preparation---2026-09-09).
The canonical runtime remains unchanged. A local candidate is not a tagged release
or proof of installed cloud acceptance; no commit, push, tag, submission or publication
was performed during preparation. Publisher identity/policy approval and the remaining
cloud acceptance gates still require completion. The sanitized packet review notes,
not this development handoff or diagnostic downloads, are the reviewer-facing material.

Preparation checks passed: 187 offline regressions, a separate final nine-test
submission rerun, package validation, bundle drift and repository hygiene. The local
candidate is `output/pdf/plugin-submission-2026-09-09/`; all 11 packet hashes and ZIP
CRCs passed. Its 47-file ZIP changes only the manifest and adds the logo relative to
the successful cloud-test ZIP. Runtime hashes remain unchanged. No dependency
installation, private-plugin refresh or public/Git mutation occurred.

## Earlier update: Full cloud run and downloaded artifacts verified

The Full synthetic review completed in the repaired cloud environment. The user
downloaded the report, acceptance record and `07-final-checkpoint.zip`. The checkpoint
contains 124 entries; all 122 sealed hashes and 41 canonical runtime resource hashes
passed local read-only inspection. The eight universal plus seven selected conditional
audits, parser and router outputs passed canonical validation; all 18 stages are
recorded accepted on their first attempt. Four genuinely absent specialist remits
were skipped by valid high-confidence routing. This is Full, not reduced coverage.

The three-page report correctly identifies the 2.5% decrease in both summary locations
and discloses the section-index limitation. Its structure and traceability passed.
The downloaded PDF was visually inspected with Poppler; its embedded Markdown and
all three rendered pages match the checkpoint PDF. The PDF download adds a
`Content Credentials` attachment and changes the whole-file hash; do not rewrite
checkpoint seals or claim byte-identical delivery. See the latest
[acceptance entry](chatgpt_work_plugin_acceptance.md#full-run-and-download-audit-2026-09-09)
for both hashes and verification boundaries. The extra credential's signature was
not authenticated during this audit.

Next work is clean installation reliability, cross-task restoration (use a stage
checkpoint to also test finishing remaining work), installed-plugin discovery and
representative real-paper quality. A final-checkpoint reopen alone would not test
interrupted-review continuation. Actual model/effort remain unknown. The successful
cloud run does not explain the original truncation or prove zero-friction distribution.
No review agents, package installations or canonical code changes were performed
locally for this artifact audit. Only documentation and an ignored audit helper changed.

## Earlier update: isolated repair passed; Full cloud test requested

This update supersedes the earlier setup blocker and proposed repair work below.
The user now requests a Full run of the previously supplied synthetic cloud fixture
in the existing cloud task. Repository editing remains here, not in that cloud test;
the cloud task needs the trusted plugin bundle, not a canonical source snapshot.

The privately downloaded `cloud-repair-trial-results.zip` has SHA-256
`fa692aab47c4f30c54501c540b72a24b5624ff905dd6da82625e002ea665e901`.
All 49 payload hashes match its manifest (50 total entries, 7,292,491 expanded bytes).
The archived imports both exit 0 and doctor reports ready with no missing packages
or version differences. Two integrity passes record 3,806 verified RECORD hashes
across 21 distributions. The original environment/plugin/artifact inventories are
unchanged; only the intended library differs in the copied environment. No archive
code was executed locally. These are verified downloaded records, not direct access
to the still-running cloud environment.

The repaired interpreter's exact location is recorded in the private repair receipt.
Use it directly: copied activation and console/pip launchers retain original paths
and must not be used. Confirm current integrity/doctor and actual host capabilities,
then run the unchanged bundle's skill/orchestration in a fresh review directory.
Do not rerun installation or repair just to begin the review. Preserve originals;
save stage checkpoints, export the complete PDF and record actual native activity.
No Full cloud review has run yet. Clean installation, truncation cause, installed
plugin discovery, real-paper quality and cross-task recovery are still unresolved.

## Product and architecture contract

- `Ingar30/reviewer` is the canonical product. Maintain prompts, roles, schemas,
  processing, routing, validation and editor synthesis in the ordinary Reviewer.
- The skills-only plugin is a generated distribution plus native-host adaptation,
  not a second review methodology. Do not hand-edit its generated runtime.
- Preserve the ordinary CLI. Its reference configuration is `gpt-5.6-sol` / `xhigh`
  for substantive reviewers/editor, with `high` for parser/router. The user selected
  Astra Extra High for the cloud trial; actual settings were not exposed in its
  evidence, and this does not change the CLI default or establish a quality benchmark.
- Researchers should eventually install the plugin, attach a paper, and download a
  complete PDF using available subscription usage. No local checkout/interpreter,
  API keys, nested `codex exec`, or paid inference backend is an acceptable cloud fallback.
- Full/Lite keep the same review coverage rules. Do not remove pandas, skip
  deterministic processing, bypass validation or weaken audits to get past setup.

## State at original handoff, before the successful repair above

The local private plugin completed Paper22 with 19 accepted substantive reviews and
a downloaded PDF. Cloud testing is a separate gate: the attached-bundle test reached
an environment identified by execution metadata as OpenAI-hosted, but dependency
preparation failed before PDF preprocessing, native children or any reviewer ran.
There is no cloud review PDF, coordinator state or resumable review checkpoint.

The original cloud acceptance record found no installed Economics Paper Reviewer
skill in the exposed catalog, so it used the explicitly authorized attached ZIP.
This is NOT a successful plugin installation/discovery test. Native child tools were
exposed but not exercised. Actual model/effort remain unknown. Diagnostic downloading
succeeded; review PDF delivery, cross-task restore and scientific quality remain untested.

The original failure was SIGBUS during pandas import. The follow-up diagnostics now
identify an incomplete NumPy OpenBLAS shared library as the strongest immediate
explanation, rather than establishing general pandas/version incompatibility.

## Evidence to inspect, never execute

Private files remain in the publisher's Downloads folder and must stay out of Git
and public bundles.
The ZIPs contain diagnostic data and some collector source, not trusted runtime code.

| File | SHA-256 |
| --- | --- |
| `cloud-test-acceptance.md` | `7592049536555ad36e1427a52cc38677b2862b56a4b90f0e99b41a9cd42bfa58` |
| `cloud-test-diagnostics.zip` | `8412d22af051f8b2cb07e3d06b24058388bd8eed475046da319f2a1de7db1ff1` |
| `numpy-pandas-cloud-diagnostics.zip` | `352b59fa1bd3406ffbbb7afdf75c0bba47d3b7ce2ebffa5e4fb3072234c25bc2` |

`cloud-test-acceptance (1).md` is byte-identical to the first acceptance download.
The first archive's acceptance copy also matches. All three attachment hashes and
all 46 recorded plugin file hashes match the prepared local cloud kit.

The follow-up ZIP has 36 entries, 3,231,834 expanded bytes. All 35 payload hashes
match `SHA256-MANIFEST.json`; there are no unlisted payloads. It contains no native
package binaries. Inspection confirmed internal consistency of the recorded evidence,
not an independent observation of the live cloud filesystem or an authenticated
attestation of hosting. No archive code was run locally.

### Confirmed recorded failure details

- Cloud Python: CPython 3.12.14, x86_64, glibc 2.39. NumPy 2.5.3, pandas 3.0.2.
  Both wheel tags match supported interpreter tags. The earlier successful Windows
  cold-start receipt has the same NumPy/pandas versions, but different platform wheels.
- Separate NumPy-only and pandas-only subprocesses both exited `-7` with faulthandler
  traces converging at NumPy's native extension import. `135` is the corresponding
  conventional shell status, not a separately observed shell invocation.
- `numpy.libs/libscipy_openblas64_-f48b354e.so` is recorded as **12,582,912 bytes**
  (exactly 12 MiB), versus **24,325,657 bytes** in installed NumPy `RECORD`.
- Observed file SHA-256:
  `22c35943ee2338b2ad099d532b28b372ec199408e30012a269713163e3b1e560`.
  Expected SHA-256, decoded from the archived `RECORD`:
  `432e1c1739731468ba305771af96773939e43016643e2d630f58cb45b6670e96`.
- Archived `readelf` output identifies this dependency and its NumPy library RPATH;
  the OpenBLAS file's section headers/dynamic segment extend beyond recorded EOF.
- The integrity report records one mismatch among 928 hashed NumPy files and zero
  among 1,521 hashed pandas files, with none missing. This is a comparison to installed
  metadata, not an independently downloaded wheel. Unhashed entries were not verified.
- Before/after inventories are byte-identical across 7,238 recorded environment
  entries. The bad file already had this size/hash before both import probes.
  The collector compares metadata for all entries and hashes selected critical files;
  it does not hash every environment file or establish when the truncation happened.
- The exact native faulting instruction, truncation cause and time remain unknown.
  Do not assert that OpenAI imposes a 12 MiB file limit, that PyPI supplied a corrupt
  wheel, or that changing the model/package versions will fix this.

## Where the maintained implementation lives

- `scripts/prepare_work_environment.py`: permission-gated fresh venv preparation;
  canonical direct requirements, wheel-only PyPI installation, same coordinator doctor.
  It retains failed environments and currently collapses setup errors into a generic
  message. The doctor imports dependencies in-process, so native crashes kill it.
- `scripts/work_plugin.py`: deterministic native-host coordinator, validation,
  reservations/retries, checkpoints, PDF export. It never calls a model API.
- `scripts/build_work_plugin.py`: generated runtime/import closure, drift/release checks.
- `scripts/build_cloud_test_kit.py`: fresh private ZIP, synthetic PDF, prompt and receipt.
- `scripts/render_report_pdf.py`: shared deterministic export of validated Markdown.
- `plugins/economics-paper-reviewer/skills/review-paper/`: maintained skill and host
  orchestration plus generated runtime. Consult the maintenance guide before changes.

The tested cloud kit is `output/cloud-test-2026-09-08/`:
`economics-paper-reviewer.zip`, `cloud-test-paper.pdf`, `START_HERE.md`, `receipt.json`.
Plugin ZIP hash: `eed2e51917fedcb91587e3b22b532435b9636aea410c28ff20a8f98007c5c029`.
Preserve this exact build and use fresh output names for subsequent candidates.

The installed local private snapshot remains `0.1.0+codex.20260908154926`, sourced
from `output/work-plugin-private-pdf-2026-09-08/`. Cloud preparation deliberately did
not replace it. The repository manifest is development version `0.1.0`, not a public
release. The working tree contains substantial uncommitted/untracked prior work;
preserve it. Nothing has been committed, pushed, tagged, submitted or published here.

## Original proposed next work (read the latest update first)

1. Review the evidence and current source. Focus first on installed-file integrity,
   not removing pandas or changing review methodology. Do not rerun a Full review yet.
2. For a separately authorized cloud repair trial, preserve the failed environment
   and use a fresh destination. Compare a verified original wheel and its internal
   RECORD with newly installed files before imports. Retain versions for the first
   controlled experiment; record any transitive versions explicitly. Investigate
   recurring truncation rather than retrying indefinitely or bypassing host limits.
3. Consider hardening the shared setup path to report native-import crashes with
   subprocess isolation and useful integrity diagnostics. These are candidate fixes,
   not implemented or tested changes. Keep checks deterministic, bounded and secret-safe.
4. Any setup/code change needs targeted tests, regenerated runtime, drift checks and
   a new cloud candidate. Keep the ordinary CLI and existing installed plugin intact.
5. Only after the pinned dependency check passes, test preprocessing and native child
   artifact access, then Full completion, PDF download and a second-task restoration.
   Installed-plugin distribution and representative real-paper quality are later gates.

The user authorized the original cloud setup. The latest follow-up diagnostic was
explicitly read-only: no reinstall, pin changes or reviewer start was performed.
State the planned effect and obtain appropriate permission before a new installation,
external mutation, publication or paid action; this handoff itself grants none.

The user is signed in to ChatGPT in Chrome. Our browser-control bootstrap previously
failed on a stale service path; do not assume access to that signed-in session. Do not
read/copy cookies or browser profiles. Ask the user only for actions that available
tools cannot perform. Keep the original cloud task available for evidence/repair.

## Verification history and handoff checks

- Historical pre-cloud full suite: 167 offline tests passed.
- Cloud helper/kit work: 63 distinct relevant tests passed across focused runs, plus
  bundle/plugin/skill/hygiene checks and a successful local empty-venv installation.
  These are historical local results, not successful cloud imports or review quality.
- This handoff turn: ZIP payload hashes, archived RECORD/ELF/trace consistency and
  before/after inventory hashes checked. Documentation only changed; no dependencies,
  executable code, runtime bundle, private installation or cloud environment modified.

Continue with [cloud acceptance](chatgpt_work_plugin_acceptance.md) and
[joint maintenance](plugin_maintenance.md). Update those records when new evidence
changes the outcome; do not turn this dated handoff into a second maintenance manual.
