# Reviewer Release Readiness Record

Date: 2026-09-01; workflow decision updated 2026-09-02

Scope: local-versus-GitHub audit, GPT-5.6 model migration, deterministic PDF preprocessing, reviewer routing, normalization, editor transport, and report-quality controls.

This tracked record is intentionally safe to publish. It contains aggregate paper IDs and run metrics, not manuscript text, author identities, reviewer JSON, report excerpts, or issue-level details. Detailed adjudication remains in Git-ignored `work/` and `outputs/` artifacts.

## Executive decision

The local branch is a material improvement over the current GitHub state. The empirical path has fresh end-to-end acceptance on paper21. The formal-theory specialist has focused contract and routing tests; a representative formal-theory full-paper run remains useful follow-up validation when a suitable non-confidential paper is available.

The recommended release configuration is:

- `gpt-5.6-sol` with `xhigh` reasoning for substantive reviewers and the editor.
- `gpt-5.6-sol` with `high` reasoning for parser-quality preflight.
- One conservative applicability workflow: 8 universal review-stage auditors plus every plausibly relevant conditional specialist.
- Eleven conditional specialists have no call-count cap. Only high-confidence single-type classifications may skip a role whose entire remit is clearly absent; mixed, unknown, or lower-confidence classifications run the full 19-reviewer substantive roster.
- A dedicated theory-logic specialist for propositions, proofs, assumptions, equilibria, domains, and comparative statics, distinct from the universal model/equation consistency audit.
- A mandatory, no-search source-consistency audit that reconciles central prose with displays, definitions, samples, coding sources, and appendices.
- Local deterministic PyMuPDF preprocessing with retained native text, coordinates, page images, crops, inventories, and explicit quality flags.
- No external parsing service, hosted OCR dependency, LLM-generated parser repair, or inferred replacement text.
- Precision-first deterministic normalization. Uncertain duplicates stay separate for the editor rather than risking the merger of different signs, values, columns, pages, or corrections.
- A lossless normalized editor bundle plus a compact provenance index. Raw reviewer JSON is validated but not duplicated in the model input. Oversized input is minified losslessly and then fails clearly rather than truncating evidence.
- One constructive editor that leads with narrow correctness and auditability issues, then discusses broader positioning and implications.

## Git and GitHub audit snapshot

Remote: `https://github.com/Ingar30/reviewer.git`

Branch under review: `reasoning-effort-option`

State recorded before the final release-candidate commit:

- Local HEAD is `f11482f Make reviewer quality-first and exhaustive`.
- The feature branch contains seven local commits after the common base `6b529fb`.
- `origin/reasoning-effort-option` contains the first two of those commits; local HEAD is five commits ahead of that remote branch.
- `origin/main` has one upstream-only documentation commit, `339513f Update README.md`, beyond the common base.
- The single-workflow applicability router and theory specialist were working-tree changes at this point in the audit.

Local commits to retain:

| Commit | Decision | Main value |
| --- | --- | --- |
| `6f055db` | Keep | Adds explicit model and reasoning-effort overrides. |
| `66872ae` | Keep | Updates review defaults, routing, and editor behavior. |
| `e78d015` | Keep | Adds validation, provenance, manifests, concurrency, timeouts, and deterministic parser improvements; removes the parser-repair overlay. |
| `3124553` | Keep | Restricts glyph repair to verified source-positioned mappings. |
| `ff82ae3` | Keep | Conservatively composes verified spacing accents. |
| `dc72d5a` | Keep | Records the first quality-first release validation. |
| `f11482f` | Keep | Adds conservative applicability, source consistency, safe normalization, compact editor transport, parser hardening, controls, and updated documentation. |
| Final working-tree update | Keep after checks | Replaces public routing modes with conservative applicability and adds formal theory review. |

The GitHub update should preserve the final no-overlay behavior and not restore obsolete parser-repair instructions. Review of the open contributor PRs accepted the cross-platform README commands and local `.codex` runtime ignores. The reasoning-effort plumbing remains useful for controlled tests, while the suggested parser-repair default was superseded by removing that experimental layer. The current Dependabot action upgrades are also suitable for the hosted `ubuntu-latest` workflow.

## Local differences from GitHub

