# Reviewer Release Readiness Record

Date: 2026-09-01

Scope: local repository audit, model migration, deterministic PDF preprocessing, reviewer and editor workflow, full acceptance runs on paper7, paper8, and paper9, and the eventual GitHub update. This file intentionally records decisions and evidence without including private paper text, generated reviewer JSON, or report excerpts.

## Executive decision

The local implementation is a material improvement over the current GitHub state and should be preserved in local commits. It should not be pushed directly to `origin/main` yet.

The strongest release configuration is:

- `gpt-5.6-sol` with `xhigh` reasoning for substantive reviewers and the editor.
- `gpt-5.6-sol` with `high` reasoning for parser-quality preflight.
- `gpt-5.6-sol` with `medium` reasoning for dynamic reviewer selection.
- Local, deterministic PyMuPDF preprocessing with source coordinates, page images, artifact inventories, conservative glyph handling, and visual-verification flags.
- No external document service, no LLM-generated parser overlay, and no silent OCR replacement.
- A single author-oriented editor: first correct clear errors and inaccurate descriptions, then discuss broader positioning and implications.
- Dynamic reviewer selection for normal runs, with a quality-first ceiling of 13 optional reviewers and 4 specialized pilots. Use static mode when exhaustive coverage matters more than the additional calls.

The paper7 and paper8 reports generated with Sol/xhigh are better overall than the old reports in prioritization, evidence, actionability, and tone. They are not better on every individual check. Each missed some valid details that appeared in the old report. The acceptance findings led to wider reviewer routing and systematic numerical and sample-flow passes before this local commit.

## Git and GitHub state

Remote: `https://github.com/Ingar30/reviewer.git`

Branch under review: `reasoning-effort-option`

State before the acceptance commit containing this record:

- `origin/main` is one commit ahead of the local branch and the local branch is five commits ahead of `origin/main`.
- The upstream-only commit is `339513f Update README.md` from 2026-05-15. It only reorders and rewords documentation for the parser-repair overlay.
- `origin/reasoning-effort-option` already contains the first two local commits below. The local feature branch is three committed changes ahead of that remote before this acceptance commit.
- No GitHub push, pull request, deployment, or remote mutation was performed during this audit.

Local commits that should be retained:

| Commit | Decision | Reason |
| --- | --- | --- |
| `6f055db` Add reasoning effort option | Keep | Adds explicit model/reasoning overrides and supports current GPT-5.6 effort values. |
| `66872ae` Relax selector and update review defaults | Keep | Improves routing, defaults, and author-oriented report behavior. |
| `e78d015` Harden reviewer workflow and PDF preprocessing | Keep | Adds validation, provenance, run manifests, concurrency/timeouts, local parser improvements, and removes the poor-value parser overlay. |
| `3124553` Fix source-faithful PDF glyph extraction | Keep | Repairs only verified source-positioned glyphs and flags unknowns. |
| `ff82ae3` Compose source-positioned tilde accents | Keep | Conservatively composes verified spacing accents without global text guessing. |
| Acceptance commit containing this file | Keep | Incorporates the paper7/paper8 findings: appendix captions, landscape order, table anchoring, systematic number/sample passes, and wider quality-first selection. |

The upstream README commit must be reconciled before a GitHub pull request. Its parser-overlay instructions are obsolete relative to the local decision to remove that feature. Merge or rebase the upstream commit, preserve any unrelated wording improvement, and keep the local no-overlay workflow. Do not reintroduce the removed scripts, schema, prompt, fixtures, or README command.

The eventual GitHub update should be a feature-branch pull request, not a force push or a direct unreviewed update to `main`. Private files under `inputs/`, `work/`, `outputs/`, `tmp/`, and local virtual environments must remain excluded.

## Model decision

OpenAI's current [GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model) identifies `gpt-5.6-sol` as the flagship model, `gpt-5.6-terra` as the intelligence/cost balance, and `gpt-5.6-luna` for high-volume efficiency. It supports `none`, `low`, `medium`, `high`, `xhigh`, and `max` reasoning effort.

Recommendation:

