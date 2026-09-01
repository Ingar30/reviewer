# Reviewer Release Readiness Record

Date: 2026-09-01

Scope: local-versus-GitHub audit, GPT-5.6 model migration, deterministic PDF preprocessing, reviewer routing, normalization, editor transport, and report-quality controls. No GitHub mutation was performed.

This tracked record is intentionally safe to publish. It contains aggregate paper IDs and run metrics, not manuscript text, author identities, reviewer JSON, report excerpts, or issue-level details. Detailed adjudication remains in Git-ignored `work/` and `outputs/` artifacts.

## Executive decision

The local branch is a material improvement over the current GitHub state. Preserve it in a local commit after the frozen-snapshot acceptance run, but do not push it directly to `main`.

The recommended release configuration is:

- `gpt-5.6-sol` with `xhigh` reasoning for substantive reviewers and the editor.
- `gpt-5.6-sol` with `high` reasoning for parser-quality preflight.
- Static exhaustive reviewer selection by default: 4 mandatory review-stage agents plus all 14 optional specialists, for 18 substantive reviewers.
- Dynamic selection only as an explicit cost/latency tradeoff. It chooses 7 to 13 optional specialists, at most 4 from the narrow pilot group, for 11 to 17 substantive reviewers after the 4 mandatory agents.
- A mandatory, no-search source-consistency audit that reconciles central prose with displays, definitions, samples, coding sources, and appendices.
- Local deterministic PyMuPDF preprocessing with retained native text, coordinates, page images, crops, inventories, and explicit quality flags.
- No external parsing service, hosted OCR dependency, LLM-generated parser repair, or inferred replacement text.
- Precision-first deterministic normalization. Uncertain duplicates stay separate for the editor rather than risking the merger of different signs, values, columns, pages, or corrections.
- A lossless normalized editor bundle plus a compact provenance index. Raw reviewer JSON is validated but not duplicated in the model input. Oversized input is minified losslessly and then fails clearly rather than truncating evidence.
- One constructive editor that leads with narrow correctness and auditability issues, then discusses broader positioning and implications.

## Git and GitHub state

Remote: `https://github.com/Ingar30/reviewer.git`

Branch under review: `reasoning-effort-option`

State audited immediately before this release commit:

- This release commit is based on `dc72d5a Validate quality-first reviewer release`.
- The feature branch contains six local commits after the common base `6b529fb`.
- `origin/reasoning-effort-option` contains the first two of those commits; local HEAD is four commits ahead of that remote branch before the final commit.
- `origin/main` has one upstream-only documentation commit, `339513f Update README.md`, beyond the common base.
- No push, pull request, deployment, or other remote mutation occurred during this audit.

Local commits to retain:

| Commit | Decision | Main value |
| --- | --- | --- |
| `6f055db` | Keep | Adds explicit model and reasoning-effort overrides. |
| `66872ae` | Keep | Updates review defaults, routing, and editor behavior. |
| `e78d015` | Keep | Adds validation, provenance, manifests, concurrency, timeouts, and deterministic parser improvements; removes the parser-repair overlay. |
| `3124553` | Keep | Restricts glyph repair to verified source-positioned mappings. |
| `ff82ae3` | Keep | Conservatively composes verified spacing accents. |
| `dc72d5a` | Keep | Records the first quality-first release validation. |
| This release commit | Keep | Adds exhaustive defaults, source consistency, safe normalization, compact editor transport, parser hardening, controls, and updated documentation. |

The eventual GitHub update should use a feature-branch pull request. Reconcile `339513f` while preserving the final no-overlay behavior; do not restore obsolete parser-repair instructions.

## Local differences from GitHub

