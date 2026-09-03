# Parser Quality Validation and Recommendations

Date: 2026-09-03 to 2026-09-04

## Decision

Accept the current bounded parser changes. They fix material failures found in the recent papers, survive a ten-paper regression corpus, preserve the source-evidence layer byte for byte, and do not add OCR, an external service, or a learned repair layer.

The agreed report-quality condition is now met. A fresh paper21 run completed all 18 selected substantive reviewers, validation, normalization, editing, and final-report smoke checks. Relative to the preserved healthy baseline, the new report is materially better: it removes disproven parser claims, surfaces newly verified table omissions, improves reviewer completion status, retains comparable editorial depth, and concentrates more of the final bundle on high-severity issues.

The next parser milestone should target table structure. It should not add document-specific strings or silently repair mathematical content.

## Validation method

- Established a baseline before changing the parser: 96 unit tests passed.
- Used four recent papers, four previously completed numbered papers (`paper4`, `paper9`, `paper13`, and `paper16`), and the completed paper21 and paper22 runs: 10 PDFs and 378 pages in total.
- Ran every experiment under `tmp/parser-validation/`; existing `work/`, `outputs/`, and source PDFs were not changed.
- Used 72 DPI for validation renders to reduce iteration cost. Text extraction, geometry, inventories, and source hashes do not depend on that render setting; production runs retain their configured DPI.
- Reran the final accepted implementation from scratch at 72 DPI with up to four parallel parser workers. A transient Dropbox file-open error on paper13 was recovered by rerunning only the incomplete deterministic job.
- The ten-paper regression corpus made no reviewer-agent or live API calls. A separate production paper21 parser-quality preflight was attempted, then stopped before substantive reviewers when it exposed cleanup and audit-routing issues; those issues were resolved and retested deterministically.

## Acceptance gates

| Gate | Result |
| --- | --- |
| All ten PDFs preprocess successfully | Pass |
| Source PDF hashes unchanged from baseline | Pass: 0 mismatches |
| Raw extracted page text unchanged | Pass: 0 mismatches across 378 pages |
| Unit suite | Pass: 113 tests |
| Duplicate canonical table or figure labels | Pass: 0 duplicate groups |
| Environment check | Pass |
| Shareable-repository check | Pass |
| Tracked sensitive-name check | Pass |
| Fresh paper21 reviewer run | Pass: 18 of 18 substantive reviewers completed and validated |
| Final report smoke check | Pass |

## Corpus results

Counts are baseline -> accepted implementation. Final `table_count` means canonical caption-grounded tables; `Candidates` includes retained unlabeled extraction candidates and is therefore intentionally broader.

| Paper | Pages | Missing labels | Sections | Citation candidates | References | Canonical tables | Candidates | Unlabeled | Figures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Faith Favors the Fortunate | 18 | 0 -> 0 | 4 -> 3 | 39 -> 15 | 31 | 3 -> 3 | 3 | 0 | 7 -> 7 |
| Maren Ehrgott | 12 | 11 -> 0 | 3 -> 1 | 56 -> 56 | 163 | 12 -> 12 | 12 | 0 | 0 -> 0 |
| Ong | 26 | 0 -> 0 | 5 -> 8 | 35 -> 35 | 66 | 5 -> 5 | 7 | 2 | 1 -> 6 |
| Vincent Rost | 41 | 0 -> 0 | 27 -> 26 | 83 -> 54 | 43 | 13 -> 12 | 13 | 1 | 11 -> 11 |
| paper4 | 8 | 0 -> 0 | 8 -> 1 | 2 -> 2 | 29 | 1 -> 1 | 1 | 0 | 0 -> 0 |
| paper9 | 12 | 12 -> 12 | 22 -> 22 | 33 -> 34 | 47 | 3 -> 3 | 3 | 0 | 4 -> 4 |
| paper13 | 63 | 1 -> 1 | 27 -> 21 | 50 -> 50 | 63 | 21 -> 21 | 21 | 0 | 17 -> 17 |
| paper16 | 30 | 0 -> 0 | 15 -> 15 | 35 -> 26 | 26 | 4 -> 4 | 4 | 0 | 11 -> 11 |
| paper21 | 116 | 2 -> 2 | 64 -> 62 | 52 -> 53 | 107 | 19 -> 18 | 19 | 1 | 23 -> 23 |
| paper22 | 52 | 1 -> 1 | 27 -> 26 | 88 -> 88 | 133 | 0 -> 0 | 0 | 0 | 2 -> 2 |

