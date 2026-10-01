# Comparing reviewer models

This is an **optional, checkout-only research exercise**, not the normal review
workflow. It reuses the canonical prompts, evidence, backend adapters and JSON
validators without changing model defaults. Preparation, collection and scoring
are offline; running a job consumes the selected CLI account's quota. Do not run
paid tasks until the plan and budget have been approved.

## Exercise

Start with explicit profiles for GPT-6.1 Sol, GPT-6 Luna and Claude Opus 5.5, all at
`xhigh`. Profiles are configurable; pin the model rather than a moving alias.
Equal effort labels do **not** imply equal reasoning budgets. Claude readiness
and authentication are described in [Claude Code](claude_code.md).

| Phase | Design | Scheduled model sessions |
| --- | --- | ---: |
| Pilot | One long paper; numerical, claim-evidence and reference auditors; three profiles; one repeat | 9 |
| Development panel | Three papers; ten paper-role pairs; three profiles; two repeats | 60 |
| Held-out confirmation | At least two previously unused papers, plus clean/seeded synthetic controls | Set after pilot |
| Full-pipeline confirmation | Finalists run the existing complete wrapper on the same papers in fresh workspaces | Up to 22 stages per model/paper before retries |

The proposed development panel spans a long interviews paper (four roles), a
long empirical paper (three roles), and a short theory paper (three roles).
Keep actual paper paths, reference notes and results private. Previously examined
papers are development cases, not an unseen test set. Do not count pilot runs as
extra independent panel repetitions. Historical GPT-5.6 outputs are context only:
they used different runs/settings and are neither a matched candidate nor truth.
To compare GPT-5.6 fairly, add an explicit profile and approve fresh matched runs.

### What stays fixed

For each paper, reuse the same source-hash-validated parsed artifacts and validated
parser preflight. Every candidate receives an identical rendered reviewer prompt,
the same evidence and role-specific web-search policy, in a fresh persistent local
workspace. No other candidate's reviews or adjudication ledger are copied there.
The fixed panel does not rerun preprocessing, preflight, routing or the editor.
It therefore measures reviewer performance conditional on that parser/preflight.

Freeze a **human source-checked reference ledger before running**. Record issue
IDs, PDF page locations, role scope and impact weights (1 minor, 3 major, 5
critical). `status: provisional` entries are excluded from recall. A plan with
only provisional entries is a draft: confirm/correct them and prepare a new plan
before quality measurement. Preserve plausible-but-wrong negative controls in
the ledger's optional `negative_controls` list, outside the recall denominator.
Do not promote candidates merely because an older model reported them.

The plan freezes hashes of evidence, preflight, canonical runtime, runner and any
provided reference ledger. Changing them requires a new plan directory. Keep the
same software/CLI versions throughout a comparison. Run sequentially in the
seeded shuffled schedule, with no feedback or prompt tuning between candidates.
Record account/CLI updates, outages and laptop sleep separately. Never erase or
hide failed attempts; the runner refuses automatic retries and overwrites.

This compares **model plus execution host**: Codex and Claude have different tool
and image capabilities, settings, tokenizers and service conditions. It is not an
isolated base-model experiment. Existing permissions are retained, not bypassed.
Verify the reported effective model/effort against the requested profile before
accepting results. Web results, provider caching and service load are not frozen;
record usage rather than claiming identical cold-cache conditions.

## Commands

Use the existing Python environment/dependencies from the README; uv is not
required. From the checkout, copy and edit `benchmarks/example.json` into a private
location. `workspace` and `pdf` resolve relative to the config file. The workspace
must already contain `work/<paper_id>/parsed/` and a valid parser preflight.
Optionally set `reference_issues` to a private ledger path; its format is shown in
`benchmarks/reference-issues.example.json`.

Prepare and inspect (zero model calls):

```powershell
python scripts/benchmark_models.py prepare --config ".private/benchmark.json" --output "output/b1"
Get-Content "output/b1/PLAN.md"
Get-Content "output/b1/plan.json"
```

After approval and CLI authentication, run **one** scheduled task:

```powershell
python scripts/benchmark_models.py run --plan "output/b1/plan.json" --job j001 --allow-live
```

Inspect `output/b1/runs/j001/result.json` and its `work/<paper_id>/logs/` before
continuing with the next job. Omitting `--allow-live` refuses execution. One task
can involve many model/tool turns; the call count is not a token or money cap.
The per-task timeout defaults to 45 minutes. No whole-suite loop is provided.

After interruption, retain the workspace and check that the underlying CLI has
stopped before continuing. The current shared runner terminates its owned process
tree on timeout/interruption, but power-loss recovery is not a live-tested guarantee.
Completed jobs stay intact: continue with unattempted job
IDs. A retry requires a separately approved new plan/attempt, retained alongside
the original failure. Fixed-task jobs do not resume conversational context.

Export an offline rating packet (also works on partial runs):

```powershell
python scripts/benchmark_models.py collect --plan "output/b1/plan.json" --output "output/br1"
```

Give an independent assessor **only `output/br1/blind/`**, the source PDFs and
access to reference sources. Keep `operator-key.json`, plan and raw logs hidden
until ratings are locked. Sample labels are randomly assigned independently of
the run schedule; writing style can still reveal a model. The benchmark operator
cannot be considered fully blinded. Do not send private papers elsewhere without
authorization. Collection preserves failed/not-run entries and full finding text.