- Keep Sol/xhigh as the full-review default. The task is difficult, quality sensitive, and tolerant of latency.
- Do not use GPT-5.5/high as the current default or benchmark target. Historical results can remain labeled as historical, but new runs should use GPT-5.6.
- Keep Terra/high as an explicit lower-cost comparison option, not the quality-first default.
- Keep Sol/high as a measured alternative for editor refreshes or routine comparison runs.
- Do not default to `max` until it beats xhigh on representative whole-report evaluations. Higher effort is not automatically better at every stage.
- Keep preflight at high and selection at medium. Their outputs are narrower, and the acceptance runs did not show a reason to pay xhigh latency for routing.

Editor-only benchmark on the same 419,638-byte paper9 evidence bundle:

| Model and effort | Seconds | Reported tokens | Report bytes | Assessment |
| --- | ---: | ---: | ---: | --- |
| Terra/high | 119 | 112,150 | 25,326 | Valid and concise, but less complete. |
| Sol/high | 297 | 123,191 | 34,199 | Valid and more detailed. |
| Sol/xhigh | 386 | 125,629 | 30,885 | Best prioritization and synthesis. |

Full clean wrapper runs used Sol/high preflight, Sol/medium selection, and Sol/xhigh reviewers/editor with four-way reviewer concurrency:

| Paper | Pages | Substantive reviewers | Wall time | Reported tokens | Report words | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| paper9 | 12 | 12 | 2,737 s (45.6 min) | 1,718,231 | not used for old/new comparison here | All validation and final checks passed. |
| paper8 | 75 | 12 | 2,853 s (47.6 min) | 1,976,957 | 5,798 | All validation and final checks passed. |
| paper7 | 71 | 12 | 3,929 s (65.5 min) | 2,693,007 | 7,132 | All validation and final checks passed. |

Reported tokens are Codex run metrics, not billing guarantees. Paper length alone does not determine runtime because web search, cache state, evidence density, reviewer behavior, and service load vary.

## Reviewer selection and pilots

The terms need to remain precise:

- Parser-quality preflight is mandatory and runs separately before substantive review.
- Three review-stage agents are always mandatory: cross-reference, reference, and grammar audit.
- Optional reviewers are full Sol/xhigh specialists selected for relevance. They are not weaker agents.
- "Pilot" describes five narrower audit roles: replication/data availability, institutional context, power/multiple testing, design/randomization, and economic magnitude. A pilot uses the same model, reasoning effort, schema, evidence requirements, and validation as every other substantive reviewer.

GitHub status quo on `origin/main`:

- The selector prompt described 5 to 9 optional reviewers as typical and allowed 10 or more for complex papers.
- There was no enforced code ceiling. A prior paper7 selector run chose 14 optional reviewers.
- Pilot guidance preferred at most 2 but allowed 3 or more with justification.

Acceptance configuration at commit `ff82ae3`:

- A hard ceiling of 9 optional reviewers and 2 pilots had been added to control overlap.
- Both paper7 and paper8 used all 9 optional slots, for 12 substantive review-stage agents after the 3 mandatory agents.
- This was too restrictive for a quality-first default. The reports missed non-overlapping institutional, multiplicity, sample-denominator, and experimental-design checks.

Final local policy:

- Dynamic selection remains the normal default required by the project workflow.
- The prompt normally chooses 7 to 13 optional reviewers, with a hard ceiling of 13 and no more than 4 pilots.
- A normal dynamic run therefore has 10 to 16 substantive review-stage agents after adding the 3 mandatory agents.
- The selector is told that institutional/platform facts, many-outcome validation, substantive experiments, and methods-paper constructs are separate issue classes, not substitutes for broader numerical, robustness, or identification review.
- Static mode runs all 14 optional plus 3 mandatory review-stage agents and is the exhaustive option for a final pre-submission audit.

Live routing evidence after the full runs:

- Paper8 selected 11 optional reviewers and restored external-validity, replication, power, and randomization-design coverage while retaining numerical, claim-evidence, literature, identification, robustness, sample, and equation audits.
- An initial paper7 11-slot run restored identification, platform/privacy context, and multiplicity but omitted design.
- A strengthened paper7 12-slot run restored both design and multiplicity. It then omitted model/equation review, which had supplied several distinct construct-definition findings in the full report.
- The final ceiling is therefore 13, not 9, 11, or 12. This is intentionally close to exhaustive on a heterogeneous 71-page methods paper while allowing smaller ordinary papers to avoid irrelevant agents.

