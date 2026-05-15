# Parser Repair Agent Experiment

## Objective

Test whether adding another LLM agent after parser-quality preflight can address parser limitations and fix issues before parsed evidence is passed to substantive reviewers.

## Implementation Tested

This historical experiment introduced a parser repair planner and newer overlay mode. The current wrapper now runs overlay mode by default when parser-quality preflight reports high- or medium-severity parser artifacts:

```powershell
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --parser-repair plan
.\.venv\Scripts\python.exe scripts\review_paper.py --pdf "inputs\my-paper.pdf" --parser-repair overlay
```

When enabled, the wrapper:

1. preprocesses the PDF
2. renders initial prompts
3. runs `parser_quality_auditor`
4. validates and gates parser-quality findings
5. runs `scripts/run_parser_repair_agent.py`
6. writes `work/<paper_id>/repair/parser_repair_plan.json`
7. writes `work/<paper_id>/repair/parser_repair_notes.md`
8. in overlay mode, writes `work/<paper_id>/repair/repaired_artifacts/` and `work/<paper_id>/repair/repair_manifest.json`
9. passes the repair-notes path into reviewer selection and substantive reviewer prompts

The repair planner is conditional. `--parser-repair plan` and `--parser-repair overlay` check the parser-quality JSON first and invoke the LLM only when high- or medium-severity `parser_artifact` findings are reported. If no such issue is reported, the repair step is skipped.

The repair planner uses `schemas/parser_repair_plan.schema.json`. It is asked to cover each high- or medium-severity parser artifact, identify safe fallback artifacts, identify artifacts that should not be primary evidence, and distinguish mitigated issues from issues that still require deterministic preprocessing changes. In overlay mode, it may also include small repaired artifact contents in the JSON plan; the deterministic runner writes those contents under `work/<paper_id>/repair/repaired_artifacts/` and records provenance in `repair_manifest.json`. It never overwrites the canonical parse under `work/<paper_id>/parsed/`.

After the LLM returns the structured plan, the runner applies a narrow deterministic quality pass to generated overlay artifact content. This pass only scans generated overlay strings and small referenced text sources; it does not rescan the full paper. It normalizes common UTF-8/CP1252 mojibake such as `Ã—` or `âˆ—` when the conversion clearly reduces suspicious markers, records before/after scores in `repair_manifest.json`, and leaves warnings in the manifest if suspicious markers remain.

## Safety Constraint

A first live repair-agent run on private prior-paper artifacts was blocked because it would export private parsed-paper artifacts and parser-review outputs to an external service. After explicit user approval, real-paper runs were performed only on papers with reported high- or medium-severity parser artifacts.

The branch also includes a synthetic fixture under:

```text
tests/fixtures/parser_repair/synthetic-parser/
```

The fixture contains no private paper text and was used as a safe non-private smoke test. It simulates two parser-quality defects:

- broken structured table extraction with usable raw-page fallback
- scrambled normalized page text with usable raw-page fallback

## Evidence

### Real Papers

Parser-quality issue scan found high- or medium-severity parser artifacts in the prior paper runs. The repair planner was run on three known weak parser cases: `paper1`, `paper2`, and `paper9`.

Commands:

```powershell
.\.venv\Scripts\python.exe scripts\run_parser_repair_agent.py `
  --paper-id paper1 `
  --parsed-dir work\paper1\parsed `
  --parser-quality-output work\paper1\reviews\parser_quality_auditor.json `
  --output-dir work\experiments\parser-repair-agent-real\paper1\repair `
  --notes-output work\experiments\parser-repair-agent-real\paper1\repair\parser_repair_notes.md `
  --log-dir work\experiments\parser-repair-agent-real\paper1\logs

.\.venv\Scripts\python.exe scripts\run_parser_repair_agent.py `
  --paper-id paper2 `
  --parsed-dir work\paper2\parsed `
  --parser-quality-output work\paper2\reviews\parser_quality_auditor.json `
  --output-dir work\experiments\parser-repair-agent-real\paper2\repair `
  --notes-output work\experiments\parser-repair-agent-real\paper2\repair\parser_repair_notes.md `
  --log-dir work\experiments\parser-repair-agent-real\paper2\logs

.\.venv\Scripts\python.exe scripts\run_parser_repair_agent.py `
  --paper-id paper9 `
  --parsed-dir work\paper9\parsed `
  --parser-quality-output work\paper9\reviews\parser_quality_auditor.json `
  --output-dir work\experiments\parser-repair-agent-real\paper9\repair `
  --notes-output work\experiments\parser-repair-agent-real\paper9\repair\parser_repair_notes.md `
  --log-dir work\experiments\parser-repair-agent-real\paper9\logs
```

Results:

| Paper | Parser targets | Repair entries | Score | Unmitigated |
| --- | ---: | ---: | ---: | --- |
| paper1 | 2 | 3 | 100.0 | none |
| paper2 | 4 | 4 | 100.0 | none |
| paper9 | 4 | 4 | 100.0 | none |