| Area | Current GitHub behavior | Final local behavior | Recommendation |
| --- | --- | --- | --- |
| Models | Older/default configuration before the full GPT-5.6 evaluation | Sol/xhigh quality-first default with supported effort overrides | Publish |
| Selection | Dynamic routing is the normal path | Static exhaustive is default; dynamic is explicit opt-in; both write provenance | Publish |
| Review roster | No mandatory source-consistency specialist | Adds a narrow mandatory prose-to-source crosswalk reviewer | Publish |
| Preprocessing | Earlier parser plus optional repair-overlay documentation | Deterministic local parser only; safer captions, references, figure/table separation, landscape crops, and glyph handling | Publish |
| Normalization | Broad fuzzy/source-overlap merging can hide distinct defects | Precision-first semantic merging with numeric, sign, direction, locator, page, reviewer, and group-conflict vetoes | Publish |
| Editor input | Normalized bundle plus a second full copy of reviewer JSON can exceed context limits | Lossless bundle with per-source details, reviewer summaries/notes, and provenance paths; no truncation | Publish |
| Orchestration | Less complete run metadata and recovery behavior | Hash-checked manifests, concurrency, timeouts, preflight resume, static provenance, and editor-only refresh | Publish |
| Editor tone | Broader referee framing can dominate | Narrow corrections first, broader development later, neutral author-oriented language | Publish |
| Parser repair | Optional LLM-generated overlay exists in upstream history/docs | Removed; reviewers use retained deterministic evidence or `cannot_verify` | Keep removed |

## Model decision

OpenAI's current [model guide](https://developers.openai.com/api/docs/guides/latest-model) identifies `gpt-5.6-sol` as the flagship model, `gpt-5.6-terra` as the intelligence/cost balance, and `gpt-5.6-luna` for high-volume efficiency. Supported GPT-5.6 reasoning values are `none`, `low`, `medium`, `high`, `xhigh`, and `max`.

Recommendations:

- Keep Sol/xhigh as the default. Review quality matters more here than a few additional minutes.
- Do not use GPT-5.5/high as the current default or primary benchmark.
- Keep Terra/high as an explicit lower-cost comparison option, not the quality-first default.
- Keep Sol/high as a measured alternative for routine comparison or editor-refresh experiments.
- Do not default to `max` until it beats xhigh on representative full-report evaluations.
- Keep preflight at high. Use selector medium only when dynamic mode is explicitly requested.

Editor-only benchmark on the same 419,638-byte paper9 evidence bundle:

| Model and effort | Seconds | Reported tokens | Result |
| --- | ---: | ---: | --- |
| Terra/high | 119 | 112,150 | Valid and concise, but less complete |
| Sol/high | 297 | 123,191 | Valid and detailed |
| Sol/xhigh | 386 | 125,629 | Best prioritization and synthesis |

Reported tokens are Codex run metrics, not billing guarantees.

## Reviewer selection and pilots

The final terminology is:

- Parser-quality preflight is mandatory and runs separately.
- Four review-stage agents are mandatory: cross-reference, source consistency, reference integrity, and grammar.
- Fourteen optional agents are full Sol/xhigh specialists, not lower-quality agents.
- Five optional roles are called pilots only because their scope is narrower: replication/data availability, institutional context, power/multiple testing, design/randomization, and economic magnitude.

Static mode is the quality-first default. It runs all 18 substantive agents, writes `selection/reviewer_selection.json` with `selection_mode: static`, and does not pay for a selector call.

Dynamic mode is available through `--reviewer-selection dynamic`. It enforces 7 to 13 selected optional agents and at most 4 pilots. The validator requires the model output to declare `selection_mode: dynamic`; a model cannot claim static mode to evade the caps.

Control evidence shows both effects:

- Static routing recovered non-overlapping specialist findings on several papers.
- Papers with unchanged or nearly unchanged rosters still improved, showing a separate model/prompt effect.
- Some valid old-only details remained even under static routing, showing irreducible run variation. Exhaustive selection reduces selection-driven misses but cannot make one stochastic pass a strict superset of every earlier pass.
- A second full LLM deduplication layer is not justified. Conservative deterministic grouping plus editor synthesis retained coverage with less risk.

