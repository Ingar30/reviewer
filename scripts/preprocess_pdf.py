from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pandas as pd
import pdfplumber

HEADING_RE = re.compile(
    r"^(?:"
    r"(abstract|introduction|conclusion|references|bibliography|appendix(?:es)?|online appendix)"
    r"|(?:[0-9]+(?:\.[0-9]+)*)\s+[A-Z].{0,120}"
    r"|(?:[IVXLC]+)\.\s+[A-Z].{0,120}"
    r")$",
    re.IGNORECASE,
)

CITATION_PATTERNS = [
    re.compile(r"\(([A-Z][A-Za-z'`\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z'`\-]+)?(?:\s+et al\.)?,\s*(?:19|20)\d{2}[a-z]?(?:;\s*[^)]*)?)\)"),
    re.compile(r"\b([A-Z][A-Za-z'`\-]+(?:\s+et al\.)?\s*\((?:19|20)\d{2}[a-z]?\))"),
    re.compile(r"(\[[0-9,\-\s]+\])"),
]

NUMBER_PATTERN = re.compile(
    r"""
    (?<![\w.])
    (?:[$€£]\s*)?
    -?
    (?:
        \d{1,3}(?:,\d{3})+(?:\.\d+)?
        |
        \d+\.\d+
        |
        \d+
    )
    (?:\s?(?:%|pp|bps|bp|percent|percentage\ points|million|billion|trillion|k|m|bn))?
    (?![\w.])
    """,
    re.IGNORECASE | re.VERBOSE,
)

