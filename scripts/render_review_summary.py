#!/usr/bin/env python3
"""Recompute a privacy-minimal review summary, never a release authorization."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from contextlib import ExitStack
from datetime import date, datetime
from pathlib import Path
from typing import Any

from approval_contract import REFERENCE_ID, validate_source_contract
from apply_approved_edits import build_entry_pair
from hwpx_common import count_structure, read_entry_map, read_json, section_names, sha256_file, validate_basic_hwpx
from hwpx_locations import LOCATION_SCHEME, parse_section, validate_location_id
from render_legal_review_report import DATE, DATE_OR_UNKNOWN, require_string, validate_payload
from verify_release_pair import compare_entries

HASH = re.compile(r"[0-9a-fA-F]{64}\Z")
ENTRY_ID = re.compile(r"zip-entry-[1-9][0-9]*\Z")
FINDING_ID = re.compile(r"finding-[1-9][0-9]*\Z")
ARTIFACTS = ("source", "approved_plan", "approval", "disclosure", "legal_review")
HUMAN_ROLES = {
    "approval_open": "document_reviewer", "disclosure_open": "document_reviewer",
    "legal_review": "legal_reviewer", "public_decision": "disclosure_officer", "final_confirmation": "final_owner",
}
CHECKS = ("artifact_read", "source_contract", "package_structure", "technical_pair", "legal_record",
          "legal_source_binding", "legal_resolution", "human_evidence", "public_review_coverage", "input_stability")
HUMAN_LABELS = {
    "approval_open": ("결재용 한글 열람", "OPEN_APPROVAL_IN_HANCOM"),
    "disclosure_open": ("공개용 한글 열람", "OPEN_DISCLOSURE_IN_HANCOM"),
    "legal_review": ("법률 담당 확인", "RESOLVE_LEGAL_RECORD_GAPS"),
    "public_decision": ("정보공개 담당 판단", "REVIEW_ALL_PACKAGE_REFERENCES"),
    "final_confirmation": ("최종 담당 확인", "CONFIRM_FINAL_OWNER"),
}
NEXT_ACTIONS = (
    {"owner_role": "document_reviewer", "action_code": "RECHECK_CURRENT_ARTIFACTS_AND_BINDINGS"},
    {"owner_role": "document_reviewer", "action_code": "OPEN_APPROVAL_IN_HANCOM"},
    {"owner_role": "document_reviewer", "action_code": "OPEN_DISCLOSURE_IN_HANCOM"},
    {"owner_role": "legal_reviewer", "action_code": "RESOLVE_LEGAL_RECORD_GAPS"},
    {"owner_role": "disclosure_officer", "action_code": "REVIEW_ALL_PACKAGE_REFERENCES"},
    {"owner_role": "final_owner", "action_code": "CONFIRM_FINAL_OWNER"},
    {"owner_role": "final_owner", "action_code": "OBTAIN_SEPARATE_INSTITUTIONAL_RELEASE_APPROVAL"},
)
TRANSCRIPT_WARNING = "전사 원본 대조 미실행: 전사 누락·전사 정확도 확인 불가"


def _status(*values: str) -> str:
    return max(values, key={"PASS": 0, "PARTIAL": 1, "FAIL": 2}.__getitem__) if values else "PASS"


def _hash(value: Any) -> bool:
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except ValueError:
        return False


def _coverage(values: Any, required: set[str], pattern: re.Pattern[str]) -> str:
    if values is None:
        return "PARTIAL" if required else "PASS"
    if not isinstance(values, list) or any(not isinstance(value, str) or not pattern.fullmatch(value) for value in values):
        return "FAIL"
    if len(values) != len(set(values)):
        return "FAIL"
    return "PASS" if set(values) == required else "PARTIAL"


def validate_human_evidence(
    payload: Any, artifact_hashes: dict[str, str | None],
    manual_entry_ids: tuple[str, ...] | list[str] = (), finding_ids: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """Validate a provided human claim's form/bindings, not its authenticity."""
    result: dict[str, Any] = {
        "status": "PARTIAL", "hash_bindings": "PARTIAL", "coverage_status": "PARTIAL",
        "checks": {key: "PARTIAL" for key in HUMAN_ROLES},
        "statement_type": "provided_human_claim_not_execution_attestation",
    }
    if payload is None:
        return result
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        result["status"] = "FAIL"
        return result
    statuses: list[str] = []
    bindings = payload.get("artifact_hashes")
    if bindings is None:
        result["hash_bindings"] = "PARTIAL"
    elif not isinstance(bindings, dict) or any(key not in ARTIFACTS for key in bindings):
        result["hash_bindings"] = "FAIL"
    else:
        binding_states = []
        for key in ARTIFACTS:
            value = bindings.get(key)
            actual = artifact_hashes.get(key)
            if value is None:
                binding_states.append("PARTIAL")
            elif not _hash(value):
                binding_states.append("FAIL")
            elif actual is None:
                binding_states.append("PARTIAL")
            else:
                binding_states.append("PASS" if value.lower() == actual.lower() else "FAIL")
        result["hash_bindings"] = _status(*binding_states)
    statuses.append(result["hash_bindings"])
    checks = payload.get("checks")
    if checks is None:
        checks = {}
    if not isinstance(checks, dict) or any(key not in HUMAN_ROLES for key in checks):
        result["status"] = "FAIL"
        return result
    for check_id, role in HUMAN_ROLES.items():
        check = checks.get(check_id)
        state = "PARTIAL"
        if check is not None:
            if not isinstance(check, dict) or not isinstance(check.get("result"), str) or check["result"] not in {"pass", "pending", "fail"}:
                state = "FAIL"
            elif check["result"] == "fail":
                state = "FAIL"
            elif check["result"] == "pass":
                fields = ("reviewer_role", "checked_at", "evidence_refs")
                if any(field not in check for field in fields):
                    state = "PARTIAL"
                else:
                    refs = check["evidence_refs"]
                    valid_refs = isinstance(refs, list) and bool(refs) and all(
                        isinstance(ref, str) and REFERENCE_ID.fullmatch(ref) is not None for ref in refs)
                    state = "PASS" if check["reviewer_role"] == role and _timestamp(check["checked_at"]) and valid_refs else "FAIL"
        result["checks"][check_id] = state
        statuses.append(state)
    public = checks.get("public_decision", {})
    coverage = public.get("coverage", {}) if isinstance(public, dict) else {}
    if not isinstance(coverage, dict):
        result["coverage_status"] = "FAIL"
    else:
        result["coverage_status"] = _status(
            result["checks"]["public_decision"],
            _coverage(coverage.get("manual_entry_ids"), set(manual_entry_ids), ENTRY_ID),
            _coverage(coverage.get("finding_ids"), set(finding_ids), FINDING_ID),
        )
    statuses.append(result["coverage_status"])
    result["status"] = _status(*statuses)
    return result


