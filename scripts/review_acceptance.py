"""Completion policy shared by both hosts; schema validity is not completion.

Legacy outputs remain readable evidence, but cannot acquire a completion receipt
without a new audit. Individual unavailable sources need not invalidate a finished
attempt; unattempted required work always does.
"""
from __future__ import annotations

POLICY_VERSION = 1


def acceptance_errors(data: dict) -> list[str]:
    errors = []
    status = data.get("run_status")
    if status not in {"ok", "cannot_verify"}:
        errors.append(f"Audit is not complete: run_status={status!r}.")
    completion = data.get("completion")
    if not isinstance(completion, dict) or completion.get("version") != POLICY_VERSION:
        return [*errors, "Legacy/unknown completion record: retained for diagnosis, not accepted as completed work."]
    state = completion.get("state")
    if state not in {"complete", "not_applicable"}:
        errors.append(f"Audit is not complete: completion.state={state!r}.")
    if not str(completion.get("scope_description") or "").strip():
        errors.append("Completion must describe the assigned scope actually assessed.")
    if completion.get("missing_checks") != []:
        errors.append("Required checks are missing; preserve this output as partial, not completed.")
    checks = completion.get("checks_completed")
    if not isinstance(checks, list) or not checks or any(not str(c).strip() for c in checks):
        errors.append("Completion requires a nonempty record of checks actually performed.")
    if state == "not_applicable" and (data.get("findings") or status != "ok"):
        errors.append("An inapplicable remit must have run_status=ok and no manufactured findings.")
    if status == "cannot_verify" and not completion.get("evidence_limitations"):
        errors.append("A completed evidence-limited audit must describe its evidence limitations.")
    if data.get("reviewer") == "parser_quality_auditor" and (
        status == "cannot_verify" or any(r.get("item_id") == "assigned_remit" and
            r.get("status") == "cannot_verify" for r in data.get("coverage", []))
    ):
        errors.append("Preflight found no trustworthy source representation/fallback for its overall remit; substantive review is blocked.")
    return errors


def require_complete(data: dict) -> None:
    errors = acceptance_errors(data)
    if errors:
        raise ValueError("; ".join(errors))
