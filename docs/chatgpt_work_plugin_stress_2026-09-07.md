# Work plugin stress test — 2026-09-07

**Post-fix verdict: all 150 regression tests and all 34 supported stress scenarios pass.**
The eight original failures are resolved. Hosted Work execution and scientific review
quality still require the separate acceptance tests before public submission.

**Original verdict: normal workflows passed, but eight stress cases failed.**
The original run below was testing-only. Its findings and measurements are preserved
as the pre-fix baseline. The subsequent coordinator fixes are described in
[Fix implementation](#fix-implementation).

## Original scope and results

| Check | Result |
| --- | --- |
| Existing regression suite | 139 passed: 115 existing pipeline tests + 24 plugin tests |
| New supported-workflow stress scenarios | 26 passed, 8 failed, across 34 distinct scenarios |
| Randomized complete workflows | 6/6 passed: three Full and three Lite, 144 simulated stage attempts in total |
| Archive rejection cases | 7/7 passed: traversal, absolute/Windows paths, case collisions, symlinks, file/directory conflicts and alternate streams |
| Interrupted acceptance write | Recovered the saved candidate without an extra model attempt |
| Additional boundary diagnostic | Two stale parent writers can duplicate a reservation; explicitly outside the documented single-parent contract |
| Bundle drift and repository hygiene | Passed; packaged runtime unchanged |

The randomized runs retained all 19 applicable substantive reviewers, enforced each
mode's concurrency limit, tolerated out-of-order completion, preserved quota pauses,
restored checkpoints to different paths and reached validated final reports. They
used scripted reviewer/editor responses, not model-generated reviews.

### Larger input measurements

- A **120-page synthetic PDF**, including rotated pages and three image-only pages,
  completed deterministic preprocessing in **20.894 seconds** on this machine.
- All 120 page images were retained; signs and decimal points were checked on sampled
  native-text pages. Image-only pages **40, 80 and 120** were all flagged for OCR.
  No OCR was run, and the original PDF hash stayed unchanged.
- Parsed artifacts: **9,512,759 bytes**. Portable checkpoint: **6,294,601 bytes**.
- Three full status/integrity checks took **1.949, 1.830 and 1.734 seconds**.
- A finding with **1,100,048 evidence characters** exceeded the lossless editor-input
  limit. The coordinator paused, produced no final report, and preserved the complete
  evidence exactly across checkpoint export/restore.

These are local synthetic measurements, not latency, memory, quota or review-quality
guarantees for real papers or hosted ChatGPT Work. The test did not measure peak RSS.

## Original failures

### 1. High priority: a damaged checkpoint can dispatch a reviewer before preflight

**Case:** `checkpoint/early_reviewer_injection`.

Adding a pending, configured substantive reviewer to an otherwise valid preflight
checkpoint makes `next --slots 3` return that review job alongside parser preflight.
No accepted parser output exists yet. This is not a bypass seen in the ordinary
single-parent workflow; it is a checkpoint-corruption failure.

Before the fix, `ReviewRun.__init__` checked known names and kinds, but
[`verify_stage_barriers`](../scripts/work_plugin.py) did not reject tasks that
belonged to a later phase. `next_tasks` dispatched any
pending/retry task instead of limiting dispatch to the validated current stage.

**Required correction:** enforce phase-appropriate task and dependency invariants
both when loading saved state and immediately before dispatch. Never waive parser
preflight merely because a task name is configured.

### 2. High priority: duplicate JSON fields can silently discard findings

**Case:** `candidate/duplicate_findings_key`.

A response containing two `findings` keys is accepted; the second empty array
silently replaces the first array. A follow-up reproduction used a complete,
schema-valid parser finding in the first array and confirmed the same failure.
The loss happens before validation/normalization, not in the lossless normalizer.

Before the fix, [`accept`](../scripts/work_plugin.py) used the default `json.loads` behavior,
which keeps only the last value for a duplicate key. The already-collapsed object
then passes the schema as a no-findings review.

**Required correction:** reject duplicate keys during JSON decoding and retry the
same role. Do not choose which duplicate payload to retain or silently drop evidence.

### 3. Medium priority: malformed responses can strand an inflight attempt

**Cases:** `candidate/integer_conversion_limit` and
`candidate/unpaired_unicode_surrogate`.

- A JSON integer with 5,000 digits raises `ValueError` during decoding.
- An escaped unpaired Unicode surrogate in a schema-valid summary raises
  `UnicodeEncodeError` while writing the accepted output.

Both return a generic CLI error but leave the task `inflight`. A subsequent `next`
does not dispatch a retry, although no child is still doing useful work. Other bad
responses—truncation, invalid UTF-8, fences, arrays and null—did retry correctly.

The original acceptance error boundary at [`accept`](../scripts/work_plugin.py) did not
cover these decoding/serialization failures. The outer CLI exception handler could not
repair the task transition.

**Required correction:** treat these as invalid candidates, preserve the response,
record the failed attempt and apply the existing bounded retry policy. Validate
encoding before promoting an output; do not delete findings to make serialization pass.

### 4. Medium priority: malformed checkpoint structure exposes raw tracebacks

**Cases:** `checkpoint/top_level_null`, `checkpoint/top_level_array`,
`checkpoint/tasks_null` and `checkpoint/task_not_object`.

These malformed JSON shapes trigger `AttributeError` instead of the promised
structured, actionable error. They do not produce a completed report, but the
failure is not suitable for the nontechnical user flow.

The original [`ReviewRun.__init__`](../scripts/work_plugin.py) assumed an object before calling
`.get`/`.items`, and the outer CLI handler did not catch `AttributeError`.

**Required correction:** validate the saved-state shape and required field types
before accessing them. Return a checkpoint-invalid error without changing saved work.

## Reproduce

Use the prepared environment; no installs, API keys or model calls are needed:

```powershell
.venv/Scripts/python.exe scripts/stress_work_plugin.py --output output/stress-next --pages 120
```

The output directory must be new. Exit code 1 indicates a failed stress assertion;
the fixed runtime should return 0. Each scenario is recorded in an append-only progress file, followed by
`results.json` and `report.md`. This is opt-in, not an intentionally failing addition
to the default unit-test suite.

Rerun a single originally failing scenario quickly:

```powershell
.venv/Scripts/python.exe scripts/stress_work_plugin.py --output output/stress-duplicate-next --only candidate/duplicate_findings_key
```

Actual full-run artifacts: [machine-readable results](../output/stress-20260907-02/results.json)
and [per-scenario report](../output/stress-20260907-02/report.md).
The valid-finding duplicate-key confirmation is in
[its separate result](../output/stress-20260907-duplicate-valid/results.json).
Generated artifacts are ignored by Git; this document and the harness are shareable.

Windows sandbox temporary-directory permissions required an unsandboxed local test
run. Dropbox also briefly locked the first progress report; the harness was changed
to append-only progress files and rerun completely. That first interrupted harness
run is not counted above. The runtime was not altered to hide any failed test.

## Fix implementation

The follow-up changes are confined to the Work coordinator, its generated bundle,
regression tests and release documentation. The CLI orchestration, reviewer roster,
specialist prompts, schemas, conservative routing, parser and lossless synthesis
logic are unchanged.

- **Stage barriers:** checkpoint loading and dispatch require exactly the task roster
  appropriate to the current phase. Prerequisite tasks must be accepted, the active
  roster must come from validated selection, and candidates must belong to their
  recorded task and attempt. Future-stage tasks cannot be injected into preflight.
- **Strict JSON:** duplicate object keys are rejected at every nesting level before
  schema validation. Decoded JSON must serialize as UTF-8 with finite numbers;
  escaped unpaired surrogates and unusably large/deep values become invalid attempts.
  No ambiguous payload is silently reduced or repaired.
- **Bounded recovery:** malformed candidates are preserved byte-for-byte, not promoted
  to canonical outputs, and receive the existing retry/exhaustion handling. Encoding
  is checked before opening the temporary output file. Valid saved responses still
  recover after interrupted acceptance without another model attempt.
- **Checkpoint errors:** structural types, task history, roster and artifact-map
  shapes are checked before their fields are used. Invalid checkpoint structures
  return an actionable `checkpoint_invalid` response without altering saved work.

Regression coverage includes the eight original failures, nested/router duplicate
keys, additional malformed checkpoint shapes, later-phase task injection, valid
Unicode preservation and Lite retry exhaustion. The opt-in stress harness and its
assertions have not been weakened.

Keep using one coordinator parent with sequential state-changing calls; support for
multiple stale parent writers was not added. Existing checkpoints remain bound to
their original runtime manifest. Do not hand-edit their hashes to upgrade a run;
keep the original bundle for those runs, or start a fresh review with the fixed bundle.

## Post-fix verification

The unchanged stress harness completed with exit code **0**:

```powershell
.venv/Scripts/python.exe -m unittest tests.test_reviewer_config
.venv/Scripts/python.exe -m unittest tests.test_work_plugin
.venv/Scripts/python.exe scripts/stress_work_plugin.py --output output/stress-20260907-fixed --pages 120
```

| Check | Post-fix result |
| --- | --- |
| Regression suite | 150 passed: 115 existing pipeline tests + 35 plugin tests |
| Supported stress scenarios | 34/34 passed; all eight original failures now reject or retry safely |
| Randomized Full/Lite workflows | 6/6 passed; all 19 reviewers retained; 144 simulated stage attempts |
| Malicious archive layouts | 7/7 safely rejected |
| 120-page PDF | Passed; preprocessing 24.608 seconds; all page images retained; OCR recommended only for pages 40, 80 and 120 |
| Integrity checks on large input | 2.958, 2.984 and 3.049 seconds; source unchanged; checkpoint restore passed |
| Oversized editor evidence | 1,100,048 characters preserved exactly; safe pause without truncation |
| Interrupted acceptance | Saved valid candidate recovered without an extra model attempt |
| Packaging/hygiene | Plugin and skill validators, bundle drift, ZIP integrity, shareable-file, sensitive-name and whitespace checks passed |

There are 35 records in the raw results: 34 supported scenarios plus the unchanged
out-of-contract multiple-parent diagnostic. That diagnostic still observes duplicate
reservations with two stale writers and is **not** a claim of multi-writer support.
The parsed artifacts were 9,512,759 bytes and the new large-PDF checkpoint was
6,295,785 bytes. Measurements are local synthetic observations, not hosted guarantees.

Artifacts: [fixed-run results](../output/stress-20260907-fixed/results.json),
[per-scenario report](../output/stress-20260907-fixed/report.md), and
[corrected plugin ZIP](../output/economics-paper-reviewer-0.1.0-stress-fixed.zip).
The ZIP SHA-256 is
`8820b6a937f2ae408b4a5e50f99dd31ae20f16b228c6c30353cdab005ceb91e2`.
Comparison with the preserved original ZIP confirmed that only
`runtime/scripts/work_plugin.py` and `runtime/bundle_manifest.json` changed.
No installed settings, marketplace entries or public submissions were changed.

## What this does not establish

No real paper was uploaded, no model reviewers or editor were invoked, and no hosted
Work installation was tested. This does not establish scientific accuracy, complete
body coverage, web-reference correctness, prompt-injection resistance in live agents,
included-usage sufficiency or cross-platform deployment compatibility. These tests
exercise deterministic processing, state management and scripted responses.