Scoring command:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_parser_repair.py `
  --papers paper1 paper2 paper9 `
  --work-root work `
  --repair-root work\experiments\parser-repair-agent-real `
  --output-json work\evaluations\parser_repair_agent_real.json `
  --output-md work\evaluations\parser_repair_agent_real.md
```

Aggregate score:

| Metric | Score |
| --- | ---: |
| mean score | 100.0 |
| mean coverage score | 100.0 |
| mean mitigation score | 100.0 |
| mean guidance score | 100.0 |

The real-paper plans correctly framed their output as fallback routing. For example, `paper9` was marked as partially mitigated for broken table extraction, unreliable figure crops, contradictory page-8 figure assignments, and scrambled reading order; the plan routed reviewers to page images, raw text, words, blocks, and embedded-image inventories rather than claiming that structured tables, crops, or page order had been repaired.

Prompt handoff was also smoke-tested with real `paper9` repair notes:

```powershell
.\.venv\Scripts\python.exe scripts\render_prompts.py `
  --paper-id paper9 `
  --parsed-dir work\paper9\parsed `
  --reviews-dir work\paper9\reviews `
  --schema-path schemas\reviewer_output.schema.json `
  --output-dir work\experiments\parser-repair-agent-real\paper9\prompt-render-smoke `
  --reviewers-config work\paper9\selection\selected_reviewers.json `
  --parser-repair-notes work\experiments\parser-repair-agent-real\paper9\repair\parser_repair_notes.md
```

The repair overlay was appended to substantive reviewer prompts and not appended to `parser_quality_audit.txt`.

### Synthetic Fixture

Live synthetic repair-agent command:

```powershell
.\.venv\Scripts\python.exe scripts\run_parser_repair_agent.py `
  --paper-id synthetic-parser `
  --parsed-dir tests\fixtures\parser_repair\synthetic-parser\parsed `
  --parser-quality-output tests\fixtures\parser_repair\synthetic-parser\reviews\parser_quality_auditor.json `
  --output-dir work\experiments\parser-repair-agent\synthetic-parser\repair `
  --notes-output work\experiments\parser-repair-agent\synthetic-parser\repair\parser_repair_notes.md `
  --log-dir work\experiments\parser-repair-agent\synthetic-parser\logs
```

Result:

- repair entries: 2
- target parser findings covered: 2 of 2
- generated plan: `work/experiments/parser-repair-agent/synthetic-parser/repair/parser_repair_plan.json`
- generated notes: `work/experiments/parser-repair-agent/synthetic-parser/repair/parser_repair_notes.md`

Scoring command:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_parser_repair.py `
  --papers synthetic-parser `
  --work-root tests\fixtures\parser_repair `
  --repair-root work\experiments\parser-repair-agent `
  --output-json work\evaluations\parser_repair_agent_synthetic.json `
  --output-md work\evaluations\parser_repair_agent_synthetic.md
```

Score:

| Metric | Score |
| --- | ---: |
| mean score | 100.0 |
| mean coverage score | 100.0 |
| mean mitigation score | 100.0 |
| mean guidance score | 100.0 |

Prompt handoff smoke test:

```powershell
.\.venv\Scripts\python.exe scripts\render_prompts.py `
  --paper-id paper9 `
  --parsed-dir work\paper9\parsed `
  --reviews-dir work\paper9\reviews `
  --schema-path schemas\reviewer_output.schema.json `
  --output-dir work\experiments\parser-repair-agent\prompt-render-smoke `
  --reviewers-config work\paper9\selection\selected_reviewers.json `
  --parser-repair-notes work\paper9\repair\parser_repair_notes.md
```

The repair overlay was appended to substantive reviewer prompts and not appended to `parser_quality_audit.txt`.

## Interpretation

The added agent is useful as a repair overlay and evidence-routing step. It can translate parser-quality findings into clear downstream instructions:

- which fallback artifacts to trust
- which structured artifacts should not be primary evidence
- which parser defects remain unresolved
- which deterministic fixes are still required

It should not be described as fully fixing parser issues. In the successful synthetic test, the agent did not reconstruct the broken table or rewrite page text; it mitigated risk by telling reviewers to prefer raw-page fallback evidence and avoid misleading structured artifacts.

## Recommendation

Incorporate the parser repair planner and overlay repair mode into the default reviewer workflow, while preserving `--parser-repair off` for faster or cheaper runs and `--parser-repair plan` for guidance-only repair.

Use it when:

- parser-quality preflight reports medium-severity parser artifacts
- usable fallback artifacts exist
- overlay mode can make a narrow, evidence-preserving artifact from existing text, image, inventory, words, or blocks
- the user explicitly approves sending the relevant parsed artifacts to the LLM service, or the run uses synthetic/redacted/local artifacts

Do not rely on it when:

- full OCR, complex table reconstruction, crop regeneration, or page-order repair is required
- no trustworthy fallback artifact exists
- private parsed artifacts cannot be exported and the user has not explicitly approved the export

Before promoting it to default, compare downstream reviewer outputs with and without the repair overlay on approved real-paper runs. The current evidence supports using the planner to reduce parser-induced reviewer mistakes, but not to replace deterministic preprocessing fixes.
