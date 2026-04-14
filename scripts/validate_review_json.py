from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    schema_path = Path(args.schema)
    input_path = Path(args.input)

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = json.loads(input_path.read_text(encoding="utf-8"))

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)

    if errors:
        print("INVALID")
        for err in errors:
            path = ".".join(str(x) for x in err.path)
            print(f"- {path}: {err.message}")
        return 1

    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
