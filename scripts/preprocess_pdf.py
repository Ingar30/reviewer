from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pandas as pd
import pdfplumber

HEADING_RE = re.compile(
    r"^(?:"
    r"(abstract|introduction|conclusion|references|bibliography|appendix(?:es)?|online appendix)"
    r"|(?:[IVXLC]+)\.\s+[A-Z].{0,120}"
    r")$",
    re.IGNORECASE,
)
APPENDIX_HEADING_RE = re.compile(
    r"^(?:[A-Z]\s+[A-Z].{0,120}|[A-Z]\.\d+(?:\.\d+)*\s+[A-Z].{0,120})$"
)

TABLE_CAPTION_RE = re.compile(
    r"^\s*Table\s+(?P<label>(?:[A-Z]\.)?\d+(?:\.\d+)?[A-Za-z]?)\s*:\s*(?P<title>.+?)\s*$",
    re.IGNORECASE,
)
FIGURE_CAPTION_RE = re.compile(
    r"^\s*(?:Figure|Fig\.)\s+(?P<label>(?:[A-Z]\.)?\d+(?:\.\d+)?[A-Za-z]?)\s*:\s*(?P<title>.+?)\s*$",
    re.IGNORECASE,
)
ANY_CAPTION_RE = re.compile(
    r"^\s*(?:Table|Figure|Fig\.)\s+(?:[A-Z]\.)?\d+(?:\.\d+)?[A-Za-z]?\s*:",
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
    [-−]?
    (?:
        \d{1,3}(?:,\d{3})+(?:\.\d+)?
        |
        \d+\.\d+
        |
        \.\d+
        |
        \d+
    )
    (?:\s?(?:%|pp|bps|bp|percent|percentage\ points|million|billion|trillion|k|m|bn))?
    (?![\w.])
    """,
    re.IGNORECASE | re.VERBOSE,
)

CROSSREF_LABEL_RE = r"(?:[A-Z]\.)?\d+(?:\.\d+)*[A-Za-z]?|[A-Z](?:\.\d+)*|\d+[A-Za-z]?"
CROSSREF_PATTERN = re.compile(
    rf"\b(?P<kind>Table|Figure|Fig\.|Section|Appendix|Eq\.|Equation)"
    rf"\s+(?:\((?P<label_paren>{CROSSREF_LABEL_RE})\)(?![A-Za-z])|(?P<label>{CROSSREF_LABEL_RE})(?![A-Za-z]))",
    re.IGNORECASE,
)
FIGURE_TABLE_XREF_LABEL_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*[A-Za-z]?|[A-Z]\.\d+(?:\.\d+)*[A-Za-z]?)$"
)
SECTION_XREF_LABEL_RE = re.compile(r"^(?:\d+(?:\.\d+)*[A-Za-z]?|[A-Z](?:\.\d+)*)$")
APPENDIX_XREF_LABEL_RE = re.compile(r"^[A-Z](?:\.\d+)*$")
EQUATION_XREF_LABEL_RE = re.compile(r"^(?:\d+(?:\.\d+)*[A-Za-z]?|[A-Z]\.\d+(?:\.\d+)*)$")

REF_START_RE = re.compile(r"^\s*(references|bibliography)\s*$", re.IGNORECASE)
REF_ENTRY_START_RE = re.compile(
    r"^\s*(?:\[\d+\]\s*)?"
    r"(?:[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'`.\-]+"
    r"|(?:[Vv]an|[Vv]on|[Dd]e|[Dd]el|[Dd]a|[Dd]i|[Ll]e|[Ll]a)"
    r"\s+[A-ZÀ-ÖØ-Þ]?[A-Za-zÀ-ÖØ-öø-ÿ'`.\-]+)"
    r"(?:,|\s+and\s+).{2,}",
)
REPEATED_AUTHOR_ENTRY_START_RE = re.compile(
    r"^(?:and\s*,|(?:,\s*)+(?:and\s+)?).{2,}",
    re.IGNORECASE,
)
APPENDIX_START_RE = re.compile(
    r"^\s*(?:(?:[A-Z]\s+)?(?:appendix|online appendix)\b|(?:appendix|online appendix)\s+[A-Z]\b)",
    re.IGNORECASE,
)
REF_SECTION_END_RE = re.compile(
    r"^\s*(?:for online publication only:?|(?:[A-Z]\s+)?(?:(?:main|additional)\s+)?(?:figures and tables|tables and figures))\s*$",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b", re.IGNORECASE)
REFERENCE_HYPHEN_BREAK_RE = re.compile(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])-\s+(?=[a-zà-öø-ÿ])")
TABLE_TRAILING_CELL_RE = re.compile(
    r"(?<!\S)(?P<cell>"
    r"\(\s*[-−]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"\s*,\s*[-−]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)\s*\)(?:\*+)?"
    r"|\(\s*[-−]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"\s?(?:%|pp|bps|bp)?\s*\)(?:\*+)?"
    r"|[-−]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"\s?(?:%|pp|bps|bp)?(?:\*+)?"
    r"|Yes|No|[-\u2013\u2014]|✓"
    r")\s*$",
    re.IGNORECASE,
)
PAGE_LABEL_LINE_RE = re.compile(r"^(?:\d{1,4}|[ivxlcdmIVXLCDM]{1,12})$")


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
    embedded_image_coverage_ratio: float
    ocr_recommended: bool
    ocr_reason: str | None
    two_column_detected: bool
    normalized_text_strategy: str
    landscape: bool
    raw_sorted_similarity: float


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "paper"


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root).as_posix())
    except ValueError:
        return str(path)


def line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def context_around(text: str, start: int, end: int, window: int = 100) -> str:
    before = max(0, start - window)
    after = min(len(text), end + window)
    return " ".join(text[before:after].split())


def join_reference_chunks(chunks: list[str]) -> str:
    text = " ".join(chunk.strip() for chunk in chunks if chunk.strip())
    return REFERENCE_HYPHEN_BREAK_RE.sub("", text).strip()


def repeated_author_entry_start(text: str, current: dict[str, Any] | None) -> bool:
    if current is None:
        return False
    previous_text = join_reference_chunks(current["chunks"])
    return bool(YEAR_RE.search(previous_text) and REPEATED_AUTHOR_ENTRY_START_RE.match(text))


def is_heading(line: str) -> bool:
    s = " ".join(line.strip().split())
    if not s:
        return False
    if len(s) > 140:
        return False
    if s.endswith((".", ",", ";", ":")):
        return False
    if looks_like_table_or_axis_line(s):
        return False
    if REF_SECTION_END_RE.match(s):
        return True
    if REF_START_RE.match(s) or APPENDIX_START_RE.match(s):
        return True
    roman_heading = re.match(r"^(?P<num>[IVXLC]+)\.\s+", s, re.IGNORECASE)
    if roman_heading and roman_heading.group("num") != roman_heading.group("num").upper():
        return False
    if HEADING_RE.match(s):
        return True
    if APPENDIX_HEADING_RE.match(s):
        return True
    numeric_heading = re.match(r"^(?P<num>[0-9]+(?:\.[0-9]+)*)\s+(?P<title>[A-Z].*)", s)
    if numeric_heading:
        first_number = int(numeric_heading.group("num").split(".")[0])
        title = numeric_heading.group("title")
        if first_number < 1 or first_number > 9:
            return False
        if re.search(r"\.\s+\S", title):
            return False
        if re.match(r"^(?:NOK|USD|EUR|GBP)\b", title):
            return False
        return True
    if s.isupper() and 2 <= len(s.split()) <= 12:
        words = re.findall(r"[A-Z]+", s)
        if words and len(set(words)) < len(words):
            return False
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
    blocks = page.get_text("blocks", sort=False) or []
    return raw_text, sorted_text, words, blocks if isinstance(blocks, list) else []


def native_blocks_are_column_major(blocks: list[list[Any]], page_width: float) -> bool:
    midpoint = page_width / 2
    tolerance = page_width * 0.06
    sequence: list[str] = []
    for block in blocks:
        if len(block) <= 6 or block[6] != 0 or not clean_inline_text(block[4]):
            continue
        x0, x1 = float(block[0]), float(block[2])
        center = (x0 + x1) / 2
        if x1 <= midpoint + tolerance and center < midpoint:
            column = "left"
        elif x0 >= midpoint - tolerance and center > midpoint:
            column = "right"
        else:
            continue
        if not sequence or sequence[-1] != column:
            sequence.append(column)
    return sequence == ["left", "right"]


def choose_normalized_text(
    raw_text: str,
    sorted_text: str,
    blocks: list[list[Any]],
    page_width: float,
    two_column_detected: bool,
) -> tuple[str, str]:
    if two_column_detected and native_blocks_are_column_major(blocks, page_width):
        return raw_text, "native_content_order_two_column"
    return sorted_text, "coordinate_sorted"


def embedded_image_coverage_ratio(page: fitz.Page) -> float:
    page_area = float(page.rect.get_area())
    if page_area <= 0:
        return 0.0

    image_area = 0.0
    for image in page.get_images(full=True):
        try:
            rects = page.get_image_rects(image)
        except Exception:
            continue
        for rect in rects:
            clipped = rect & page.rect
            if not clipped.is_empty:
                image_area += float(clipped.get_area())
    return round(min(1.0, image_area / page_area), 3)


def two_column_layout_detected(page: fitz.Page) -> bool:
    blocks = [
        block
        for block in (page.get_text("blocks", sort=False) or [])
        if len(block) > 6 and block[6] == 0 and clean_inline_text(block[4])
    ]
    if len(blocks) < 4:
        return False

    midpoint = float(page.rect.width) / 2
    tolerance = float(page.rect.width) * 0.06
    left = [
        block
        for block in blocks
        if float(block[2]) <= midpoint + tolerance
        and (float(block[0]) + float(block[2])) / 2 < midpoint
    ]
    right = [
        block
        for block in blocks
        if float(block[0]) >= midpoint - tolerance
        and (float(block[0]) + float(block[2])) / 2 > midpoint
    ]
    left_chars = sum(len(clean_inline_text(block[4])) for block in left)
    right_chars = sum(len(clean_inline_text(block[4])) for block in right)
    return len(left) >= 2 and len(right) >= 2 and left_chars >= 180 and right_chars >= 180


def text_order_similarity(raw_text: str, sorted_text: str) -> float:
    def lines(text: str) -> list[str]:
        return [clean_inline_text(line) for line in text.splitlines() if clean_inline_text(line)]

    return round(SequenceMatcher(None, lines(raw_text), lines(sorted_text), autojunk=False).ratio(), 3)


def save_page_image(page: fitz.Page, out_path: Path, dpi: int = 200) -> None:
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    pix.save(out_path)


def save_page_clip_image(page: fitz.Page, out_path: Path, bbox: list[float], dpi: int = 200) -> bool:
    clip = fitz.Rect(*bbox) & page.rect
    if clip.is_empty or clip.width < 1 or clip.height < 1:
        return False
    pix = page.get_pixmap(dpi=dpi, alpha=False, clip=clip)
    pix.save(out_path)
    return True


def relative_artifact_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root).as_posix())
    except ValueError:
        return str(path.as_posix())


def clean_inline_text(text: str) -> str:
    return " ".join(str(text).replace("\u00a0", " ").split())


def normalize_page_label(label: str | None) -> str | None:
    cleaned = clean_inline_text(label or "")
    return cleaned or None


def plausible_page_label_line(line: str) -> str | None:
    text = clean_inline_text(line)
    if not PAGE_LABEL_LINE_RE.fullmatch(text):
        return None
    if text.isdigit():
        page_number = int(text)
        if page_number == 0 or page_number > 300:
            return None
    return text


def infer_page_label_from_text(*texts: str) -> str | None:
    for text in texts:
        lines = [clean_inline_text(line) for line in text.splitlines()]
        nonempty = [line for line in lines if line]
        if not nonempty:
            continue
        for line in [*nonempty[-5:], *nonempty[:3]]:
            candidate = plausible_page_label_line(line)
            if candidate is not None:
                return candidate
    return None


def clean_page_label(page: fitz.Page, raw_text: str, sorted_text: str) -> str | None:
    return normalize_page_label(page.get_label()) or infer_page_label_from_text(raw_text, sorted_text)


def page_label_for(page_labels: dict[int, str | None] | None, page_number: int, page: fitz.Page) -> str | None:
    if page_labels is not None:
        return page_labels.get(page_number)
    raw_text = page.get_text("text", sort=False) or ""
    sorted_text = page.get_text("text", sort=True) or raw_text
    return clean_page_label(page, raw_text, sorted_text)


def group_words_into_lines(words: list[list[Any]], page_height: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current: list[list[Any]] = []
    current_y: float | None = None
    y_tolerance = 3.0

    usable_words = [w for w in words if len(w) >= 5 and str(w[4]).strip()]
    for word in sorted(usable_words, key=lambda w: (float(w[1]), float(w[0]))):
        y0 = float(word[1])
        if current_y is None or abs(y0 - current_y) <= y_tolerance:
            current.append(word)
            current_y = y0 if current_y is None else ((current_y * (len(current) - 1)) + y0) / len(current)
            continue

        rows.append(line_from_words(current, page_height))
        current = [word]
        current_y = y0

    if current:
        rows.append(line_from_words(current, page_height))

    return [row for row in rows if row["text"]]


def line_from_words(words: list[list[Any]], page_height: float) -> dict[str, Any]:
    ordered = sorted(words, key=lambda w: float(w[0]))
    text = clean_inline_text(" ".join(str(w[4]) for w in ordered))
    bbox = [
        min(float(w[0]) for w in ordered),
        min(float(w[1]) for w in ordered),
        max(float(w[2]) for w in ordered),
        max(float(w[3]) for w in ordered),
    ]
    return {
        "text": text,
        "bbox": bbox,
        "is_page_footer": bool(re.fullmatch(r"\d+", text)) and bbox[1] > page_height * 0.82,
    }


def union_bboxes(bboxes: list[list[float]]) -> list[float]:
    return [
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    ]


def positioned_text_lines(page: fitz.Page) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    text_dict = page.get_text("dict", sort=False) or {}
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = clean_inline_text(
                "".join(str(span.get("text", "")) for span in line.get("spans", []))
            )
            bbox = [float(value) for value in line.get("bbox", [])]
            if not text or len(bbox) != 4:
                continue
            lines.append(
                {
                    "text": text,
                    "bbox": bbox,
                    "is_page_footer": bool(re.fullmatch(r"\d+", text))
                    and bbox[1] > float(page.rect.height) * 0.82,
                }
            )
    return lines


def group_positioned_rows(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[list[dict[str, Any]]] = []
    row_y_values: list[float] = []
    for line in sorted(lines, key=lambda item: (item["bbox"][1], item["bbox"][0])):
        y0 = float(line["bbox"][1])
        if rows and abs(y0 - row_y_values[-1]) <= 3.5:
            rows[-1].append(line)
            row_y_values[-1] = sum(float(item["bbox"][1]) for item in rows[-1]) / len(rows[-1])
        else:
            rows.append([line])
            row_y_values.append(y0)

    grouped: list[dict[str, Any]] = []
    for row in rows:
        ordered = sorted(row, key=lambda item: item["bbox"][0])
        grouped.append(
            {
                "text": clean_inline_text(" ".join(item["text"] for item in ordered)),
                "bbox": union_bboxes([item["bbox"] for item in ordered]),
            }
        )
    return grouped


def caption_column_bounds(page: fitz.Page, caption_bbox: list[float]) -> tuple[float, float]:
    page_width = float(page.rect.width)
    midpoint = float(page.rect.x0) + page_width / 2
    caption_width = caption_bbox[2] - caption_bbox[0]
    if caption_bbox[0] < midpoint < caption_bbox[2] or caption_width >= page_width * 0.55:
        return float(page.rect.x0) + 24, float(page.rect.x1) - 24
    if (caption_bbox[0] + caption_bbox[2]) / 2 < midpoint:
        return float(page.rect.x0) + 24, midpoint - 4
    return midpoint + 4, float(page.rect.x1) - 24


def table_region_above_caption(
    page: fitz.Page,
    lines: list[dict[str, Any]],
    caption_bbox: list[float],
) -> dict[str, Any] | None:
    column_x0, column_x1 = caption_column_bounds(page, caption_bbox)
    eligible = []
    for line in lines:
        bbox = line["bbox"]
        center_x = (bbox[0] + bbox[2]) / 2
        if (
            not line.get("is_page_footer")
            and column_x0 <= center_x <= column_x1
            and bbox[3] <= caption_bbox[1] + 1
        ):
            eligible.append(line)

    rows = group_positioned_rows(eligible)
    selected: list[dict[str, Any]] = []
    boundary = caption_bbox[1]
    for row in reversed(rows):
        gap = boundary - row["bbox"][3]
        if gap < -8:
            continue
        if gap > (30 if not selected else 22):
            break
        if caption_bbox[1] - row["bbox"][1] > 380:
            break
        row_has_cells = bool(split_trailing_table_cells(row["text"])[1])
        if selected and (
            ANY_CAPTION_RE.match(row["text"])
            or (is_heading(row["text"]) and not row_has_cells)
        ):
            break
        selected.append(row)
        boundary = row["bbox"][1]

    selected.reverse()
    raw_lines = [row["text"] for row in selected]
    numeric_rows = sum(bool(split_trailing_table_cells(text)[1]) for text in raw_lines)
    if numeric_rows < 2:
        return None

    content_bbox = union_bboxes([row["bbox"] for row in selected])
    crop_bbox = union_bboxes([content_bbox, caption_bbox])
    crop_bbox = [
        max(float(page.rect.x0), crop_bbox[0] - 12),
        max(float(page.rect.y0), crop_bbox[1] - 8),
        min(float(page.rect.x1), crop_bbox[2] + 12),
        min(float(page.rect.y1), crop_bbox[3] + 8),
    ]
    return {"raw_lines": raw_lines, "crop_bbox": crop_bbox, "content_bbox": content_bbox}


def rects_are_near(a: fitz.Rect, b: fitz.Rect, gap: float = 18) -> bool:
    horizontal_gap = max(a.x0 - b.x1, b.x0 - a.x1, 0.0)
    vertical_gap = max(a.y0 - b.y1, b.y0 - a.y1, 0.0)
    return horizontal_gap <= gap and vertical_gap <= gap


def merge_visual_rects(rects: list[fitz.Rect]) -> list[fitz.Rect]:
    regions: list[fitz.Rect] = []
    for rect in rects:
        merged = fitz.Rect(rect)
        changed = True
        while changed:
            changed = False
            remaining: list[fitz.Rect] = []
            for region in regions:
                if rects_are_near(merged, region):
                    merged |= region
                    changed = True
                else:
                    remaining.append(region)
            regions = remaining
        regions.append(merged)
    return regions


def page_visual_regions(page: fitz.Page) -> list[fitz.Rect]:
    rects: list[fitz.Rect] = []
    for image in page.get_images(full=True):
        try:
            rects.extend(page.get_image_rects(image))
        except Exception:
            continue
    try:
        rects.extend(page.cluster_drawings())
    except Exception:
        pass
    clipped = []
    for rect in rects:
        candidate = fitz.Rect(rect) & page.rect
        if not candidate.is_empty and candidate.width >= 12 and candidate.height >= 12:
            clipped.append(candidate)
    return merge_visual_rects(clipped)


def figure_crop_above_caption(
    page: fitz.Page, caption_bbox: list[float]
) -> list[float] | None:
    caption = fitz.Rect(*caption_bbox)
    candidates = []
    for region in page_visual_regions(page):
        gap = caption.y0 - region.y1
        horizontal_overlap = min(region.x1, caption.x1) - max(region.x0, caption.x0)
        if -6 <= gap <= 48 and (horizontal_overlap > 0 or caption.width >= page.rect.width * 0.55):
            candidates.append((max(gap, 0.0), -region.get_area(), region))
    if not candidates:
        return None

    _gap, _area, visual = min(candidates, key=lambda item: (item[0], item[1]))
    crop = visual | caption
    return [
        max(float(page.rect.x0), crop.x0 - 12),
        max(float(page.rect.y0), crop.y0 - 12),
        min(float(page.rect.x1), crop.x1 + 12),
        min(float(page.rect.y1), crop.y1 + 8),
    ]


def looks_like_table_or_axis_line(text: str) -> bool:
    s = clean_inline_text(text)
    if ANY_CAPTION_RE.match(s):
        return True
    numeric_tokens = re.findall(r"[-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", s)
    if len(numeric_tokens) >= 3:
        alpha_tokens = re.findall(r"[A-Za-z]+", s)
        if len(alpha_tokens) <= 8:
            return True
    if re.fullmatch(r"(?:[-−]?\d+(?:\.\d+)?\s+){2,}[-−]?\d+(?:\.\d+)?", s):
        return True
    return False


def should_append_heading_continuation(heading_so_far: str, next_line: str) -> bool:
    text = clean_inline_text(next_line)
    if not text or len(text) > 80:
        return False
    if is_heading(text) or looks_like_table_or_axis_line(text):
        return False
    if re.fullmatch(r"\d+", text):
        return False
    return heading_so_far.rstrip().endswith(":") or text[:1].islower()


def complete_heading(lines: list[str], start_index_0based: int) -> str:
    heading_parts = [clean_inline_text(lines[start_index_0based])]
    lookahead = start_index_0based + 1
    skipped_blank = False

    while lookahead < len(lines):
        candidate = lines[lookahead]
        if not candidate.strip():
            if skipped_blank:
                break
            skipped_blank = True
            lookahead += 1
            continue
        if not should_append_heading_continuation(" ".join(heading_parts), candidate):
            break
        heading_parts.append(clean_inline_text(candidate))
        break

    return clean_inline_text(" ".join(heading_parts))


def extract_sections(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for page in page_records:
        page_no = page["pdf_page_number"]
        lines = page["normalized_text"].splitlines()
        for idx, line in enumerate(lines, start=1):
            if is_heading(line):
                heading = complete_heading(lines, idx - 1)
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
                        "line_number": line_number_for_offset(text, match.start()),
                        "match_start": match.start(),
                        "match_end": match.end(),
                        "context": context_around(text, match.start(), match.end()),
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
                    "line_number": line_number_for_offset(text, match.start()),
                    "match_start": match.start(),
                    "match_end": match.end(),
                    "context": context_around(text, start, end, window=0),
                }
            )
    return out


def valid_crossref_label(kind: str, label: str | None) -> bool:
    if not label:
        return False
    normalized_kind = kind.lower().rstrip(".")
    if normalized_kind in {"table", "figure", "fig"}:
        return bool(FIGURE_TABLE_XREF_LABEL_RE.fullmatch(label))
    if normalized_kind == "section":
        return bool(SECTION_XREF_LABEL_RE.fullmatch(label))
    if normalized_kind == "appendix":
        return bool(APPENDIX_XREF_LABEL_RE.fullmatch(label))
    if normalized_kind in {"eq", "equation"}:
        return bool(EQUATION_XREF_LABEL_RE.fullmatch(label))
    return False


def normalized_crossref_kind(kind: str) -> str:
    normalized = kind.lower().rstrip(".")
    return "figure" if normalized == "fig" else normalized


def extract_crossrefs(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in page_records:
        seen_page_kind_label: set[tuple[int, str, str]] = set()
        text = page["normalized_text"]
        for match in CROSSREF_PATTERN.finditer(text):
            label = match.group("label") or match.group("label_paren")
            if not valid_crossref_label(match.group("kind"), label):
                continue
            seen_page_kind_label.add(
                (page["pdf_page_number"], normalized_crossref_kind(match.group("kind")), label)
            )
            out.append(
                {
                    "page": page["pdf_page_number"],
                    "page_label": page["page_label"],
                    "reference_text": match.group(0),
                    "kind": match.group("kind"),
                    "label": label,
                    "line_number": line_number_for_offset(text, match.start()),
                    "match_start": match.start(),
                    "match_end": match.end(),
                    "context": context_around(text, match.start(), match.end()),
                }
            )
        raw_text = page.get("raw_text", "")
        offset = 0
        for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
            line = clean_inline_text(raw_line)
            for kind, pattern in (("Table", TABLE_CAPTION_RE), ("Figure", FIGURE_CAPTION_RE)):
                match = pattern.match(line)
                if not match:
                    continue
                label = match.group("label")
                key = (page["pdf_page_number"], normalized_crossref_kind(kind), label)
                if key in seen_page_kind_label:
                    continue
                reference_text = f"{kind} {label}"
                out.append(
                    {
                        "page": page["pdf_page_number"],
                        "page_label": page["page_label"],
                        "reference_text": reference_text,
                        "kind": kind,
                        "label": label,
                        "line_number": line_number,
                        "match_start": offset,
                        "match_end": offset + len(raw_line),
                        "context": line,
                        "source": "raw_text_caption_fallback",
                    }
                )
                seen_page_kind_label.add(key)
            offset += len(raw_line) + 1
    return out


def reference_column(bbox: list[float], page_width: float) -> str:
    return "right" if bbox[0] >= page_width * 0.48 else "left"


def merge_reference_line_fragments(
    lines: list[dict[str, Any]], page_width: float
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for line in lines:
        if line.get("is_page_footer"):
            continue
        item = {"text": line["text"], "bbox": list(line["bbox"])}
        column = reference_column(item["bbox"], page_width)
        if merged:
            previous = merged[-1]
            previous_column = reference_column(previous["bbox"], page_width)
            same_baseline = abs(item["bbox"][1] - previous["bbox"][1]) <= 1.5
            if column == previous_column and same_baseline:
                fragments = sorted([previous, item], key=lambda part: part["bbox"][0])
                previous["text"] = clean_inline_text(" ".join(part["text"] for part in fragments))
                previous["bbox"] = union_bboxes([part["bbox"] for part in fragments])
                continue
        merged.append(item)
    return merged


def extract_reference_list_positioned(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared_pages: list[dict[str, Any]] = []
    for page in page_records:
        page_width = float(page.get("page_width", 0.0))
        lines = merge_reference_line_fragments(page.get("positioned_lines", []), page_width)
        prepared_pages.append({**page, "reference_lines": lines})

    started = False
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for page in prepared_pages:
        lines = page["reference_lines"]
        if not started:
            start_on_page = next(
                (index for index, line in enumerate(lines) if REF_START_RE.match(line["text"])),
                None,
            )
            if start_on_page is None:
                continue
            started = True
            lines = lines[start_on_page + 1 :]

        if not lines:
            continue
        page_width = float(page["page_width"])
        column_margins: dict[str, float] = {}
        for line in lines:
            column = reference_column(line["bbox"], page_width)
            column_margins[column] = min(column_margins.get(column, float("inf")), line["bbox"][0])

        for line_index, line in enumerate(lines):
            line_number = line_index + 1
            text = line["text"]
            next_text = lines[line_index + 1]["text"] if line_index + 1 < len(lines) else ""
            split_appendix_heading = bool(
                re.fullmatch(r"[A-Z]", text) and REF_SECTION_END_RE.match(next_text)
            )
            if APPENDIX_START_RE.match(text) or REF_SECTION_END_RE.match(text) or split_appendix_heading:
                started = False
                break
            if not text or re.fullmatch(r"\d+", text):
                continue
            column = reference_column(line["bbox"], page_width)
            at_hanging_margin = abs(line["bbox"][0] - column_margins[column]) <= 4
            repeated_author_start = repeated_author_entry_start(text, current)
            if (at_hanging_margin or repeated_author_start) and current is not None:
                current["text"] = join_reference_chunks(current["chunks"])
                del current["chunks"]
                entries.append(current)
                current = None
            if current is None:
                current = {
                    "start_page": page["pdf_page_number"],
                    "start_page_label": page.get("page_label"),
                    "start_line": line_number,
                    "source": "positioned_text_hanging_indent",
                    "chunks": [],
                }
            current["chunks"].append(text)
        if not started:
            break

    if current is not None:
        current["text"] = join_reference_chunks(current["chunks"])
        del current["chunks"]
        entries.append(current)
    for reference_id, entry in enumerate(entries, start=1):
        entry["reference_id"] = reference_id
    return entries


def extract_reference_list_text(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines_with_meta: list[dict[str, Any]] = []
    for page in page_records:
        for idx, raw_line in enumerate(page["normalized_text"].splitlines(), start=1):
            line = raw_line.rstrip()
            lines_with_meta.append(
                {
                    "page": page["pdf_page_number"],
                    "page_label": page["page_label"],
                    "line_number": idx,
                    "text": line.strip(),
                    "is_indented": line.startswith((" ", "\t")),
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
        if re.fullmatch(r"\d+", text):
            continue
        if APPENDIX_START_RE.match(text) or REF_SECTION_END_RE.match(text) or ANY_CAPTION_RE.match(text):
            break
        starts_new_entry = (
            not item["is_indented"]
            and REF_ENTRY_START_RE.match(text)
            and not ANY_CAPTION_RE.match(text)
            and not re.fullmatch(r"\d+", text)
        )
        if repeated_author_entry_start(text, current):
            starts_new_entry = True
        if starts_new_entry or (current is None):
            if current is not None:
                current["text"] = join_reference_chunks(current["chunks"])
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
        current["text"] = join_reference_chunks(current["chunks"])
        del current["chunks"]
        entries.append(current)

    for i, entry in enumerate(entries, start=1):
        entry["reference_id"] = i

    return entries


def extract_reference_list(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(page.get("positioned_lines") for page in page_records):
        return extract_reference_list_positioned(page_records)
    return extract_reference_list_text(page_records)


def should_append_caption_continuation(title_so_far: str, next_text: str, y_gap: float) -> bool:
    text = clean_inline_text(next_text)
    if y_gap < -0.5 or y_gap > 18:
        return False
    if not text or ANY_CAPTION_RE.match(text):
        return False
    if re.match(r"^(?:Note:|Panel\b|\([a-z0-9]+\)|[-−]?\d|N\b|Controls\b|Control mean\b)", text):
        return False
    return title_so_far.rstrip().endswith(":") or text[:1].islower()


def fallback_caption_crop_bbox(page: fitz.Page) -> list[float]:
    return [
        max(0.0, page.rect.x0 + 48),
        max(0.0, page.rect.y0 + 64),
        min(float(page.rect.width), page.rect.x1 - 48),
        min(float(page.rect.height), page.rect.y1 - 42),
    ]


def should_append_raw_caption_continuation(title_so_far: str, next_text: str) -> bool:
    text = clean_inline_text(next_text)
    if not text or ANY_CAPTION_RE.match(text):
        return False
    if re.match(r"^(?:Note:|Panel\b|\([a-z0-9]+\)|[-−]?\d|N\b|Controls\b|Control mean\b)", text):
        return False
    if len(text) > 180:
        return False
    if title_so_far.rstrip().endswith(":"):
        return True
    if title_so_far.rstrip().endswith((".", "?", "!", ")")):
        return False
    if text[:1].islower():
        return True
    if re.search(r"\b(?:and|or|of|for|from|to|when|with|without|by|in|on|the|a|an)$", title_so_far, re.IGNORECASE):
        return True
    return False


def extract_raw_captioned_items_for_page(
    page: fitz.Page,
    kind: str,
    page_number: int,
    page_label: str | None,
) -> list[dict[str, Any]]:
    pattern = TABLE_CAPTION_RE if kind == "table" else FIGURE_CAPTION_RE
    display_kind = "Table" if kind == "table" else "Figure"
    raw_lines = [clean_inline_text(line) for line in (page.get_text("text", sort=False) or "").splitlines()]
    lines = [line for line in raw_lines if line]
    items: list[dict[str, Any]] = []

    i = 0
    while i < len(lines):
        match = pattern.match(lines[i])
        if not match:
            i += 1
            continue

        label = match.group("label")
        title_parts = [clean_inline_text(match.group("title"))]
        caption_end = i
        while caption_end + 1 < len(lines):
            if should_append_raw_caption_continuation(" ".join(title_parts), lines[caption_end + 1]):
                title_parts.append(lines[caption_end + 1].strip())
                caption_end += 1
            else:
                break
        title = clean_inline_text(" ".join(title_parts))
        next_caption_idx = None
        for j in range(caption_end + 1, len(lines)):
            if ANY_CAPTION_RE.match(lines[j]):
                next_caption_idx = j
                break

        body_end = next_caption_idx if next_caption_idx is not None else len(lines)
        content_lines = lines[i:body_end]
        while content_lines and plausible_page_label_line(content_lines[-1]) is not None:
            content_lines.pop()
        if not content_lines:
            i += 1
            continue

        crop_bbox = fallback_caption_crop_bbox(page)
        items.append(
            {
                "kind": kind,
                "label": label,
                "caption": f"{display_kind} {label}: {title}",
                "title": title,
                "page": page_number,
                "page_label": page_label,
                "caption_bbox": [crop_bbox[0], crop_bbox[1], crop_bbox[2], min(crop_bbox[3], crop_bbox[1] + 24)],
                "crop_bbox": crop_bbox,
                "raw_lines": content_lines,
                "body_lines": content_lines[caption_end - i + 1:],
                "caption_source": "raw_text",
                "sort_y": float(i),
            }
        )
        i = body_end if next_caption_idx is not None else len(lines)

    return items


def extract_captioned_items(
    doc: fitz.Document,
    kind: str,
    page_labels: dict[int, str | None] | None = None,
) -> list[dict[str, Any]]:
    pattern = TABLE_CAPTION_RE if kind == "table" else FIGURE_CAPTION_RE
    display_kind = "Table" if kind == "table" else "Figure"
    items: list[dict[str, Any]] = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_number = page_index + 1
        page_label = page_label_for(page_labels, page_number, page)
        lines = positioned_text_lines(page)
        lines = [line for line in lines if not line["is_page_footer"]]

        i = 0
        while i < len(lines):
            match = pattern.match(lines[i]["text"])
            if not match:
                i += 1
                continue

            label = match.group("label")
            title_parts = [match.group("title").strip()]
            caption_end = i
            while caption_end + 1 < len(lines):
                y_gap = lines[caption_end + 1]["bbox"][1] - lines[caption_end]["bbox"][1]
                if should_append_caption_continuation(" ".join(title_parts), lines[caption_end + 1]["text"], y_gap):
                    title_parts.append(lines[caption_end + 1]["text"].strip())
                    caption_end += 1
                else:
                    break

            next_caption_idx = None
            for j in range(caption_end + 1, len(lines)):
                if ANY_CAPTION_RE.match(lines[j]["text"]):
                    next_caption_idx = j
                    break

            body_start = caption_end + 1
            body_end = next_caption_idx if next_caption_idx is not None else len(lines)
            content_lines = lines[i:body_end]
            if not content_lines:
                i += 1
                continue

            caption_lines = lines[i:caption_end + 1]
            caption_bbox = union_bboxes([line["bbox"] for line in caption_lines])
            x0 = max(0.0, min(line["bbox"][0] for line in content_lines) - 24)
            y0 = max(0.0, lines[i]["bbox"][1] - 10)
            x1 = min(float(page.rect.width), max(line["bbox"][2] for line in content_lines) + 24)
            y1 = min(float(page.rect.height), max(line["bbox"][3] for line in content_lines) + 10)
            crop_bbox = [x0, y0, x1, y1]
            raw_lines = [line["text"] for line in content_lines]
            body_lines = [line["text"] for line in lines[body_start:body_end]]
            caption_source = "positioned_lines"

            if kind == "table":
                table_region = table_region_above_caption(page, lines, caption_bbox)
                if table_region is not None:
                    crop_bbox = table_region["crop_bbox"]
                    raw_lines = table_region["raw_lines"]
                    body_lines = table_region["raw_lines"]
                    caption_source = "positioned_lines_above_caption"
            else:
                figure_crop = figure_crop_above_caption(page, caption_bbox)
                if figure_crop is not None:
                    crop_bbox = figure_crop
                    raw_lines = [line["text"] for line in caption_lines]
                    body_lines = []
                    caption_source = "positioned_lines_visual_anchor"

            title = clean_inline_text(" ".join(title_parts))
            items.append(
                {
                    "kind": kind,
                    "label": label,
                    "caption": f"{display_kind} {label}: {title}",
                    "title": title,
                    "page": page_number,
                    "page_label": page_label,
                    "caption_bbox": caption_bbox,
                    "crop_bbox": crop_bbox,
                    "raw_lines": raw_lines,
                    "body_lines": body_lines,
                    "caption_source": caption_source,
                    "sort_y": float(lines[i]["bbox"][1]),
                }
            )

            i = body_end if next_caption_idx is not None else len(lines)

        existing = {(item["kind"], item["label"], item["page"]) for item in items}
        for item in extract_raw_captioned_items_for_page(page, kind, page_number, page_label):
            key = (item["kind"], item["label"], item["page"])
            if key not in existing:
                items.append(item)
                existing.add(key)

    items.sort(key=lambda item: (item["page"], item.get("sort_y", 0.0), item["label"]))
    for item in items:
        item.pop("sort_y", None)
    return items


def extract_embedded_images(
    doc: fitz.Document,
    page_labels: dict[int, str | None] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, page in enumerate(doc, start=1):
        page_images = page.get_images(full=True)
        for j, img in enumerate(page_images, start=1):
            bbox_list = []
            try:
                rects = page.get_image_rects(img)
                for rect in rects:
                    bbox_list.append([rect.x0, rect.y0, rect.x1, rect.y1])
            except Exception:
                bbox_list = []
            out.append(
                {
                    "image_id": f"page_{i:03d}_image_{j:02d}",
                    "page": i,
                    "page_label": page_label_for(page_labels, i, page),
                    "xref": img[0],
                    "width": img[2] if len(img) > 2 else None,
                    "height": img[3] if len(img) > 3 else None,
                    "bbox_list": bbox_list,
                }
            )
    return out


def rects_intersect(a: list[float], b: list[float]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def rect_overlap_ratio(candidate: list[float], region: list[float]) -> float:
    left = max(candidate[0], region[0])
    top = max(candidate[1], region[1])
    right = min(candidate[2], region[2])
    bottom = min(candidate[3], region[3])
    if right <= left or bottom <= top:
        return 0.0
    candidate_area = max(0.0, candidate[2] - candidate[0]) * max(
        0.0, candidate[3] - candidate[1]
    )
    if candidate_area == 0:
        return 0.0
    return ((right - left) * (bottom - top)) / candidate_area


def associated_embedded_images(
    embedded_images: list[dict[str, Any]], page_number: int, crop_bbox: list[float]
) -> list[dict[str, Any]]:
    associated = []
    for image in embedded_images:
        if image["page"] != page_number:
            continue
        if not image.get("bbox_list"):
            associated.append(image)
            continue
        if any(rects_intersect(crop_bbox, bbox) for bbox in image["bbox_list"]):
            associated.append(image)
    return associated


def save_figures(
    doc: fitz.Document,
    figures_dir: Path,
    repo_root: Path,
    dpi: int,
    embedded_images: list[dict[str, Any]],
    page_labels: dict[int, str | None] | None = None,
) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    captioned_figures = extract_captioned_items(doc, "figure", page_labels)

    for figure_counter, item in enumerate(captioned_figures, start=1):
        crop_path = figures_dir / f"figure_{figure_counter}.png"
        text_path = figures_dir / f"figure_{figure_counter}.txt"
        page = doc[item["page"] - 1]
        crop_saved = save_page_clip_image(page, crop_path, item["crop_bbox"], dpi=dpi)
        text_path.write_text("\n".join(item["raw_lines"]).strip() + "\n", encoding="utf-8")

        associated_images = associated_embedded_images(embedded_images, item["page"], item["crop_bbox"])
        source = "raw_text_caption_fallback" if item.get("caption_source") == "raw_text" else "caption"
        inventory.append(
            {
                "figure_id": figure_counter,
                "figure_label": item["label"],
                "caption": item["caption"],
                "title": item["title"],
                "page": item["page"],
                "page_label": item["page_label"],
                "source": source,
                "caption_source": item.get("caption_source"),
                "status": "captioned_with_embedded_image" if associated_images else "captioned_visual_crop_only",
                "crop_bbox": item["crop_bbox"],
                "crop_path": relative_artifact_path(crop_path, repo_root) if crop_saved else None,
                "text_path": relative_artifact_path(text_path, repo_root),
                "embedded_image_count": len(associated_images),
                "embedded_images": associated_images,
                "line_count": len(item["raw_lines"]),
            }
        )

    return inventory


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


def split_trailing_table_cells(text: str) -> tuple[str, list[str]]:
    remaining = clean_inline_text(text)
    cells: list[str] = []
    while remaining:
        match = TABLE_TRAILING_CELL_RE.search(remaining)
        if not match:
            break
        cells.insert(0, clean_inline_text(match.group("cell")))
        remaining = remaining[: match.start()].rstrip()
    return remaining, cells


def parse_captioned_table_rows(lines: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    in_note = False
    for line in lines:
        text = clean_inline_text(line)
        if not text or TABLE_CAPTION_RE.match(text):
            continue
        if text.startswith("Note:") or text.startswith("* p ") or text.startswith("* p<") or in_note:
            in_note = True
            continue
        label, cells = split_trailing_table_cells(text)
        if rows and not cells and (is_heading(text) or FIGURE_CAPTION_RE.match(text)):
            break
        if cells:
            rows.append({"row_label": label, "cells": cells, "source_text": text})
        elif rows or text.startswith("Panel ") or len(text.split()) <= 10:
            rows.append({"row_label": text, "cells": [], "source_text": text})
    return rows


def split_caption_table_header(text: str, expected_columns: int) -> list[str] | None:
    tokens = clean_inline_text(text).split()
    cells: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if (
            token.endswith(".")
            and index + 1 < len(tokens)
            and re.fullmatch(r"\d+[A-Za-z]?", tokens[index + 1])
        ):
            cells.append(f"{token} {tokens[index + 1]}")
            index += 2
        else:
            cells.append(token)
            index += 1
    return cells if len(cells) == expected_columns else None


def structure_captioned_table_rows(
    parsed_rows: list[dict[str, Any]],
) -> tuple[list[str], list[list[str]], list[dict[str, Any]], bool]:
    max_values = max((len(row["cells"]) for row in parsed_rows), default=0)
    columns = ["row_label"] + [f"value_{i}" for i in range(1, max_values + 1)]
    structured_rows = parsed_rows
    header_promoted = False

    data_max_values = max((len(row["cells"]) for row in parsed_rows[1:]), default=0)
    if len(parsed_rows) > 1 and data_max_values:
        header_names = split_caption_table_header(
            parsed_rows[0]["source_text"], data_max_values + 1
        )
        alphabetic_headers = (
            sum(any(character.isalpha() for character in name) for name in header_names)
            if header_names is not None
            else 0
        )
        if header_names is not None and alphabetic_headers >= 2:
            columns = header_names
            structured_rows = parsed_rows[1:]
            header_promoted = True

    csv_rows: list[list[str]] = []
    for row in structured_rows:
        values = [row["row_label"], *row["cells"]]
        if len(values) < len(columns):
            values.extend([""] * (len(columns) - len(values)))
        csv_rows.append(values)
    return columns, csv_rows, structured_rows, header_promoted


def caption_table_quality(parsed_rows: list[dict[str, Any]]) -> tuple[str, list[str]]:
    if not parsed_rows:
        return "caption_text_only", ["no_structured_cells"]

    flags: list[str] = []
    max_values = max((len(row["cells"]) for row in parsed_rows), default=0)
    if max_values == 0:
        flags.append("no_value_columns")
    if any(len(row["cells"]) != max_values for row in parsed_rows):
        flags.append("ragged_rows")
    if any(
        not row["cells"] and len(row["source_text"].split()) > 12
        for row in parsed_rows
    ):
        flags.append("possible_prose_contamination")

    if "no_value_columns" in flags:
        status = "caption_text_unstructured"
    elif "possible_prose_contamination" in flags:
        status = "caption_text_contaminated"
    else:
        status = "caption_text_needs_visual_verification"
    return status, flags


def save_captioned_tables(
    doc: fitz.Document,
    tables_dir: Path,
    repo_root: Path,
    dpi: int,
    page_labels: dict[int, str | None] | None = None,
    *,
    captioned_tables: list[dict[str, Any]] | None = None,
    start_table_id: int = 1,
) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    if captioned_tables is None:
        captioned_tables = extract_captioned_items(doc, "table", page_labels)

    for table_counter, item in enumerate(captioned_tables, start=start_table_id):
        csv_path = tables_dir / f"table_{table_counter}.csv"
        raw_json_path = tables_dir / f"table_{table_counter}.raw.json"
        markdown_path = tables_dir / f"table_{table_counter}.md"
        text_path = tables_dir / f"table_{table_counter}.txt"
        crop_path = tables_dir / f"table_{table_counter}.png"
        page = doc[item["page"] - 1]

        table_text = "\n".join(item["raw_lines"]).strip() + "\n"
        parsed_rows = parse_captioned_table_rows(item["raw_lines"])
        columns, csv_rows, structured_rows, header_promoted = structure_captioned_table_rows(
            parsed_rows
        )
        quality_status, quality_flags = caption_table_quality(structured_rows)
        if csv_rows:
            df = pd.DataFrame(csv_rows, columns=columns)
            df.to_csv(csv_path, index=False, encoding="utf-8")
            markdown_table = df.to_markdown(index=False, disable_numparse=True)
        else:
            csv_path.write_text("", encoding="utf-8")
            markdown_table = "_No structured cells parsed; see raw text fallback._"

        markdown_path.write_text(
            f"### {item['caption']}\n\n{markdown_table}\n\n```text\n{table_text.strip()}\n```\n",
            encoding="utf-8",
        )
        text_path.write_text(table_text, encoding="utf-8")
        crop_saved = save_page_clip_image(page, crop_path, item["crop_bbox"], dpi=dpi)

        write_json(
            raw_json_path,
            {
                "source": (
                    "caption_text_fallback_raw_text"
                    if item.get("caption_source") == "raw_text"
                    else "caption_text_fallback"
                ),
                "table_label": item["label"],
                "caption": item["caption"],
                "title": item["title"],
                "page": item["page"],
                "page_label": item["page_label"],
                "caption_source": item.get("caption_source"),
                "crop_bbox": item["crop_bbox"],
                "raw_lines": item["raw_lines"],
                "parsed_rows": parsed_rows,
                "structured_rows": structured_rows,
                "columns": columns,
                "header_promoted": header_promoted,
                "quality_status": quality_status,
                "quality_flags": quality_flags,
                "quality_note": (
                    "Caption-anchored fallback from positioned page text; use the crop image "
                    "for visual verification of column alignment."
                ),
            },
        )

        inventory.append(
            {
                "table_id": table_counter,
                "table_label": item["label"],
                "caption": item["caption"],
                "page": item["page"],
                "page_label": item["page_label"],
                "caption_source": item.get("caption_source"),
                "source": (
                    "caption_text_fallback_raw_text"
                    if item.get("caption_source") == "raw_text"
                    else "caption_text_fallback"
                ),
                "csv_path": relative_artifact_path(csv_path, repo_root),
                "markdown_path": relative_artifact_path(markdown_path, repo_root),
                "raw_json_path": relative_artifact_path(raw_json_path, repo_root),
                "text_path": relative_artifact_path(text_path, repo_root),
                "crop_path": relative_artifact_path(crop_path, repo_root) if crop_saved else None,
                "crop_bbox": item["crop_bbox"],
                "row_count": len(structured_rows),
                "col_count": len(columns) if structured_rows else 0,
                "header_names": columns if header_promoted else [],
                "header_promoted": header_promoted,
                "status": quality_status,
                "quality_flags": quality_flags,
            }
        )

    return inventory


def save_auto_tables(
    doc: fitz.Document,
    pdf_path: Path,
    tables_dir: Path,
    repo_root: Path,
    page_labels: dict[int, str | None] | None = None,
    excluded_regions_by_page: dict[int, list[list[float]]] | None = None,
) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    table_counter = 1

    for page_number, page in enumerate(doc, start=1):
        page_tables = extract_tables_with_pymupdf(page)
        if not page_tables:
            page_tables = extract_tables_with_pdfplumber(pdf_path, page_number)

        for t in page_tables:
            bbox = t.get("bbox")
            excluded_regions = (excluded_regions_by_page or {}).get(page_number, [])
            if (
                isinstance(bbox, (list, tuple))
                and len(bbox) == 4
                and any(rect_overlap_ratio(list(bbox), region) >= 0.5 for region in excluded_regions)
            ):
                continue
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

            nonempty_cells = [
                cell.strip()
                for row in normalized_rows
                for cell in row
                if cell.strip()
            ]
            if not nonempty_cells:
                continue
            total_cells = max(1, len(normalized_rows) * max_cols)
            quality_flags = []
            if len(nonempty_cells) / total_cells < 0.4:
                quality_flags.append("sparse_cells")
            if any(cell.count("\n") >= 4 for cell in nonempty_cells):
                quality_flags.append("multiline_cell_may_be_diagram_or_merged_content")
            if len(normalized_rows) < 2:
                quality_flags.append("too_few_rows")
            quality_status = (
                "auto_extracted_suspect"
                if quality_flags
                else "auto_extracted_needs_visual_verification"
            )

            df = pd.DataFrame(normalized_rows)
            df.to_csv(csv_path, index=False, header=False, encoding="utf-8")
            markdown_text = df.to_markdown(index=False, disable_numparse=True)

            markdown_path.write_text(markdown_text, encoding="utf-8")
            write_json(raw_json_path, t)

            inventory.append(
                {
                    "table_id": table_counter,
                    "page": page_number,
                    "page_label": page_label_for(page_labels, page_number, page),
                    "source": t.get("source"),
                    "table_index_on_page": t.get("table_index_on_page"),
                    "bbox": t.get("bbox"),
                    "header_names": t.get("header_names", []),
                    "csv_path": relative_artifact_path(csv_path, repo_root),
                    "markdown_path": relative_artifact_path(markdown_path, repo_root),
                    "raw_json_path": relative_artifact_path(raw_json_path, repo_root),
                    "row_count": len(normalized_rows),
                    "col_count": max_cols,
                    "status": quality_status,
                    "quality_flags": quality_flags,
                    "quality_note": (
                        "Deterministic native table candidate; compare with the page image before "
                        "relying on column alignment, signs, or values."
                    ),
                }
            )
            table_counter += 1

    return inventory


def attach_captions_to_auto_tables(
    captioned_tables: list[dict[str, Any]], auto_tables: list[dict[str, Any]]
) -> set[int]:
    matched_caption_indexes: set[int] = set()
    for auto_table in auto_tables:
        if auto_table.get("status") != "auto_extracted_needs_visual_verification":
            continue
        auto_bbox = auto_table.get("bbox")
        if not isinstance(auto_bbox, (list, tuple)) or len(auto_bbox) != 4:
            continue
        candidates = []
        for index, caption in enumerate(captioned_tables):
            caption_bbox = caption.get("crop_bbox")
            if caption.get("page") != auto_table.get("page"):
                continue
            if not isinstance(caption_bbox, (list, tuple)) or len(caption_bbox) != 4:
                continue
            if rects_intersect(list(auto_bbox), list(caption_bbox)):
                caption_line = caption.get("caption_bbox") or caption_bbox
                distance = abs(float(auto_bbox[1]) - float(caption_line[3]))
                candidates.append((distance, index, caption))
        if not candidates:
            continue
        _distance, index, caption = min(candidates, key=lambda item: item[0])
        matched_caption_indexes.add(index)
        auto_table.update(
            {
                "table_label": caption.get("label"),
                "caption": caption.get("caption"),
                "caption_source": caption.get("caption_source"),
                "caption_bbox": caption.get("caption_bbox"),
            }
        )
    return matched_caption_indexes


def save_tables(
    doc: fitz.Document,
    pdf_path: Path,
    tables_dir: Path,
    repo_root: Path,
    dpi: int,
    page_labels: dict[int, str | None] | None = None,
) -> list[dict[str, Any]]:
    captioned_items = extract_captioned_items(doc, "table", page_labels)
    figure_regions_by_page: dict[int, list[list[float]]] = {}
    for figure in extract_captioned_items(doc, "figure", page_labels):
        crop_bbox = figure.get("crop_bbox")
        if (
            figure.get("caption_source") == "positioned_lines_visual_anchor"
            and isinstance(crop_bbox, list)
            and len(crop_bbox) == 4
        ):
            figure_regions_by_page.setdefault(figure["page"], []).append(crop_bbox)
    auto_tables = save_auto_tables(
        doc,
        pdf_path,
        tables_dir,
        repo_root,
        page_labels,
        figure_regions_by_page,
    )
    matched_caption_indexes = attach_captions_to_auto_tables(captioned_items, auto_tables)
    unmatched_captions = [
        item for index, item in enumerate(captioned_items) if index not in matched_caption_indexes
    ]
    caption_fallbacks = save_captioned_tables(
        doc,
        tables_dir,
        repo_root,
        dpi,
        page_labels,
        captioned_tables=unmatched_captions,
        start_table_id=len(auto_tables) + 1,
    )
    return [*auto_tables, *caption_fallbacks]


def prune_stale_numbered_artifacts(
    directory: Path, prefix: str, keep_paths: set[Path]
) -> None:
    numbered_name = re.compile(rf"^{re.escape(prefix)}_\d+(?:\.|_)")
    resolved_keep = {path.resolve() for path in keep_paths}
    for path in directory.iterdir():
        if path.is_file() and numbered_name.match(path.name) and path.resolve() not in resolved_keep:
            path.unlink()


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


def plausible_sparse_page(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return True
    compact = " ".join(lines)
    if ANY_CAPTION_RE.search(compact):
        return True
    if len(lines) <= 3 and all(PAGE_LABEL_LINE_RE.match(line) or len(line) < 90 for line in lines):
        return True
    if len(compact) < 250 and re.search(r"\b(?:table|figure|appendix|survey|question|note)\b", compact, re.IGNORECASE):
        return True
    if len(compact) < 250 and compact.count("%") >= 2:
        return True
    return False


def page_quality_summary(page_records: list[dict[str, Any]]) -> dict[str, Any]:
    low_text_pages = []
    sparse_plausible_pages = []
    ocr_recommended_pages = []
    two_column_pages = []
    landscape_pages = []
    reading_order_review_pages = []
    raw_normalized_ratios = []
    suspicious_order_pages = []
    normalized_text_strategies: dict[str, int] = {}
    for page in page_records:
        raw_text = page.get("raw_text", "")
        normalized_text = page.get("normalized_text", "")
        page_number = page["pdf_page_number"]
        if page.get("ocr_recommended"):
            ocr_recommended_pages.append(page_number)
        if page.get("two_column_detected"):
            two_column_pages.append(page_number)
        if page.get("landscape"):
            landscape_pages.append(page_number)
        strategy = page.get("normalized_text_strategy", "coordinate_sorted")
        normalized_text_strategies[strategy] = normalized_text_strategies.get(strategy, 0) + 1
        two_column_unresolved = page.get("two_column_detected") and strategy != "native_content_order_two_column"
        if (
            (two_column_unresolved or page.get("landscape"))
            and page.get("raw_sorted_similarity", 1.0) < 0.9
        ):
            reading_order_review_pages.append(page_number)
        if len(raw_text.strip()) < 250 and not page.get("likely_scanned"):
            if plausible_sparse_page(raw_text):
                sparse_plausible_pages.append(page_number)
            else:
                low_text_pages.append(page_number)
        if raw_text and normalized_text:
            raw_normalized_ratios.append(len(normalized_text) / max(len(raw_text), 1))
            raw_lines = max(1, len([line for line in raw_text.splitlines() if line.strip()]))
            normalized_lines = max(1, len([line for line in normalized_text.splitlines() if line.strip()]))
            if normalized_lines > raw_lines * 2.25 and len(normalized_text) > 1000:
                suspicious_order_pages.append(page_number)
    median_ratio = None
    if raw_normalized_ratios:
        ratios = sorted(raw_normalized_ratios)
        middle = len(ratios) // 2
        if len(ratios) % 2:
            median_ratio = ratios[middle]
        else:
            median_ratio = (ratios[middle - 1] + ratios[middle]) / 2
    return {
        "low_text_pages": low_text_pages,
        "sparse_plausible_pages": sparse_plausible_pages,
        "ocr_recommended_pages": ocr_recommended_pages,
        "two_column_pages": two_column_pages,
        "landscape_pages": landscape_pages,
        "reading_order_review_pages": reading_order_review_pages,
        "suspicious_order_pages": suspicious_order_pages,
        "normalized_text_strategies": normalized_text_strategies,
        "raw_normalized_char_ratio_median": round(median_ratio, 3) if median_ratio is not None else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preprocess a paper PDF into structured artifacts.")
    parser.add_argument("--pdf", required=True, help="Path to input PDF")
    parser.add_argument("--paper-id", default=None, help="Optional paper id; defaults to filename stem")
    parser.add_argument("--dpi", type=int, default=200, help="DPI for saved page images")
    parser.add_argument(
        "--work-root",
        default="work",
        help="Directory for run artifacts; defaults to work. Useful for isolated branch experiments.",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {pdf_path.name}")

    paper_id = slugify(args.paper_id or pdf_path.stem)
    repo_root = Path.cwd()
    work_root_arg = Path(args.work_root)
    work_root_base = work_root_arg if work_root_arg.is_absolute() else repo_root / work_root_arg
    work_root = work_root_base / paper_id
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
    ocr_recommended_pages = []

    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            pdf_page_number = page_index + 1
            raw_text, sorted_text, words, blocks = extract_page_text(page)
            page_label = clean_page_label(page, raw_text, sorted_text)
            two_column_detected = two_column_layout_detected(page)
            normalized_source, normalized_text_strategy = choose_normalized_text(
                raw_text,
                sorted_text,
                blocks,
                float(page.rect.width),
                two_column_detected,
            )
            normalized_text = normalize_page_text(normalized_source)
            positioned_lines = positioned_text_lines(page)

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
            image_coverage = embedded_image_coverage_ratio(page)
            ocr_reason = None
            if likely_scanned:
                ocr_reason = "no_native_text"
            elif image_coverage >= 0.18 and len(raw_text.strip()) < 1500:
                ocr_reason = "large_embedded_images_with_limited_native_text"
            ocr_recommended = ocr_reason is not None
            if ocr_recommended:
                ocr_recommended_pages.append(pdf_page_number)
            landscape = float(page.rect.width) > float(page.rect.height)
            raw_sorted_similarity = text_order_similarity(raw_text, sorted_text)

            page_meta = PageMeta(
                pdf_page_index=page_index,
                pdf_page_number=pdf_page_number,
                page_label=page_label,
                page_width=float(page.rect.width),
                page_height=float(page.rect.height),
                raw_text_path=portable_path(raw_text_path, repo_root),
                normalized_text_path=portable_path(normalized_text_path, repo_root),
                image_path=portable_path(image_path, repo_root),
                words_path=portable_path(words_path, repo_root),
                blocks_path=portable_path(blocks_path, repo_root),
                extracted_char_count=len(raw_text),
                likely_scanned=likely_scanned,
                embedded_image_coverage_ratio=image_coverage,
                ocr_recommended=ocr_recommended,
                ocr_reason=ocr_reason,
                two_column_detected=two_column_detected,
                normalized_text_strategy=normalized_text_strategy,
                landscape=landscape,
                raw_sorted_similarity=raw_sorted_similarity,
            )

            page_records.append(
                {
                    **asdict(page_meta),
                    "raw_text": raw_text,
                    "normalized_text": normalized_text,
                    "positioned_lines": positioned_lines,
                }
            )

        full_text = build_full_text(page_records)
        (parsed_dir / "full_text.md").write_text(full_text, encoding="utf-8")

        page_index_json = []
        for rec in page_records:
            copy = {
                k: v
                for k, v in rec.items()
                if k not in {"raw_text", "normalized_text", "positioned_lines"}
            }
            page_index_json.append(copy)
        write_json(parsed_dir / "page_index.json", page_index_json)
        page_labels = {rec["pdf_page_number"]: rec["page_label"] for rec in page_records}

        sections = extract_sections(page_records)
        citations = extract_citations(page_records)
        numbers = extract_numbers(page_records)
        crossrefs = extract_crossrefs(page_records)
        references = extract_reference_list(page_records)
        tables_inventory = save_tables(doc, pdf_path, tables_dir, repo_root, args.dpi, page_labels)
        embedded_images_inventory = extract_embedded_images(doc, page_labels)
        figures_inventory = save_figures(
            doc, figures_dir, repo_root, args.dpi, embedded_images_inventory, page_labels
        )

    page_keep_paths: set[Path] = set()
    for page_number in range(1, len(page_records) + 1):
        page_keep_paths.update(
            {
                raw_pages_dir / f"page_{page_number:03d}.txt",
                pages_dir / f"page_{page_number:03d}.md",
                words_dir / f"page_{page_number:03d}.words.json",
                blocks_dir / f"page_{page_number:03d}.blocks.json",
                page_images_dir / f"page_{page_number:03d}.png",
            }
        )
    for directory in (raw_pages_dir, pages_dir, words_dir, blocks_dir, page_images_dir):
        prune_stale_numbered_artifacts(directory, "page", page_keep_paths)

    table_keep_paths = {
        (repo_root / value).resolve()
        for item in tables_inventory
        for key in ("csv_path", "markdown_path", "raw_json_path", "text_path", "crop_path")
        if isinstance((value := item.get(key)), str) and value
    }
    figure_keep_paths = {
        (repo_root / value).resolve()
        for item in figures_inventory
        for key in ("crop_path", "text_path")
        if isinstance((value := item.get(key)), str) and value
    }
    prune_stale_numbered_artifacts(tables_dir, "table", table_keep_paths)
    prune_stale_numbered_artifacts(figures_dir, "figure", figure_keep_paths)

    write_json(parsed_dir / "sections.json", sections)
    write_json(parsed_dir / "in_text_citations.json", citations)
    write_json(parsed_dir / "reference_list.json", references)
    write_json(parsed_dir / "numbers_in_text.json", numbers)
    write_json(parsed_dir / "crossrefs.json", crossrefs)
    write_json(tables_dir / "table_inventory.json", tables_inventory)
    write_json(figures_dir / "figure_inventory.json", figures_inventory)
    write_json(figures_dir / "embedded_image_inventory.json", embedded_images_inventory)

    manifest = {
        "paper_id": paper_id,
        "source_pdf": str(pdf_path),
        "source_pdf_sha256": file_sha256(pdf_path),
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
            "work_root": portable_path(work_root_base, repo_root),
        },
        "summary": {
            "page_count": len(page_records),
            "likely_scanned_pages": likely_scanned_pages,
            "ocr_recommended_pages": ocr_recommended_pages,
            "page_quality": page_quality_summary(page_records),
            "section_count": len(sections),
            "citation_candidate_count": len(citations),
            "reference_count": len(references),
            "numeric_claim_candidate_count": len(numbers),
            "crossref_count": len(crossrefs),
            "table_count": len(tables_inventory),
            "figure_count": len(figures_inventory),
            "embedded_image_count": len(embedded_images_inventory),
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
            "ocr_recommended_pages": ocr_recommended_pages,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