## Aggregate report evidence

The current normalization counts below use the final precision-first rules. Counts are evidence-volume diagnostics, not quality scores.

| Paper | Mode | Wall time | Reported tokens | Raw to canonical | Old to new report words | Assessment |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| paper4 | Static | 69.8 min | 2.414m | 102 to 72 | 4,938 to 5,437 | Clearly better overall |
| paper5 | Static, same roster as old | 91.1 min | 3.319m | 106 to 86 | 4,715 to 6,914 | Better and more complete, but longer |
| paper7 | Dynamic | 65.5 min | 2.693m | 112 to 102 | 5,471 to 7,132 | Better overall, not a strict superset |
| paper8 | Dynamic | 47.6 min | 1.977m | 77 to 64 | 5,552 to 5,798 | Better overall, not a strict superset |
| paper9 | Dynamic, same roster | 45.6 min | 1.718m | 68 to 53 | 4,265 to 4,749 | Strong model/parser acceptance |
| paper13 | Static | 78.9 min | 2.818m | 107 to 90 | 4,159 to 6,798 | Substantially stronger |
| paper15 | Static | 95.0 min | 3.262m | 127 to 115 | 5,771 to 8,815 | Stronger; old editor input needed recovery |
| paper16 | Static | 66.3 min | 2.652m | 112 to 95 | 5,639 to 6,874 | Material improvement |
| paper18 | Static panel plus refreshed editor | 90.7 min panel; 315 s editor | 3.005m panel; 222,200 editor | 121 to 102 | 5,350 to 7,313 | Stronger and valid after transport fix |
| paper4 final frozen acceptance | Static default | 81.5 min | 2.794m | 145 to 97 | 4,938 to 6,622 | Strongest paper4 report; full default path valid |

The expanded control set intentionally includes paper13 and excludes paper2. The tracked document does not publish manuscript identities or issue-level content.

Across the controls, the new reports are consistently stronger in prioritization, actionability, traceability, tone, and number of consequential checks. They are not superior on every individual detail. The release claim should therefore be "materially better and safer overall," not "guaranteed to include every finding from every previous run."

## Source-consistency pilot

The new mandatory reviewer was tested separately with Sol/xhigh and no web search:

| Paper | Seconds | Tokens | Findings | Marginal assessment |
| --- | ---: | ---: | ---: | --- |
| paper7 | 1,405 | 275,855 | 14 | Added 2-3 useful source/coding crosswalks; one over-broad cannot-verify item informed prompt tightening |
| paper8 | 1,269 | 243,208 | 9 | Added five valid narrow checks, including one old-only recovery; no clear false positive |
| paper18 | 853 | 198,069 | 11 | Added two useful display-level checks; most others correctly duplicated existing evidence |

Decision: retain it as mandatory for a quality-maximizing workflow. Its marginal token cost was about ten percent on paper7, while concurrent execution should absorb much of the wall-clock cost. The final prompt is narrow and precision-focused: it requires a claim ledger, repeated-code/coding-source crosswalks, explicit sample-denominator reconciliation, and a terminal display-by-display pass over captions, axes, panels, labels, samples, and denominators. It forbids inferred labels, values, signs, formulas, or denominators.

It supplements rather than replaces the numerical, sample, model, robustness, or claim-evidence specialists.

## PDF preprocessing research

Non-negotiable criterion: preprocessing must not invent content or silently change signs, decimals, percentages, parentheses, equations, labels, or names.

