"""Lossless large-editor handoff; no model executables are called."""
import io
import json
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_editor_input import MAX_EDITOR_INPUT_BYTES, bounded_editor_input, bundle_read_plan


class EditorInputPagingTests(unittest.TestCase):
    def document_args(self, bundle):
        return dict(paper_id="fixture", editor_prompt_text="Complete the report.",
                    bundle_path=Path("work/path with spaces/editor/normalized_bundle.json"),
                    bundle_json=bundle, reviews_dir=Path("work/path with spaces/reviews"),
                    reviewers=[], review_paths=[], review_json_by_name={}, selection_json=None)

    def test_large_evidence_is_file_backed_without_losing_any_line(self):
        # Non-ASCII and Unicode line separators must not shift file-read offsets.
        bundle = {"paper_id": "fixture", "canonical_findings": [],
                  "notes": [f"{i}: caf\u00e9\u2028" + "retained evidence " * 70 for i in range(1000)]}
        text = json.dumps(bundle, ensure_ascii=False, indent=4) + "\n"
        self.assertGreater(len(text.encode("utf-8")), MAX_EDITOR_INPUT_BYTES)
        document, mode, size = bounded_editor_input(self.document_args(bundle), bundle_file_text=text)
        self.assertEqual(mode, "file-backed")
        self.assertLess(size, MAX_EDITOR_INPUT_BYTES)
        self.assertNotIn(bundle["notes"][-1], document)
        self.assertIn("work/path with spaces/editor/normalized_bundle.json", document)
        self.assertIn("read ALL", document)
        ranges = [(int(a), int(b), int(c)) for a, b, c in
                  re.findall(r"^\| (\d+) \| (\d+) \| (\d+) \|$", document, re.M)]
        self.assertGreater(len(ranges), 1)
        lines, rebuilt, next_line = io.StringIO(text).readlines(), [], 1
        for first, last, byte_count in ranges:
            self.assertEqual(first, next_line)
            section = "".join(lines[first - 1:last])
            self.assertEqual(len(section.encode("utf-8")), byte_count)
            self.assertLessEqual(byte_count, 48_000)
            rebuilt.append(section)
            next_line = last + 1
        self.assertEqual("".join(rebuilt), text)
        self.assertEqual(json.loads("".join(rebuilt)), bundle)

    def test_backing_file_mismatch_is_rejected_even_for_bool_and_number(self):
        for retained, expected in (({"x": True}, {"x": 1}), ({"x": "old"}, {"x": "new"})):
            with self.subTest(retained=retained), self.assertRaisesRegex(ValueError, "differs"):
                bundle_read_plan(Path("bundle.json"), expected, json.dumps(retained))

    def test_small_input_is_unchanged_and_an_oversized_brief_still_fails(self):
        bundle = {"paper_id": "fixture", "canonical_findings": []}
        args = self.document_args(bundle)
        self.assertEqual(bounded_editor_input(args),
                         bounded_editor_input(args, bundle_file_text=json.dumps(bundle)))
        args["editor_prompt_text"] = "x" * MAX_EDITOR_INPUT_BYTES
        with self.assertRaisesRegex(ValueError, "will not truncate evidence"):
            bounded_editor_input(args, bundle_file_text=json.dumps(bundle))

    def test_single_line_bundle_still_has_an_exact_complete_range(self):
        bundle = {"x": "data"}
        for ending in ("", "\n", "\r\n"):
            text = json.dumps(bundle) + ending
            plan = bundle_read_plan(Path("bundle.json"), bundle, text)
            self.assertIn(f"| 1 | 1 | {len(text.encode('utf-8'))} |", plan)


if __name__ == "__main__":
    unittest.main()
