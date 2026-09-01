# Limitation Branch Recommendations

> **Historical record, superseded.** This document preserves results from an earlier branch-evaluation phase. Its dynamic selector-breadth targets and source-overlap normalization recommendations do not describe the current quality-first workflow. The current wrapper defaults to an exhaustive static roster, and its normalizer is precision-first and preserves lossless per-source-finding detail. Use `README.md` and the current release-readiness record for active behavior.

This report records the limitation branches tested against the nine prior actual paper runs (`paper1` through `paper9`) before incorporation into `main`.

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

## Incorporated Branches

| Limitation | Branch | Test evidence | Decision |
| --- | --- | --- | --- |
| Shared scoring and branch comparison | `experiment/evaluation-harness` | Added `scripts/evaluate_prior_runs.py`; baseline scorecard generated for all nine prior actual runs; unit tests passed. | Incorporated first so future changes can be scored consistently. |
| Raw-caption fallback is conservative and can truncate captions | `improve/caption-fallback-diagnostics` | Direct extractor run on actual `inputs/paper9.pdf` changed Table 1 from a truncated caption to the full sentence and did not over-append Table 2 after a period. Unit tests passed. | Incorporated as a narrow caption fix. |
| Selective rerun/resume support is manual | `improve/editor-refresh-helper` | Added `scripts/refresh_editor.py`. Build-only test on actual paper9 artifacts rerendered prompts and rebuilt editor input without reviewer reruns or editor API calls. Unit tests passed. | Incorporated as low-risk operational support. |
| Pilot reviewers can add length or overlap when selector cues are broad | `improve/selector-breadth-gating` | Live selector-only Codex runs improved paper3 72.0 to 88.0, paper5 70.0 to 92.0, and paper7 62.0 to 88.0; optional reviewer counts fell from 12/14/14 to 9/10/9. Unit tests passed. | Incorporated with monitoring for zero-finding optional reviewers. |
| Normalization heuristics under-merge related findings | `improve/normalization-source-overlap` | Re-normalized paper6 from the same actual reviewer JSON. Canonical findings dropped 47 to 45, cross-agent groups rose 1 to 4, and normalization score moved from 70.0 to 100.0 under the harness. Unit tests passed. | Incorporated with caution because stronger merging can hide distinct findings if source-object IDs are reused too broadly. |
| Final report checker verifies shape/IDs but not external-reference truth | `improve/report-external-source-coverage` | Added external URL coverage checks. Existing reports paper2 and paper4 were flagged for missing external-source appendices; paper3 and paper6 were flagged for missing specific external URLs. Unit tests passed. | Incorporated as a stricter traceability gate. |
| Complex PDFs can produce misleading text-quality diagnostics and sometimes scrambled sorted text | `improve/preprocess-isolated-quality` | Added isolated `--work-root` and manifest page-quality diagnostics. Reprocessed paper1 and paper2 into `work/experiments/preprocess-isolated-quality`; preprocessing score improved from 0.0 to 88.0 across those two weak cases. Unit tests passed. | Incorporated last because it touches shared preprocessing and evaluator behavior. |

## Final Merge Order

1. `experiment/evaluation-harness`
2. `improve/caption-fallback-diagnostics`
3. `improve/editor-refresh-helper`
4. `improve/selector-breadth-gating`
5. `improve/normalization-source-overlap`
6. `improve/report-external-source-coverage`
7. `improve/preprocess-isolated-quality`

No tested branch was rejected. The two changes that should receive the closest review in future runs are normalization source-overlap merging and preprocessing page-quality diagnostics, because they affect how downstream evidence is interpreted.

## Tests and Runs Used

- `.\.venv\Scripts\python.exe -m unittest`
- `.\.venv\Scripts\python.exe scripts\evaluate_prior_runs.py`
- isolated preprocessing runs for paper1 and paper2 under `work/experiments/preprocess-isolated-quality`
- direct paper9 caption extraction from `inputs/paper9.pdf`
- re-normalization of paper6 under `work/experiments/normalization-source-overlap`
- report checker sweep across paper1 through paper9
- live selector-only Codex runs for paper3, paper5, and paper7 under `work/experiments/selector-breadth-gating`
- build-only editor refresh on paper9 using `scripts/refresh_editor.py`