| Option | Evidence and friction | Decision |
| --- | --- | --- |
| [Firecrawl AnyDoc](https://github.com/firecrawl/anydoc) | Very fast and light locally, but the test dropped a minus sign and important equation structure. Hosted OCR adds an external service/API dependency. | Reject as canonical parser |
| [Docling](https://github.com/docling-project/docling) | Preserved more structure than AnyDoc on difficult pages, but adds a large dependency/model stack and platform variance without a demonstrated end-to-end report gain. | Internal benchmark only |
| Poppler `pdftotext` | Useful source-fidelity diagnostic, but weaker reading order and no project artifact/inventory contract. Requires a system install. | Diagnostic only |
| [Marker](https://github.com/datalab-to/marker) | Heavy inference dependencies/model weights and no demonstrated benefit large enough for normal installation. | Do not add |
| [PyMuPDF4LLM](https://github.com/pymupdf/pymupdf4llm) | Closest lightweight future ablation, but duplicates the MuPDF base and still needs custom provenance, page-label, crop, and glyph safeguards. | Reconsider only on a fixed benchmark |

Final decision: improve the existing PyMuPDF pipeline and keep installation local and simple.

Implemented deterministic protections include:

- Preserve raw native text, normalized page text, coordinates, words, blocks, page images, source hash, and original page labels.
- Repair glyphs only through verified font/code mappings at source-aligned positions.
- Preserve unknown glyphs and flag them instead of guessing.
- Detect and flag difficult column, landscape, sparse, image-heavy, and unresolved-math pages.
- Retain titleless figure labels only when a same-page source note provides a visual anchor; never invent a title.
- Recover label-only table captions only when a bold label and following title have matching source block, font, alignment, and spacing metadata.
- Stop caption continuations at both `Note:` and `Notes:` and use conservative same-block/font/position rules.
- Use full-width crops for landscape exhibits.
- Suppress bounded and unlocatable native-table candidates on verified figure pages, while retaining caption-anchored real tables.
- Join reference fragments split by artificial column thresholds only when block, baseline, and horizontal-gap checks agree.
- Filter repeated page headers, reject narrow bibliography-like footnotes, and stop references at appendix, figure, or table boundaries.
- Keep OCR as a recommendation flag only. The default does not install or run an OCR or learned-layout engine.

Final complete parser controls:

| Paper | References | Figures | Tables | Key result |
| --- | ---: | ---: | ---: | --- |
| paper4 | 29 | 0 | 1 | Exact bibliography boundary; verified label-only Table 1 recovered |
| paper13 | 63 | 17 | 21 | Exact references and complete landscape-width crops |
| paper15 | 83 | 30 | 11 | Titleless appendix figure recovered without invented text |
| paper16 | 26 | 11 | 4 | Missing figures recovered; zero uncaptioned plot-as-table artifacts |
| paper18 | 47 | 22 | 15 | False table candidates reduced from 53 to the 15 captioned real tables |

All full parser reruns completed successfully. The changes are dependency-free and do not generate replacement content.

## Normalization and editor transport

The old normalization strategy could merge distinct concerns because they shared a quote, source path, generic wording, or one transitive anchor. The final normalizer:

- never merges two findings from the same reviewer;
- requires compatible issue class and known page;
- treats exact quote/path overlap as evidence, not a merge decision;
- checks semantic similarity against every source anchor;
- vetoes incompatible signs, directions, values, numeric sequences, table/figure/equation/column/panel/question locators, and conflicting group members;
- recognizes appendix locators with or without a period, such as `S8` and `S.8`;
- ignores digits embedded in identifiers such as `2SLS` and formula constants that are not claim values;
- preserves each source finding's summary, claim, evidence summary, severity, assessment, confidence, cannot-verify reason, and location;
- produces deterministic groups independent of reviewer-config order.

Final control counts are paper4 72 in the earlier static control and 97 in the fresh expanded acceptance, paper5 86, paper13 90, paper15 115, and paper18 102 canonical findings. Remaining under-merges are intentional and safe for editor consolidation.

The editor-input builder validates every raw reviewer JSON, but embeds only:

1. the editor prompt and deterministic brief;
2. the lossless normalized bundle;
3. a compact validated reviewer provenance table.

It retains reviewer run summaries and non-process notes. A required-coverage table instructs the editor to address every high/medium manuscript, cannot-verify, reference-integrity, and material parser finding in the body. Inputs above 1,000,000 UTF-8 bytes are minified losslessly; inputs still above the budget fail instead of truncating.

This recovered the paper18 editor failure: the old 1,078,016-byte input exceeded the Codex limit, while the final source-inclusive input remains below the local safety budget and validates.

## Changes recommended for the GitHub pull request

Commit and publish the tracked project machinery for:

- GPT-5.6 Sol defaults and supported effort overrides;
- static exhaustive default and dynamic opt-in validation;
- mandatory source-consistency review and targeted specialist prompt passes;
- deterministic parser improvements and regression tests;
- precision-first normalization and lossless editor transport;
- static provenance, run manifests, timeouts, concurrency, resume safeguards, and editor refresh;
- constructive narrow-first editor behavior and complete traceability;
- setup, security, privacy, contribution, extension, and workflow documentation;
- removal of the LLM parser-repair overlay and obsolete guidance;
- this privacy-safe release record.

Do not commit or publish:

- source PDFs;
- parsed pages, images, crops, prompts, logs, reviewer JSON, editor bundles, or generated reports;
- temporary environments, downloaded benchmark packages/models, or benchmark caches;
- credentials, environment-variable values, signed-in Codex state, or manuscript-derived search logs;
- manuscript author identities or issue-level private evaluation notes.

## Verification record

Completed on the release candidate:

- Nine-paper aggregate report/control matrix, with paper13 included and paper2 omitted.
- Three paid source-consistency pilots, all schema/semantic/provenance valid.
- Final deterministic parser reruns on papers 4, 13, 15, 16, and 18.
- Exact reference counts and zero uncaptioned table artifacts on the affected figure-heavy controls.
- Precision-first normalizer re-simulation on five static controls.
- Paper18 Sol/xhigh editor recovery: 315 seconds, 222,200 tokens, valid 7,313-word report.
- Source-inclusive editor input checks near the 1 MB budget.
- Fresh default paper4 acceptance: parser preflight, all 18 substantive agents, 19 reviewer-output validations, normalization, editor-input assembly, Sol/xhigh editor, and final report validation.
- The wrapper's first final-check invocation exposed a deterministic URL-regex false positive on a DOI with balanced parentheses. A regression-tested checker fix accepted the unchanged report; no model stage needed to be rerun.
- Final parser-only regression after the acceptance recovered the paper4 label-only table and preserved the exact validated counts on papers 13, 15, 16, and 18.
- 91 focused unit tests.
- Python compilation checks for modified scripts.
- `git diff --check`.

The final report contains 6,622 words and passed schema, traceability, external-source, required-section, and smoke checks. Its principal gains over both prior paper4 reports are fuller source/display reconciliation, explicit static-roster disclosure, clearer narrow-first prioritization, and more complete reference, parser, and copyediting appendices. The reports are still stochastic outputs: the acceptance supports a stronger-overall claim, not guaranteed recovery of every detail from every prior run.

## Remaining GitHub steps

After the final local commit, but before any GitHub update:

1. Fetch read-only and confirm `origin/main` has not moved beyond the inspected upstream commit.
2. Rebase or merge the upstream README-only change while preserving the no-overlay workflow.
3. Rerun unit, environment, shareable-tree, sensitive-name, compilation, and diff checks on the reconciled tree.
4. Inspect ignored acceptance artifacts locally.
5. Push the feature branch and open a pull request; do not force-push or update `main` directly.
6. Require CI to pass and inspect the rendered documentation before merge.

## Final assessment

The local workflow is meaningfully better than the current GitHub implementation. The strongest changes are Sol/xhigh, exhaustive static review, a narrow source-consistency pass, deterministic source-faithful parsing, conservative normalization, lossless editor transport, and author-oriented synthesis.

The honest release claim is not universal dominance. It is a materially more comprehensive, accurate, inspectable, and failure-resistant review, with residual model variation made visible through provenance and conservative evidence handling.
