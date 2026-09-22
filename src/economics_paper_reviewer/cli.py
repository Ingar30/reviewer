"""Stage a persistent workspace and invoke the existing, unmodified pipeline."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib


RECEIPT = ".reviewer-workspace.json"


def bundled_runtime() -> Path:
    return Path(__file__).resolve().parent / "runtime"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_files(runtime: Path) -> dict[str, str]:
    manifest = json.loads((runtime / RECEIPT).read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or not manifest.get("files"):
        raise ValueError("Unsupported or empty runtime manifest; rebuild/reinstall this package.")
    for name, digest in manifest["files"].items():
        path = runtime / name
        if not path.resolve().is_relative_to(runtime.resolve()) or not path.is_file():
            raise ValueError(f"Missing or unsafe bundled resource: {name}")
        if sha256(path) != digest:
            raise ValueError(f"Bundled resource differs from its manifest: {name}")
    return manifest["files"]


def validate_workspace_location(workspace: Path, runtime: Path) -> None:
    # uv can discard installations/caches. Never put research artifacts there.
    excluded = [runtime.resolve(), Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()]
    for name in ("UV_CACHE_DIR", "UV_TOOL_DIR"):
        if os.environ.get(name):
            excluded.append(Path(os.environ[name]).expanduser().resolve())
    home = Path.home()
    excluded.extend([
        home / ".cache" / "uv", home / "Library" / "Caches" / "uv",
        home / ".local" / "share" / "uv",
        Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "uv",
        Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "uv",
        Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / "uv",
        Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "uv",
    ])
    # Also detect custom --cache-dir locations, which uv need not export as an env var.
    in_cache = any((parent / "CACHEDIR.TAG").is_file() for parent in (workspace, *workspace.parents))
    if in_cache or any(workspace.is_relative_to(path.resolve()) for path in excluded):
        raise ValueError("Choose --workspace outside Python installations and uv cache/tool directories.")


def prepare_workspace(workspace: Path, runtime: Path) -> None:
    validate_workspace_location(workspace, runtime)
    files = runtime_files(runtime)
    receipt = workspace / RECEIPT
    if receipt.exists():
        if receipt.read_bytes() != (runtime / RECEIPT).read_bytes():
            raise ValueError(
                "Workspace uses a different runtime. Resume with the original package/version, "
                "or choose a new --workspace for a new run. Existing files were not overwritten."
            )
        for name, digest in files.items():
            target = workspace / name
            if (not target.resolve().is_relative_to(workspace) or not target.is_file()
                    or sha256(target) != digest):
                raise ValueError(f"Workspace runtime resource changed or missing: {name}; not overwriting it.")
        return
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError("--workspace must be empty or an existing launcher workspace; not overwriting it.")
    workspace.mkdir(parents=True, exist_ok=True)
    for name in files:
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(runtime / name, target)
    (workspace / ".gitignore").write_text("*\n", encoding="utf-8")
    shutil.copyfile(runtime / RECEIPT, receipt)


def check_codex(cwd: Path) -> None:
    executable = next((path for name in ("codex.cmd", "codex.exe", "codex")
                       if (path := shutil.which(name))), None)
    if executable is None:
        raise ValueError(
            "Codex CLI was not found on PATH. Install Codex CLI, run `codex login` "
            "with your ChatGPT account, then retry. No API key is required."
        )
    try:
        result = subprocess.run(
            [executable, "login", "status"], cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Could not check Codex authentication. Run `codex login status` in this shell.") from exc
    if result.returncode:
        # Do not echo login output: some CLI versions include credential details.
        raise ValueError(
            "Codex authentication is missing or could not be checked. Run `codex login`, "
            "then `codex login status` in this shell. No API key is required."
        )


def keep_input(source: Path, workspace: Path, category: str) -> Path:
    destination = workspace / "inputs" / category / sha256(source) / source.name
    if not destination.resolve().is_relative_to(workspace):
        raise ValueError("Workspace input path escapes the workspace.")
    if destination.exists():
        if sha256(destination) != sha256(source):
            raise ValueError(f"Saved input changed; not overwriting it: {destination}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--workspace", default="reviewer-workspace")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--refresh-editor", action="store_true")
    parser.add_argument("--pdf")
    parser.add_argument("--reviewers-config")
    args, forwarded = parser.parse_known_args(argv)
    runtime = bundled_runtime()
    script = "refresh_editor.py" if args.refresh_editor else "review_paper.py"
    if "--help" in forwarded or "-h" in forwarded:
        print(
            "Optional launcher: economics-paper-reviewer [--workspace DIR] [pipeline options]\n"
            "  --workspace DIR   Persistent local workspace (default: ./reviewer-workspace)\n"
            "  --check           Check resources, dependencies and Codex login; no review\n"
            "  --refresh-editor  Use the existing editor-refresh helper and its options\n"
            "Relative input paths are resolved from your current directory.\n",
            flush=True,
        )
        return subprocess.run([sys.executable, str(runtime / "scripts" / script), "--help"]).returncode
    try:
        workspace = Path(args.workspace).expanduser().resolve()
        validate_workspace_location(workspace, runtime)
        runtime_files(runtime)
        if args.check:
            for module in ("fitz", "pdfplumber", "pandas", "jsonschema", "tabulate"):
                importlib.import_module(module)
            check_codex(Path.cwd())
            print(f"OK: bundled resources, Python dependencies and Codex login checked.\nWorkspace: {workspace}")
            print("No review run; model access, quota and live sandbox behavior were not tested.")
            return 0
        if not args.refresh_editor and not args.pdf:
            raise ValueError("--pdf is required (or use --help / --check / --refresh-editor).")
        inputs = {}
        for option, value in (("--pdf", args.pdf), ("--reviewers-config", args.reviewers_config)):
            if value:
                source = Path(value).expanduser().resolve(strict=True)
                if not source.is_file() or (option == "--pdf" and source.suffix.lower() != ".pdf"):
                    raise ValueError(f"Invalid input for {option}: {source}")
                inputs[option] = source
        check_codex(Path.cwd())
        prepare_workspace(workspace, runtime)
        for option, source in inputs.items():
            saved = keep_input(source, workspace, "papers" if option == "--pdf" else "config")
            forwarded.extend([option, str(saved)])
        # An untrusted/non-Git workspace may not load project config in Codex.
        # Pass the canonical model explicitly, without changing permission settings.
        defaults = tomllib.loads((workspace / ".codex" / "config.toml").read_text(encoding="utf-8"))
        default_options = {"--model": defaults["model"]}
        if args.refresh_editor:
            default_options["--reasoning-effort"] = defaults["model_reasoning_effort"]
        for option, value in default_options.items():
            if not any(item == option or item.startswith(option + "=") for item in forwarded):
                forwarded.extend([option, value])
        env = os.environ.copy()
        env["ECONOMICS_REVIEWER_NON_GIT"] = "1"
        print(f"[workspace] {workspace}", flush=True)
        print(f"[outputs] {workspace / 'outputs'}", flush=True)
        return subprocess.run(
            [sys.executable, str(workspace / "scripts" / script), *forwarded],
            cwd=workspace, env=env,
        ).returncode
    except (OSError, ValueError, ImportError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. Workspace retained; see --resume-after-preflight or --refresh-editor.", file=sys.stderr)
        return 130