Lower citation counts for Faith, Vincent, and paper16 reflect removal of reference-list occurrences from the in-text citation inventory, not evidence loss. Compound citations such as `Becker (1973, 1974)` are now retained, and a unit fixture verifies that citations in a later appendix remain eligible after the reference-list boundary. On paper13, the final context-aware cleanup preserves the genuine footnote marker in `1Hsieh et al. (2019)`, leaving the citation count unchanged from baseline.

## What improved

### Evidence preservation and layout noise

Raw page text remains immutable. Repeated headers, footers, and vertical margin notices are removed only from normalized prose and written to `layout_artifacts.json` with their source text, geometry, signature, page, and reason.

- Maren: 12 repeated footers and 11 repeated headers are recorded.
- Ong: 25 repeated headers and 25 vertical Wiley notices are recorded. The normalized pages contain no Wiley agreement/terms contamination.
- paper4: 7 repeated headers and 7 repeated footers are recorded.
- Printed page-label tokens are removed from normalized prose only when supported by edge geometry plus either explicit PDF label metadata or a reconciled run of at least three consecutive geometric labels. Exact-block and mixed-block cases are distinguished in provenance so a mixed block is never discarded.
- Paper21's four verified contamination examples on pages 54, 55, 65, and 73 no longer inject `52`, `53`, `7`, or `15` into surrounding prose. Numeric values such as `-10.53` and `53.0` remain unchanged.

Detection uses geometry, recurrence, digit-normalized signatures, and PDF label metadata rather than publisher names. Numeric-only recurring edge blocks cannot establish a layout-artifact signature, preventing chart ticks from being mistaken for footers.

### Page labels

Geometric header/footer labels are accepted only when they form a run of at least three consecutive Arabic or Roman labels. This recovered Maren's `01` through `12`; a final overlap test also verifies that short labels are removed when they share a recurring publisher-footer block whose lines are reordered in normalized text. On paper9, isolated candidates on physical pages 4, 6, 8, and 11 were rejected and retained as rejected-candidate provenance instead of being promoted to page labels.

### Tables and figures

Caption matching now supports a split label and title on the same geometric row, plus the common all-uppercase, unpunctuated convention such as `TABLE 1  Descriptive statistics`. The uppercase rule is typographically bounded; sentence-like `Figure 1 shows the estimates` remains rejected.

- Maren retains canonical table labels 1 through 12.
- Ong recovers table labels 1 through 5 and figure labels 1 through 6.
- Vincent's false cover-design table remains visible as an unlabeled candidate but is excluded from the canonical count, which falls from 13 to 12.
- Paper21's five figures on 90-degree rotated pages use an explicit `full_page_rotated_fallback`; each saved crop is byte-identical to its 72-DPI full page image and therefore no longer omits upper or right panels.
- Wrapped captions are complete for paper21 Figure A.17 and paper22 Figures 1 and 2. The same general fix also completes paper9 Figures 3 and 4.
- Unsafe table status is not upgraded merely because a caption was recovered.

The first live paper21 preflight incorrectly described the full-page Figure A.3 fallback as blank even though its dimensions, file size, and SHA-256 hash matched the page image and visual inspection showed the complete figure. The parser-quality prompt now requires those deterministic checks before alleging that a full-page rotated fallback is blank or truncated. It also distinguishes generated page metadata headers and exclusion provenance from text that actually remains in normalized body content.

### Glyphs and normalization

Unresolved control glyphs are now reported with font, character code, bounding box, and origin. Ong's affected pages are 7, 8, 11, 14, 15, 16, and 19. Maren's recurring header control glyph is likewise preserved in provenance even though the header is excluded from normalized prose.

Soft hyphens are removed only from normalized prose and counted in page diagnostics. Vincent's three source soft hyphens, on pages 1 and 41, remain in raw evidence and no longer survive in normalized page files.

### Sections and reading order

The parser now rejects several general classes of false headings, including letter-spaced metadata, initial lists, generic editorial metadata, math-operator strings, overlong appendix sentences, repeated chart categories, multi-panel chart labels, and sample-size rows containing repeated numeric cells. This removes the false `2 Groups 3 Groups` heading in Vincent, six `N ...` rows in paper13, the paper22 multi-panel chart line, and seven repeated running-header headings in paper4. Ong's eight final headings correspond to visible document sections.

An initially broader reading-order divergence rule overflagged Faith and Vincent during step testing. It was narrowed before acceptance to severe first-page divergence plus existing multi-column and landscape conditions.

## Remaining limitations

