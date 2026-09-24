# Optional Claude Code backend (experimental)

This experimental option adds `--backend claude`; Codex/GPT-6 Sol remains the default.
It uses Claude Code's subscription-authenticated CLI, not an API SDK or a second
review pipeline. Prompts, schemas, preprocessing, reviewer selection, validators,
normalization and report checks are unchanged. It has **not completed a full live Claude pipeline**; the limited live checks below are not a quality benchmark.

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
For reproducible testing/recovery, pin the Git revision (`reviewer.git@COMMIT`) and
keep the same revision, workspace, paper ID and model when resuming.

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

Repeat `--backend claude` with the same paper ID, PDF and runtime:

```powershell
python scripts/review_paper.py --backend claude --pdf "inputs/my-paper.pdf" --paper-id "my-paper-claude" --resume-after-preflight
python scripts/refresh_editor.py --backend claude --paper-id "my-paper-claude" --run-editor
```

Resume reuses parsed artifacts and validated preflight, then reruns routing and
substantive reviewers. Editor refresh reuses completed reviewer outputs. Both may
consume usage. A saved backend mismatch is rejected: use separate IDs/workspaces
for Codex/Claude comparisons. With uv, use the same workspace and replace the
editor command with `--refresh-editor --backend claude --paper-id ID --run-editor`.
Claude's own session resume is not used; recovery follows the pipeline artifacts.

**Quota interruption:** keep the workspace and wait for the reset shown by Claude.
There is currently no public skip-completed-reviewers resume option. Retrying with
`--resume-after-preflight` spends allowance again on substantive reviewers and can
overwrite their earlier outputs/logs; copy the workspace first if retaining that
attempt matters. Use editor-only refresh only when all selected reviews are present.
A failed run can leave the manifest marked `running`; this is not proof that a
process is still active or that a complete report exists. The wrapper does not
change your billing settings or automatically switch to an API key.

## Validation status

Offline tests use synthetic PDFs and fake Claude/Codex processes; they are not
end-to-end model or quality validation:

```powershell
python -m unittest tests.test_claude_backend tests.test_uv_launcher
```

They exercise schema transport, failure/permission handling, prerequisites,
backend provenance, all pipeline stages, spaces/non-Git directories, persistent
outputs, and recovery after simulated stage failures. Local package validation
must use the newly built wheel, not GitHub. Real Ctrl+C, laptop sleep, web-tool
permissions, long-paper quality and actual usage remain live-test gates. The limited
live checks below do not establish compatibility on other platforms;
macOS/Linux/WSL have not had live-Claude validation here.

Local Windows validation (2026-09-24): 148 targeted offline tests passed. A newly
built wheel installed into a clean environment passed both backends' mocked
resume/editor-refresh acceptance, plus a fresh complete Claude pipeline. All 45
bundled runtime resources matched canonical sources. A deeply nested Windows
workspace initially failed during PDF copying; the shorter path with spaces passed,
so keep trial workspace paths short. Builds were staged outside Dropbox to avoid
file locks. These offline results alone do not establish live Claude compatibility or quality.

Live Windows checks (2026-09-24, Claude Code 2.1.281): after refreshing an expired
subscription login, Opus 5.5 passed a tiny text/image/structured-output test and
one canonical numerical reviewer on an existing 71-page paper. The latter reused
validated historical parsed artifacts/preflight, completed in 383 seconds, and
passed the canonical schema/provenance checks without changing evidence. Combined
reported API-equivalent usage was about $2.00, not measured billing. Local-wheel
`uvx --check` also passed with real subscription login. Preliminary source checks
found both useful findings and overstatements/omissions; no accuracy or full-report
completeness claim follows. A subsequent fresh local-wheel run passed preprocessing,
Claude preflight/routing, and two substantive reviewers with schema/provenance
validation, then stopped at the subscription session limit. Completed artifacts
persisted; no paid fallback or automatic retry was used. This trial did not fit a
complete xhigh pipeline into one session window (earlier tests also consumed usage).
Partial source checks against saved Sol results showed complementary catches and
some overstatements, not an overall winner. Live web roles, editor, continuation
and the complete end-to-end pipeline remain unvalidated. Keep Usage credits OFF
for subscription-only testing and retain the workspace when a limit is reached.

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
