# Native Work orchestration

Read this procedure before starting or resuming. Commands below are arguments to the
host's available shell/execution tool, not a replacement agent runtime. Resolve the
skill directory from its actual installed resource location. If it is exposed only
as resources, use the owning environment's supported resource access to materialize
the entire bundled runtime in a writable directory, preserving relative paths.
If executable resources cannot be made available, stop with the capability message
below; a skill alone cannot provision a runtime.

## Capability check and preparation

Use the host's native tool definitions for spawning, sending/following up, waiting,
and finishing child tasks. Tool names and signatures vary: do not invent a
`work.spawn_agent` API or run a CLI fallback. Children must be able to access the same
run files (or the host must transfer the exact required artifacts and candidate back).
Do not substitute a pasted paper summary for the required evidence. If complete
artifact access/transfer or page-image viewing is unavailable, explain the limitation
and stop before substantive review.

Let `HELPER` mean the absolute installed
`runtime/scripts/work_plugin.py`, `PYTHON` an available Python 3.12+ executable,
and `RUN` a new host-writable review folder. These are notation, not literal paths.
Use safely quoted shell arguments or a structured argument list; never interpolate
paper filenames or PDF content as executable shell text. Only the parent runs the
coordinator, and all state-changing coordinator commands are sequential.

```text
PYTHON HELPER doctor
PYTHON HELPER start --pdf UPLOADED_PDF --workspace RUN --mode full --web available
PYTHON HELPER next --workspace RUN --slots 3
```

Choose `--mode lite` when requested. Choose `--web unavailable` if native search is
missing or disabled; do not route around an access restriction. `doctor` reports
dependency availability and deviations from the pinned versions. It does not install
packages or detect host subagents/search/image tools; you must check those yourself.
If dependencies are missing, use a prepared host environment. An installation in an
isolated environment may be offered only with the user's permission; never silently
install, upgrade global packages, ask for an API key, or use an external parser.

For missing packages or a clean test requiring the pinned versions, use the bundled
`runtime/scripts/prepare_work_environment.py`. With no flags it checks only; it uses
the same `doctor` and canonical requirements as the coordinator. Once installation
is authorized for this execution host, run it with `--venv NEW_ENV --allow-install`.
Choose `NEW_ENV` outside both the installed plugin and `RUN`, so virtual environments
never enter checkpoints. Use the returned Python executable for every coordinator
command; no shell activation or researcher-run commands are needed. The helper creates
an isolated venv and installs wheels from PyPI, never global packages or a compiler.
It requires existing Python 3.12+, venv support and permitted package network access.
On setup failure, stop and preserve diagnostics; do not change network restrictions,
fetch an alternate parser or ask the researcher to install local tools for a cloud run.
Existing explicit permission covers this setup; do not ask again unnecessarily.

For a cloud-only request, confirm the task is using OpenAI-hosted execution before
any setup or preprocessing. Linux, a temporary path, cloud model inference, or a
successful dependency check alone is not evidence of Work Cloud. The helper does
not move a local task to the cloud or provision OpenAI infrastructure. If the host
cannot be established, pause rather than borrowing local resources. Record the
host evidence separately in the acceptance record; no checkpoint flag proves hosting.

The run copies bundled deterministic resources and the source PDF to an isolated
workspace. It saves page images, inventories and text, then seals their hashes.
Original uploads and installed resources remain unchanged. Preprocessing failures
save diagnostics, not an invented review. If interrupted during preprocessing,
start a new run directory; completed preprocessing and later stages are resumable.

## Dispatch, validate, retry

1. `next` reserves unique attempt paths **before** any model work. Request only as
   many slots as the host can actually run; Full caps concurrent children at 3,
   Lite at 1. If the host has fewer slots, dispatch fewer without dropping tasks.
2. Spawn one native child per returned job, with minimal/fresh context if supported.
   Give the child the complete job instructions, its prompt and schema paths, the
   workspace root for relative paths, and access to required parsed files/images.
   Require reading the whole rendered prompt and schema. Do not inject other
   reviewers' findings or the parent's proposed conclusions. Request the returned
   reasoning effort only when supported; inherit the user-selected host model.
