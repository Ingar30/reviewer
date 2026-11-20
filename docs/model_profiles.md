# Model Overrides

## Defaults and access

The Codex backend uses `gpt-6.2-sol` with `xhigh` reasoning for substantive
reviewers and the editor. Parser-quality preflight and applicability routing use
`high`. Claude has its own [model choices](claude_code.md#choose-a-model).

```powershell
python scripts/review_paper.py --backend codex --pdf "inputs/my-paper.pdf"
```

Use an up-to-date CLI and an account with access to the requested model. Check
access before starting a review; authentication alone does not establish model
availability or remaining quota. Never silently substitute a different model.
Existing packaged workspaces retain their recorded runtime and settings. Native
plugin agents inherit the host model; the CLI default does not force a host change.

## Explicit overrides

GPT-6 Luna is an optional lower-cost choice, not a guarantee of equivalent quality:

```powershell
python scripts/review_paper.py --backend codex --pdf "inputs/my-paper.pdf" --model gpt-6-luna --reasoning-effort xhigh
```

The previous default can be selected explicitly with `--model gpt-6.1-sol`.
For any other supported combination:

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model MODEL_ID --reasoning-effort EFFORT
```

`EFFORT` may be `none`, `low`, `medium`, `high`, `xhigh`, or `max`, subject to
backend/model support. The model flag applies to every model-backed stage.
Preflight and routing effort have separate `--preflight-reasoning-effort` and
`--selector-reasoning-effort` flags. Overrides do not change the project default.
Effective settings are recorded in `work/<paper_id>/run_manifest.json`.

## Evidence and usage limits

Model availability and passing structural checks do not establish scientific
accuracy, complete coverage, unattended reliability or superiority over another
configuration. Source-check consequential findings and keep failed attempts.
Reported tokens or API-equivalent estimates are not subscription bills or
remaining quota. Consult the provider's account dashboard and current rates.

The optional [comparison exercise](model_benchmark.md) describes fixed-input,
source-checked comparisons. Real-paper identities, measurements, findings,
comparisons and run histories belong in ignored private storage, not public
documentation, even when names have been replaced with sample labels.
