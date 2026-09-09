"""Build/check the self-contained skills-only package from an explicit allowlist.

Never bundle inputs, work, outputs, credentials, CLI launchers, or environments.
Generated runtime files are distribution snapshots; edit only canonical sources.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

from reviewer_config import load_reviewers_config

PLUGIN_NAME = "economics-paper-reviewer"
# Entry points, not a second manually maintained dependency list. New local imports
# under scripts/ follow these roots automatically, including function-local imports.
RUNTIME_ENTRYPOINTS = ("preprocess_pdf.py", "work_plugin.py", "prepare_work_environment.py")
EXCLUDED_SCRIPTS = {"review_paper.py", "select_reviewers.py", "refresh_editor.py", "build_work_plugin.py"}
CANONICAL_SKILL = ".agents/skills/paper-reviewer"
CANONICAL_GUIDANCE = "reviewer-guidance/paper-reviewer.md"
REPO_MARKETPLACE = ".agents/plugins/marketplace.json"
RESOURCE_TREES = {"config": {".json"}, "prompts/templates": {".txt"},
                  "schemas": {".json"}, CANONICAL_SKILL: {".md", ".txt", ".json"}}
PACKAGE_FILES = (
    ".codex-plugin/plugin.json", "skills/review-paper/SKILL.md",
    "skills/review-paper/agents/openai.yaml", "skills/review-paper/references/orchestration.md",
    "assets/logo.svg",
)
RUNTIME_PATH = "skills/review-paper/runtime"


def canonical_files(repo: Path) -> list[str]:
    reviewers = load_reviewers_config(repo / "config/reviewers.json", enabled_only=False)
    templates = sorted({r.prompt for r in reviewers} | {
        "editor_report.txt", "reviewer_contract.txt", "reviewer_selection.txt"})
    files = {"LICENSE.md", "requirements.txt", f"{CANONICAL_SKILL}/SKILL.md",
             "config/reviewers.json", "schemas/reviewer_output.schema.json",
             "schemas/reviewer_selection.schema.json",
             *("prompts/templates/" + name for name in templates)}
    for root, extensions in RESOURCE_TREES.items():
        files.update(path.relative_to(repo).as_posix() for path in (repo / root).rglob("*")
                     if path.is_file() and path.suffix in extensions)
    files.update("scripts/" + name for name in runtime_scripts(repo))
    return sorted(files)


def runtime_scripts(repo: Path) -> list[str]:
    """Static local-import closure; never follow imports into CLI model launchers."""
    pending, included = list(RUNTIME_ENTRYPOINTS), set()
    while pending:
        name = pending.pop()
        if name in included:
            continue
        if name in EXCLUDED_SCRIPTS:
            raise ValueError(f"Native adapter depends on excluded CLI/build script: {name}")
        tree = ast.parse(source_bytes(repo / "scripts" / name), filename=name)
        included.add(name)
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                local = module.replace(".", "/") + ".py"
                if (repo / "scripts" / local).is_file():
                    pending.append(local)
    return sorted(included)


def source_bytes(path: Path) -> bytes:
    # Stable across LF/CRLF checkouts; no semantic changes to canonical content.
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError(f"Refusing a symlinked package resource: {path.name}")
    return path.read_text(encoding="utf-8").encode("utf-8")


def runtime_payload(repo: Path) -> dict[str, bytes]:
    files = {}
    for relative in canonical_files(repo):
        path = repo / relative
        if (PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts
                or "\\" in relative or ":" in relative or not path.resolve().is_relative_to(repo.resolve())):
            raise ValueError(f"Canonical resource escapes the repository: {relative}")
        files[bundled_path(relative)] = source_bytes(path)
    manifest = {"format": 1, "files": {relative: hashlib.sha256(data).hexdigest()
                                       for relative, data in sorted(files.items())}}
    files["bundle_manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    return files


def bundled_path(relative: str) -> str:
    # Ship the canonical skill as a reference, not a second discoverable CLI skill.
    # Preserve relative reference paths alongside it without rewriting its content.
    if relative == f"{CANONICAL_SKILL}/SKILL.md":
        return CANONICAL_GUIDANCE
    if relative.startswith(CANONICAL_SKILL + "/"):
        return "reviewer-guidance/" + relative[len(CANONICAL_SKILL) + 1:]
    return relative


def retired_runtime_files(plugin: Path, payload: dict[str, bytes]) -> list[Path]:
    """Only retire unmodified files owned by the previous generated manifest."""
    runtime = plugin / RUNTIME_PATH
    manifest_path = runtime / "bundle_manifest.json"
    if not manifest_path.is_file():
        return []
    previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    retired = []
    for relative, expected in previous["files"].items():
        parts = PurePosixPath(relative)
        path = runtime / relative
        if (parts.is_absolute() or ".." in parts.parts or "\\" in relative or ":" in relative
                or not path.resolve().is_relative_to(runtime.resolve())
                or path.is_symlink() or any(parent.is_symlink() for parent in path.parents)):
            raise ValueError("Unsafe path in previous generated manifest.")
        if relative not in payload and path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Retired generated file has local edits; preserve and inspect it: {relative}")
            retired.append(path)
    return retired


def check_bundle(repo: Path, plugin: Path) -> list[str]:
    failures = []
    expected = runtime_payload(repo)
    runtime = plugin / RUNTIME_PATH
    for relative, data in expected.items():
        path = runtime / relative
        if not path.is_file() or path.read_bytes() != data:
            failures.append(f"Missing/stale generated runtime file: {relative}")
    allowed = set(PACKAGE_FILES) | {f"{RUNTIME_PATH}/{name}" for name in expected}
    for path in plugin.rglob("*"):
        if "__pycache__" in path.parts:
            continue
        if path.is_symlink():
            failures.append(f"Symlink in package: {path.relative_to(plugin)}")
        elif path.name == "SKILL.md" and path.relative_to(plugin).as_posix() != "skills/review-paper/SKILL.md":
            failures.append(f"Unexpected discoverable skill in package: {path.relative_to(plugin)}")
        elif path.is_file() and path.relative_to(plugin).as_posix() not in allowed:
            failures.append(f"Unexpected file in package: {path.relative_to(plugin)}")
    for relative in PACKAGE_FILES:
        if not (plugin / relative).is_file():
            failures.append(f"Missing package file: {relative}")
    manifest_path = plugin / ".codex-plugin/plugin.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("name") != plugin.name or manifest.get("skills") != "./skills/":
            failures.append("Plugin identity or skills path does not match its folder.")
        if any(k in manifest for k in ("apps", "mcpServers", "hooks")):
            failures.append("This package must remain skills-only.")
        interface = manifest.get("interface", {})
        if "screenshots" in interface:
            failures.append("Skills-only submissions cannot include interface.screenshots.")
        for key in ("displayName", "shortDescription"):
            if not 1 <= len(interface.get(key, "")) <= 30:
                failures.append(f"{key} must have 1-30 characters for directory submission.")
        prompts = interface.get("defaultPrompt", [])
        if not 1 <= len(prompts) <= 3 or len(set(prompts)) != len(prompts):
            failures.append("Use 1-3 unique starter prompts.")
        if any(not p.strip() or len(p) > 128 or "@" in p or "\n" in p for p in prompts):
            failures.append("Invalid starter prompt.")
    return failures


def build(repo: Path, plugin: Path, *, check: bool = False, archive: Path | None = None) -> list[str]:
    payload = runtime_payload(repo)
    if not check:
        retired = retired_runtime_files(plugin, payload)
        for relative, data in payload.items():
            target = plugin / RUNTIME_PATH / relative
            if target.is_symlink() or not target.resolve().is_relative_to(plugin.resolve()):
                raise ValueError("Runtime target escapes plugin directory.")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != data:
                target.write_bytes(data)
        for path in retired:
            path.unlink()
            print(f"Removed retired generated snapshot: {path.relative_to(plugin)}")
    failures = check_bundle(repo, plugin)
    if failures or archive is None:
        return failures
    if archive.exists() or archive.resolve().is_relative_to(plugin.resolve()):
        raise ValueError("Choose a new archive path outside the plugin folder; existing ZIPs are never overwritten.")
    archive.parent.mkdir(parents=True, exist_ok=True)
    files = {relative: source_bytes(plugin / relative) for relative in PACKAGE_FILES}
    files.update({f"{RUNTIME_PATH}/{relative}": data for relative, data in payload.items()})
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as output:
        for relative, data in sorted(files.items()):
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            output.writestr(info, data)
    return []


def git_output(repo: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=repo, capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError("Release provenance requires a Git checkout and an existing tag at HEAD.")
    return result.stdout.strip()


def check_repo_marketplace(repo: Path) -> None:
    catalog = json.loads(source_bytes(repo / REPO_MARKETPLACE))
    entries = [entry for entry in catalog.get("plugins", []) if entry.get("name") == PLUGIN_NAME]
    if (catalog.get("name") != "reviewer" or len(entries) != 1
            or entries[0].get("source") != {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"}
            or entries[0].get("policy") != {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}):
        raise ValueError("Repository marketplace must expose the canonical generated plugin without extra product/auth requirements.")


def release_provenance(repo: Path, plugin: Path, tag: str) -> dict:
    """Refuse to label uncommitted, untracked or mismatched source as a release."""
    check_repo_marketplace(repo)
    version = json.loads(source_bytes(plugin / ".codex-plugin/plugin.json"))["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version) or tag != "v" + version:
        raise ValueError("Release tag must be v<plugin version>, without a local cachebuster.")
    commit = git_output(repo, "rev-parse", "HEAD")
    if git_output(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}") != commit:
        raise ValueError("Release tag must point at the checked-out HEAD commit.")
    if git_output(repo, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Release requires a clean working tree; commit and test the generated snapshot first.")
    payload = runtime_payload(repo)
    tracked = set(git_output(repo, "ls-files").splitlines())
    package_root = plugin.relative_to(repo).as_posix()
    required = set(canonical_files(repo)) | {REPO_MARKETPLACE} | {f"{package_root}/{path}" for path in PACKAGE_FILES}
    required.update(f"{package_root}/{RUNTIME_PATH}/{path}" for path in payload)
    if required - tracked:
        raise ValueError("Every canonical and generated package resource must be tracked at the release tag.")
    return {"format": 1, "repository": "https://github.com/Ingar30/reviewer",
            "tag": tag, "commit": commit, "plugin_version": version,
            "runtime_manifest_sha256": hashlib.sha256(payload["bundle_manifest.json"]).hexdigest()}


def build_release(repo: Path, plugin: Path, destination: Path, tag: str) -> Path:
    provenance = release_provenance(repo, plugin, tag)
    failures = check_bundle(repo, plugin)
    if failures:
        raise ValueError("\n".join(failures))
    if destination.exists() or destination.resolve().is_relative_to(plugin.resolve()):
        raise ValueError("Release needs a new directory outside the plugin; old releases are never overwritten.")
    destination.mkdir(parents=True)
    archive = destination / f"{PLUGIN_NAME}-{provenance['plugin_version']}.zip"
    build(repo, plugin, check=True, archive=archive)
    provenance["archive"] = archive.name
    provenance["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as bundle:
        provenance["files"] = {name: hashlib.sha256(bundle.read(name)).hexdigest() for name in bundle.namelist()}
    # A sidecar avoids embedding HEAD into a committed snapshot (a circular hash).
    (destination / "release.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on stale bundles; do not write files.")
    parser.add_argument("--zip", type=Path, help="Write an install/submission ZIP to a new path.")
    parser.add_argument("--private-marketplace", type=Path,
                        help="Create a fresh private test catalog (does not install or change user settings).")
    parser.add_argument("--release-tag", help="Require a clean checkout at v<plugin version> and emit release provenance.")
    parser.add_argument("--release-dir", type=Path, help="New output directory for the release ZIP and release.json receipt.")
    args = parser.parse_args()
    if bool(args.release_tag) != bool(args.release_dir):
        parser.error("--release-tag and --release-dir must be used together")
    if args.release_tag and (args.zip or args.private_marketplace):
        parser.error("release mode cannot be combined with --zip or --private-marketplace")
    repo = Path(__file__).resolve().parents[1]
    plugin = repo / "plugins" / PLUGIN_NAME
    try:
        check_repo_marketplace(repo)
        if args.release_tag:
            archive = build_release(repo, plugin, args.release_dir, args.release_tag)
            print(f"Release ZIP: {archive}\nProvenance: {args.release_dir / 'release.json'}")
            return 0
        failures = build(repo, plugin, check=args.check, archive=args.zip)
        if failures:
            print("\n".join(failures))
            return 1
        if args.private_marketplace:
            make_private_marketplace(repo, plugin, args.private_marketplace)
    except (ValueError, OSError) as exc:
        print(str(exc))
        return 1
    print("OK: skills-only bundle matches canonical sources; no private runtime files included.")
    if args.zip:
        print(f"ZIP: {args.zip}")
    return 0


def make_private_marketplace(repo: Path, plugin: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError("Private test marketplace needs a new directory; existing catalogs are not overwritten.")
    failures = check_bundle(repo, plugin)
    if failures:
        raise ValueError("\n".join(failures))
    payload = {relative: source_bytes(plugin / relative) for relative in PACKAGE_FILES}
    payload.update({f"{RUNTIME_PATH}/{relative}": data for relative, data in runtime_payload(repo).items()})
    destination.mkdir(parents=True)
    for relative, data in payload.items():
        target = destination / "plugins" / PLUGIN_NAME / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    catalog = {"name": "reviewer-private", "interface": {"displayName": "Paper Reviewer (private test)"},
               "plugins": [{"name": PLUGIN_NAME,
                            "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
                            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                            "category": "Productivity"}]}
    path = destination / ".agents/plugins/marketplace.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
