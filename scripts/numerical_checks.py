"""Bounded Decimal interval arithmetic, without eval, code execution or I/O.

Results establish arithmetic only, not comparable estimands or a paper defect.
The CLI reads one structured request, making the same tool usable by either host.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, localcontext
import json
import re
import sys

OPERATIONS = {"sum", "difference", "mean", "product", "ratio", "percent_change", "percentage_points"}
SCALES = {"number", "proportion", "percent"}


def number(value) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 80:
        raise ValueError("Number must be a bounded decimal value")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal value") from exc
    if not result.is_finite() or (result and abs(result.adjusted()) > 100):
        raise ValueError("Nonfinite or out-of-range decimal")
    return result


def interval(quantity: dict):
    value = number(quantity["value"])
    half = number(quantity["rounding_half_width"])
    if half < 0:
        raise ValueError("Rounding half-width cannot be negative")
    scale = quantity["scale"]
    if scale not in SCALES:
        raise ValueError("Unknown scale")
    factor = Decimal(100) if scale == "percent" else Decimal(1)
    return value / factor, (value - half) / factor, (value + half) / factor


def calculate(operation: str, values: list[tuple]) -> tuple:
    if operation not in OPERATIONS:
        raise ValueError("Unsupported operation; remains unresolved")
    if not 1 <= len(values) <= 100:
        raise ValueError("Between 1 and 100 inputs are required")
    if operation in {"difference", "ratio", "percent_change", "percentage_points"} and len(values) != 2:
        raise ValueError("This operation requires exactly two inputs")
    if operation in {"sum", "mean"}:
        sums = tuple(sum(v[i] for v in values) for i in range(3))
        return tuple(v / len(values) for v in sums) if operation == "mean" else sums
    if operation in {"difference", "percentage_points"}:
        a, b = values
        return a[0] - b[0], a[1] - b[2], a[2] - b[1]
    if operation == "product":
        mid = lo = hi = Decimal(1)
        for m, l, h in values:
            mid *= m
            corners = [lo*l, lo*h, hi*l, hi*h]
            lo, hi = min(corners), max(corners)
        return mid, lo, hi
    a, b = values
    if b[1] <= 0 <= b[2]:
        raise ValueError("Denominator rounding interval includes zero; unresolved")
    corners = [x / y for x in a[1:] for y in b[1:]]
    result = a[0] / b[0], min(corners), max(corners)
    # percent_change is (new / old - 1); both inputs must describe same scale.
    return tuple(v - 1 for v in result) if operation == "percent_change" else result


def evaluate(check: dict) -> dict:
    """A failed/unsupported calculation is unresolved, never a verified error."""
    unresolved = {"status": "unresolved", "arithmetic_only": True}
    if check.get("kind") != "arithmetic":
        return {**unresolved, "reason": "Not an independently recomputable arithmetic check"}
    try:
        inputs, reported = check["quantities"], check["reported"]
        if not isinstance(inputs, list) or not 1 <= len(inputs) <= 100:
            raise ValueError("Between 1 and 100 quantities are required")
        quantities = [*inputs, reported]
        if any(not all(str(q.get(k) or "").strip() for k in
                       ("source_id", "unit", "sample", "denominator", "context")) for q in quantities):
            raise ValueError("Source links, units, sample, denominator and contexts are required")
        for key in ("sample", "denominator"):
            if len({q[key] for q in quantities}) != 1:
                raise ValueError(f"Mismatched {key}; comparison remains unresolved")
        operation = check["operation"]
        if operation in {"sum", "mean", "difference", "percentage_points", "percent_change"}:
            if len({q["unit"] for q in inputs}) != 1:
                raise ValueError("Input units do not match")
            if len({q["scale"] == "number" for q in inputs}) != 1:
                raise ValueError("Number and proportion/percent scales cannot be interchanged")
        if operation == "percentage_points" and any(q["scale"] not in {"percent", "proportion"} for q in inputs):
            raise ValueError("Percentage-point differences need percent/proportion inputs")
        if operation in {"sum", "mean", "difference"} and reported["unit"] != inputs[0]["unit"]:
            raise ValueError("Reported and computed units differ")
        tolerance = number(check["tolerance"])
        if tolerance < 0:
            raise ValueError("Tolerance cannot be negative")
        with localcontext() as ctx:
            ctx.prec = 40
            result = calculate(operation, [interval(q) for q in inputs])
            observed = interval(reported)
            factor = Decimal(100) if reported["scale"] == "percent" else Decimal(1)
            if operation in {"percent_change", "percentage_points"} and reported["scale"] == "number":
                raise ValueError("Ratio/change comparison must specify proportion or percent scale")
            tolerance /= factor
            if not all(v.is_finite() for v in (*result, *observed)):
                raise ValueError("Nonfinite result")
            if abs(number(check["computed_value"]) / factor - result[0]) > max(tolerance, Decimal("1e-30")):
                raise ValueError("Declared computed value differs from deterministic recomputation")
            compatible = result[1] - tolerance <= observed[2] and observed[1] <= result[2] + tolerance
            return {"status": "rounding_compatible" if compatible else "arithmetic_discrepancy",
                    "computed": str(result[0] * factor), "scale": reported["scale"],
                    "computed_interval": [str(v * factor) for v in result[1:]],
                    "reported_interval": [str(v * factor) for v in observed[1:]],
                    "arithmetic_only": True, "comparability": "requires_source_assessment"}
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        return {**unresolved, "reason": str(exc)}


def numeric_errors(check: dict, source_ids: set[str], *, cannot_verify: bool) -> list[str]:
    if check.get("kind") not in {"arithmetic", "cross_source", "underdetermined"}:
        return ["numeric_check needs a typed check; legacy calculations remain diagnostic only"]
    quantities = check.get("quantities", [])
    if check.get("reported"):
        quantities = [*quantities, check["reported"]]
    errors = []
    for q in quantities:
        if q.get("source_id") not in source_ids:
            errors.append("numeric_check references an undeclared source quantity")
    if check["kind"] == "underdetermined":
        if not cannot_verify or check.get("status") != "unresolved" or not check.get("missing_information"):
            errors.append("Underdetermined numeric_check must remain cannot_verify with missing information")
    elif check["kind"] == "arithmetic":
        verdict = evaluate(check)
        if verdict["status"] != "arithmetic_discrepancy" and not cannot_verify:
            errors.append("numeric_check does not establish a numerical discrepancy: " + verdict["status"])
    elif len(quantities) < 2 or not str(check.get("comparability") or "").strip():
        errors.append("Cross-source numeric_check requires both quantities and their comparability rationale")
    return errors


def quantity_source_errors(check: dict, sources: list[dict], *, cannot_verify: bool = False) -> list[str]:
    """Published quantities must occur in their quoted source evidence.

    Visual quantities remain explicitly assessor-checked. Matching a number does
    not establish its unit, sample, denominator, estimand or role in the claim.
    No undocumented scaling, transformations or inferred input values are allowed.
    """
    if check.get("kind") not in {"arithmetic", "cross_source"}:
        return []
    by_id = {s["id"]: s for s in sources}
    token = re.compile(r"(?<![\w.+,\-\u2212])[-+\u2212]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?(?!\w|[.,]\d)")
    errors = []
    quantities = list(check.get("quantities", []))
    if check.get("reported"):
        quantities.append(check["reported"])
    for quantity in quantities:
        source = by_id.get(quantity.get("source_id"))
        if source and source.get("correspondence") in {"unresolved", "url_only", None} and not cannot_verify:
            errors.append("Indispensable numerical source is unresolved; retain conditional analysis as cannot_verify")
        if source is None or source.get("correspondence") != "text":
            continue  # Link validity and explicit visual/unresolved state checked elsewhere.
        try:
            quote = source.get("text_quote") or ""
            raw_value = quantity.get("value")
            if check["kind"] == "cross_source" and raw_value in {"+", "-", "\u2212"}:
                # Published polarity labels are a legitimate comparison, not
                # invented +/-1 measurements. Require a standalone exact symbol.
                if not re.search(r"(?<![\w.+,\-\u2212])" + re.escape(raw_value) + r"(?![\w.+,%\-\u2212])", quote):
                    errors.append("Published polarity symbol is not present as a standalone source label")
                continue
            value = number(raw_value)
            matches = [m for m in token.finditer(quote)
                       if number(m.group().replace(",", "").replace("\u2212", "-")) == value]
            if not matches:
                errors.append("Numerical quantity is not present in its source quote; copy published values/scales or retain explicit unresolved/visual evidence")
            elif all(re.match(r"\s*(?:%|percent\b)", quote[m.end():], re.IGNORECASE) for m in matches) and quantity.get("scale") != "percent":
                errors.append("Published percent quantity must retain its percent scale")
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a bounded arithmetic JSON request from stdin; no code or paths are executed.")
    parser.parse_args()
    raw = sys.stdin.read(65537)
    if len(raw) > 65536:
        raise ValueError("Request exceeds 64 KiB")
    result = evaluate(json.loads(raw))
    print(json.dumps(result, allow_nan=False))
    return 0 if result["status"] != "unresolved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
