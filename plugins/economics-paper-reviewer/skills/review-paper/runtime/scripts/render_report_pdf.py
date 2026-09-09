"""Deterministic, offline PDF presentation of an existing Markdown report.

The editor's Markdown remains authoritative. This is a conservative report-format
renderer, not a full Markdown/LaTeX engine: unknown syntax is shown literally;
pipe tables become labelled records so long evidence cells can span pages.
Uses the already-required PyMuPDF; never loads HTML, images, fonts or URLs from
the report. No inference, browser, TeX installation or external service is used.
"""
from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

import fitz

RENDERER_VERSION = 1
MAX_REPORT_BYTES = 5_000_000
MAX_PAGES = 250
PAGE = fitz.Rect(0, 0, 595, 842)
BODY = fitz.Rect(48, 54, 547, 790)
CSS = """
body { font-family: sans-serif; font-size: 10pt; line-height: 1.4; color: #202a35; }
p { margin: 0 0 9pt; }
h1 { font-size: 22pt; color: #18384d; margin: 0 0 18pt; }
h2 { font-size: 15pt; color: #18384d; margin: 20pt 0 10pt; }
h3 { font-size: 12pt; color: #18384d; margin: 15pt 0 8pt; }
h4, h5, h6 { font-size: 10.5pt; margin: 12pt 0 7pt; }
h1, h2, h3, h4, h5, h6 { page-break-after: avoid; }
a { color: #165e88; }
code, .literal { font-family: monospace; font-size: 9pt; }
.item { margin-left: 12pt; }
.cell { margin-left: 12pt; margin-bottom: 5pt; }
.row-start { margin-top: 12pt; padding-top: 6pt; }
"""


class PDFExportError(ValueError):
    """A delivery failure, not a failure of the accepted scientific review."""


def escaped(text: str) -> str:
    # Break long identifiers/URLs without altering their visible spelling.
    text = re.sub(r"\S{28,}", lambda m: "\u200b".join(
        m[0][i:i + 24] for i in range(0, len(m[0]), 24)), text)
    return html.escape(text, quote=True)


INLINE = re.compile(
    r"(`+)(.+?)\1|\[([^\]\n]+)\]\(([^\s()]+(?:\([^\s()]*\)[^\s()]*)*)\)"
    r"|\*\*([^*\n]+)\*\*|(?<!\*)\*([^*\n]+)\*(?!\*)"
    r"|\\([\\`*{}\[\]()#+.!|>_-])"
)


def inline(text: str) -> str:
    """Format a small safe subset; all other source characters remain visible."""
    result, previous = [], 0
    for match in INLINE.finditer(text):
        result.append(escaped(text[previous:match.start()]))
        code, label, url, bold, italic, literal = (
            match[2], match[3], match[4], match[5], match[6], match[7])
        if code is not None:
            result.append("<code>" + escaped(code) + "</code>")
        elif label is not None:
            try:
                safe = urlsplit(url).scheme in {"http", "https"} and bool(urlsplit(url).netloc)
            except ValueError:
                safe = False
            if safe:
                result.append('<a href="' + html.escape(url, quote=True) + '">' + escaped(label) + "</a>")
                # Keep source URLs usable on paper, not only as hidden PDF links.
                if label != url:
                    result.append(" (" + escaped(url) + ")")
            else:
                result.append(escaped(match[0]))
        elif bold is not None:
            result.append("<b>" + escaped(bold) + "</b>")
        elif italic is not None:
            result.append("<i>" + escaped(italic) + "</i>")
        else:
            result.append(escaped(literal))
        previous = match.end()
    result.append(escaped(text[previous:]))
    return "".join(result)


def table_cells(line: str) -> list[str]:
    # Pipes in code spans and escaped pipes are content, not column separators.
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells, cell, fence, index = [], [], 0, 0
    while index < len(line):
        character = line[index]
        if character == "\\" and index + 1 < len(line):
            cell.append(line[index:index + 2])
            index += 2
            continue
        if character == "`":
            end = index + 1
            while end < len(line) and line[end] == "`":
                end += 1
            width = end - index
            if not fence:
                fence = width
            elif width == fence:
                fence = 0
            cell.append(line[index:end])
            index = end
            continue
        if character == "|" and not fence:
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(character)
        index += 1
    return [*cells, "".join(cell).strip()]


