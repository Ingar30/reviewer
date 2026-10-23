"""Version-bound source objects and conservative correspondence, never adjudication.

No network requests, OCR, inferred repairs, or executable manuscript content.
Whole-file text spans and page/crop regions complement the parser's inventories.
CSV cells have additional row/column locators. Unavailable visual correspondence
remains explicit rather than being mistaken for a deterministic text match.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import re

REGISTRY = "source_registry.json"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_artifact(root: Path, relative: str) -> Path:
    path = Path(relative)
    if (path.is_absolute() or ".." in path.parts or ":" in relative
            or "\\" in relative or not relative):
        raise ValueError("Unsafe artifact path")
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Artifact escapes parsed evidence")
    if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != root.parent):
        raise ValueError("Symlinked evidence is not supported")
    if not target.is_file():
        raise ValueError("Registered artifact is missing")
    return target


def build_registry(parsed: Path) -> dict:
    manifest = json.loads((parsed / "manifest.json").read_text(encoding="utf-8"))
    source_hash = manifest["source_pdf_sha256"]
    pages = json.loads((parsed / "page_index.json").read_text(encoding="utf-8"))
    page_by_file = {}
    for page in pages:
        for value in page.values():
            if isinstance(value, str) and "/parsed/" in value.replace("\\", "/"):
                page_by_file[value.replace("\\", "/").split("/parsed/", 1)[1]] = page["pdf_page_number"]
    for name in ("tables/table_inventory.json", "figures/figure_inventory.json"):
        path = parsed / name
        if path.exists():
            for item in json.loads(path.read_text(encoding="utf-8")):
                for value in item.values():
                    if isinstance(value, str) and "/parsed/" in value.replace("\\", "/"):
                        page_by_file[value.replace("\\", "/").split("/parsed/", 1)[1]] = item.get("page") or item.get("pdf_page_number")
    objects = []
    for path in sorted(parsed.rglob("*")):
        if not path.is_file() or path.name == REGISTRY:
            continue
        relative = path.relative_to(parsed).as_posix()
        safe_artifact(parsed, relative)
        digest = sha256(path)
        page = page_by_file.get(relative)
        if page is None and (match := re.search(r"page_(\d+)", path.name)):
            page = int(match[1])
        kind = "image_region" if path.suffix == ".png" else "text_span"
        content = None if kind == "image_region" else path.read_text(encoding="utf-8")
        locators = [(kind, {"start": 0, "end": len(content)} if content is not None else {"region": "entire_retained_image"}, None)]
        if path.suffix == ".csv":
            for row, cells in enumerate(csv.reader(io.StringIO(content)), 1):
                locators.extend(("table_cell", {"row": row, "column": col}, cell)
                                for col, cell in enumerate(cells, 1))
        for kind, locator, value in locators:
            identity = json.dumps([source_hash, relative, digest, locator], sort_keys=True)
            objects.append({"id": "OBJ-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                "path": relative, "sha256": digest, "page": page, "kind": kind,
                "locator": locator, "value": value})
    registry = {"version": 1, "source_pdf_sha256": source_hash,
                "page_count": manifest["summary"]["page_count"], "objects": objects}
    (parsed / REGISTRY).write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return registry


def corresponding_text(text: str) -> str:
    # Only discretionary SOFT hyphens at a line wrap, never a visible hyphen:
    # x-\ny and alpha-\nbeta may be subtraction, not word hyphenation.
    # Preserve signs, decimal points, percentages, inequalities and subscripts.
    return " ".join(re.sub(r"(?<=[A-Za-z])\u00ad\r?\n(?=[A-Za-z])", "", text).split())


def quote_corresponds(quote: str, text: str) -> bool:
    quote, text = corresponding_text(quote), corresponding_text(text)
    # A quoted numeric/token fragment must not drop a sign, decimal prefix or
    # subscript. This establishes correspondence, never contextual relevance.
    before = r"(?<![\w.+,\-\u2212])" if re.match(r"[\w.+\-\u2212]", quote) else ""
    # A sentence-ending period is not a decimal suffix; .5 and exponent
    # fragments still cannot shed their preceding sign/mantissa.
    after = r"(?![\w%]|[.,]\d)" if quote and (quote[-1].isalnum() or quote[-1] in "_%") else ""
    return bool(quote) and re.search(before + re.escape(quote) + after, text) is not None


def check_source(source: dict, parsed: Path, registry: dict, *, paper_id: str) -> dict:
    result = {"source_id": source.get("id"), "located": False,
              "correspondence": "unchecked", "relevance": "not_assessed",
              "criticism_support": "not_assessed", "errors": []}
    mode = source.get("correspondence")
    if source.get("type") == "external":
        # URL syntax is checked separately; offline checks never retrieve URLs.
        result["correspondence"] = "retrieval_asserted_not_independently_checked" if mode == "retrieved_external" else "url_only"
        if mode == "retrieved_external" and not str(source.get("verification_note") or "").strip():
            result["errors"].append("Retrieved external evidence needs a retrieval/context note")
        return result
    manifest = json.loads((parsed / "manifest.json").read_text(encoding="utf-8"))
    if registry.get("source_pdf_sha256") != manifest.get("source_pdf_sha256"):
        result["errors"].append("Registry belongs to a different PDF")
        return result
    obj = next((o for o in registry["objects"] if o["id"] == source.get("object_id")), None)
    if obj is None:
        result["errors"].append("Missing or unknown registered source object ID")
        return result
    expected_path = f"work/{paper_id}/parsed/{obj['path']}"
    if str(source.get("path")).replace("\\", "/") != expected_path:
        result["errors"].append("Registered source object and cited path differ")
        return result
    try:
        path = safe_artifact(parsed, obj["path"])
        if sha256(path) != obj["sha256"]:
            raise ValueError("Registered source artifact changed")
    except (OSError, ValueError) as exc:
        result["errors"].append(str(exc))
        return result
    page = source.get("page")
    if page is not None and (type(page) is not int or not 1 <= page <= registry["page_count"]):
        result["errors"].append("Invalid source page")
    if obj["page"] is not None and page != obj["page"]:
        result["errors"].append("Cited page differs from registered object page")
    result["located"] = not result["errors"]
    if mode in {"visual", "unresolved"}:
        result["correspondence"] = "visual_assessment_required" if mode == "visual" else "unresolved"
        if not str(source.get("verification_note") or "").strip():
            result["errors"].append("Visual/unresolved evidence needs an explicit verification note")
        return result
    if mode != "text":
        result["errors"].append("Manuscript evidence needs text, visual or unresolved correspondence")
        return result
    quote = source.get("text_quote")
    if not isinstance(quote, str) or not quote.strip() or obj["kind"] == "image_region":
        result["errors"].append("Text correspondence needs a nonempty quote and textual object")
        return result
    text = obj["value"] if obj["kind"] == "table_cell" else path.read_text(encoding="utf-8")
    if not quote_corresponds(quote, text):
        result["errors"].append("Quote/value does not correspond to registered source; inspect visual evidence explicitly")
        result["correspondence"] = "mismatch"
        # A digit adjacent to prose may be a footnote, exponent or meaningful
        # token. Do not guess, strip it, or silently certify a text mismatch.
        # Point the repair at intact same-page visual evidence when available.
        for visual in registry["objects"]:
            if (visual["kind"] != "image_region" or page is None
                    or visual["page"] != page):
                continue
            try:
                image = safe_artifact(parsed, visual["path"])
                if sha256(image) != visual["sha256"]:
                    continue
            except (OSError, ValueError):
                continue
            result.setdefault("visual_candidates", []).append({
                "object_id": visual["id"],
                "path": f"work/{paper_id}/parsed/{visual['path']}", "page": page})
    else:
        result["correspondence"] = "matched_text_not_adjudicated"
    return result


def review_evidence_checks(data: dict, repo: Path) -> list[dict]:
    parsed = repo / "work" / data["paper_id"] / "parsed"
    sources = [(f["id"], s, f"findings.{fi}.source_objects.{si}")
               for fi, f in enumerate(data.get("findings", []))
               for si, s in enumerate(f.get("source_objects", []))]
    if not sources:
        return []
    try:
        registry = json.loads((parsed / REGISTRY).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        registry = None
    return [{"reviewer": data.get("reviewer"), "finding_id": fid, "field": field,
             "path": s.get("path"), "object_id": s.get("object_id"),
             **(check_source(s, parsed, registry, paper_id=data["paper_id"]) if registry is not None
                else {"source_id": s.get("id"), "errors": [
                    "Source registry missing/invalid; reprocess in a new workspace, preserving legacy evidence."]})}
            for fid, s, field in sources]


def evidence_error_messages(checks: list[dict]) -> list[str]:
    """Located repair feedback shared by CLI, native and optional adapters."""
    messages = []
    for check in checks:
        label = (f"reviewer/stage={check.get('reviewer')} finding={check.get('finding_id')} "
                 f"source={check.get('source_id')} object={check.get('object_id')} "
                 f"field={check.get('field')} artifact={check.get('path')}")
        for error in check["errors"]:
            message = f"{label}: {error}"
            if check.get("visual_candidates"):
                candidates = "; ".join(f"{v['object_id']} at {v['path']} (PDF page {v['page']})"
                                       for v in check["visual_candidates"])
                message += (". Intact visual candidates (not yet inspected): " + candidates
                            + ". Only after inspection, use correspondence=visual with an explicit "
                            "verification_note identifying the image and what it establishes; otherwise "
                            "retain unresolved/cannot_verify. Do not alter the quote to force a match.")
            messages.append(message)
    return messages