CROSSREF_PATTERN = re.compile(
    r"\b(?P<kind>Table|Figure|Fig\.|Section|Appendix|Eq\.|Equation)\s+(?P<label>[A-Z]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

REF_START_RE = re.compile(r"^\s*(references|bibliography)\s*$", re.IGNORECASE)
REF_ENTRY_START_RE = re.compile(
    r"^\s*(?:\[\d+\]\s*)?[A-Z][A-Za-z'`\-]+,\s*(?:[A-Z]\.)?(?:.*?)(?:19|20)\d{2}[a-z]?\."
)
APPENDIX_START_RE = re.compile(r"^\s*(appendix|online appendix)\b", re.IGNORECASE)


@dataclass
class PageMeta:
    pdf_page_index: int
    pdf_page_number: int
    page_label: str | None
    page_width: float
    page_height: float
    raw_text_path: str
    normalized_text_path: str
    image_path: str
    words_path: str
    blocks_path: str
    extracted_char_count: int
    likely_scanned: bool


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "paper"


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_heading(line: str) -> bool:
    s = " ".join(line.strip().split())
    if not s:
        return False
    if len(s) > 140:
        return False
    if s.endswith((".", ",", ";", ":")):
        return False
    if REF_START_RE.match(s) or APPENDIX_START_RE.match(s):
        return True
    if HEADING_RE.match(s):
        return True
    if s.isupper() and 2 <= len(s.split()) <= 12:
        return True
    if re.match(r"^(?:[0-9]+(?:\.[0-9]+)*)\s+\S+", s):
        return True
    return False


def normalize_page_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def extract_page_text(page: fitz.Page) -> tuple[str, str, list[list[Any]], list[list[Any]]]:
    raw_text = page.get_text("text", sort=False) or ""
    sorted_text = page.get_text("text", sort=True) or raw_text
    words = page.get_text("words", sort=True) or []
    blocks = page.get_text("blocks", sort=True) or []
    return raw_text, sorted_text, words, blocks if isinstance(blocks, list) else []


def save_page_image(page: fitz.Page, out_path: Path, dpi: int = 200) -> None:
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    pix.save(out_path)


def extract_sections(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for page in page_records:
        page_no = page["pdf_page_number"]
        lines = page["normalized_text"].splitlines()
        for idx, line in enumerate(lines, start=1):
            if is_heading(line):
                heading = " ".join(line.strip().split())
                if current is not None:
                    current["end_page"] = page_no
                    current["end_line"] = idx - 1 if idx > 1 else None
                    sections.append(current)
                current = {
                    "heading": heading,
                    "start_page": page_no,
                    "start_line": idx,
                    "end_page": None,
                    "end_line": None,
                }

    if current is not None:
        current["end_page"] = page_records[-1]["pdf_page_number"] if page_records else None
        current["end_line"] = None
        sections.append(current)

    return sections


def extract_citations(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()

    for page in page_records:
        text = page["normalized_text"]
        for pattern in CITATION_PATTERNS:
            for match in pattern.finditer(text):
                key = (page["pdf_page_number"], match.start(), match.group(0))
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "page": page["pdf_page_number"],
                        "page_label": page["page_label"],
                        "match": match.group(0),
                        "match_start": match.start(),
                        "match_end": match.end(),
                        "pattern": pattern.pattern,
                    }
                )
    return out


def extract_numbers(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()

    for page in page_records:
        text = page["normalized_text"]
        for match in NUMBER_PATTERN.finditer(text):
            key = (page["pdf_page_number"], match.start(), match.group(0))
            if key in seen:
                continue
            seen.add(key)
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            out.append(
                {
                    "page": page["pdf_page_number"],
                    "page_label": page["page_label"],
                    "number": match.group(0).strip(),
                    "match_start": match.start(),
                    "match_end": match.end(),
                    "context": text[start:end].replace("\n", " "),
                }
            )
    return out


def extract_crossrefs(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in page_records:
        text = page["normalized_text"]
        for match in CROSSREF_PATTERN.finditer(text):
            out.append(
                {
                    "page": page["pdf_page_number"],
                    "page_label": page["page_label"],
                    "reference_text": match.group(0),
                    "kind": match.group("kind"),
                    "label": match.group("label"),
                    "match_start": match.start(),
                    "match_end": match.end(),
                }
            )
    return out


def extract_reference_list(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines_with_meta: list[dict[str, Any]] = []
    for page in page_records:
        for idx, line in enumerate(page["normalized_text"].splitlines(), start=1):
            lines_with_meta.append(
                {
                    "page": page["pdf_page_number"],
                    "page_label": page["page_label"],
                    "line_number": idx,
                    "text": line.strip(),
                }
            )

    start_idx = None
    for i, item in enumerate(lines_with_meta):
        if REF_START_RE.match(item["text"]):
            start_idx = i + 1
            break

    if start_idx is None:
        return []

    ref_lines = lines_with_meta[start_idx:]
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for item in ref_lines:
        text = item["text"]
        if not text:
            continue
        if APPENDIX_START_RE.match(text):
            break
        if REF_ENTRY_START_RE.match(text) or (current is None):
            if current is not None:
                current["text"] = " ".join(current["chunks"]).strip()
                del current["chunks"]
                entries.append(current)
            current = {
                "start_page": item["page"],
                "start_page_label": item["page_label"],
                "start_line": item["line_number"],
                "chunks": [text],
            }
        else:
            assert current is not None
            current["chunks"].append(text)

    if current is not None:
        current["text"] = " ".join(current["chunks"]).strip()
        del current["chunks"]
        entries.append(current)

    for i, entry in enumerate(entries, start=1):
        entry["reference_id"] = i

    return entries


def extract_figures(doc: fitz.Document) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    for i, page in enumerate(doc, start=1):
        images = page.get_images(full=True)
        for j, img in enumerate(images, start=1):
            bbox_list = []
            try:
                rects = page.get_image_rects(img)
                for rect in rects:
                    bbox_list.append([rect.x0, rect.y0, rect.x1, rect.y1])
            except Exception:
                bbox_list = []
            figures.append(
                {
                    "figure_id": f"page_{i:03d}_image_{j:02d}",
                    "page": i,
                    "page_label": page.get_label(),
                    "xref": img[0],
                    "bbox_list": bbox_list,
                }
            )
    return figures


def extract_tables_with_pymupdf(page: fitz.Page) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not hasattr(page, "find_tables"):
        return found

    try:
        table_finder = page.find_tables()
        tables = getattr(table_finder, "tables", []) or []
        for idx, table in enumerate(tables, start=1):
            rows = table.extract()[:] if hasattr(table, "extract") else []
            found.append(
                {
                    "source": "pymupdf",
                    "table_index_on_page": idx,
                    "bbox": list(table.bbox) if hasattr(table, "bbox") else None,
                    "header_names": list(table.header.names) if getattr(table, "header", None) else [],
                    "rows": rows,
                }
            )
    except Exception:
        return []

    return found


def extract_tables_with_pdfplumber(pdf_path: Path, page_number_1based: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[page_number_1based - 1]
        tables = page.extract_tables() or []
        for idx, rows in enumerate(tables, start=1):
            found.append(
                {
                    "source": "pdfplumber",
                    "table_index_on_page": idx,
                    "rows": rows,
                }
            )
    return found


def save_tables(doc: fitz.Document, pdf_path: Path, tables_dir: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    table_counter = 1

    for page_number, page in enumerate(doc, start=1):
        page_tables = extract_tables_with_pymupdf(page)
        if not page_tables:
            page_tables = extract_tables_with_pdfplumber(pdf_path, page_number)

        for t in page_tables:
            rows = t.get("rows") or []
            csv_path = tables_dir / f"table_{table_counter}.csv"
            raw_json_path = tables_dir / f"table_{table_counter}.raw.json"
            markdown_path = tables_dir / f"table_{table_counter}.md"

            max_cols = max((len(r) for r in rows), default=0)
            normalized_rows = []
            for r in rows:
                vals = ["" if v is None else str(v) for v in r]
                if len(vals) < max_cols:
                    vals.extend([""] * (max_cols - len(vals)))
                normalized_rows.append(vals)

            if normalized_rows:
                df = pd.DataFrame(normalized_rows)
                df.to_csv(csv_path, index=False, header=False, encoding="utf-8")
                markdown_text = df.to_markdown(index=False)
            else:
                csv_path.write_text("", encoding="utf-8")
                markdown_text = ""

            markdown_path.write_text(markdown_text, encoding="utf-8")
            write_json(raw_json_path, t)

            inventory.append(
                {
                    "table_id": table_counter,
                    "page": page_number,
                    "page_label": page.get_label(),
                    "source": t.get("source"),
                    "table_index_on_page": t.get("table_index_on_page"),
                    "bbox": t.get("bbox"),
                    "header_names": t.get("header_names", []),
                    "csv_path": str(csv_path.as_posix()),
                    "markdown_path": str(markdown_path.as_posix()),
                    "raw_json_path": str(raw_json_path.as_posix()),
                    "row_count": len(normalized_rows),
                    "col_count": max_cols,
                    "status": "ok" if normalized_rows else "empty",
                }
            )
            table_counter += 1

    return inventory


def build_full_text(page_records: list[dict[str, Any]]) -> str:
    chunks = []
    for page in page_records:
        chunks.append(
            f"# Page {page['pdf_page_number']}"
            + (f" (label: {page['page_label']})" if page["page_label"] else "")
            + "\n\n"
            + page["normalized_text"].strip()
            + "\n"
        )
    return "\n\n".join(chunks).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Preprocess a paper PDF into structured artifacts.")
    parser.add_argument("--pdf", required=True, help="Path to input PDF")
    parser.add_argument("--paper-id", default=None, help="Optional paper id; defaults to filename stem")
    parser.add_argument("--dpi", type=int, default=200, help="DPI for saved page images")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {pdf_path.name}")

    paper_id = slugify(args.paper_id or pdf_path.stem)
    repo_root = Path.cwd()
    work_root = repo_root / "work" / paper_id
    parsed_dir = work_root / "parsed"
    reviews_dir = work_root / "reviews"

    raw_pages_dir = parsed_dir / "raw_pages"
    pages_dir = parsed_dir / "pages"
    words_dir = parsed_dir / "words"
    blocks_dir = parsed_dir / "blocks"
    tables_dir = parsed_dir / "tables"
    figures_dir = parsed_dir / "figures"
    page_images_dir = parsed_dir / "page_images"

    for d in [
        parsed_dir,
        reviews_dir,
        raw_pages_dir,
        pages_dir,
        words_dir,
        blocks_dir,
        tables_dir,
        figures_dir,
        page_images_dir,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    page_records: list[dict[str, Any]] = []
    likely_scanned_pages = []

    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            pdf_page_number = page_index + 1
            page_label = page.get_label()
            raw_text, sorted_text, words, blocks = extract_page_text(page)
            normalized_text = normalize_page_text(sorted_text)

            raw_text_path = raw_pages_dir / f"page_{pdf_page_number:03d}.txt"
            normalized_text_path = pages_dir / f"page_{pdf_page_number:03d}.md"
            words_path = words_dir / f"page_{pdf_page_number:03d}.words.json"
            blocks_path = blocks_dir / f"page_{pdf_page_number:03d}.blocks.json"
            image_path = page_images_dir / f"page_{pdf_page_number:03d}.png"

            raw_text_path.write_text(raw_text, encoding="utf-8")
            normalized_text_path.write_text(
                f"# Page {pdf_page_number}"
                + (f" (label: {page_label})" if page_label else "")
                + "\n\n"
                + normalized_text,
                encoding="utf-8",
            )
            write_json(words_path, words)
            write_json(blocks_path, blocks)
            save_page_image(page, image_path, dpi=args.dpi)

            likely_scanned = len(raw_text.strip()) == 0 and len(words) == 0
            if likely_scanned:
                likely_scanned_pages.append(pdf_page_number)

            page_meta = PageMeta(
                pdf_page_index=page_index,
                pdf_page_number=pdf_page_number,
                page_label=page_label,
                page_width=float(page.rect.width),
                page_height=float(page.rect.height),
                raw_text_path=str(raw_text_path.relative_to(repo_root).as_posix()),
                normalized_text_path=str(normalized_text_path.relative_to(repo_root).as_posix()),
                image_path=str(image_path.relative_to(repo_root).as_posix()),
                words_path=str(words_path.relative_to(repo_root).as_posix()),
                blocks_path=str(blocks_path.relative_to(repo_root).as_posix()),
                extracted_char_count=len(raw_text),
                likely_scanned=likely_scanned,
            )

            page_records.append(
                {
                    **asdict(page_meta),
                    "raw_text": raw_text,
                    "normalized_text": normalized_text,
                }
            )

        full_text = build_full_text(page_records)
        (parsed_dir / "full_text.md").write_text(full_text, encoding="utf-8")

        page_index_json = []
        for rec in page_records:
            copy = {k: v for k, v in rec.items() if k not in {"raw_text", "normalized_text"}}
            page_index_json.append(copy)
        write_json(parsed_dir / "page_index.json", page_index_json)

        sections = extract_sections(page_records)
        citations = extract_citations(page_records)
        numbers = extract_numbers(page_records)
        crossrefs = extract_crossrefs(page_records)
        references = extract_reference_list(page_records)
        tables_inventory = save_tables(doc, pdf_path, tables_dir)
        figures_inventory = extract_figures(doc)

    write_json(parsed_dir / "sections.json", sections)
    write_json(parsed_dir / "in_text_citations.json", citations)
    write_json(parsed_dir / "reference_list.json", references)
    write_json(parsed_dir / "numbers_in_text.json", numbers)
    write_json(parsed_dir / "crossrefs.json", crossrefs)
    write_json(tables_dir / "table_inventory.json", tables_inventory)
    write_json(figures_dir / "figure_inventory.json", figures_inventory)

    manifest = {
        "paper_id": paper_id,
        "source_pdf": str(pdf_path),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "tool_versions": {
            "python": sys.version,
            "pymupdf": getattr(fitz, "VersionBind", None),
            "pdfplumber": getattr(pdfplumber, "__version__", None),
            "pandas": getattr(pd, "__version__", None),
        },
        "settings": {
            "dpi": args.dpi,
            "ocr_used": False,
            "project_root": str(repo_root),
        },
        "summary": {
            "page_count": len(page_records),
            "likely_scanned_pages": likely_scanned_pages,
            "section_count": len(sections),
            "citation_candidate_count": len(citations),
            "reference_count": len(references),
            "numeric_claim_candidate_count": len(numbers),
            "crossref_count": len(crossrefs),
            "table_count": len(tables_inventory),
            "figure_count": len(figures_inventory),
        },
    }
    write_json(parsed_dir / "manifest.json", manifest)

    print(json.dumps(
        {
            "status": "ok",
            "paper_id": paper_id,
            "parsed_dir": str(parsed_dir),
            "reviews_dir": str(reviews_dir),
            "page_count": len(page_records),
            "likely_scanned_pages": likely_scanned_pages,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
