# ChatGPT Work plugin: private testing and release

For the canonical-source architecture, regeneration rules, GitHub tag distribution
and release automation, see [Maintaining and releasing one Reviewer](plugin_maintenance.md).
The generated runtime is not a second implementation. New changes are built from
the authoritative core and released as explicit, pinned snapshots.

The **Economics Paper Reviewer** plugin is a skills-only adapter to this repository's
review pipeline. Install it, attach an economics paper PDF in **Work**, and select
**Review this paper** (or the Full starter prompt). The intended result is a complete,
downloadable PDF report, with the original Markdown retained, plus a private checkpoint. Normal users do not need a
Git checkout, terminal commands, Codex CLI, API keys, or API credits **once an installed
plugin has access to a prepared Work runtime**.

This is an unpublished package. A Full synthetic attached-bundle cloud run succeeded
on 2026-09-09 in a repaired dependency environment; clean cloud installation, installed
discovery and cross-task recovery remain unverified. See the
[test record](chatgpt_work_plugin_acceptance.md#full-run-and-download-audit-2026-09-09)
and [public submission runbook](plugin_publication.md).
Installation instructions cannot guarantee that every account has native
subagents, file execution, Python PDF dependencies, or page-image viewing. A missing
capability produces an explanation, not a degraded review passed off as complete.

**Cloud-only target:** local tests and a local plugin catalog do not establish
cloud availability. Use the [cloud acceptance procedure](chatgpt_work_plugin_acceptance.md#cloud-only-acceptance).
The cloud task must supply all execution and dependencies; connecting back to the
researcher's computer is not a cloud-only pass.

**Stress-test fixes (2026-09-07):** the eight failures involving JSON decoding and
checkpoint/task validation have been fixed. All 150 regression tests pass, including
11 new tests covering these defects and related cases, and all 34 supported stress
scenarios pass. Hosted Work acceptance testing is still required. See the
[stress findings, fixes and reproducible cases](chatgpt_work_plugin_stress_2026-09-07.md).

## What is included

- `plugins/economics-paper-reviewer/.codex-plugin/plugin.json`: stable identity,
  install metadata and three starter prompts (Full, Lite, resume).
- `skills/review-paper/SKILL.md` and `agents/openai.yaml`: **Review this paper** entry
  point and the nontechnical interaction contract.
- `references/orchestration.md`: native-subagent dispatch, validation, bounded retry,
  quota pause, recovery and artifact handoff instructions.
- `runtime/`: self-contained, LF-normalized copies of the canonical deterministic
  processor, conservative routing, all prompts, schemas, validators, lossless
  normalizer, editor-input builder, final checker, requirements and license.
  It also includes the canonical `.agents/skills/paper-reviewer/SKILL.md` unchanged
  as `reviewer-guidance/paper-reviewer.md` (a reference, not another discoverable
  skill). The plugin adapts only CLI-specific execution details.
- `scripts/work_plugin.py`: model-free state machine. It launches only the bundled
  deterministic PDF-processing Python program; the host dispatches all model work.
- `scripts/build_work_plugin.py`: allowlisted bundle synchronization, drift check,
  reproducible ZIP and optional fresh private marketplace generation.

There are no MCP servers, app connections, hosted backends, hooks, API clients, model
API calls, or nested `codex exec` processes in the plugin. The CLI wrappers are
deliberately excluded from its archive. The existing CLI still works as documented
in the main README. Its pure routing functions are shared with the adapter through
`scripts/reviewer_routing.py` and remain importable from `review_paper.py`.

The only report-checker behavior adjustment allows a genuinely empty validated
bundle to produce an honest no-findings report without inventing a finding ID.
Nonempty bundles still require complete traceability and the existing checks.

## Full and Lite

| | Full (default) | Lite (explicit) |
| --- | --- | --- |
| Substantive coverage | 8 universal + all applicable specialists; up to 19 | Identical |
| Parser/router effort request | High | High |
| Reviewer/editor effort request | Extra High / `xhigh` | High |
| Parallel children | Up to 3, bounded by host capacity | 1 |
| Total attempts per stage | 3 | 2 |
| Prompts, schemas, evidence and report checks | Canonical | Identical |

Both inherit the user-selected host model. These are **requests**, not enforceable
subscription or model settings. If the host lacks an effort override, its settings
apply; observations are recorded as `unknown` when not exposed. Full preserves the
CLI's substantive workflow, but does not automatically reproduce its benchmarked
Sol/xhigh model configuration. Lite is unbenchmarked and is not claimed to match Full
quality or guarantee savings. Serial execution is not itself a total-token saving.

No mode drops an applicable specialist, caps findings, repairs evidence with an LLM,
or truncates the editor bundle. Mixed/unknown or lower-confidence routing expands
to all conditional specialists, exactly as in the CLI.

## Usage and quota

ChatGPT Work and Codex share pricing, credits and usage limits. Native subagents add
model/tool usage, and long PDFs, web checks and retries can consume substantial
allowance. These facts are documented by OpenAI's [pricing page](https://learn.chatgpt.com/docs/pricing)
and [subagent guide](https://learn.chatgpt.com/docs/agent-configuration/subagents).

The plugin requires no model API key and does not use API billing. That is **not** a
promise of unlimited or zero-cost account usage: it cannot read remaining quota or
enforce included-only billing. Account/workspace credits or overage settings remain
outside the plugin. It never purchases credits, changes billing, or automatically
switches to an API. To require strictly included usage, use the relevant account's
existing usage/spending controls; do not assume a skill can implement them.

Quota/capability failures pause dispatch. Valid completed stages remain saved. There
is no automatic scheduler to restart at reset time, and no promise of a full review
within an account's allowance. A user-requested resume continues from saved work.

## Test privately in ChatGPT Work

These are **maintainer setup steps**, not the end-user review workflow. They do not
publish anything or require API credits. Use the existing prepared `.venv`; do not
run setup scripts or install dependencies just to build the ZIP.

### 1. Build and test the exact local package

From the repository root, on Windows:

```powershell
.venv/Scripts/python.exe scripts/build_work_plugin.py --check
.venv/Scripts/python.exe -m unittest tests.test_work_plugin
.venv/Scripts/python.exe scripts/build_work_plugin.py --zip output/economics-paper-reviewer-0.1.0.zip --private-marketplace output/work-plugin-private
```

On macOS/Linux, replace `.venv/Scripts/python.exe` with `.venv/bin/python`.
If the ZIP and private catalog have already been generated from the current sources,
skip the last command and use them directly, or choose fresh output names.
For a fresh source change, first run the builder without `--check` to synchronize
generated runtime files. ZIP/catalog destinations must be new; use a new versioned
path for another build. The builder will not overwrite a prior ZIP or catalog.

**After the 2026-09-07 stress fixes:** the original `output/economics-paper-reviewer-0.1.0.zip`
and `output/work-plugin-private` were preserved and still contain the older runtime.
The corrected archive is `output/economics-paper-reviewer-0.1.0-stress-fixed.zip`.
Do not use an old catalog copy to test the fixes. Generate a fresh private catalog
with `scripts/build_work_plugin.py --private-marketplace output/work-plugin-private-fixed`
(using the same Python executable), then use that new catalog root in the installation
steps below. No catalog or installed plugin was updated automatically. For an already
installed local plugin, follow the update/reinstall guidance below and confirm which
source path is actually installed. Start a fresh review with the fixed bundle;
older checkpoints require their original runtime.

The repository plugin is already self-contained, so ordinary installation requires
no builder or runtime fetch from GitHub. The ZIP contains only the plugin package;
the optional marketplace is a separate local testing catalog.

### 2. Add the private source, then install in the desktop app

With a Codex CLI version that supports plugin marketplaces:

```powershell
codex plugin marketplace add ./output/work-plugin-private
codex plugin marketplace list
```

This command configures the **local private test catalog**; it does not launch a
review or publish anything. It is a one-time maintainer installation helper, not a
nested process used by Work. The generated entry resolves to
`./plugins/economics-paper-reviewer` relative to that catalog root.

Restart the ChatGPT desktop app, open **Plugins Directory**, choose
**Paper Reviewer (private test)** / `reviewer-private`, and install **Economics Paper
Reviewer**. Start a **new Work chat** with it enabled. If the desktop app exposes
local marketplace authoring directly, its Plugin Creator can register this same
plugin folder without the CLI. Do not overwrite an existing personal catalog.

OpenAI documents local marketplaces and installed cache copies in
[Package your plugin](https://developers.openai.com/plugins/build/plugins), and
recommends testing skills-only plugins immediately through the complete-plugin flow
in [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt).
No MCP developer-mode connection is necessary for this package. Local sources are
not the public directory, and their availability varies by surface. In particular,
do not assume a web-only account can install an arbitrary local ZIP through the MCP
connection dialog; the documented ZIP upload is a submission flow, not that dialog.

### 3. Prepare the runtime and exercise the user flow

The host needs Python 3.12+, the packages in the bundled `requirements.txt`, file
execution, native subagents, shared artifact access and page-image viewing. Native
web search is needed for live literature/reference verification. Availability varies
by account, platform, rollout and workspace policy; see [Use ChatGPT](https://learn.chatgpt.com/docs/use-chatgpt).

For the first private test, a desktop **Work locally** environment that can use this
repository's existing `.venv` avoids new dependency installation. The plugin still
uses only its bundled sources and an isolated run folder, not CLI review wrappers.
If testing hosted Work, have it run the skill's `doctor` and capability check first.
The skills-only manifest cannot provision a custom environment or guarantee that
the pinned packages are preinstalled. Missing packages require a prepared environment
or a separately approved isolated install. The bundled `prepare_work_environment.py`
can perform that install on the current host with `--venv NEW_ENV --allow-install`;
without permission it only checks. This does not create or switch to a cloud host.

Attach a short non-sensitive paper, then select **Review this paper** or send:

> Review this paper. Use native subagents for the Full review.

You should see a short usage warning and stage progress, native child activity,
then a downloadable `report.pdf`, optional `report.md`, and a private checkpoint containing
both after successful export. Test the actual PDF preview/download, not only the ZIP.
You should **not** be asked
for an API key, given raw JSON as the final report, or see nested Codex runs.
Try Lite and resume separately using the other starter prompts. The manifest supplies
starter text and the skill display label; exact chips/menu presentation is host-owned,
not a custom button or UI implemented by this plugin.

Use [the acceptance cases](chatgpt_work_plugin_acceptance.md). Record the actual host,
model/effort if exposed, package versions, enabled tools, outcome and caveats. Local
synthetic tests exercise the coordinator but do not establish hosted model behavior,
quality, quota consumption or one-click completion.

### 4. Update a private install

Rebuild after changing canonical sources, increment the plugin version for a release,
and produce a fresh catalog/ZIP. Installed plugins are cached, not live views of the
source tree. Refresh the configured marketplace and reinstall/update from its new
source, restart the app and use a new chat. If the replacement catalog is at a new
path, explicitly replace the configured source before reinstalling:

```text
codex plugin marketplace remove reviewer-private
codex plugin marketplace add ./output/work-plugin-private-v2
```

These commands change the local catalog registration, not the saved review data or
public directory. For iterative cache troubleshooting, use
Plugin Creator's supported cachebuster/reinstall flow for that marketplace instead
of hand-editing user settings. Keep the original bundle to resume older checkpoints;
the coordinator refuses a changed runtime fingerprint.

Workspace admins may publish a tested local plugin to selected workspace roles via
**Plugins → Personal → … → Publish**, subject to workspace policy. This is private
workspace distribution, not public submission. It has not been performed here.
[Official workspace-publishing instructions](https://developers.openai.com/plugins/build/plugins#publish-a-local-plugin-to-your-workspace).

## Checkpoints and known boundaries

- State and canonical artifacts are saved in a fresh isolated folder. Existing PDFs,
  installed plugin resources and existing review folders are not overwritten.
- PDF, parsed artifacts, runtime resources, rendered prompts and accepted outputs
  are hash-checked on reuse. Candidate attempts are kept separately; the parent is
  the single state writer. This is a cooperative workflow, not an adversarial sandbox
  around native agents or a cryptographic signature of checkpoint authorship.
- Checkpoints are ZIPs containing private paper content, images, reviews and state.
  Keep them private. Restore checks traversal/entry types/limits and artifact hashes
  into a new directory. Always use the trusted installed helper, not code from an
  untrusted checkpoint. A checkpoint cannot grant authority to execute its contents.
- A running child is not silently redispatched. Resume first accepts its saved
  candidate or confirms it stopped, then records an interrupted attempt. Failed
  attempts retain their files; reaching the cap needs an explicit request for one
  extra attempt. A parser blocker cannot be bypassed by resume.
- Preprocessing interrupted mid-write starts again in a **new** folder. It is not
  page-by-page resumable. Completed preprocessing and all later stages are reusable.
- Hosted file retention and final checkpoint export are not guaranteed. A hard quota
  cutoff can stop export before the latest stage is captured. Download checkpoints
  while the host is still usable; same-chat resume depends on the files surviving.
- Scanned/image-only and badly extracted pages are retained and assessed by preflight.
  No OCR/service/model-repair layer is added. Lack of usable fallback stops review.
- No-web runs retain all auditors with explicit `partial`/`cannot_verify` outcomes.
  A schema-valid `failed` review is not accepted as completed coverage.
- Editor input has the canonical lossless size guard; it never truncates findings.
  If the host cannot consume it fully, the review pauses instead of fabricating a
  shortened evidence set. Very large PDFs/checkpoints may also exceed host limits.
- The final smoke check tests structure and traceability, not truth, citation
  existence, complete body coverage or substantive quality. Human review is needed.

## Public submission: what remains

### Local verification record

On 2026-09-06, Windows / Python 3.12.10 with the pinned requirements passed all
**139 unit/integration tests** (115 existing and 24 plugin tests). The plugin and
skill format validators, bundle drift check, repository hygiene checks, CLI entry
point checks and whitespace diff check passed. A separate native-subagent forward
test exercised the helper's checkpoint/quota workflow with synthetic responses.
Its malformed-URL and false-completion findings were fixed and regression-tested.
Tests used real deterministic PDF preprocessing but simulated reviewer/editor
outputs. No live API calls, public submission, app installation or hosted full-paper
review was performed. Windows sandbox temporary-directory restrictions required
running the new local tests outside that sandbox; no dependencies were installed.

On 2026-09-07, after the stress-test fixes, **150 regression tests passed** (115
existing pipeline tests plus 35 plugin tests). Plugin/skill format validation,
bundle drift and repository hygiene checks passed again. The corrected ZIP differs
from the original only in the coordinator and runtime hash manifest; the original
ZIP and private catalog remain available for older checkpoints. See the
[stress-test report](chatgpt_work_plugin_stress_2026-09-07.md) for the separate
opt-in adversarial and large-input checks and their limitations.

### Submission checklist

As checked against official documentation on **2026-09-06**:

1. Run the real installed-plugin acceptance cases on supported Work environments,
   including Full, Lite, interruption, quota simulation, no web and parser failure.
   Resolve runtime provisioning friction and benchmark quality/usage before making
   stronger reliability or savings claims. Keep results with the version tested.
2. Use an OpenAI Platform organization with **Apps Management: Write** (owners already
   have it) and a **verified individual or business identity**. Replace the current
   GitHub-handle publisher metadata with that matching identity when preparing the
   public listing; the repository cannot perform or assert identity verification.
3. Open the [plugin submission portal](https://platform.openai.com/plugins), create a
   plugin, choose **Skills only**, and upload the exact tested ZIP. Complete listing,
   starter prompts, availability, release notes and attestations. Prepare a logo and
   support materials requested by the portal; the local package does not invent them.
4. Provide the five positive and three negative cases in the acceptance document.
   The general submission guide requests these; the error reference explicitly
   makes exact counts a final requirement for MCP-backed plugins. Supplying them
   also makes this skills-only package reviewable without relying on an exemption.
5. Pass uploaded-skill safety/security scans and review. Scans can take up to two
   hours. Reviewers may require changes; upload validation is not public approval.
6. After OpenAI approval, explicitly publish from the portal. Submission alone does
   not publish. No public submission or publishing has been performed by this change.

For skills-only submissions, the current error reference marks website/support/
privacy/terms HTTPS URLs **optional** (required for MCP-backed submissions). The general
guide still recommends preparing them. Do not falsely attach OpenAI's legal policies
as the publisher's own. Adopt accurate publisher policies/support before broad use
and review third-party dependency licenses if redistributing dependencies; this ZIP
contains requirements, not third-party Python binaries.

Do not add `.mcp.json`, `.app.json`, their manifest fields or screenshots to a
Skills-only ZIP. MCP-backed requirements such as a production server, OAuth demo
credentials, domain verification, tool scans and UI screenshots do not apply to this
implementation. An OpenAI Platform publisher account is distinct from requiring end
users to supply API keys or API credits.

Sources: [Build skills](https://developers.openai.com/plugins/build/skills),
[Package your plugin](https://developers.openai.com/plugins/build/plugins),
[Submit plugins](https://developers.openai.com/plugins/deploy/submission), and
[Submission errors and skills-only limits](https://developers.openai.com/plugins/deploy/submission-errors).