def _legal_summary(payload: Any, source_hash: str, entries: dict[str, bytes]) -> tuple[dict[str, str], dict[str, int]]:
    if isinstance(payload, dict) and payload.get("issues") == []:
        # The shared report renderer requires at least one finding. A valid empty
        # review is still unconfirmed here; do not invent a finding to validate it.
        case, issues = payload.get("case"), []
        if not isinstance(case, dict):
            raise ValueError
        for field in ("case_token", "reviewed_at", "reviewer_role", "source_document_hash"):
            require_string(case, field, "case")
        if not DATE.fullmatch(case["reviewed_at"]) or not isinstance(case.get("event_dates"), dict):
            raise ValueError
        for field in ("event_date", "hearing_date", "disposition_date", "minutes_finalized_date"):
            value = case["event_dates"].get(field)
            if not isinstance(value, str) or not DATE_OR_UNKNOWN.fullmatch(value):
                raise ValueError
    else:
        case, issues = validate_payload(payload)
    states = {"legal_record": "PASS", "legal_source_binding": "PASS", "legal_resolution": "PASS"}
    if not issues:
        states.update(legal_record="PARTIAL", legal_resolution="PARTIAL")
    counts = {"legal_issues": len(issues), "high_risk_issues": 0, "legal_action_l": 0, "legal_action_v": 0,
              "unresolved_legal_issues": 0, "unverified_legal_bases": 0, "unknown_case_dates": 0}
    scheme = payload.get("location_scheme")
    if scheme is None:
        states["legal_source_binding"] = "PARTIAL"
    elif scheme != LOCATION_SCHEME:
        states["legal_source_binding"] = "FAIL"
    linked_hash = case["source_document_hash"]
    if not _hash(linked_hash):
        states["legal_source_binding"] = _status(states["legal_source_binding"], "PARTIAL")
    elif linked_hash.lower() != source_hash:
        states["legal_source_binding"] = "FAIL"
    paragraphs = {
        paragraph.location_id: hashlib.sha256(paragraph.own_text.encode("utf-8")).hexdigest()
        for index, name in enumerate(section_names(entries)) for paragraph in parse_section(index, entries[name])
    }
    for value in case["event_dates"].values():
        if value == "미확인":
            counts["unknown_case_dates"] += 1
        else:
            date.fromisoformat(value)
    date.fromisoformat(case["reviewed_at"])
    for issue in issues:
        counts["high_risk_issues"] += int(issue["risk_level"] == "높음")
        counts["legal_action_l"] += int(issue["action_code"] == "L")
        counts["legal_action_v"] += int(issue["action_code"] == "V")
        location = issue["location_id"]
        try:
            validate_location_id(location)
        except ValueError:
            location = ""
        statement_hash = issue["statement_text_hash"]
        if location not in paragraphs or not _hash(statement_hash):
            states["legal_source_binding"] = _status(states["legal_source_binding"], "PARTIAL")
        elif statement_hash.lower() != paragraphs[location]:
            states["legal_source_binding"] = "FAIL"
        unresolved = bool(counts["unknown_case_dates"]) or issue["confidence"] != "충분"
        resolved_statuses = {"담당자 승인", "수정 반영", "법무 확인", "정보공개 담당 확인"}
        unresolved |= issue["approval_status"] not in resolved_statuses
        if issue["action_code"] == "L" or issue["risk_level"] == "높음":
            unresolved |= issue["approval_status"] != "법무 확인"
        if issue["action_code"] == "V":
            unresolved |= issue["approval_status"] not in {"수정 반영", "법무 확인"}
        for basis in issue["legal_basis"]:
            date.fromisoformat(basis["retrieved_at"])
            basis_unverified = basis["verification_status"] != "원문확인"
            for field in ("promulgation_date", "effective_date", "applicable_event_date"):
                if basis[field] == "미확인":
                    basis_unverified = True
                else:
                    date.fromisoformat(basis[field])
            counts["unverified_legal_bases"] += int(basis_unverified)
            unresolved |= basis_unverified
        counts["unresolved_legal_issues"] += int(unresolved)
    if counts["unresolved_legal_issues"]:
        states["legal_resolution"] = "PARTIAL"
    return states, counts