| Area | Current GitHub behavior | Final local behavior | Recommendation |
| --- | --- | --- | --- |
| Models | Older/default configuration before the full GPT-5.6 evaluation | Sol/xhigh quality-first default; overrides retained for controlled tests | Publish |
| Selection | Dynamic routing is the normal path | One conservative applicability workflow with deterministic full-roster fallback on uncertainty | Publish after fresh acceptance |
| Review roster | No mandatory source-consistency or formal-theory specialist | Adds a universal prose-to-source crosswalk and an applicability-routed theory-logic reviewer | Publish after fresh acceptance |
| Preprocessing | Earlier parser plus optional repair-overlay documentation | Deterministic local parser only; safer captions, references, figure/table separation, landscape crops, and glyph handling | Publish |
| Normalization | Broad fuzzy/source-overlap merging can hide distinct defects | Precision-first semantic merging with numeric, sign, direction, locator, page, reviewer, and group-conflict vetoes | Publish |
| Editor input | Normalized bundle plus a second full copy of reviewer JSON can exceed context limits | Lossless bundle with per-source details, reviewer summaries/notes, and provenance paths; no truncation | Publish |
| Orchestration | Less complete run metadata and recovery behavior | Hash-checked manifests, concurrency, timeouts, preflight resume, applicability provenance, and editor-only refresh | Publish |
| Editor tone | Broader referee framing can dominate | Narrow corrections first, broader development later, neutral author-oriented language | Publish |
| Parser repair | Optional LLM-generated overlay exists in upstream history/docs | Removed; reviewers use retained deterministic evidence or `cannot_verify` | Keep removed |

## Model decision

OpenAI's current [model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol) identifies `gpt-5.6-sol` as the flagship model for complex professional work and supports `none`, `low`, `medium`, `high`, `xhigh`, and `max` reasoning.

Recommendations:

- Keep Sol/xhigh as the default. Review quality matters more here than a few additional minutes.
- Do not use GPT-5.5/high as the current default or primary benchmark.
- Do not offer or document a lower-cost or lower-reasoning review configuration. The tested alternatives were not quality-equivalent.
- Retain model and reasoning overrides only for controlled evaluation and debugging.
- Do not default to `max` until it beats xhigh on representative full-report evaluations.
- Keep preflight and applicability routing at high.

Editor-only benchmark on the same 419,638-byte paper9 evidence bundle:

| Model and effort | Seconds | Reported tokens | Result |
| --- | ---: | ---: | --- |
| Terra/high | 119 | 112,150 | Valid and concise, but less complete |
| Sol/high | 297 | 123,191 | Valid and detailed |
| Sol/xhigh | 386 | 125,629 | Best prioritization and synthesis |

Reported tokens are Codex run metrics, not billing guarantees.

The editor-only result understated the quality loss from changing the model for the complete workflow. A controlled 116-page empirical benchmark subsequently held the PDF, deterministic parsed artifacts, high-confidence applicability classification, 18-reviewer substantive roster, normalization, and C+ editor instructions constant. All cheaper configurations ran parser preflight, routing, all 18 selected reviewers, normalization, and the editor, for 21 model calls each.

| Configuration | Measurement | Minutes | Reported tokens | Raw to canonical | Non-copyedit canonical | C+ report words | Preselected core corrections recovered |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sol/xhigh | Measured full run plus replacement C+ editor estimate | about 91 | 4,199,336 | 142 to 131 | 89 | 9,980 | 5 of 5 |
| Terra/high | Measured end to end | 28.6 | 1,872,505 | 58 to 53 | 49 | 3,713 | 1 of 5 |
| Terra/xhigh | Measured end to end | 40.5 | 2,356,465 | 81 to 77 | 50 | 5,760 | 1 of 5 |
| Luna/xhigh | Measured end to end | 78.9 | 4,639,687 | 115 to 102 | 87 | 7,758 | 3 of 5; 2 prioritized |

The Sol estimate replaces its original 215,127-token editor call with the measured 445,923-token C+ refresh; it is not a single timed end-to-end run. The three lower-cost rows are direct wrapper measurements. Finding counts are diagnostics, not quality scores. Terra/high included one material source-faithfulness false positive. Terra/xhigh missed four of the five preselected consequential corrections and recovered only 50 of Sol's 89 non-copyedit canonical findings. Luna/xhigh came closer on breadth, but it used more reported tokens and wall time than the original Sol run, promoted a judgment-dependent framing concern over narrower corrections, fragmented related concerns, and still missed the clearest accounting check. None is quality-equivalent to Sol/xhigh on this paper, so none is offered as a supported configuration.

## Reviewer applicability and theory coverage

The active design has one workflow:

- Parser-quality preflight is mandatory and runs separately.
- Eight universal review-stage agents always run: cross-reference, source consistency, claim/evidence, literature, reference integrity, grammar, abstract/conclusion consistency, and model/equation consistency.
- Eleven conditional roles are full Sol/xhigh specialists, not reduced-quality agents: numerical, identification, robustness, sample construction, limitations/external validity, theory logic, replication/data availability, institutional context, power/multiple testing, design/randomization, and economic magnitude.
- The applicability router runs on Sol/high. It has no reviewer-count or pilot budget and may skip a specialist only when a high-confidence single-type classification gives positive evidence that the role's entire remit is absent.
- The wrapper deterministically selects every conditional specialist for `mixed`, `unknown`, `medium`-confidence, or `low`-confidence classifications. It also restores `theory_logic_auditor` if a high-confidence theory classification omits it.
- Every reviewer first checks applicability. A genuinely inapplicable role returns `run_status: ok` with no findings; absence of an empirical design, formal model, dataset, experiment, or claim type is not a manuscript defect.

