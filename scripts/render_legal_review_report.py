#!/usr/bin/env python3
"""Validate de-identified legal-review records and render a Markdown review table.

This program never reads HWPX minutes.  Give it a locally prepared, de-identified
JSON review record; it refuses a high-risk record that lacks a fact/evidence/
official-source trail.  It is a review aid, not a legal conclusion engine.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ISSUE_TYPES = {"절차", "사실인정", "재량판단", "편견·예단", "개인정보", "기록무결성", "명예·분쟁확대", "법적 근거"}
RISK_LEVELS = {"높음", "중간", "낮음"}
ACTION_CODES = {"K", "S", "N", "D", "L", "V"}
CONFIDENCE = {"충분", "부분", "부족"}
SCOPES = {"결재용", "정보공개청구용", "양쪽"}
APPROVALS = {"미검토", "담당자 승인", "수정 반영", "법무 확인", "반려", "정보공개 담당 확인"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fail(message: str) -> None:
    raise ValueError(message)


def require_string(record: dict[str, Any], field: str, issue_id: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        fail(f"{issue_id}: {field}가 필요합니다.")
    return value.strip()


def require_list(record: dict[str, Any], field: str, issue_id: str) -> list[Any]:
    value = record.get(field)
    if not isinstance(value, list) or not value:
        fail(f"{issue_id}: {field}는 비어 있지 않은 배열이어야 합니다.")
    return value


def validate_basis(basis: dict[str, Any], issue_id: str) -> None:
    for field in ("law_name", "article", "effective_date", "applicable_event_date", "retrieved_at", "source_type", "source_id", "verification_status"):
        require_string(basis, field, issue_id)
    for field in ("effective_date", "applicable_event_date", "retrieved_at"):
        if not DATE.fullmatch(str(basis[field])):
            fail(f"{issue_id}: {field}은 YYYY-MM-DD 형식이어야 합니다.")
    if basis["verification_status"] not in {"원문확인", "시점확인필요", "법무확인필요"}:
        fail(f"{issue_id}: 알 수 없는 verification_status입니다.")


def validate_issue(issue: dict[str, Any]) -> None:
    issue_id = require_string(issue, "issue_id", "unknown")
    for field in ("location", "location_id", "speaker_role", "statement_summary", "statement_text_hash", "source_level", "reasoning_summary", "suggested_wording"):
        require_string(issue, field, issue_id)
    if issue["source_level"] not in {"E1", "E2", "E3", "E4", "E5"}:
        fail(f"{issue_id}: source_level은 E1~E5여야 합니다.")
    for field in ("legal_factor", "legal_issue_type", "risk_type", "evidence_to_check"):
        require_list(issue, field, issue_id)
    if not set(issue["legal_issue_type"]).issubset(ISSUE_TYPES):
        fail(f"{issue_id}: legal_issue_type 값이 올바르지 않습니다.")
    if issue.get("risk_level") not in RISK_LEVELS:
        fail(f"{issue_id}: risk_level 값이 올바르지 않습니다.")
    if issue.get("action_code") not in ACTION_CODES:
        fail(f"{issue_id}: action_code 값이 올바르지 않습니다.")
    if issue.get("recommended_scope") not in SCOPES:
        fail(f"{issue_id}: recommended_scope 값이 올바르지 않습니다.")
    if issue.get("confidence") not in CONFIDENCE:
        fail(f"{issue_id}: confidence 값이 올바르지 않습니다.")
    if issue.get("approval_status") not in APPROVALS:
        fail(f"{issue_id}: approval_status 값이 올바르지 않습니다.")

    bases = require_list(issue, "legal_basis", issue_id)
    for basis in bases:
        if not isinstance(basis, dict):
            fail(f"{issue_id}: legal_basis 항목은 객체여야 합니다.")
        validate_basis(basis, issue_id)
    if issue["risk_level"] == "높음" and issue["action_code"] != "L":
        fail(f"{issue_id}: 높은 위험은 L 법무 확인으로 남겨야 합니다.")


def validate_payload(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        fail("최상위 JSON은 객체여야 합니다.")
    case = payload.get("case")
    issues = payload.get("issues")
    if not isinstance(case, dict):
        fail("case 객체가 필요합니다.")
    for field in ("case_token", "reviewed_at", "reviewer_role", "source_document_hash"):
        require_string(case, field, "case")
    if not DATE.fullmatch(str(case["reviewed_at"])):
        fail("case.reviewed_at은 YYYY-MM-DD 형식이어야 합니다.")
    if not isinstance(issues, list) or not issues:
        fail("issues는 비어 있지 않은 배열이어야 합니다.")
    ids: set[str] = set()
    for issue in issues:
        if not isinstance(issue, dict):
            fail("issues 항목은 객체여야 합니다.")
        validate_issue(issue)
        if issue["issue_id"] in ids:
            fail(f"중복 issue_id: {issue['issue_id']}")
        ids.add(issue["issue_id"])
    return case, issues


def cell(value: Any) -> str:
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value)
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def render(case: dict[str, Any], issues: list[dict[str, Any]]) -> str:
    lines = [
        "# 법률위험 검토표",
        "",
        "> 이 문서는 법률 자문이나 처분 결론이 아닙니다. 승인 전 사실·시점·공식 원문을 재확인하십시오.",
        "",
        f"- 내부 식별자: `{cell(case['case_token'])}`",
        f"- 검토일: {cell(case['reviewed_at'])}",
        f"- 검토 역할: {cell(case['reviewer_role'])}",
        f"- 입력본 해시: `{cell(case['source_document_hash'])}`",
        "",
        "| ID | 위치 | 쟁점 | 위험 | 조치 | 적용 범위 | 자료 충족도 | 승인 상태 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for issue in issues:
        lines.append(
            "| {id} | {location} | {types} | {risk} | {action} | {scope} | {confidence} | {approval} |".format(
                id=cell(issue["issue_id"]), location=cell(issue["location_id"]), types=cell(issue["legal_issue_type"]),
                risk=cell(issue["risk_level"]), action=cell(issue["action_code"]),
                scope=cell(issue["recommended_scope"]), confidence=cell(issue["confidence"]), approval=cell(issue["approval_status"]),
            )
        )
    lines.extend(["", "## 항목별 확인", ""])
    for issue in issues:
        basis = issue["legal_basis"]
        lines.extend([
            f"### {cell(issue['issue_id'])}",
            f"- 발언 요지: {cell(issue['statement_summary'])}",
            f"- 쟁점 연결: {cell(issue['reasoning_summary'])}",
            f"- 확인 자료: {cell(issue['evidence_to_check'])}",
            f"- 반대 자료: {cell(issue.get('counterevidence', ['미확인']))}",
            f"- 제안: {cell(issue['suggested_wording'])}",
            "- 근거: " + "; ".join(f"{cell(item['law_name'])} {cell(item['article'])} (시행 {cell(item['effective_date'])}, 사건 기준 {cell(item['applicable_event_date'])}, {cell(item['verification_status'])})" for item in basis),
            "",
        ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="비식별 법률위험 기록 JSON")
    parser.add_argument("--output", required=True, type=Path, help="새 Markdown 검토표 경로")
    args = parser.parse_args()
    try:
        if args.output.exists():
            fail(f"출력 파일이 이미 존재합니다: {args.output}")
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        case, issues = validate_payload(payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(case, issues), encoding="utf-8", newline="\n")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: issues={len(issues)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
