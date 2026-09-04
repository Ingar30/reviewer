# Model Overrides

## Recommended default

The normal command uses `gpt-5.6-sol` with `xhigh` reasoning for substantive reviewers and the editor. Parser-quality preflight and applicability routing use `high`.

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf"
```

[OpenAI describes Sol as its flagship model for complex professional work](https://developers.openai.com/api/docs/models/gpt-5.6-sol). It remains the strongest configuration tested in this repository.

## Example: Terra/xhigh

If you are not on one of Codex's higher-usage plans, consider a more cost-efficient model and/or lower reasoning effort so a full review is less likely to exhaust your allowance. [OpenAI similarly recommends switching to a smaller model when approaching usage limits](https://developers.openai.com/codex/pricing). To use Terra while retaining `xhigh` reasoning:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model gpt-5.6-terra --reasoning-effort xhigh
```

[OpenAI describes Terra as balancing intelligence and cost](https://developers.openai.com/api/docs/models/gpt-5.6-terra). In a full-pipeline test on a 116-page applied microeconomics paper, including a large online appendix with many tables and figures, Terra/xhigh used about 23% fewer aggregate logged tokens than Sol/xhigh.

The Terra report was valid and useful but materially less exhaustive. Terra/xhigh is therefore an explicit lower-usage option, not a second recommended default.

Logged token totals combine all model-backed stages and do not reveal the input, cached-input, reasoning, and output split. They are not an exact bill, subscription quota, or promise of future usage.

## Other overrides

Any supported model and reasoning combination can be selected for one run:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model MODEL_ID --reasoning-effort EFFORT
```

`EFFORT` may be `none`, `low`, `medium`, `high`, `xhigh`, or `max`. The `--model` flag applies to every model-backed stage. Preflight and applicability effort can be changed separately with `--preflight-reasoning-effort` and `--selector-reasoning-effort`.

Overrides do not change the project default. The effective settings are recorded in `work/<paper_id>/run_manifest.json`; combinations not evaluated on representative papers should be treated as unbenchmarked.