1. **Table cell structure remains the highest substantive risk.** Caption coverage is much better, but merged headers, signs, and cell alignment can still be unsafe. Canonical means caption-grounded, not numerically verified.
2. **Section recall is still uneven.** Maren exposes real numbered headings in source text but the section inventory retains only `References`. The accepted structural guards fix the verified false positives without attempting a larger typography-scoring rewrite.
3. **Mathematical extraction is diagnostic, not reconstructive.** Exact glyph locations are now available, but missing or ambiguous mathematical symbols are deliberately not guessed.
4. **The parser cannot recover absent source material.** A cited online appendix or supplement that is not included in the input package must remain `cannot_verify`; this is an intake-completeness issue, not a text-repair problem.
5. **Image-only pages remain conservative.** OCR is recommended where appropriate but is not installed or silently invoked by the default workflow. Paper21 Figure A.7 retains unresolved source-font control-glyph provenance and must be checked visually.
6. **Unlabeled extraction candidates remain deliberately visible.** Paper21's heatmap-derived page-89 candidate is not counted as a canonical table, but it remains available for audit instead of being silently deleted.

## Prioritized recommendations

### 1. Build a conservative table-extraction ensemble

Use caption-bounded regions, compare PyMuPDF and pdfplumber output, cluster cells by x-coordinate, and require agreement on dimensions and stable row/column boundaries. Preserve both candidates and downgrade to `cannot_verify` when they disagree. Validate against synthetic fixtures and this same ten-paper corpus. Do not infer missing signs or values.

### 2. Make section recognition typography-aware

Score candidates using body-region position, font size/weight relative to nearby prose, numbering continuity, whitespace, and recurrence. This should address Maren's missed headings without growing a lexical exception list. Keep deterministic evidence explaining every accepted or rejected candidate.

### 3. Add equation-focused evidence artifacts

For pages with unresolved math/control glyphs, save equation-region crops and token/font sidecars. Permit deterministic replacement only when a font/code mapping is verified against page geometry and rendered source. Otherwise preserve the glyph warning and route reviewers to the image.

### 4. Add an intake-completeness manifest

Record whether the submission includes the main paper, appendices, supplementary files, data/code links, and any files explicitly cited by the paper. Missing components should become explicit source-scope limitations before review begins.

### 5. Profile before adding parser dependencies

The corpus run was not a controlled performance benchmark. Profile repeated document opens, caption crops, and table extraction before optimizing. Evaluate packages such as `pymupdf-layout` only in an isolated branch against the same acceptance gates; do not add a dependency based on the library's console suggestion alone.

### 6. Keep OCR opt-in and local

If scanned submissions become common, add local OCR as a separately enabled fallback with page-level provenance and confidence. It is not the next priority for this corpus.

## Editorial-report comparison

The preserved paper21 baseline is a healthy comparator: including parser preflight, 14 reviewers reported `ok` and 5 reported `partial`. It contains 135 source findings, 127 canonical findings, 8,369 words, and 25 URLs.

An intervening degraded run remains useful only as failure evidence: 13 substantive reviewers failed on an internal code-mode IPC decoding error, leaving a 3,280-word report with 28 source findings and one URL. It was not used to judge parser quality.

The final fresh run completed all 18 selected substantive reviewers with 16 `ok`, 2 `partial`, and no failures; including parser preflight, the totals are 17 `ok` and 2 `partial`. Its 118 source findings normalize to 110 canonical findings in an 8,123-word report with 25 URLs. The lower count reflects a more selective bundle rather than obvious lost depth: high-severity findings increase from 6 to 8, low-severity findings fall from 31 to 24, bibliography-maintenance items fall from 10 to 4, and the number of `cannot_verify` assessments falls from 15 to 11.

Qualitatively, the new report removes the false claims that Figure A.3 is blank/truncated and that cleaned footer labels remain in body prose. It adds the verified Table 4 and Table A.9 panel omissions, retains the central outcome-definition, portfolio-accounting, preregistration, governance, treatment-source, external-validity, and replication issues, and gives the most directly actionable problems higher priority. The final report validator returns `VALID`. This is materially better than both the degraded run and the healthy baseline for the parser-related dimensions under test.

## Quality-first boundary

The durable design is a two-layer parser: immutable evidence (PDF hash, raw page text, word/block geometry, and page images) plus a normalized semantic layer with explicit exclusions and confidence/provenance. The current changes move in that direction. Further work should improve agreement checks and abstention behavior, not make the parser appear complete by guessing.