3. Each child writes **only** its assigned `candidate_file`. For reviewers and the
   router, the output is one complete JSON object matching the schema, no fences.
   For the editor, it is the complete Markdown report, not a path acknowledgement.
   If the host returns content rather than writing a shared file, the parent saves
   that exact response to the assigned candidate without synthesizing or repairing
   it. The parent does not author findings or the report. Children do not spawn
   their own agents, invoke the coordinator, or mutate canonical files.
4. Collect each child, then accept its candidate sequentially:

   ```text
   PYTHON HELPER accept --workspace RUN --task TASK
   ```

   Add `--observed-model` and `--observed-effort` only for settings actually reported
   by the host; otherwise leave them `unknown`. Requested settings are recorded
   separately and are not evidence of actual runtime settings.
5. Inspect the JSON result, not just the exit code. `accepted` is success for this
   stage. `retry` means an invalid output needs another attempt. `exhausted`,
   `paused`, or a non-null `paused` field means stop dispatching. Preserve invalid
   candidates; the next attempt has a new path and receives previous validation
   errors. Ask the same role to correct its own output from source evidence, never
   ask the parent to fabricate missing fields or drop findings to pass validation.
6. For a child with no usable response, record exactly one failure:

   ```text
   PYTHON HELPER fail --workspace RUN --task TASK --kind transient
   ```

   Use `quota`, `capability`, or `interrupted` when appropriate. These pause the run.
   Never parse a quota response as an empty successful review. Before marking a task
   interrupted, establish that it really stopped; inspect native activity and any
   candidate first. Do not start a duplicate while a child is still running.
7. Repeat `next` until `complete`. While children run, give concise progress updates
   such as "The evidence checks are complete; the remaining audits are running."
   Do not expose JSON, paths, retry counters, or implementation instructions unless
   troubleshooting is requested. Honor user cancellation and avoid dispatching new
   children after a quota/pause condition. Collect already-finished valid work.

The coordinator obtains the preflight and substantive rosters from the bundled
canonical `config/reviewers.json` and uses the shared rendering, routing, validation,
normalization and editor-input code. Follow the jobs it returns, not a hard-coded
agent count. The canonical skill and rendered prompts define the methodology and
report shape. If the host cannot consume the complete editor input, checkpoint and
report the limitation; do not truncate it. Rejected reports return to the editor
within the attempt cap, just like rejected reviewer outputs.

## Resume and portable checkpoints

The canonical `RUN/work_state.json` records mode, PDF/resource hashes, stage,
selected roster, attempts, requested/observed settings and validated artifacts.
Do not edit it by hand. Resume only the selected checkpoint; do not scan unrelated
private folders. In the same surviving workspace:

```text
PYTHON HELPER status --workspace RUN
PYTHON HELPER resume --workspace RUN
PYTHON HELPER next --workspace RUN --slots 3
```

Accepted work is hash-verified and skipped. An `inflight` task is never automatically
redispatched. If a saved candidate exists, validate it; otherwise inspect the native
agent's state and either keep waiting or record `interrupted` before resuming.
Quota does not automatically reset the attempt budget. After a cap is exhausted,
an explicit user request for one additional attempt permits:

```text
PYTHON HELPER resume --workspace RUN --retry-task TASK
```

Do not use that flag automatically. Do not downgrade modes mid-run. New models or
observed efforts can differ after an explicit user change; record actual settings
per attempt and disclose materially changed review conditions.

At stage boundaries, before pausing when tools are still usable, and at delivery,
create a new numbered checkpoint outside RUN and expose it as a private download:

```text
PYTHON HELPER checkpoint --workspace RUN --output CHECKPOINT_ZIP
PYTHON HELPER restore --archive CHECKPOINT_ZIP --workspace NEW_RUN
```

