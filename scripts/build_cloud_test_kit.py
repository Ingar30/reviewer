"""Build a non-sensitive cloud acceptance kit from the canonical plugin package.

No installation, upload, inference or publication. The fixture is deliberately
synthetic; it is not an evaluation of scientific review quality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fitz

from build_work_plugin import PLUGIN_NAME, build, check_bundle

FIXTURE = (
    ("A Synthetic Economics Paper", "Cloud acceptance fixture - not real research"),
    ("Abstract", "We describe a synthetic two-group outcome comparison. The effect is a 2.5 percent increase. "
     "No real participants, institutions, private data or external references are involved."),
    ("Design", "The synthetic treated mean is 97.5 and the synthetic comparison mean is 100.0. "
     "Both outcomes use the same units. We define the relative difference as "
     "100 times (treated mean minus comparison mean) divided by comparison mean. "
     "This is a descriptive comparison; no causal identification is claimed."),
    ("Results", "The estimate is -2.5 percent. The outcome level in the treated group is 97.5, "
     "compared with 100.0 in the comparison group."),
    ("Conclusion", "The effect is a 2.5 percent increase. The comparison is purely synthetic and "
     "does not support a policy recommendation or a claim about a real population."),
    ("Availability", "All quantities used by this fixture appear above. This fictional text may be "
     "shared for Reviewer testing under the repository's MIT license."),
)


def write_fixture(pdf: Path, sections=FIXTURE, *, required_text=("-2.5 percent", "2.5 percent increase")) -> None:
    """One shared synthetic-fixture renderer for cloud and submission test kits."""
    if pdf.exists() or any(p.is_symlink() for p in (pdf, *pdf.parents)):
        raise ValueError("Use a new, unlinked fixture file.")
    with fitz.open() as document:
        page = document.new_page(width=595, height=842)
        y = 58
        for index, (heading, paragraph) in enumerate(sections):
            page.insert_text((48, y), heading, fontsize=18 if index == 0 else 12, fontname="hebo")
            y += 16 if index == 0 else 10
            box = fitz.Rect(48, y, 547, y + 87)
            remaining = page.insert_textbox(box, paragraph, fontsize=11, fontname="helv", lineheight=1.35)
            if remaining < 0:
                raise ValueError("Synthetic fixture text exceeded its layout box.")
            y += 87 - remaining + 28
        page.insert_text((48, 812), "Synthetic Reviewer fixture | page 1 of 1", fontsize=9)
        document.set_metadata({"title": "Synthetic Reviewer Cloud Test", "author": "Reviewer test fixture"})
        document.save(pdf)
    with fitz.open(pdf) as document:
        if len(document) != 1 or any(not document[0].rect.contains(fitz.Rect(w[:4]))
                                     for w in document[0].get_text("words")):
            raise ValueError("Synthetic fixture pagination failed.")
        text = document[0].get_text()
        if any(value not in text for value in required_text):
            raise ValueError("Synthetic fixture signs/text were not preserved.")


def build_kit(repo: Path, destination: Path) -> dict:
    destination = destination.absolute()
    if destination.exists() or any(p.is_symlink() for p in (destination, *destination.parents)):
        raise ValueError("Choose a fresh, unlinked test-kit directory.")
    plugin = repo / "plugins" / PLUGIN_NAME
    failures = check_bundle(repo, plugin)
    if failures:
        raise ValueError("Regenerate and validate the canonical plugin before building the cloud kit.")
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination / "economics-paper-reviewer.zip"
    if build(repo, plugin, check=True, archive=archive):
        raise ValueError("The plugin bundle failed validation.")
    pdf = destination / "cloud-test-paper.pdf"
    write_fixture(pdf)
    prompt = destination / "START_HERE.md"
    prompt.write_bytes((repo / "docs/cloud_test_prompt.md").read_bytes())
    receipt = {"purpose": "private cloud acceptance preparation; not a hosted test result",
               "plugin_version": json.loads((plugin / ".codex-plugin/plugin.json").read_text())["version"],
               "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive, pdf, prompt)},
               "contains_private_papers": False, "cloud_execution_verified": False}
    (destination / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = build_kit(Path(__file__).resolve().parents[1], args.output)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
