# Optional uv launcher: validation

The [README Quick Start](../README.md#quick-start) remains primary. uv is optional;
existing setup scripts, Python commands, dependencies and review methodology are
unchanged. The launcher uses authenticated Codex CLI, not a new API client.

## Local testing

From this checkout, with uv available, these do not start a review:

```text
uvx --from . economics-paper-reviewer --help
uvx --from . economics-paper-reviewer --check
```

For maintainer packaging tests, use an isolated build environment with `build`
and uv installed. Build locally, then test the local wheel (not GitHub) using a
new evidence directory. The acceptance driver uses only mocked Codex responses:

```powershell
python -m build --outdir dist
python -m unittest
$root = (Get-Location).Path
$wheel = Join-Path $root "dist/economics_paper_reviewer-0.1.0rc1-py3-none-any.whl"
python scripts/validate_cli_package.py --output "validation evidence NEW" -- uvx --from "$wheel" economics-paper-reviewer
```

Repeat the acceptance command with `--from "$root"` for the checkout. Use absolute
source paths because the driver launches from an unrelated directory. It retains
its synthetic paper, artifacts, mock report and `validation.json`; it refuses an
existing evidence directory. Clean-install and legacy setup checks are separate.

## Recorded validation - 2026-09-22

Host: Windows x64, Python 3.12.10, uv 0.12.17. Automated model calls were mocked;
deterministic PDF processing, routing checks, validation and report assembly were
real. No manuscript or private logs are included in the package or this record.
The live review below used GPT-5.6 Sol; it does not benchmark the newer GPT-6 Sol default.

| Check | Result |
| --- | --- |
| Regression tests | 195 passed initially; final launcher suite 10 passed, including two additions: 197 distinct tests |
| Local sdist-to-wheel build and clean installation | Passed; 44 canonical resources plus hash receipt; dependencies match `requirements.txt` |
| Installed wheel, local-checkout uvx and local-wheel uvx | Passed from unrelated non-Git directories with spaces; 24 mocked executions per acceptance run |
| Isolated `uv tool install` | Installed; help and mocked readiness passed |
| Persistent artifacts after recreating uv's environment/cache | Preserved; mocked editor refresh reused retained inputs and reviews |
| Interrupted selection/editor recovery | Passed with mocks; preflight reused, retained PDF usable after moving original |
| Resource/input protection and missing Codex/login diagnostics | Passed; runtime mismatches and cache/install workspaces rejected |
| Existing PowerShell setup and Python launch without uv | Fresh setup passed; full synthetic pipeline completed with 22 mocked calls |
| Generated-resource drift and repository hygiene | Passed; generated resources unchanged |

The user separately completed a **live review** of a 71-page PDF from an unrelated
Windows directory containing spaces, using the tested local wheel. A deterministic
cross-check confirmed all 20 reviewer outputs validated, 145 source findings were
accounted for in 122 canonical findings, prompts/editor input matched reconstruction,
and the final report passed consistency checks. Effective permissions were
**read-only / on-request**. All 590 live artifact files were unchanged by the audit,
which made no new model calls. Six reviewers reported partial coverage; parser
preflight had six warnings and no blockers. This was execution/integrity validation,
not an independent scientific re-review or fresh verification of every citation.

## Additional validation - 2026-09-23

The GPT-6-default release passed all 200 offline tests, fresh source/wheel builds,
clean installation, resource checks, and two local-wheel acceptance runs with 24
mocked Codex calls each. Ordinary Python launch checks passed without uv. Ubuntu
[CI passed](https://github.com/Ingar30/reviewer/actions/runs/35857500591), and an
exact-commit Git-source uvx install and `--help` passed outside Git.

Separately, both GPT-6 models completed the [71-page live comparison](model_profiles.md#recorded-full-pipeline-comparison---2026-09-23)
using the tested local wheel. The source paper and existing results were preserved.
Luna required manual continuation after laptop sleep and a wrapper timeout; this
was not an unattended-recovery pass. No paper, report or private session log is published.

## Limits and recovery

- macOS, Linux, Windows ARM and other Python versions were not tested locally.
  `setup.sh` is unchanged but was not executed on this Windows host.
- Automated recovery tests use mocked stage failures. The later live sleep/timeout
  case required manual recovery and exposed incomplete Windows process-tree cleanup;
  reliable unattended recovery, reboot, disk-full and concurrent same-paper runs
  remain unvalidated. Do not launch a duplicate while an old review process is active.
- Git-source installation/help passed for the recorded commit; this does not
  validate every future Git revision. No PyPI publication is needed.
- Resume with the same workspace, paper ID and exact runtime (retain the wheel or
  pin the Git commit). `--resume-after-preflight` reuses valid preflight, then
  reruns selection and substantive reviews; `--refresh-editor --paper-id ID
  --run-editor` reuses completed reviews. A retained PDF can replace a moved original.
- The runtime receipt does not lock the complete Python/transitive-dependency
  environment. Back up persistent workspaces and avoid concurrent same-ID runs.
- `--check` checks resources, imports and login, not model access, quota or scientific
  quality. Actual reviews consume Codex usage and retain the existing data-disclosure
  and sandbox/approval rules.

Detailed development evidence remains local under ignored `output/uv-validation/`
and the retained test workspaces. It is not part of the distributable package.