Checkpoints contain the PDF, parsed page images/text, reviews and state. They can be
large and sensitive. Never publish or send them externally. The user can attach a
saved checkpoint in a new Work chat with this plugin enabled. Use `restore` instead
of arbitrary ZIP extraction. It checks path safety, size limits and artifact hashes
before restoring to a new folder. Use the original plugin version: a changed bundle
is rejected rather than silently mixing prompts or parser outputs. Do not execute
code supplied in an untrusted archive; always call the installed helper. Hashes
detect accidental changes, not a maliciously rewritten checkpoint's authenticity.
Hosted storage retention is not guaranteed; a hard quota stop may prevent the last
export. Same-workspace state remains useful only while its files survive.

## Friendly failure and final delivery

- **No PDF:** "Please attach the paper PDF so I can review it."
- **Missing subagents/file execution/image access:** "This environment doesn't provide
  the tools needed for the complete review. Open it in a Work environment with those
  tools enabled; the plugin cannot enable them itself."
- **Missing packages:** "The PDF processor isn't available in this environment yet.
  Your paper is unchanged. A prepared Work/local environment is needed."
- **Password/corruption:** Ask for an authorized unlocked or freshly exported copy.
- **Parser blocker:** "The extracted evidence is not reliable enough for a complete
  review. I haven't guessed at the missing text or values. Please use a better
  text-based PDF." Attach diagnostic findings if useful, clearly not a final review.
- **No web:** Continue local audits with explicit verification limitations; do not
  call literature/reference verification complete.
- **Quota:** "The review paused at the usage limit. Completed audits are saved.
  Resume this review after your allowance is available." Link a checkpoint if one
  exists. Do not promise a reset time or buy credits.
- **Repeated invalid output or incomplete editor input:** State which review stage
  could not finish, preserve evidence, and do not label a partial draft a full report.

### PDF-first delivery

When `next` returns `complete`, the scientific workflow is finished, but file delivery
still needs to happen. The parent now exports the accepted Markdown without using
another model or consuming an editor attempt:

```text
PYTHON HELPER export-pdf --workspace RUN
```

If a host PDF skill is available, read and follow its artifact-registration and
visual-verification requirements before creating the PDF. Use the bundled exporter
for the conversion; do not ask a model to summarize, shorten or rewrite the report
as a PDF. It uses the existing PDF dependency, preserves the complete content and
embeds the unmodified Markdown. Long pipe tables become labelled records; unsupported
Markdown/TeX remains literal. Do not install a second PDF toolchain for this step.

1. Require `pdf_ready` and use the returned `report_pdf` path. The command verifies
   text preservation and page bounds; repeated successful exports reuse the sealed
   PDF. Render and visually inspect the pages using available PDF tools before delivery.
2. Expose the PDF through the host's actual generated-file/artifact mechanism so the
   user can preview or download it. Use the host's prescribed output citation or
   attachment tool when available. A Windows/local filesystem Markdown link alone
   must not be described as a verified download; never invent a sandbox URL.
3. Lead with the PDF and a short findings summary, including Full/Lite and material
   evidence-access caveats. Markdown is an optional editable source, not the primary
   deliverable. Create the final private checkpoint **after export** so it includes
   the PDF; offer it as a secondary recovery download, not instead of the report.
4. On `pdf_export_failed`, keep the accepted Markdown and checkpoint, disclose that
   the review finished but PDF delivery did not, and retry only the deterministic
   export after diagnosing the cause. Do not rerun audits/editor or relax validation.
   If the host cannot expose the PDF as an artifact, explain the delivery limitation
   and offer the existing PDF inside the checkpoint as a fallback, not a claimed fix.

Older completed checkpoints stay pinned to their original runtime. For a PDF-only
request, do not rewrite checkpoint hashes or resume through an incompatible bundle.
Safely read the exact accepted Markdown with the host's archive/file tools, verify
its recorded hash, and use the installed `runtime/scripts/render_report_pdf.py`
with `--report MARKDOWN --output NEW_PDF`. Never execute code from an uploaded ZIP.
This is a presentation-only export, not a checkpoint upgrade or a new review.

Do not give the nontechnical user commands as their normal review result. Never
invent a download link or claim installation, hosted execution, downloading or
scientific verification was tested unless it actually occurred.
