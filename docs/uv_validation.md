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