The theory specialist checks whether propositions and economic conclusions follow from assumptions, including proof gaps, hidden conditions, existence and uniqueness, optimization domains, comparative statics, and formal-to-prose validity. The universal model/equation auditor remains separate and checks notation, definitions, signs, estimands, and text-equation consistency. This avoids asking an empirical specialist to invent work on a pure theory paper while adding the formal-validity coverage the prior roster lacked.

Control evidence shows both effects:

- Historical exhaustive routing recovered non-overlapping specialist findings on several papers.
- Papers with unchanged or nearly unchanged rosters still improved, showing a separate model/prompt effect.
- Some valid old-only details remained even under exhaustive routing, showing irreducible run variation. Broader selection reduces selection-driven misses but cannot make one stochastic pass a strict superset of every earlier pass.
- A second full LLM deduplication layer is not justified. Conservative deterministic grouping plus editor synthesis retained coverage with less risk.

The current applicability change has unit coverage and completed a paid empirical end-to-end acceptance on paper21. The router classified the paper as empirical causal with high confidence, selected all ten empirically applicable conditional specialists, and skipped only the theory-logic reviewer because the manuscript contains no formal model, proposition, proof, optimization problem, or equilibrium. All 18 substantive outputs validated. The run took 4,601 seconds, reported 3,968,540 tokens across preflight, routing, review, and editing, conservatively normalized 142 raw findings to 131 canonical findings, and produced a valid 7,790-word report. No earlier paper21 report existed; independent acceptance therefore checked the report against the source artifacts, reviewer evidence, recomputed quantities, and primary external sources rather than claiming an old-to-new improvement.

When a suitable non-confidential formal theory paper is available, run the same full-workflow acceptance to confirm that the new specialist adds concrete, source-grounded validity checks and that the editor handles those findings without asking empirical specialists to invent inapplicable concerns.

## Public model policy

The public workflow has one supported quality configuration: Sol/xhigh for substantive review and editing, with Sol/high for parser preflight and applicability routing. Model and reasoning flags remain available for controlled development tests, but the user guide does not present inferior configurations as review options.

## Aggregate report evidence

The historical control counts below use the accepted precision-first rules. Their Static/Dynamic labels describe predecessor runs, not selectable modes in the current wrapper. Counts are evidence-volume diagnostics, not quality scores.

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
| paper4 final frozen acceptance | Historical exhaustive default | 81.5 min | 2.794m | 145 to 97 | 4,938 to 6,622 | Strongest predecessor paper4 report; full predecessor path valid |
| paper21 | Applicability, empirical acceptance plus C+ editor refresh | 76.7 min full predecessor editor; 18.5 min C+ refresh | 3.969m full predecessor editor; 445,923 C+ refresh | 142 to 131 | No prior report to 7,790, then 9,980 C+ | Full current empirical path and refined editor passed |

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

It retains reviewer run summaries and non-process notes. A required-coverage table instructs the editor to address every high/medium manuscript, cannot-verify, and material reference-integrity finding outside the traceability map. Technical-appendix coverage counts for parser, bibliography-maintenance, and copyediting findings, so preprocessing limitations no longer become author revision priorities merely to satisfy a transport heuristic. Inputs above 1,000,000 UTF-8 bytes are minified losslessly; inputs still above the budget fail instead of truncating.

This recovered the paper18 editor failure: the old 1,078,016-byte input exceeded the Codex limit, while the final source-inclusive input remains below the local safety budget and validates.

## C+ editor acceptance

The final editor prompt silently separates confirmed corrections, material qualifications, and exploratory suggestions. It ranks by tier, consequence, and actionability rather than treating deterministic scores or reviewer counts as editorial truth. Headline items require direct evidence, a material consequence, and a proportionate immediate fix. The report uses a compact executive summary, a consistent evidence/importance/minimum-fix structure, a short revision sequence, and late technical appendices for parser limitations, bibliography maintenance, review scope, and traceability. Cannot-verify items distinguish unavailable evidence from demonstrated manuscript omissions.

On paper21, the Sol/xhigh C+ refresh put all five preselected direct corrections in the headline section and moved the contested causal-framing point to material qualifications. The main body grew only from 4,085 words in the preferred C variant to 4,270 words in C+; most of the 9,980-word total is complete traceability and technical appendices. Every one of 131 canonical identifiers appears exactly once in the traceability map. The same prompt improved structure across the rejected lower-cost controls, but could not recover evidence their reviewer panels failed to find or fully correct weak model prioritization.

