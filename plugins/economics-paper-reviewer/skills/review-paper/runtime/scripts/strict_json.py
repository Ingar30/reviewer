"""Decode agent artifacts without duplicate keys, nonfinite values or surrogates."""
import json
from pathlib import Path


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object keys are ambiguous.")
        result[key] = value
    return result


def parse_json(text: str):
    data = json.loads(text, object_pairs_hook=unique_json_object)
    json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return data


def read_json(path: Path):
    return parse_json(path.read_text(encoding="utf-8"))
