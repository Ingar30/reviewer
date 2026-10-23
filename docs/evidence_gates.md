# Completion, evidence and editorial contracts

The wrapper still uses the configured backend, reviewer roster and model defaults.
This contract changes acceptance, not which allegations are presumed correct.

## Completion and recovery

Quotation failures identify the reviewer, finding, source object, field and cited
artifact. Intact registered images on the same page are offered as inspection
candidates, not as automatic verification. In particular, attached footnote digits
cannot safely be distinguished from exponents, subscripts or other meaningful
text by stripping characters. Inspect the retained image; if it establishes the
quotation, use the existing `visual` correspondence and an explicit verification
note identifying that image and the observed boundary. Otherwise retain
`unresolved`/`cannot_verify`. Visual correspondence remains an asserted inspection,
not a deterministic text match or independent human validation. Preserve rejected
outputs and source bytes; offline recovery creates a separately labelled artifact.

New reviewer outputs require a version-1 `completion` record and a `coverage`
ledger. Process success and JSON validity are prerequisites, not audit completion.
`complete` and `not_applicable` can be accepted; partial/failed work stays diagnostic.
A finished audit with an evidence limitation can use `cannot_verify`, with the
attempt and limitation recorded. Unattempted required work cannot use that label
to bypass the gate. An absent remit produces no manufactured manuscript defect.
An added source-linked applicability check may have no claim text when its
status is `not_applicable`; it still needs an attempted check and an explicit
reason. Other added claims require claim text.

The fresh model-facing schema requests a nonempty reason for every coverage row
and only typed numerical checks. Historical exhaustive rows with null reasons
remain readable without invented text; sampled checks and limitations still need
actual reasons. Preflight cannot authorize substantive work when its overall
`assigned_remit` or run status is `cannot_verify`: a completed inspection is not
evidence usability. A local unreadable display can remain a stated limitation
when trustworthy fallbacks or an explicit limited scope support the rest.

CLI runs permit one extra output-repair call per paper by default. Set
`--max-repair-calls 0` to disable, or choose an explicit total cap. Each stage may
be repaired at most once, including across resume/editor refresh. Rejected output,
the exact errors and the repair prompt are retained under `work/<paper>/repairs/`.
The model must supply corrections or missing work; all acceptance checks run
again. Reservation precedes dispatch and failures consume the allowance. Transport,
authentication and quota failures do not trigger automatic retries or provider
fallback. The native host keeps its existing host-managed attempt protocol.

The same acceptance policy is used by preflight, CLI validation, normalization,
benchmark execution, checkpoint reuse, editor refresh and the native adapter.
Selective-resume checkpoints use format 2 and acceptance-policy version 1.
Source/runtime/input hashes and accepted-output hashes must match. Editorial
decisions, evidence/coverage ledgers and the rendering receipt are bound to the
completed report. A preparation-only editor refresh invalidates the old completion
receipt while preserving the old synthesis in its attempt log directory.

Legacy outputs remain inspectable with:

```sh
python scripts/validate_review_json.py --schema schemas/reviewer_output.schema.json \
  --input work/paper/reviews/crossref_auditor.json --diagnostic
```

Diagnostic validation does **not** grant completion. Retain old manuscripts,
reviews and their original runtime. Do not fill in completion records or alter
checkpoint hashes to migrate them. New reviews use new paper IDs/workspaces.
Current editor-only refresh needs current receipts and unchanged inputs/runtime;
it is not a way to approve old evidence under newly edited prompts or validators.

## New derived synthesis from completed evidence (CLI)

Keep the completed parent workspace and its original runtime intact. From a new
runtime with compatible upstream resources, create a **fresh child workspace**:

```sh
python scripts/derive_report.py --parent-workspace /path/to/completed-parent \
  --paper-id paper --output-workspace /path/to/new-child
# Installed launcher equivalent (no parent workspace upgrade):
economics-paper-reviewer --derive-from /path/to/completed-parent \
  --paper-id paper --workspace /path/to/new-child
```

