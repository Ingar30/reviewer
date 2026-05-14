# Limitation Branch Recommendations

This report evaluates the limitations listed in `README.md` against the nine prior actual paper runs (`paper1` through `paper9`). Each proposed improvement was isolated on its own branch and tested separately.

## Baseline

Baseline command:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_prior_runs.py
```

Baseline scorecard from the actual prior runs:

| Area | Mean score |
| --- | ---: |
| preprocessing | 75.6 |
| caption_extraction | 98.5 |
| normalization | 96.7 |
| report_checking | 96.7 |
| selector_breadth | 81.6 |
| resume_readiness | 100.0 |
| overall | 91.5 |

Weakest baseline cases:

| Paper | Weak area | Baseline evidence |
| --- | --- | --- |
| paper1 | preprocessing | preprocessing score 0.0; many sparse figure/appendix pages flagged as low text |
| paper2 | preprocessing/report checking | preprocessing score 0.0; report score 85.0 |
| paper3 | selector breadth | selector score 72.0; 12 optional reviewers selected |
| paper5 | selector breadth | selector score 70.0; 14 optional reviewers selected |
| paper6 | normalization | normalization score 70.0; 49 source findings collapsed to 47 canonical findings |
| paper7 | selector breadth | selector score 62.0; 14 optional reviewers selected |
| paper9 | caption extraction | caption score 90.0; raw Table 1 caption was truncated |

## Branch Results

| Limitation | Branch | Test evidence | Recommendation |
| --- | --- | --- | --- |
| Complex PDFs can produce misleading text-quality diagnostics and sometimes scrambled sorted text | `improve/preprocess-isolated-quality` | Added isolated `--work-root` and manifest page-quality diagnostics. Reprocessed paper1 and paper2 into `work/experiments/preprocess-isolated-quality`; preprocessing score improved from 0.0 to 88.0 across those two weak cases by separating plausible sparse visual/appendix pages from extraction-risk pages. Unit tests passed. | Merge, but review alongside other preprocessing changes because it touches `preprocess_pdf.py` and `evaluate_prior_runs.py`. |
| Raw-caption fallback is conservative and can truncate captions | `improve/caption-fallback-diagnostics` | Direct extractor run on actual `inputs/paper9.pdf` changed Table 1 from `Table 1: Analysis of the 22 labeling functions when` to `Table 1: Analysis of the 22 labeling functions when applied to the real estate condition report corpus.` It did not over-append Table 2 after a period. Unit tests passed. | Merge. This is a narrow, high-signal fix. |
| Normalization heuristics under-merge related findings | `improve/normalization-source-overlap` | Re-normalized paper6 from the same actual reviewer JSON. Canonical findings dropped 47 to 45, cross-agent groups rose 1 to 4, and normalization score moved from 70.0 to 100.0 under the harness. Unit tests passed. | Merge after spot-checking paper6 editor output, because stronger merging can hide distinct findings if source-object IDs are reused too broadly. |
| Final report checker verifies shape/IDs but not external-reference truth | `improve/report-external-source-coverage` | Added external URL coverage checks. Existing reports paper2 and paper4 are now flagged for missing external-source appendices; paper3 and paper6 are flagged for missing specific external URLs. Unit tests passed. | Merge as a stricter safety gate. It does not prove external truth, but it catches missing source traceability and makes the limitation explicit. Existing reports may need editor refresh before passing. |
| Pilot reviewers can add length or overlap when selector cues are broad | `improve/selector-breadth-gating` | Live selector-only Codex runs on broad-selection papers improved scores: paper3 72.0 to 88.0, paper5 70.0 to 92.0, paper7 62.0 to 88.0. Optional reviewer counts fell from 12/14/14 to 9/10/9. Unit tests passed. | Merge, with residual caution: paper3 and paper7 still selected one prior zero-finding pilot reviewer, so watch future runs. |
| Selective rerun/resume support is manual | `improve/editor-refresh-helper` | Added `scripts/refresh_editor.py`. Build-only test on actual paper9 artifacts rerendered prompts and rebuilt `work/paper9/editor/editor_input.md` without reviewer reruns or editor API calls. Unit tests passed. | Merge. This directly reduces manual editor-only refresh steps with low behavioral risk. |
| Shared scoring and branch comparison | `experiment/evaluation-harness` | Added `scripts/evaluate_prior_runs.py`; baseline scorecard generated for all nine prior actual runs; 32-test suite passed on the branch. | Merge first or cherry-pick into each accepted improvement so future branches can be scored consistently. |

## Suggested Merge Order

1. `experiment/evaluation-harness`
2. `improve/caption-fallback-diagnostics`
3. `improve/editor-refresh-helper`
4. `improve/selector-breadth-gating`
5. `improve/normalization-source-overlap`
6. `improve/report-external-source-coverage`
7. `improve/preprocess-isolated-quality`

Rationale: merge the harness first, then the narrowest low-risk operational fixes. Merge the stricter checker and preprocessing diagnostic branches after reviewing whether old reports should be refreshed immediately.

## Branches To Incorporate Into Main

Recommended for incorporation:

- `experiment/evaluation-harness`
- `improve/caption-fallback-diagnostics`
- `improve/editor-refresh-helper`
- `improve/selector-breadth-gating`
- `improve/normalization-source-overlap`
- `improve/report-external-source-coverage`
- `improve/preprocess-isolated-quality`

No branch is recommended for rejection based on current evidence. The two branches needing the most careful review before merging are `improve/normalization-source-overlap` and `improve/preprocess-isolated-quality`, because they affect shared interpretation of downstream evidence.

## Tests And Runs Used

- `.\.venv\Scripts\python.exe -m unittest`
- `.\.venv\Scripts\python.exe scripts\evaluate_prior_runs.py`
- Isolated preprocessing runs for paper1 and paper2 under `work/experiments/preprocess-isolated-quality`
- Direct paper9 caption extraction from `inputs/paper9.pdf`
- Re-normalization of paper6 under `work/experiments/normalization-source-overlap`
- Report checker sweep across paper1 through paper9
- Live selector-only Codex runs for paper3, paper5, and paper7 under `work/experiments/selector-breadth-gating`
- Build-only editor refresh on paper9 using `scripts/refresh_editor.py`
