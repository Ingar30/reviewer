# Optional Claude Code backend (experimental)

Use your Claude subscription to run the reviewer by adding `--backend claude`.
It follows the same review pipeline as Codex, with no API key required. Your first
review remembers the backend for this workspace. Start with Opus 5.5, or
choose Sonnet for a lower-cost option.

## Prerequisites and first test

Use the existing Python environment. Install the native Claude Code CLI separately
and sign in with a Claude subscription using `claude auth login` (not `--console`).
Opus 5.5's pinned model ID is `claude-opus-5-5`; it requires Claude Code **2.1.280+**.
See Anthropic's [model configuration](https://code.claude.com/docs/en/model-config)
and [authentication](https://code.claude.com/docs/en/authentication) documentation.
The adapter checks for subscription authentication and refuses API/provider overrides;
it never installs, updates, logs in or changes credentials on your behalf.

The no-review check verifies the **saved** login, not whether the server still
accepts its credentials. If a live call returns `401` / `OAuth access token is
invalid`, run `claude auth login` again and choose the subscription account, then
repeat a small smoke test before starting the reviewer suite. Do not switch to an
API key to work around subscription authentication failures.

From the repository, this check makes **no model request**:

```powershell
.\.venv\Scripts\python.exe scripts/check_environment.py --backend claude
```

After subscription/model access is ready, this command **consumes Claude usage**:

```powershell
.\.venv\Scripts\python.exe scripts/review_paper.py --backend claude --pdf "inputs/my-paper.pdf" --paper-id "my-paper-claude"
```

For the optional Git-backed uv launcher, Python 3.12+, Git and uv must also be
installed. Codex is not required for a Claude-only run. Run from the folder containing
the PDF:

```text
uvx --from git+https://github.com/Ingar30/reviewer.git economics-paper-reviewer --backend claude --pdf "paper.pdf"
```

For development, test **local changes** with the absolute checkout path or a locally
built wheel in `--from`, rather than the GitHub version:

```powershell
uvx --from "C:/path/to/reviewer" economics-paper-reviewer --backend claude --pdf "paper with spaces.pdf"
```

Replace the PDF/run options with `--check` for a no-review prerequisite check. A
locally built wheel can also be supplied to `--from`. The launcher resolves input
paths from the caller's directory and retains resources, papers, logs and reports
in `./reviewer-workspace/`, outside installation/cache directories. Optionally use
`--workspace DIR` to choose another folder; its name does not select a backend.
Use a separate workspace for Codex/Claude comparisons. Existing workspaces remain
tied to their original runtime and are not silently upgraded.
Keep Windows workspace paths reasonably short: a deeply nested trial failed
during PDF copying, while a shorter path containing spaces passed.
For reproducible testing/recovery, pin the Git revision (`reviewer.git@COMMIT`) and
keep the same revision, workspace, paper ID and model when resuming.

## Choose a model

The reviewer defaults to **Opus 5.5**. For a lower-cost option, select **Sonnet 5.5**:

```powershell
python scripts/review_paper.py --backend claude --model claude-sonnet-5-5 --pdf "inputs/my-paper.pdf"
```

The same `--model claude-sonnet-5-5` flag works with the uv launcher. Sonnet 5.5
requires Claude Code **2.1.284+**; run `claude update` if needed. See Anthropic's
[model configuration](https://code.claude.com/docs/en/model-config).

Sonnet generally uses less of your subscription allowance than Opus; see
[Anthropic's usage guide](https://support.claude.com/en/articles/14552983-models-usage-and-limits-in-claude-code).
Its paper-review quality has not yet been benchmarked here. The model choice applies
to the whole review and does not change your default. Keep the same model when
resuming; use a new paper ID or workspace to compare models.

## Behavior and limitations

- All stages use Claude only when selected. Default efforts remain `high` for
  preflight/routing and `xhigh` for reviewers/editor; `--model` and effort overrides
  still work. Claude rejects `none`. These labels do not establish equivalent
  reasoning quality or cost across providers.
- Each stage runs through `claude --print --output-format json`. Canonical schemas
  go through `--json-schema`; the adapter extracts `structured_output` for reviewers
  and `result` for the editor, then runs the existing checks. Raw stdout logs retain
  usage/model metadata. Failed, malformed or permission-denied results are rejected.
  See [programmatic Claude Code](https://code.claude.com/docs/en/headless).
- Available agent tools are Read/Glob/Grep, with WebSearch/WebFetch added only for
  search-enabled reviewers. Shell, editing and delegation tools are not exposed;
  MCP tools and skills are disabled for these calls. `dontAsk` denies unapproved
  actions; existing deny/ask rules still apply. No permission bypass, API-only
  `--bare` mode or sandbox downgrade is used. Existing trusted Claude settings/hooks
  still apply; tool restrictions are **not filesystem isolation**.
- Native Windows has no Claude Bash sandbox. The prototype therefore does not
  offer arbitrary shell/Python calculations to Claude. Image reading has passed
  limited live checks; web evidence, numerical-audit coverage and large editor
  inputs still need broader live validation. See
  [sandbox scope](https://code.claude.com/docs/en/sandboxing).
- To restrict a trial to the subscription's included allowance, keep **Usage
  credits / Extra usage disabled** in Claude Settings > Usage. Subscription login
  alone does not prove that overage billing is disabled. The CLI's reported USD
  value is an API-equivalent estimate, not a charge or remaining-plan balance.
  See [Anthropic's usage-credit controls](https://support.claude.com/en/articles/12429409-manage-usage-credits-for-paid-claude-plans).
- Manuscript content goes to Anthropic; search roles can transmit derived queries.
  Subscription limits, model access and any enabled extra usage are account-specific.
  No cost/quality parity with Sol or Luna has been measured. Reviewers use the
  existing default of up to four running concurrently.

## Resume and editor refresh

Keep the same paper ID, PDF and runtime. The saved run supplies the backend, so
you do not need to repeat `--backend claude`:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --paper-id "my-paper-claude" --resume-after-preflight
python scripts/refresh_editor.py --paper-id "my-paper-claude" --run-editor
```

Resume reuses parsed artifacts and validated preflight, then reruns routing and
substantive reviewers. Editor refresh reuses completed reviewer outputs. Both may
consume usage. A saved backend mismatch is rejected: use separate IDs/workspaces
for Codex/Claude comparisons. With uv, use the same workspace and replace the
editor command with `--refresh-editor --paper-id ID --run-editor`.
Claude's own session resume is not used; recovery follows the pipeline artifacts.

**Quota interruption:** keep the workspace and wait for the reset shown by Claude.
Quota/authentication errors identify the retained stdout log containing provider
details; a saved login check does not establish available quota. If preflight
itself failed, rerun the original command after resolving the limit/login.
For runs started with this version, repeat the original command with
`--resume-incomplete`. After preflight and routing have completed, it reuses
validated successful reviewers and retries only unfinished reviewers and the
editor. It requires the same PDF, backend, model, effort settings, configuration,
parsed artifacts and runtime. Changed accepted reviews are refused, and new
attempt logs are retained separately. A completed checkpoint makes no model call.

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --paper-id "my-paper-claude" --resume-incomplete
```

With uv, append that flag to the original pinned launcher command and keep the
same workspace. Do not upgrade an interrupted workspace in place. Older runs
without a selective-resume checkpoint retain the existing recovery methods:
`--resume-after-preflight` reruns routing and **all substantive reviewers**;
`--refresh-editor` needs all selected reviews and reruns only assembly/editor.
Do not combine the two resume flags. Selective resume is not Claude session resume.

Backend preferences apply to new papers, not to an existing paper's provenance.
Changing the workspace preference cannot switch a saved Claude run to Codex.
Older frozen runtimes keep their original behavior; repeat `--backend claude`
when using a version from before remembered backend choices were added.

A failed run can leave the manifest marked `running`; this is not proof that a
process is still active or that a complete report exists. The wrapper does not
change billing settings, poll for quota resets, retry automatically or switch to
an API key. Keep the computer awake during live calls. The wrapper now holds a
per-paper run lock and terminates its owned process tree on timeout/interruption;
power loss and laptop sleep can still leave the latest stage incomplete.

## Validation status

Offline tests use synthetic PDFs and fake Claude/Codex processes; they are not
end-to-end model or quality validation:

```powershell
python -m unittest tests.test_claude_backend tests.test_uv_launcher tests.test_resume_incomplete
```

They exercise schema transport, failure/permission handling, prerequisites,
backend provenance, all pipeline stages, spaces/non-Git directories, persistent
outputs, and recovery after simulated stage failures. Local package validation
must use the newly built wheel, not GitHub. Real Ctrl+C, laptop sleep, web-tool
permissions, long-paper quality and actual usage remain live-test gates. The limited
live checks below do not establish compatibility on other platforms;
macOS/Linux/WSL have not had live-Claude validation here.

### Live evidence and remaining limits

Windows / Claude Code 2.1.281 / Opus 5.5:

| Check | Result |
| --- | --- |
| Subscription login, text/image reads and structured reviewer output | Passed after refreshing an expired login |
| One-line synthetic PDF | All 22 live stages completed; zero findings and the final report validated. This tests workflow, not substantive review quality |
| 71-page qualitative-interviews paper | All 20 audits, including preflight, and the final editor completed across session-limit continuations; final structural checks passed on 30 September 2026. This was mixed-runtime recovery, not a clean single-version run |
| Additional single-version local-wheel trial, 1 October | Preflight, routing and three substantive reviewers completed before a subscription limit. Outputs/checkpoint were retained; the extra run was stopped, not counted as another complete pipeline |
| Source-grounded quality | The completed report contains useful corrections but also source-version errors and lost qualifications. Structural success does not establish semantic completeness, accuracy or cross-model equivalence |
| Clean local-wheel installation, spaces/non-Git paths and persistence | Mocked acceptance passed; these checks do not consume model usage or establish model quality |

The **30 September** long-paper continuation reused hash-checked accepted audits through a private
validation helper. This is **not** the public resume command and does not establish
unattended interruption recovery. Accepted workspaces keep their original runtime;
the large-editor continuation explicitly uses a newer builder/prompt. It is a
recovery validation, not a clean single-version full run or matched model benchmark.

The completed web-enabled audits used both Opus and a reported Haiku helper in
Claude Code's usage metadata. Comparisons therefore measure the CLI workflow,
not an isolated base model. The large editor handoff has completed once. The new
public selective resume passes mocked clean-wheel tests, including successful
sibling retention and changed-input rejection; full live selective continuation
has not been validated. Reliable report-body fidelity and a fresh single-version
completed long run remain limitations of this experimental release, not claims
established by the completed reports. macOS/Linux/WSL remain untested here. Keep Usage
credits OFF and retain outputs if a session limit is hit.

## Feedback from experimental testers

Start with `--backend claude --check` using the uv launcher; it makes no model
request and does not verify remaining quota or server acceptance of saved login.
Then try a paper you are permitted to send to Anthropic, keeping the computer awake.
Higher subscription limits may help, but completion in one session is not guaranteed.

Useful feedback: OS, Python/Claude versions, Git revision, model/effort, approximate
paper length, completed/failed stage, whether a final report was produced, and
source-checked examples of useful findings or false alarms. If comfortable, record
before/after session and weekly percentages from Claude's usage page; logged USD
estimates are not subscription usage. Do not post credentials, private papers or
unredacted prompts/logs publicly. Web-enabled roles, editor output and interrupted
recovery are the main remaining live test targets.