def _next_actions(summary: dict[str, Any]) -> list[dict[str, str]]:
    checks = summary.get("checks", {})
    human = summary.get("human_evidence", {})
    human_checks = human.get("checks", {})
    needed: set[str] = set()
    technical = ("artifact_read", "source_contract", "package_structure", "technical_pair", "input_stability")
    if any(checks.get(key, {}).get("status") != "PASS" for key in technical) or human.get("hash_bindings") != "PASS":
        needed.add("RECHECK_CURRENT_ARTIFACTS_AND_BINDINGS")
    for key in ("approval_open", "disclosure_open"):
        if human_checks.get(key) != "PASS":
            needed.add(HUMAN_LABELS[key][1])
    if any(checks.get(key, {}).get("status") != "PASS" for key in ("legal_record", "legal_source_binding", "legal_resolution")) or human_checks.get("legal_review") != "PASS":
        needed.add("RESOLVE_LEGAL_RECORD_GAPS")
    if checks.get("public_review_coverage", {}).get("status") != "PASS" or human_checks.get("public_decision") != "PASS":
        needed.add("REVIEW_ALL_PACKAGE_REFERENCES")
    if human_checks.get("final_confirmation") != "PASS":
        needed.add("CONFIRM_FINAL_OWNER")
    if summary.get("quality_result") == "PASS":
        needed.add("OBTAIN_SEPARATE_INSTITUTIONAL_RELEASE_APPROVAL")
    return [dict(action) for action in NEXT_ACTIONS if action["action_code"] in needed]