This explicitly runs only the editor, using the parent's accepted model/effort
unless overridden with `--model` / `--reasoning-effort`. It preserves the provider;
there is no automatic fallback. `--max-repair-calls` has the usual default of one
validation repair for this new synthesis. Failed calls/results stay in the child;
an existing destination is never overwritten or retried silently.

The helper verifies the parent's complete checkpoint, preflight receipt, source,
parsed artifacts, selection, prompts, accepted reviews and editorial products. It
then revalidates the copied evidence and uses the existing editor-input builder,
editor runner, renderer and final checks. Only explicitly downstream resources
(editor prompt/schema, synthesis/input/rendering helpers and optional verification)
may differ. Reviewer/routing prompts, configuration, evidence/acceptance rules and
unknown runtime changes block reuse. Retain the accepted upstream runtime with
the intended downstream changes, or rerun affected upstream work; there is no
blanket force/ignore-hashes flag. Different checkout/package file layouts may also
need a compatible runtime. Legacy records are not upgraded.

A recorded source PDF may remain outside the parent workspace, including an
original absolute path retained in preprocessing receipts. That exact file and
any local manuscript copy must still match the accepted manuscript hash. The
child receives its own verified `inputs/source.pdf`; original receipts are not
rewritten. Parent inputs (including external manuscript references) and sealed
child inputs are rechecked after editor execution; a mismatch leaves the child
incomplete. Other nonlocal checkpoint inputs are not supported.

The same paper and finding IDs are preserved in a separate workspace. Original
receipts/report are copied under `work/<paper>/parent_receipts/`; `derivation.json`
records parent hashes, accepted upstream settings, downstream changes, new inputs
and the new validated report. It is **not** a new whole-paper review or an exact
resume, and does not fabricate a child `resume_checkpoint.json`. Another synthesis
should refer to the original accepted parent in a fresh destination. The native
host's continuation protocol is unchanged; this is a CLI-only interface.

## Source and numerical evidence

Preprocessing additionally writes `parsed/source_registry.json`. IDs are bound to
the PDF hash, artifact bytes and locator. Entries describe retained text spans,
CSV cells and image regions. Cross-reference equation locations are assignment
candidates, not a claim that every formula has been extracted correctly.

Findings link registered objects. Conservative quote matching tolerates whitespace
and discretionary soft-hyphen line wraps, not visible hyphens or changed signs, decimals, percentages,
inequalities or subscripts. Visual and unresolved correspondence require explicit
notes. No OCR, repaired source content or automatic URL retrieval is added.
Footnote-adjacent extraction such as `21Our` is not repaired by stripping digits:
inspect the retained image and use explicit visual correspondence, or unresolved
if it cannot be checked. Null text quotations remain invalid.
`editor/evidence_checks.json` separates location/correspondence from relevance and
criticism support; the latter remain assessor judgments. External retrieval claims
are labelled as reviewer assertions, not independent offline verification.

Typed numerical checks distinguish arithmetic, cross-source comparisons and
underdetermined questions. `python scripts/numerical_checks.py` reads one bounded
JSON request on stdin. Decimal interval arithmetic supports sum, difference, mean,
product, ratio, relative percent change and percentage-point differences. It does
not execute submitted code. Unsupported operations, incompatible context metadata,
nonfinite inputs or zero-containing divisor intervals remain unresolved.
Compatible published rounding intervals do not establish an arithmetic error.
The reported unit/scale, sample and denominator still require source assessment;
arithmetic cannot prove a common estimand or specification.
Both arithmetic and cross-source quantities are checked against their linked text
quotes. Standalone published polarity labels (`+`, `-`, `−`) can be compared
without inventing numerical codes. An indispensable unresolved input keeps the
conclusion conditional (`cannot_verify`); an unrelated unresolved citation does
not invalidate established quantities. Visual correspondence stays explicitly
assessor-checked, not a deterministic text match.

## Editorial ownership

The editor authors all substantive prose in version-1 `editor_decisions.json`.
The deterministic renderer validates blocks/dispositions and writes `report.md`
plus an exact traceability map. Each canonical finding is included, merged,
rejected, narrowed or appendix-only. Rejection needs an evidence-based reason;
merges retain evidence and qualifications and cannot cycle or terminate in a
rejected claim. Included treatment is actually rendered, not merely referenced.
Block introductions may be empty when valid finding treatments supply the content;
wholly empty blocks and headings-only required sections still fail. The renderer
does not insert filler prose.