Two general prompt hardenings followed the benchmark. The numerical auditor must now test adding-up identities only after verifying a common sample, denominator, timing, and specification, and must never invent a balancing component. The shared reviewer contract now forbids substantive reviewers from reading one another's outputs, preventing wave-order anchoring while leaving comparison and deduplication to downstream stages. Both behaviors have focused regression tests; the frozen budget runs predate these two additions.

## Changes recommended for the GitHub pull request

Commit and publish the tracked project machinery for:

- the single GPT-5.6 Sol quality configuration, with overrides retained only for controlled tests;
- one conservative applicability workflow, deterministic uncertainty fallback, and the theory-logic specialist;
- mandatory source-consistency review and targeted specialist prompt passes;
- deterministic parser improvements and regression tests;
- precision-first normalization and lossless editor transport;
- applicability provenance, run manifests, timeouts, concurrency, resume safeguards, and editor refresh;
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
- Precision-first normalizer re-simulation on five historical exhaustive controls.
- Paper18 Sol/xhigh editor recovery: 315 seconds, 222,200 tokens, valid 7,313-word report.
- Source-inclusive editor input checks near the 1 MB budget.
- Fresh predecessor paper4 acceptance: parser preflight, all 18 then-configured substantive agents, 19 reviewer-output validations, normalization, editor-input assembly, Sol/xhigh editor, and final report validation.
- Fresh paper21 applicability acceptance: 116-page input, parser preflight, high-confidence empirical routing, all 18 applicable substantive agents, 19 reviewer-output validations, lossless normalization, editor synthesis, final-report validation, source/evidence cross-checking, and a visually and textually verified 17-page PDF.
- Paper21 Sol/xhigh C+ editor refresh: 1,112 seconds, 445,923 reported tokens, 9,980 words, complete 131-ID traceability, and all five preselected direct corrections prioritized.
- Three full-paper lower-cost controls with identical deterministic artifacts and reviewer rosters: Terra/high, Terra/xhigh, and Luna/xhigh. All 63 model calls completed and all three final reports validated; none matched Sol/xhigh on the preselected correction set.
- Matched HTML and paginated A4 PDFs for the Sol C+ report, all three lower-cost reports, and the detailed local comparison. Text, canonical-ID coverage, encoding, page bounds, page numbers, and representative first/middle/last pages were checked.
- The wrapper's first final-check invocation exposed a deterministic URL-regex false positive on a DOI with balanced parentheses. A regression-tested checker fix accepted the unchanged report; no model stage needed to be rerun.
- Final parser-only regression after the acceptance recovered the paper4 label-only table and preserved the exact validated counts on papers 13, 15, 16, and 18.
- 96 focused unit tests, including conservative applicability fallback, mandatory theory coverage, C+ routing, source-faithful adding-up checks, independent-reviewer behavior, legacy selection provenance, and theory-prompt safety checks.
- Python compilation checks for modified scripts.
- `git diff --check`.

The accepted predecessor report contains 6,622 words and passed schema, traceability, external-source, required-section, and smoke checks. Its principal gains over both prior paper4 reports are fuller source/display reconciliation, explicit roster disclosure, clearer narrow-first prioritization, and more complete reference, parser, and copyediting appendices. The reports are still stochastic outputs: the acceptance supports a stronger-overall claim, not guaranteed recovery of every detail from every prior run. The applicability path now has fresh empirical acceptance; the theory specialist still requires the formal-paper acceptance described above.

## Remaining GitHub steps

After the final local commit, but before any GitHub update:

1. Fetch read-only and confirm `origin/main` has not moved beyond the inspected upstream commit.
2. Rebase or merge the upstream README-only change while preserving the no-overlay workflow.
3. Rerun unit, environment, shareable-tree, sensitive-name, compilation, and diff checks on the reconciled tree.
4. Record a formal-theory acceptance run as follow-up validation when a suitable non-confidential paper is available.
5. Inspect ignored acceptance artifacts locally.
6. Commit the applicability update only after the diff and acceptance evidence are satisfactory.
7. Push the feature branch and open a pull request; do not force-push or update `main` directly.
8. Require CI to pass and inspect the rendered documentation before merge.

## Final assessment

The local workflow is meaningfully better than the current GitHub implementation. The strongest accepted changes are Sol/xhigh, broad specialist coverage, a narrow source-consistency pass, deterministic source-faithful parsing, conservative normalization, lossless editor transport, and C+ author-oriented synthesis. The applicability workflow has fresh empirical full-paper acceptance. The lower-cost controls support offering Sol/xhigh as the only quality configuration. Formal-theory full-paper acceptance remains a documented follow-up validation gap.

The honest release claim is not universal dominance. It is a materially more comprehensive, accurate, inspectable, and failure-resistant review, with residual model variation made visible through provenance and conservative evidence handling.