def build_summary(
    source: Path, approved: Path, approval: Path, disclosure: Path,
    legal_review: Path | None = None, human_evidence: Path | None = None,
) -> dict[str, Any]:
    """Read current local artifacts and return only allowlisted, source-free data."""
    paths = {"source": Path(source), "approved_plan": Path(approved), "approval": Path(approval),
             "disclosure": Path(disclosure), "legal_review": Path(legal_review) if legal_review is not None else None}
    hashes: dict[str, str | None] = {key: None for key in ARTIFACTS}
    checks = {key: {"status": "PARTIAL", "code": "NOT_VERIFIED"} for key in CHECKS}
    summary: dict[str, Any] = {
        "schema_version": 1, "quality_result": "PARTIAL", "external_release_authorized": False,
        "artifacts": {key: {"artifact_ref": "artifact:" + key.replace("_", "-"), "sha256": None, "status": "PARTIAL"}
                      for key in ARTIFACTS},
        "checks": checks, "counts": {},
        "disclosure_package": {"release_ready": False, "manual_review_refs": [], "residual_finding_refs": [],
                               "checked_entry_count": 0, "terms_configured": 0, "configured_terms_check_pass": False},
        "human_evidence": validate_human_evidence(None, hashes),
        "next_actions": [], "warnings": [TRANSCRIPT_WARNING],
        "interpretation": "evidence_format_and_technical_requirements_only_not_public_release_approval",
    }

    def record(key: str, state: str, code: str) -> None:
        checks[key] = {"status": state, "code": code}

    read_state = "PASS"
    for key, path in paths.items():
        if path is None:
            read_state = _status(read_state, "PARTIAL")
            continue
        try:
            hashes[key] = sha256_file(path)
            summary["artifacts"][key].update(sha256=hashes[key], status="PASS")
        except Exception:
            summary["artifacts"][key]["status"] = "FAIL"
            read_state = "FAIL"
    record("artifact_read", read_state, "ARTIFACTS_CURRENT" if read_state == "PASS" else "ARTIFACT_UNAVAILABLE")
    entries: dict[str, bytes] = {}
    pair: dict[str, Any] | None = None
    try:
        for path in (paths["source"], paths["approval"], paths["disclosure"]):
            validate_basic_hwpx(path)
            infos, entry_map = read_entry_map(path)
            if len(infos) != len(entry_map):
                raise ValueError
        _, entries = read_entry_map(paths["source"])
        _, approval_entries = read_entry_map(paths["approval"])
        _, disclosure_entries = read_entry_map(paths["disclosure"])
        structures = [{name: count_structure(value) for name, value in data.items() if name in section_names(data)}
                      for data in (entries, approval_entries, disclosure_entries)]
        if structures[0] != structures[1] or structures[1] != structures[2]:
            raise ValueError
        record("package_structure", "PASS", "STRUCTURE_MATCH")
    except Exception:
        record("package_structure", "FAIL", "STRUCTURE_OR_PACKAGE_INVALID")
    try:
        specification = read_json(paths["approved_plan"])
        validate_source_contract(specification, paths["source"])
        record("source_contract", "PASS", "SOURCE_CONTRACT_VALID")
        pair = build_entry_pair(entries, specification)
        summary["counts"].update(approved_edits=len(pair["approval_changes"]), approved_redactions=len(pair["redactions"]))
        if checks["package_structure"]["status"] != "PASS":
            raise ValueError
        _, actual_approval = read_entry_map(paths["approval"])
        _, actual_disclosure = read_entry_map(paths["disclosure"])
        compare_entries(pair["approval_entries"], actual_approval, "approval")
        compare_entries(pair["disclosure_entries"], actual_disclosure, "disclosure")
        record("technical_pair", "PASS", "SOURCE_RECOMPUTED_PAIR_MATCH")
    except Exception:
        if checks["source_contract"]["status"] != "PASS":
            record("source_contract", "FAIL", "SOURCE_CONTRACT_INVALID")
        record("technical_pair", "FAIL", "SOURCE_RECOMPUTED_PAIR_MISMATCH")
    if pair is not None:
        package = pair["disclosure_package"]
        manual = sorted({item["entry_id"] for item in package["coverage"]["manual_review_entries"]})
        findings = [f"finding-{index}" for index in range(1, len(package["findings"]) + 1)]
        summary["disclosure_package"].update(
            manual_review_refs=manual, residual_finding_refs=findings,
            checked_entry_count=len(package["coverage"]["checked_entries"]),
            terms_configured=package["coverage"]["terms_configured"],
            configured_terms_check_pass=package["configured_terms_check_pass"],
        )
        summary["counts"].update(manual_package_entries=len(manual), residual_findings=len(findings))
    if legal_review is not None:
        try:
            legal_states, counts = _legal_summary(read_json(Path(legal_review)), hashes["source"] or "", entries)
            summary["counts"].update(counts)
            for key, state in legal_states.items():
                record(key, state, "LEGAL_RECORD_CHECKED" if state == "PASS" else "LEGAL_RECORD_GAPS")
        except Exception:
            record("legal_record", "FAIL", "LEGAL_RECORD_INVALID")
    human = None
    try:
        if human_evidence is not None:
            human = read_json(Path(human_evidence))
        package_summary = summary["disclosure_package"]
        human_result = validate_human_evidence(human, hashes, package_summary["manual_review_refs"], package_summary["residual_finding_refs"])
        summary["human_evidence"] = human_result
        record("human_evidence", human_result["status"], "HUMAN_CLAIM_FORM_AND_BINDINGS")
        record("public_review_coverage", human_result["coverage_status"], "CURRENT_PACKAGE_COVERAGE")
    except Exception:
        summary["human_evidence"]["status"] = "FAIL"
        record("human_evidence", "FAIL", "HUMAN_EVIDENCE_INVALID")
    stability = "PASS"
    for key, path in paths.items():
        if path is not None and hashes[key] is not None:
            try:
                if sha256_file(path) != hashes[key]:
                    stability = "FAIL"
            except Exception:
                stability = "FAIL"
    record("input_stability", stability, "INPUTS_STABLE" if stability == "PASS" else "INPUT_CHANGED_DURING_REVIEW")
    summary["quality_result"] = _status(*(value["status"] for value in checks.values()))
    summary["next_actions"] = _next_actions(summary)
    return summary