## Source-based scoring

Fill every finding's row in `blind/ratings.csv`; preserve IDs. Ideally use two
independent domain-qualified assessors, then reconcile disagreements while still
blinded. If resources permit only one assessor, have a second check all major
claims, false positives and disagreements plus a random 20% of remaining rows;
report that limitation. No automatic paid model judge is used.

| Field | Rule |
| --- | --- |
| `verdict` | `confirmed`: supported defect; `false_positive`: incorrect/already-addressed criticism; `unresolved`: insufficient evidence; `suggestion`: useful optional enhancement, not a demonstrated defect |
| `issue_key` | Same substantive concern gets the same key across samples; use the reference key when it matches, a new key for a genuinely new concern |
| `evidence_correct` | `true`, `false`, or `unknown`; independently check cited page, quote, number and external source |
| `actionability` | `0`: unusable; `1`: interpretable but vague; `2`: specific feasible correction consistent with the evidence |
| `source_check_notes` | Required source locations, reasoning and any uncertainty; do not infer correctness from confident wording |

Judge the actual claim, including qualifications. A cautious `cannot_verify`
request is not a proven defect; classify it unresolved or suggestion as appropriate.
Mark a confident invented fact or unsupported allegation false positive. Do not
reward finding count, verbosity, overlap with old reports or demands outside a
reviewer's remit. When one finding mixes valid and invalid claims, use a
conservative verdict and explain the mixture; do not split it differently across
models to improve a score. Only merge true duplicates, not related distinct issues.

After locking adjudication, score offline:

```powershell
python scripts/benchmark_scoring.py --packet "output/br1/blind" --references "output/br1/blind/reference-issues.json" --key "output/br1/operator-key.json" --output "output/br1/scores-v1.json"
```

If preparation had no ledger, use the emitted template but disclose that recall
was not preregistered. Never amend a frozen ledger after seeing candidate outputs
to improve recall. Novel confirmed issues still count for precision. A revised
ledger belongs to a new benchmark version; retain original scores.

Report these dimensions separately, with paper/role/repeat results:

- **Correctness:** deduplicated confirmed / (confirmed + false-positive) claims,
  plus lower/upper bounds treating unresolved claims as all wrong/all correct.
- **Coverage:** recall of independently confirmed known issues, also weighted by
  their preregistered impact. This is not recall of every possible paper defect.
- **Evidence and usefulness:** citation accuracy, actionability, concrete serious
  false-positive examples and behavior on clean negative controls.
- **Reliability:** completion/attempt rate, planned coverage, failures, retries and
  variability between repeats. A missing output is not an empty perfect review.
- **Resources:** elapsed time and reported uncached/cached/cache-write/output tokens
  per task, including failed attempts where counters exist; unknown stays unknown.

Summary means use only matched complete paper-role-repeat cells, with the number
of defined cells reported. They are task-macro means, not paper-balanced estimates.
Inspect missing denominators and publish failures alongside them. Duplicates are
collapsed within each reviewer sample; do not sum across roles and call that the
number of unique paper defects. Three papers and two repeats do not justify a
general winner or a significance test treating findings as independent samples.

## Usage, long papers and decision rule

Codex JSONL supplies `turn.completed` usage; the collector uses one final fresh
turn's counters, subtracts cached input from total input, and does not add reasoning
output a second time. Missing or ambiguous usage is unknown.
See [Codex noninteractive output](https://developers.openai.com/codex/noninteractive).

Claude final-result usage separates ordinary input, cache reads and cache writes;
their sum is total input. Its USD field is a provider cost estimate, **not a
subscription bill**. See [Claude usage tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking)
and [cache accounting](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

Preserve raw counters and rate-table date if later calculating an estimate. Do
not equate Codex credits with Claude USD, or cross-provider token counts with
identical text/budget. Include failed/retried work; label unreported usage as a
lower-bound gap. The pilot measures only three reviewer tasks, not whole-paper
cost. Use the long-paper full-pipeline confirmation for an actual stage-by-stage
estimate; do not multiply short-paper cost linearly by page count. Keep sleep,
outages and manual intervention separate from normal elapsed time.

Before unblinding, agree any acceptable coverage loss and serious-false-positive
tolerance. The default decision is **no automatic model/default change**. A cheaper
profile is a candidate only when its savings coexist with acceptable source-checked
coverage, reliability and false-positive behavior, confirmed on held-out papers.
Report a quality/resource trade-off, not a composite score chosen after results.

For full-pipeline confirmation, use the existing `review_paper.py` or installed
launcher in separate new workspaces with explicit backend/model/effort. Let normal
routing run and record its roster: routing is part of this test, not a controlled
fixed-stage comparison. Assess the final report independently, including whether
each consequential confirmed reviewer finding survives **in the report body**, not
just traceability IDs. Structural checks alone cannot establish scientific quality.

## Validation status

The harness has Windows offline/mock tests for preparation, both backend adapters,
input preservation, usage accounting, failure retention, blinding and scoring.
These are not live model-quality, quota, web-access or end-to-end report validation.
Claude live readiness, non-Windows execution, held-out quality and full-pipeline
benchmarking remain separate checks. Private papers and generated results must not
be committed; these checkout-only scripts are not added to the installed runtime.
