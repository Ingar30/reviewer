# Model Overrides

## Recommended default

The normal command uses `gpt-6-sol` with `xhigh` reasoning for substantive reviewers and the editor. Parser-quality preflight and applicability routing use `high`.

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf"
```

[GPT-6 Sol supports the retained reasoning settings](https://developers.openai.com/api/docs/models/gpt-6-sol). Selected reviewers have been tested on three papers; full-pipeline and editor validation with GPT-6 remains outstanding. No new API-key requirement is introduced; reviews still use authenticated Codex CLI.

Use an up-to-date Codex CLI and an account with access to the selected model. These GPT-6 tests used Codex CLI 0.156.1; an older 0.153 client rejected GPT-6 Sol in this environment. If a model is unavailable, update Codex and check account access rather than silently substituting another model.

## Optional budget override: GPT-6 Luna

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model gpt-6-luna --reasoning-effort xhigh
```

GPT-6 Luna has [lower published Codex credit rates](https://learn.chatgpt.com/docs/pricing#token-rates) than Sol. Small reviewer-only tests found useful but uneven coverage, so it remains an explicit budget choice, not a replacement default; its full pipeline and editor have not been validated here.

## Historical example: GPT-5.6 Terra/xhigh

The earlier GPT-5.6 Terra/Sol comparison is retained as historical evidence, not a benchmark or cost comparison against GPT-6 Sol. To explicitly select the older Terra configuration:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model gpt-5.6-terra --reasoning-effort xhigh
```

In a historical full-pipeline test on a 116-page applied microeconomics paper, including a large online appendix with many tables and figures, GPT-5.6 Terra/xhigh used about 23% fewer aggregate logged tokens than GPT-5.6 Sol/xhigh.

The Terra report was valid and useful but materially less exhaustive. That configuration remains an explicit override, not a second recommended default.

Logged token totals combine all model-backed stages and do not reveal the input, cached-input, reasoning, and output split. They are not an exact bill, subscription quota, or promise of future usage.

## Other overrides

Any supported model and reasoning combination can be selected for one run:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model MODEL_ID --reasoning-effort EFFORT
```

`EFFORT` may be `none`, `low`, `medium`, `high`, `xhigh`, or `max`. The `--model` flag applies to every model-backed stage. Preflight and applicability effort can be changed separately with `--preflight-reasoning-effort` and `--selector-reasoning-effort`.

Overrides do not change the project default. The effective settings are recorded in `work/<paper_id>/run_manifest.json`; combinations not evaluated on representative papers should be treated as unbenchmarked.