def render_summary(summary: dict[str, Any]) -> str:
    """Render our allowlisted model without repeating arbitrary input strings."""
    state = summary["quality_result"] if summary.get("quality_result") in {"PASS", "PARTIAL", "FAIL"} else "FAIL"
    lines = ["# 검수요약", "", f"- 품질판정: {state}", "- 외부 공개 승인: false", "- disclosure_package.release_ready: false", "",
             "> 사람의 진술을 형식·해시로 확인한 결과이며 실제 한글 실행 인증이 아닙니다.",
             "> PASS는 제공 증거 형식과 기술요건 충족을 뜻하며 법률적 타당성이나 외부 공개 승인이 아닙니다.", "",
             "- " + TRANSCRIPT_WARNING, "",
             "## 자료 결속", "", "| 자료 참조 | SHA-256 | 상태 |", "| --- | --- | --- |"]
    for key in ARTIFACTS:
        item = summary.get("artifacts", {}).get(key, {})
        digest = item.get("sha256") if _hash(item.get("sha256")) else "—"
        item_state = item.get("status") if item.get("status") in {"PASS", "PARTIAL", "FAIL"} else "FAIL"
        lines.append(f"| artifact:{key.replace('_', '-')} | {digest} | {item_state} |")
    lines.extend(["", "## 확인 상태", "", "| 검사 | 상태 |", "| --- | --- |"])
    for key in CHECKS:
        value = summary.get("checks", {}).get(key, {}).get("status")
        lines.append(f"| {key} | {value if value in {'PASS', 'PARTIAL', 'FAIL'} else 'FAIL'} |")
    lines.extend(["", "## 사람 확인 진술", "", "| 확인 항목 | 상태 | 담당 역할 | 다음 조치 |", "| --- | --- | --- | --- |"])
    for key in HUMAN_ROLES:
        value = summary.get("human_evidence", {}).get("checks", {}).get(key)
        label, action = HUMAN_LABELS[key]
        next_action = "확인 진술 완료" if value == "PASS" else action
        lines.append(f"| {label} (`{key}`) | {value if value in {'PASS', 'PARTIAL', 'FAIL'} else 'FAIL'} | {HUMAN_ROLES[key]} | {next_action} |")
    lines.extend(["", "## 공개 담당 전건 검토 참조", ""])
    package = summary.get("disclosure_package", {})
    coverage_state = summary.get("human_evidence", {}).get("coverage_status")
    lines.append(f"- 전건 확인 상태: {coverage_state if coverage_state in {'PASS', 'PARTIAL', 'FAIL'} else 'FAIL'}")
    for field, pattern in (("manual_review_refs", ENTRY_ID), ("residual_finding_refs", FINDING_ID)):
        for value in package.get(field, []):
            if isinstance(value, str) and pattern.fullmatch(value):
                lines.append(f"- {value}")
    lines.extend(["", "## 건수", ""])
    for key in ("approved_edits", "approved_redactions", "legal_issues", "high_risk_issues", "legal_action_l", "legal_action_v",
                "unresolved_legal_issues", "unverified_legal_bases", "unknown_case_dates", "manual_package_entries", "residual_findings"):
        value = summary.get("counts", {}).get(key)
        lines.append(f"- {key}: {value if type(value) is int and value >= 0 else '미확인'}")
    lines.extend(["", "## 다음 담당·조치", ""])
    for action in _next_actions(summary):
        lines.append(f"- {action['owner_role']}: {action['action_code']}")
    lines.extend(["", "## 자동 확인 범위 밖", "", "- 법률적 결론·정보공개 결정·실제 한글 열람의 진위·외부 공개 승인", ""])
    return "\n".join(lines)