Consequential findings require an explicitly identified semantic-fidelity judgment.
The default judgment is the editor's self-assessment, **not independent verification**.
Model output cannot claim a human/independent assessor; the execution context
determines that identity. Block prose and finding treatments share section-boundary
and table-header checks. Each table must be complete within one fragment.
For material omissions, the editor checks main text and appendix, acknowledges
any partial definition, and requests only the missing operational details.
Structural coverage, source matching and a faithful verdict do not guarantee truth.
The optional shadow pass and source-based human assessment address that remaining
uncertainty. Reviewer agreement remains in provenance but adds no ranking bonus.

The paired source-comparison instructions are provisional discovery guidance.
Limited matched development cases show both useful distinctions and missed or
lost qualifications; synthesis and structural checks do not establish a discovery
gain or uniformly improved review quality.

## Optional bounded shadow verification

This is off by default and does not change or score the main report. Preselect
at most five consequential canonical findings before viewing verifier results:

```sh
python scripts/verify_findings.py prepare \
  --bundle work/paper/editor/normalized_bundle.json --ids CANON-001 CANON-002 \
  --output work/paper/editor/shadow/packet.json
python scripts/verify_findings.py run --packet work/paper/editor/shadow/packet.json \
  --candidate work/paper/editor/shadow/candidate.json \
  --output work/paper/editor/shadow/verification.json
```

`run` explicitly consumes a model session using the completed run's backend/model/
effort; there is no fallback, silent retry or new general discovery reviewer.
Outcomes are `confirmed`, `narrowed`, `unsupported` or `unresolved`, with source
evidence and the strongest alternative interpretation. Failed verification never
confirms or removes a candidate. Original candidates and disagreements are retained.
`prepare` and `accept` are deterministic; native hosts use `work_plugin.py
shadow-prepare --workspace ... --ids ...` and `shadow-accept --workspace ...`, with
one native agent between them, never a nested CLI. A second pass needs a new run;
the adapter deliberately refuses to overwrite the frozen selection/results.

## Permissions and limits

Codex commands explicitly request `web_search="disabled"` for non-search roles
and read-only model-tool execution. The CLI's output-message writer publishes the
candidate. Claude retains its read-only tool allowlist. Source/runtime hashes are
checked before accepting outputs; the native adapter also seals stage inputs.

These are **degraded read-isolation modes**: read-only does not imply that absolute
paths to peer results, older runs or private files are inaccessible. A working
directory or an instruction to ignore peer findings is not a security boundary.
Connected tools and host policies may differ from shell permissions. Manifests
distinguish requested capabilities from unobserved effective enforcement. Native
hosts must enforce tool restrictions when available and disclose when they cannot.
Do not use sandbox/approval bypass flags. Search-disabled inference is still
cloud-backed; manuscript authorization remains necessary.

## Synthetic worked example and optional author feedback

Accepted narrow observation: a synthetic table reports `2 + 3 = 6`, with exact
inputs, matching units/sample and no rounding ambiguity. The computation yields
5. Request reconciliation; do not infer a particular coding mistake.

Rejected false positive: one group has mean output 20 and mean duration 2, while
the mean individual rate is 12. The ratio of means (10) does not refute the mean
of individual ratios (12). Preserve the original allegation and reject the
asserted correction unless source evidence establishes the same aggregation.

Optional local feedback can use this format in an ignored runtime directory:

```json
{
  "version": 1,
  "manuscript_sha256": "<exact PDF hash>",
  "finding_id": "CANON-001",
  "disposition": "disputed",
  "source_locations": ["PDF page 3, synthetic Table 1 note"],
  "reason": "The source explicitly defines a different aggregation.",
  "assessor": "author",
  "independent_validation": false
}
```

Feedback is evidence to assess, not automatic truth. No telemetry or feedback
upload is performed. Keep all manuscript-specific artifacts private.
