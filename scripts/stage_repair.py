"""One preserved repair per CLI stage, within an explicit per-paper call cap.

Callers hold the paper lease. Reservation precedes dispatch, so interruption or
failure consumes the allowance. No evidence, reasons or completion are invented.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil


def reserve_repair(work_root: Path, stage: str, limit: int, candidate: Path,
                   errors: list[str], original_prompt: str, repo: Path) -> tuple[Path, str] | None:
    if type(limit) is not int or limit < 0:
        raise ValueError("Repair call cap must be a nonnegative integer")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", stage):
        raise ValueError("Invalid repair stage")
    root = work_root / "repairs"
    prior = sorted(root.glob("*/request.json"))
    # Never silently reset the one-shot stage allowance on resume/refresh.
    if len(prior) >= limit or any(json.loads(p.read_text(encoding="utf-8"))["stage"] == stage for p in prior):
        return None
    folder = root / f"{len(prior)+1:02d}"
    folder.mkdir(parents=True)  # Existing/unrecorded reservation fails closed.
    previous = folder / "previous.json"
    shutil.copy2(candidate, previous)
    prompt = (original_prompt.rstrip() + "\n\nOne bounded repair of this stage only.\n"
        "The previous response was NOT accepted. Read the preserved response at "
        + previous.relative_to(repo).as_posix() + ".\n"
        "Correct the precise errors below using the assigned sources. Do any missing work; "
        "do not invent quotations, reasons, sources or completion. If the evidence/work "
        "remains unavailable, report that honestly even if this stage remains blocked. "
        "Return the entire replacement JSON, not a patch.\nValidation errors:\n"
        + json.dumps(errors, ensure_ascii=False, indent=2) + "\n")
    (folder / "prompt.txt").write_text(prompt, encoding="utf-8")
    (folder / "request.json").write_text(json.dumps({"stage": stage, "call_reserved": True,
        "errors": errors, "previous_sha256": hashlib.sha256(previous.read_bytes()).hexdigest()}, indent=2)+"\n", encoding="utf-8")
    return folder, prompt