def report_html(markdown: str) -> str:
    lines, blocks, paragraph = markdown.splitlines(), [], []

    def flush():
        if paragraph:
            blocks.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            flush()
        elif line.startswith(("```", "~~~")):
            flush()
            fence = re.match(r"`{3,}|~{3,}", line)[0]
            index += 1
            while index < len(lines) and not re.fullmatch(re.escape(fence[0]) + "{" + str(len(fence)) + ",}\\s*", lines[index].strip()):
                blocks.append('<p class="literal">' + escaped(lines[index]) + "</p>")
                index += 1
        elif (index + 1 < len(lines) and "|" in line
              and len(table_cells(lines[index + 1])) > 1
              and all(re.fullmatch(r":?-{3,}:?", cell) for cell in table_cells(lines[index + 1]))):
            flush()
            headers = table_cells(line)
            index += 2
            row_count = 0
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                cells = table_cells(lines[index])
                # Do not drop unexpected cells from malformed/future table formats.
                if len(cells) != len(headers):
                    blocks.append("<p>" + inline(lines[index]) + "</p>")
                else:
                    for column, (header, cell) in enumerate(zip(headers, cells)):
                        cls = "cell row-start" if column == 0 else "cell"
                        blocks.append(f'<p class="{cls}"><b>{inline(header)}:</b> {inline(cell)}</p>')
                row_count += 1
                index += 1
            if not row_count:
                blocks.append("<p>" + inline(line) + "</p>")
            continue
        elif heading := re.match(r"^(#{1,6})\s+(.+)$", line):
            flush()
            level = len(heading[1])
            blocks.append(f"<h{level}>" + inline(heading[2]) + f"</h{level}>")
        elif re.fullmatch(r"[-*_]{3,}", line):
            flush()
            blocks.append("<hr>")
        elif re.match(r"^(?:[-+*]|\d+[.)])\s+", line):
            flush()
            blocks.append('<p class="item">' + inline(line) + "</p>")
        else:
            paragraph.append(line)
        index += 1
    flush()
    return "<html><body>" + "\n".join(blocks) + "</body></html>"


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def normalized(text: str) -> str:
    # Layout whitespace, discretionary breaks and font ligatures are not evidence.
    text = unicodedata.normalize("NFKC", text)
    return "".join(c for c in text if not c.isspace() and c not in "\u200b\u00ad")


def render_report_pdf(markdown_path: Path, output_path: Path) -> dict:
    markdown_path, output_path = Path(markdown_path), Path(output_path)
    if output_path.exists() or output_path.is_symlink():
        raise PDFExportError("Choose a new PDF output path; existing files are never overwritten.")
    if output_path.suffix.lower() != ".pdf":
        raise PDFExportError("The PDF output filename must end in .pdf.")
    if markdown_path.stat().st_size > MAX_REPORT_BYTES:
        raise PDFExportError("This report exceeds the PDF export size limit; the Markdown is unchanged.")
    source = markdown_path.read_bytes()
    text = source.decode("utf-8")
    if not text.strip():
        raise PDFExportError("The report is empty; no PDF was created.")
    document_html = report_html(text)
    expected = VisibleText()
    expected.feed(document_html)
    story = fitz.Story(html=document_html, user_css=CSS, em=10)

    def rectangle(number, filled):
        if number >= MAX_PAGES:
            raise PDFExportError("PDF layout exceeded its page limit; no truncated PDF was saved.")
        return PAGE, BODY, None

    with story.write_with_links(rectangle) as document:
        actual = "".join(page.get_text(clip=BODY) for page in document)
        if normalized("".join(expected.parts)) != normalized(actual):
            raise PDFExportError("PDF text verification failed; deliver the unchanged Markdown and retry only export.")
        for page in document:
            # Story's heading font boxes can extend ~1.05pt above the layout
            # rectangle at a page boundary; a 2pt guard stays clear of furniture.
            if any(not (BODY + (-2, -2, 2, 2)).contains(fitz.Rect(word[:4]))
                   for word in page.get_text("words")):
                raise PDFExportError("PDF text extends outside the printable area; no clipped PDF was saved.")
        for page in document:
            page.insert_text((48, 30), "REVIEWER | PAPER REVIEW", fontsize=8, color=(.25, .35, .43))
            page.insert_text((48, 816), f"{page.number + 1} / {len(document)}", fontsize=8, color=(.25, .35, .43))
        document.set_metadata({"title": "Paper Review Report", "creator": "Reviewer deterministic PDF export",
                               "subject": "Complete report; original Markdown embedded as report.md"})
        document.embfile_add("report.md", source, filename="report.md", ufilename="report.md",
                             desc="Unmodified authoritative editor report")
        document.subset_fonts()
        result = document.tobytes(garbage=4, deflate=True)
        pages = len(document)
    # Reopen before promoting. The byte-identical source travels with the PDF.
    with fitz.open(stream=result, filetype="pdf") as check:
        if check.page_count != pages or check.embfile_get("report.md") != source:
            raise PDFExportError("The generated PDF could not be verified; the Markdown is unchanged.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as stream:
        stream.write(result)
    return {"status": "pdf_created", "path": str(output_path.resolve()), "pages": pages,
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "pdf_sha256": hashlib.sha256(result).hexdigest(), "renderer_version": RENDERER_VERSION,
            "text_verified": True,
            "format_notes": "Pipe tables use labelled rows; unsupported Markdown/TeX is literal. Original Markdown is embedded."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(render_report_pdf(args.report, args.output), indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "pdf_export_failed", "message": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