def _output_paths(outputs: list[Path], inputs: list[Path]) -> None:
    normalized = [path.resolve() for path in outputs]
    if len(set(normalized)) != len(outputs):
        raise ValueError
    for path, resolved in zip(outputs, normalized):
        if path.exists() or path.is_symlink() or resolved in {item.resolve() for item in inputs}:
            raise ValueError
        for item in inputs:
            if path.exists() and item.exists() and path.samefile(item):
                raise ValueError


class _SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError


def main() -> int:
    parser = _SafeParser(description=__doc__)
    for key in ("source", "approved", "approval", "disclosure"):
        parser.add_argument("--" + key, required=True, type=Path)
    parser.add_argument("--legal-review", type=Path)
    parser.add_argument("--human-evidence", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    try:
        args = parser.parse_args()
        inputs = [value for key, value in vars(args).items() if key not in {"output", "json"} and value is not None]
        _output_paths([args.output, args.json], inputs)
    except Exception:
        print("FAIL: OUTPUT_OR_ARGUMENT_CONTRACT", file=sys.stderr)
        return 1
    summary = build_summary(args.source, args.approved, args.approval, args.disclosure, args.legal_review, args.human_evidence)
    try:
        for path in (args.output, args.json):
            path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also rejects output races after the preflight.
        with ExitStack() as stack:
            md = stack.enter_context(args.output.open("x", encoding="utf-8", newline="\n"))
            js = stack.enter_context(args.json.open("x", encoding="utf-8", newline="\n"))
            md.write(render_summary(summary))
            json.dump(summary, js, ensure_ascii=False, indent=2)
            js.write("\n")
    except Exception:
        print("FAIL: SUMMARY_OUTPUT_UNAVAILABLE", file=sys.stderr)
        return 1
    print("SUMMARY_" + summary["quality_result"])
    return 1 if summary["quality_result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
