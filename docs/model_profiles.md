# Model Overrides

## Recommended default

The normal command uses `gpt-6.1-sol` with `xhigh` reasoning for substantive reviewers and the editor. Parser-quality preflight and applicability routing use `high`.

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf"
```

[GPT-6.1 Sol supports the retained reasoning settings](https://developers.openai.com/api/docs/models/gpt-6.1-sol). One complete long-paper run and targeted source checks support this practical default, not a general accuracy ranking. No new API-key requirement is introduced; reviews still use authenticated Codex CLI.

Use an up-to-date Codex CLI and an account with model access. The GPT-6.1 Sol run used CLI 0.159.0; 0.158.0 rejected its access probe here. If a model is unavailable, update Codex and check account access rather than silently substituting another model. To retain the previous default explicitly, use `--model gpt-6-sol`. Existing packaged workspaces retain their original runtime/defaults; use a new workspace for the new version.

## GPT-6.1 Sol and optional Opus 5.5: bounded evidence

As of 1 October 2026, both models produced complete reports on the same 71-page
development paper on Windows. GPT-6.1 Sol used a frozen runtime with interrupted
reviewers resumed; Opus 5.5 required quota-related continuations and an updated
editor handoff. These were not matched uninterrupted runs of identical software.
The [Claude Code backend](claude_code.md) remains experimental and opt-in.

Source checks found useful corrections and limitations in both reports. Sol
retained important qualifications but missed a conditional numerical-consistency
concern; Opus added coverage but also propagated source-version errors and lost
qualifications. A later three-role Sol check used common parsed/preflight inputs,
not another full pipeline or an independent held-out sample. This is not evidence
of error-free review, general superiority or guaranteed semantic completeness.

| Successful stages only | Uncached input | Cached input | Output incl. reasoning | Cost estimate |
| --- | ---: | ---: | ---: | --- |
| GPT-6.1 Sol, 22 stages | 3,780,655 | 37,683,968 | 466,924 | 399.97 Standard credits; $16–18 API-equivalent tokens, excluding separately billed tools |
| Opus 5.5 workflow, 22 stages | Different CLI cache accounting | Includes cache writes/reads | Includes helper model usage | $83.69 CLI API-equivalent, including recorded helper/search usage |

Sol's four interrupted attempts add 44.72 Standard credits; Claude's other
17 attempts add $38.07 API-equivalent. Do not erase failed-attempt usage or
compare credits directly with dollars. These are estimates, **not subscription
charges or weekly-quota percentages**. Fresh runs depend on caching, source/tool
work, reasoning and retries; the historical runs below are not controlled savings
comparisons against 6.1 Sol.

[Codex Standard rates](https://learn.chatgpt.com/docs/pricing#token-rates), checked
1 October: 50 / 2.5 / 250 credits per million uncached / cached / output tokens.
[API rates](https://developers.openai.com/api/docs/pricing) are separate: $2 input,
$0.10 cached, $2.50 cache writes and $10 output per million at Standard short-context
rates. Retained Sol requests were below the 272K long-context threshold; missing
cache-write counters account for the dollar range. Claude values come from its
CLI cost metadata, not a billed API experiment. Included allowances cannot be
reliably converted from these estimates; inspect each account's usage dashboard.

## Optional budget override: GPT-6 Luna

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model gpt-6-luna --reasoning-effort xhigh
```

GPT-6 Luna has [lower published Codex credit rates](https://learn.chatgpt.com/docs/pricing#token-rates) than Sol. Selected-reviewer tests and the full-pipeline comparison found useful but uneven coverage. It remains an explicit budget choice, not a replacement default or a promise of Sol-equivalent results.

## Historical GPT-6 Sol/Luna full-pipeline comparison - 2026-09-23

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
2026-10-01, per million uncached/cached/output tokens: Sol 6 = 50/5/250;
Luna 6 = 2.5/0.25/12.5; Sol 5.6 = 100/10/500. Current Fast mode uses 2 times
the Standard purchased-credit rate, but 2.5 times included subscription usage
where available; the sessions did not record an effective billing tier.
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
- That historical wrapper could leave a Codex child running after a Windows
  timeout. The current wrapper terminates its owned process tree and offers
  `--resume-incomplete` for new checkpointed runs. Keep the machine awake for long
  runs; these changes do not retrospectively turn the historical trial into an
  uninterrupted run or validate laptop-sleep recovery.
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

## Systematic comparisons

Use the optional [benchmark exercise](model_benchmark.md) for fixed-input, repeated,
label-blinded comparisons of explicit model profiles. It separates source-checked
quality from usage and failures; previous case studies are not ground truth.