Dynamic selection remains model based and therefore stochastic. The wider ceiling and explicit routing cues reduce known misses; they cannot prove that every run chooses the same roster. Use `--reviewer-selection static` when the cost of missing one specialist exceeds the cost of one or two additional reviewer calls.

## Workflow decisions

### Keep

- Deterministic preprocessing before any model review.
- Parser-quality preflight that can fail clearly when artifacts are unsafe.
- Structured reviewer JSON with strict schema, reviewer identity, finding ID, provenance, source-object, and claim-evidence validation.
- Original page labels, page coordinates, page images, table/figure crops, and per-page quality metadata.
- Dynamic reviewer selection output and the exact selected roster stored with the run.
- Parallel reviewer execution with bounded concurrency and per-stage timeouts.
- A run manifest containing the PDF hash, model, stage-specific reasoning, Git commit/dirty state, roster, duration, and final report path.
- Resume after a valid preflight and editor-only refresh after validated reviewer outputs.
- Normalization and deduplication before editor synthesis.
- Canonical finding identifiers in the traceability appendix rather than repetitive body footers.
- Literature and reference reviewers with web search and explicit `cannot_verify` behavior.

### Remove or do not add

- The optional LLM parser-repair overlay. It added cost, complexity, and a risk of plausible reconstruction without a demonstrated large quality gain.
- Any external document-service credit dependency. OpenAI/Codex usage is expected; Firecrawl or another parsing service is not.
- An automatic second enhancement layer on every PDF.
- Any parser that silently rewrites formulas, minus signs, decimal points, percentages, parentheses, or appendix labels.
- Separate narrow and broad editor modes for now. They add prompt and test surface without changing the underlying reviewer evidence.

### Editor behavior

Keep one editor and one report contract. The editor should:

1. Lead with clear factual errors, inaccurate descriptions, unsupported claims, denominator problems, and corrections the authors can make directly.
2. Treat a wrong description of the paper's own design, construct, or result as a narrow correction even when it affects interpretation.
3. State uncertainty and `cannot_verify` limits without accusing authors of misconduct.
4. Avoid acceptance or rejection recommendations and avoid mean-spirited referee language.
5. Discuss positioning, literature, external validity, and broader implications after the concrete corrections.
6. Suggest additional citations only when the literature reviewer found a relevant, verified source.

This preserves the useful breadth of the old editor while making the report more helpful from the author's point of view.

## Report comparison

The old reports are `outputs/paper7/report.md` and `outputs/paper8/report.md`. The new acceptance reports are stored locally under the dated acceptance run IDs and remain Git-ignored.

| Paper | Version | Words | Canonical findings | High severity | Manuscript issues |
| --- | --- | ---: | ---: | ---: | ---: |
| paper8 | Old | 5,552 | 64 | 3 | 34 |
| paper8 | New | 5,798 | 64 | 11 | 34 |
| paper7 | Old | 5,471 | 75 | 1 | 39 |
| paper7 | New | 7,132 | 102 | 10 | 41 |

Counts are not quality scores. The comparison below is based on source locations, calculations, issue distinctness, prioritization, and suggested fixes.

### Paper8

What improved:

- Correctly treats the Facts Only arm as a multi-attribute treatment rather than a clean single-mechanism contrast.
- Corrects the claim that 46% of time is a majority.
- Separates randomized treatment effects from endogenous preference matching.
- Narrows population and external-validity claims.
- Identifies a polarization construct mismatch.
- Finds a beta/gamma equation-description reversal.
- Flags the unadjusted family of about 40 coefficients.
- Finds a Wave 2 registry-arm mismatch and a slider-order contradiction.
- Makes the human-validation denominators, winsorization, and usage-variable construction more concrete.
- Prioritizes the most consequential revisions earlier and uses a more constructive tone.

Valid old-report details missing from the new report:

- Exact post-incentive active-user denominators: 390/747 and 499/718, or 52.2% and 69.5%.
- The 43% narrative versus 42.1% Table A7 allocation mismatch.
- A broad inability to verify public plans for every data collection, although the new report found the more concrete Wave 2 registry mismatch.
- Exact day-1 p-value verification, a lower-impact omission.

Assessment: the new paper8 report is better overall and only slightly longer, but not uniformly better. The systematic numerical and sample-flow prompt additions were made specifically to reduce the denominator and text-versus-table misses.

### Paper7

What improved:

- Shows that the thematic-richness benchmark is asymmetric because the code universe is derived from AI interviews.
- Explains why the probing ablation is not a clean causal mechanism test.
- Separates active-investing associations from causal and external-validity claims.
- Finds the reversed loss-protection scale.
- Finds a screener contradiction and narrows the scope of the two applications.
- Correctly converts a 0.411 log coefficient to about 50.8%, not 41.1%.
- Detects a 13,000 question-answer-pair double count.
- Distinguishes hypothetical stated interest from revealed demand in the selection experiment.
- Clarifies safety and saturation denominators, including the exclusion of codes below 5%.
- Finds incomplete replication materials and the absence of disclosed preregistration.
- Improves novelty/source verification and code-label/log-asset checks.

Valid old-report details missing from the new report:

- OpenAI API training, storage, and retention context.
- Exceptions to the description of a 10% tariff on all imports.
- The difference between a 39.6% relative change and a 21.8 percentage-point change.
- Predictive-validity multiplicity.
- Qualification of "unlimited" or effectively zero marginal cost.
- Some post-interview non-independence and coding-crosswalk details.

Assessment: the new paper7 report is substantially stronger on the main methodological and evidentiary issues, but it is also 1,661 words longer. Much of the increase is the 102-item traceability appendix and a larger grammar/reference inventory. It is not better in every aspect. The missing institutional, multiplicity, magnitude, and design lenses drove the final selector changes.

## PDF preprocessing research

Non-negotiable criterion: preprocessing must not invent content or silently change signs, decimals, percentages, parentheses, equations, labels, or names. A fast or visually attractive conversion is worse than the current parser if it turns a source minus sign into a positive quantity or reconstructs an unreadable equation plausibly.

### Alternatives considered

