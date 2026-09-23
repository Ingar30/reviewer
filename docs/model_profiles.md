# Model Overrides

## Recommended default

The normal command uses `gpt-6-sol` with `xhigh` reasoning for substantive reviewers and the editor. Parser-quality preflight and applicability routing use `high`.

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf"
```

[GPT-6 Sol supports the retained reasoning settings](https://developers.openai.com/api/docs/models/gpt-6-sol). Selected reviewers have been tested on three papers, followed by the limited full-pipeline comparison below; this does not establish general accuracy. No new API-key requirement is introduced; reviews still use authenticated Codex CLI.

Use an up-to-date Codex CLI and an account with access to the selected model. These GPT-6 tests used Codex CLI 0.156.1; an older 0.153 client rejected GPT-6 Sol in this environment. If a model is unavailable, update Codex and check account access rather than silently substituting another model.

## Optional budget override: GPT-6 Luna

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model gpt-6-luna --reasoning-effort xhigh
```

GPT-6 Luna has [lower published Codex credit rates](https://learn.chatgpt.com/docs/pricing#token-rates) than Sol. Selected-reviewer tests and the full-pipeline comparison found useful but uneven coverage. It remains an explicit budget choice, not a replacement default or a promise of Sol-equivalent results.

## Recorded full-pipeline comparison - 2026-09-23

One 71-page paper (about 34,000 extracted words) was reviewed with both models in
parallel on Windows x64/Python 3.12, using CLI 0.156.1 and a locally built wheel
from commit `5d6165171bc09898d2f3ee94e8441444760751c3`. Each used fresh
preprocessing, `high` preflight/routing, `xhigh` reviewers/editor, and two concurrent
reviewers. Independent routing selected 19 substantive reviewers for Sol and 18
for Luna. All 43 live model sessions were accounted for; both final reports passed
structural checks. This was not a mocked review.

Source checks favored Sol: it retained consequential numerical, instrument-definition
and citation corrections that Luna missed. Luna also repeated an already-addressed
criticism. Neither was flawless: Sol omitted a valid reviewer finding from its report
body despite listing it in traceability. More findings or a passing report check do
not establish scientific correctness. This is a non-blinded case study, not an
accuracy score; the paper, reports and session logs remain private.

### Token usage and estimated credits

| Model | Uncached input | Cached input | Output | Standard credits |
| --- | ---: | ---: | ---: | ---: |
| GPT-6 Sol | 2,165,792 | 19,169,664 | 235,294 | 262.96 |
| GPT-6 Luna | 1,999,840 | 16,215,424 | 447,241 | 14.64 |
| Historical GPT-5.6 Sol | 2,790,412 | 29,818,240 | 403,106 | 778.78 |

Credits are **Standard-rate equivalents, not actual charges or measured subscription
quota**. [Official rates](https://learn.chatgpt.com/docs/pricing#token-rates), checked
2026-09-23, per million uncached/cached/output tokens: Sol 6 = 50/5/250;
Luna 6 = 2.5/0.25/12.5; Sol 5.6 = 100/10/500. Fast mode would cost 2.5 times
these GPT-6 equivalents; the sessions did not record an effective billing tier.
Reasoning is included in output, not added again. Comparison/assessment work is excluded.

Luna was about 18 times cheaper in this case, not equivalently thorough. The older
Sol run used CLI 0.153.0 and four concurrent reviewers; its current-rate estimate is
historical context, not a controlled contemporary comparison or an old bill.

For long-paper planning, twice this **token workload at the same cache mix** would
be about **526 credits for Sol or 29 for Luna**. This is not a per-page estimate.
About 90% of input was cached; repricing the same workload without caching would
instead give about 1,126 and 51 credits. Complexity, roster, retries and cache reuse
matter, so these scenarios are neither quotes nor cost caps.

### Execution limits and follow-ups

- The laptop slept for 77 minutes. Sol completed through its original wrapper;
  Luna required manual continuation after a timeout. Its original delayed audit
  was validated and retained, then only unstarted stages ran; no reviewer was repeated.
  This is not a clean uninterrupted or unattended-recovery pass, nor a speed benchmark.
- Windows timeout cleanup can leave a Codex child running after the wrapper exits.
  Keep the machine awake for long runs; do not start a replacement while its old
  review process is still active. Process-tree cleanup remains an engineering follow-up.
- Report-body coverage needs stronger checking: a traceability ID alone does not
  prove that its finding survived editing. Human source checks remain necessary.
- This adds one full-paper comparison per model, not live Linux/macOS validation
  or a general reliability benchmark.

## Historical example: GPT-5.6 Terra/xhigh

The earlier GPT-5.6 Terra/Sol comparison is retained as historical evidence, not a benchmark or cost comparison against GPT-6 Sol. To explicitly select the older Terra configuration:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model gpt-5.6-terra --reasoning-effort xhigh
```

In a historical full-pipeline test on a 116-page applied microeconomics paper, including a large online appendix with many tables and figures, GPT-5.6 Terra/xhigh used about 23% fewer aggregate logged tokens than GPT-5.6 Sol/xhigh.

The Terra report was valid and useful but materially less exhaustive. That configuration remains an explicit override, not a second recommended default.

That historical comparison combines all model-backed stages without the per-category accounting used above. Its aggregate totals are not an exact bill, subscription quota, or promise of future usage.

## Other overrides

Any supported model and reasoning combination can be selected for one run:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model MODEL_ID --reasoning-effort EFFORT
```

`EFFORT` may be `none`, `low`, `medium`, `high`, `xhigh`, or `max`. The `--model` flag applies to every model-backed stage. Preflight and applicability effort can be changed separately with `--preflight-reasoning-effort` and `--selector-reasoning-effort`.

Overrides do not change the project default. The effective settings are recorded in `work/<paper_id>/run_manifest.json`; combinations not evaluated on representative papers should be treated as unbenchmarked.