| Option | Local evidence | Installation and operational impact | Decision |
| --- | --- | --- | --- |
| [Firecrawl AnyDoc](https://github.com/firecrawl/anydoc) | Tested locally with `firecrawl-anydoc` 0.2.4 on paper9. Conversion took about 0.06 to 0.23 seconds and produced 47,761 characters, but it dropped the minus sign from `-1`, lost important lambda/mu/tau structure, and flattened formula relations. | The Python package was only about 19 MiB and easy to install. Native conversion stays local, but `ocr="hosted"` sends the whole document to Firecrawl Parse and can require API credits. | Reject as the canonical parser. Speed and ease do not compensate for sign and equation corruption. Do not enable hosted OCR. |
| [Docling](https://github.com/docling-project/docling) | Tested locally on paper9 and difficult page subsets from paper16 and paper20. Paper9 Markdown preserved the `-1` sign and much more formula notation than AnyDoc. It also produced useful structure on some complex pages. | Full PDF support introduces a substantially larger dependency/model stack, local model downloads, more platform variability, and another output representation to reconcile with source coordinates and current inventories. OCR or learned layout still requires visual verification. | Keep as an internal benchmark only. It did not show a large enough end-to-end gain to justify default-user friction or replacement risk. |
| Poppler `pdftotext` | Tested locally on paper9. It retained useful native characters, including the minus sign, but two-column reading order and structure were less suitable for downstream citation and artifact inventories. | Requires a system Poppler installation and does not provide the repo's page/block/crop contracts by itself. | Useful diagnostic baseline, not the canonical pipeline. |
| [Marker](https://github.com/datalab-to/marker) | Researched but not promoted to a full local-paper benchmark because the lighter candidates already failed the source-fidelity/friction tradeoff. | Requires Python 3.10+, PyTorch, model/inference dependencies, and model weights with commercial-use conditions distinct from the Apache-2.0 code. Optional LLM paths add more uncertainty. | Do not add to normal installation. Reconsider only with a fixed public benchmark and a large measured formula/table gain. |
| [PyMuPDF4LLM](https://github.com/pymupdf/pymupdf4llm) | Researched as the closest lightweight alternative. It supports local Markdown/JSON, layout, page chunks, and selective OCR, but it is built on the same MuPDF foundation already used here. | Low relative friction and no GPU requirement, but integration would duplicate extraction logic and still require custom provenance, page labels, glyph rules, inventories, and visual gates. | A reasonable future ablation, not a current dependency. Improve the existing PyMuPDF pipeline first. |

AnyDoc is therefore not better for this reviewer despite its excellent speed and install size. Its local path is deterministic, but deterministic omission or reordering can still create substantively false text. Its hosted OCR path also violates the decision not to add a second external service.

### Implemented local parser improvements

- Preserve raw native text, coordinate-sorted normalized text, words, blocks, page images, and source PDF hash.
- Apply glyph substitutions only for verified font/code mappings at source-aligned positions.
- Compose spacing accents only when font, size, baseline, and bounding-box overlap agree.
- Preserve and flag unknown math glyphs instead of guessing their meaning.
- Record residual control characters, unresolved math codes, repair counts, and the normalization strategy per page.
- Decode only explicit valid UTF-16 BOM page-label strings, such as `<FEFF0030>` to `0`; preserve malformed labels.
- Detect two-column and landscape pages. Use native content order on landscape pages only when coordinate sorting is clearly unstable, and keep the page flagged for review.
- Recognize appendix table, figure, and cross-reference labels in both `A1` and `A.1` forms.
- Extend a multiline caption only under conservative continuation rules, including a numeric continuation after a connector such as "across".
- Prefer a table region below its caption before considering an above-caption fallback, while stopping before notes and adjacent exhibits.
- Keep all caption-derived tables marked for visual verification. Never promote a plausible reconstructed table to verified source data.
- Preserve figure and table crops so reviewers can check signs, columns, notes, and labels against the rendered source.
- Keep OCR recommendation as metadata only. The normal setup does not install or run OCR and does not replace native text.

### Deterministic acceptance results

| Paper | Result after the final parser changes |
| --- | --- |
| paper8 | 75 pages; 51 tables instead of 36; 41 figures instead of 10; all appendix Tables A1-A15 and Figures A1-A31 inventoried; 136 cross-references; first PDF label decoded to `0`; no OCR pages, unresolved math glyphs, or residual controls. Visual checks confirmed complete Table A1 and Figure A1 crops with notes. Runtime was about 378 seconds because 46 additional appendix exhibits were cropped and inventoried. |
| paper7 | 71 pages; 26 tables; 15 figures; 2,040 numeric candidates; 134 cross-references; both landscape pages use flagged native order. Table A.8 now crops its own rows below its caption rather than Table A.7. Figure B.1 retains "12,192 decisions and 32 codes". Visual inspection confirmed the Table A.8 coefficients, signs, columns, and sample sizes. Runtime was about 180 seconds. |
| paper9 | 12 pages; 3 tables; 4 figures; 484 numeric candidates; 18 cross-references; no unresolved math or controls. Full text, every page Markdown file, and all table CSV files are byte-identical to the accepted parser baseline. Runtime was about 32 seconds in the final regression run. |

Known limitations remain visible rather than repaired speculatively:

- Paper7 pages 65-67 are image-heavy survey screenshots and remain OCR-recommended. The native selectable text and page images are retained; no text is invented.
- Paper7 landscape pages 55 and 67 remain reading-order review pages even though native order is materially more coherent.
- Caption-derived tables can have ragged rows and must be checked against their crops before relying on alignment.
- Paper8 has nine two-column appendix/reference pages flagged for reading-order review.
- Extracting and rendering every appendix exhibit increases preprocessing time, but this is an accepted quality tradeoff.
- No deterministic parser can prove visual formula fidelity from text alone. Parser preflight and source crops remain required.

## Changes recommended for the GitHub pull request

Commit all tracked local machinery, including:

- GPT-5.6 Sol defaults, stage-specific reasoning, and user overrides.
- Run manifests, concurrency, timeouts, resume safeguards, and selector-only/editor-refresh helpers.
- Current reviewer contracts, schemas, semantic/provenance validation, normalization, and final-report checks.
- The author-oriented editor instructions and traceability behavior.
- Dynamic quality-first routing with the wider ceiling and explicit specialist cues.
- Systematic `numbers_in_text.json` review for differences, percentages, percentage points, log changes, denominators, and time measures.
- Systematic sample flow from screening through analysis and explicit active/zero-use denominators.
- All deterministic parser improvements and their tests.
- Setup, environment, privacy, security, contributor, and extension documentation.
- Removal of the LLM parser-repair overlay and its obsolete scripts, prompt, schema, evaluation code, and fixtures.
- This release-readiness record.

Do not commit:

- Source PDFs.
- Parsed paper artifacts, page images, crops, prompts, logs, reviewer JSON, editor bundles, or generated reports.
- Temporary virtual environments or benchmark downloads.
- Credentials, signed-in Codex state, environment variable values, or manuscript-derived web-search logs.

## Verification record

Completed:

- Full clean paper8 wrapper run at exact commit `ff82ae3`, including preflight, dynamic selection, 12 substantive reviewers, validation, normalization, editor, and final smoke check.
- Full clean paper7 wrapper run at exact commit `ff82ae3` with the same complete stage coverage.
- Full clean paper9 Sol/xhigh acceptance run.
- Old/new report comparison by source support, calculations, issue distinctness, actionability, priority, tone, and length.
- Fresh deterministic parser reruns for paper7, paper8, and paper9 after the acceptance fixes.
- Visual inspection of paper7 Table A.8 and paper8 Table A1/Figure A1 crops.
- Byte-for-byte paper9 regression comparison for full text, every page Markdown file, and all table CSVs.
- Live Sol/medium selector checks on paper7 and paper8, including iterative checks for the observed design/multiplicity routing gap.
- 70 focused unit tests.
- Python compilation checks for modified scripts.
- `git diff --check`.
- Environment readiness check.
- Shareable-tree scan including untracked/addable files.
- Tracked/addable sensitive-name scan.

The two full long-paper runs predate the narrowly targeted post-comparison parser, selector, numerical, and sample-flow changes. Those changes were separately exercised with real deterministic parses, live selector calls, visual checks, and unit tests. No second full Sol/xhigh panel was run after every prompt adjustment. This limitation should remain explicit.

## Remaining release steps

The environment, tracked-sensitive-name, and shareable-tree checks passed before the acceptance commit. The final local actions are to review the complete diff, confirm that only tracked project machinery and this document are staged, and commit locally without pushing.

Before GitHub:

1. Fetch the remote again and confirm that `origin/main` has not moved beyond the inspected README-only commit.
2. Rebase or merge the upstream README commit, resolving in favor of the local no-overlay workflow.
3. Run the full unit suite, environment check, sensitive-name scan, shareable-tree check, and diff check on the reconciled tree.
4. For the strongest release evidence, run one clean static Sol/xhigh acceptance review on a representative public or authorized paper from the reconciled commit. Dynamic paper7/paper8 runs already validate the normal path; static mode validates exhaustive specialist coverage.
5. Review generated artifacts locally but keep them ignored.
6. Push the feature branch and open a pull request with the model, parser, workflow, privacy, benchmark, and migration notes.
7. Require GitHub checks to pass and inspect the rendered README before merging.

## Final assessment

The local branch is meaningfully better than the current GitHub code. The model migration, source-faithful parser, stricter reviewer contracts, author-oriented editor, and workflow safeguards should be published together after remote reconciliation.

The acceptance reports demonstrate a clear overall quality gain, not universal dominance. The honest release claim is: better prioritization and more consequential findings, with known stochastic specialist omissions that have been reduced through wider routing and can be eliminated operationally with static mode. The parser decision is stronger: keep the improved local deterministic pipeline and reject AnyDoc or an LLM/OCR overlay as the canonical source because source fidelity is more important than conversion speed.
