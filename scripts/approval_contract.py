"""Validate explicit human approvals without inferring or manufacturing decisions."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from hwpx_common import sha256_file
from hwpx_locations import LOCATION_SCHEME, validate_location_id

SCHEMA_VERSION = 2
REAL_SCOPES = {"both", "approval", "결재용", "양쪽"}
DISCLOSURE_REDACTION_SCOPES = {"disclosure", "정보공개청구용"}
APPROVAL_FIELDS = ("issue_id", "decided_by_role", "decided_at", "evidence_refs", "reason")
# References are opaque identifiers, never quotations or human-readable evidence text.
REFERENCE_ID = re.compile(r"[a-z][a-z0-9.-]*:[A-Za-z0-9][A-Za-z0-9._-]*\Z")
NON_APPROVAL_STATUSES = {"반려", "미검토", "제안", "검토 중", "승인 필요", "추가 승인 필요", "rejected", "unreviewed", "pending"}


def _nonempty_string(record: dict[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"승인 항목의 {field}는 비어 있지 않은 문자열이어야 합니다.")
    return value


def approval_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Return decision linkage only; never include from/to source text."""
    return {field: record[field] for field in APPROVAL_FIELDS}


def validate_approval_spec(specification: Any, source_sha256: str | None = None) -> None:
    if not isinstance(specification, dict):
        raise ValueError("승인 목록은 JSON 객체여야 합니다.")
    if type(specification.get("schema_version")) is not int or specification["schema_version"] != SCHEMA_VERSION:
        raise ValueError("기존 승인 목록은 재검토가 필요합니다. schema_version=2, 원본 해시와 승인 메타를 명시하여 다시 승인하세요.")
    if specification.get("location_scheme") != LOCATION_SCHEME:
        raise ValueError("기존 좌표계는 재검토가 필요합니다. location_scheme=structural-v2를 명시하여 다시 승인하세요.")
    expected_hash = specification.get("source_sha256")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
        raise ValueError("source_sha256은 64자리 SHA-256 hex 값이어야 합니다.")
    if source_sha256 is not None and expected_hash.lower() != source_sha256.lower():
        raise ValueError("source_sha256이 실제 원본과 다릅니다. 변경된 원본을 재검토하고 다시 승인하세요.")

    seen_ids: set[str] = set()
    for collection, scopes in (("edits", REAL_SCOPES), ("redactions", DISCLOSURE_REDACTION_SCOPES)):
        records = specification.get(collection, [])
        if not isinstance(records, list):
            raise ValueError(f"{collection}는 배열이어야 합니다.")
        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"{collection} 항목은 객체여야 합니다.")
            item_id = _nonempty_string(record, "id")
            if item_id in seen_ids:
                raise ValueError("승인 목록에 중복 id가 있습니다.")
            seen_ids.add(item_id)
            scope = record.get("scope")
            if not isinstance(scope, str) or scope not in scopes:
                raise ValueError(f"{collection}의 scope가 허용 범위가 아닙니다. 정보공개 전용 처리는 redactions에 기록하세요.")
            if "approved" in record and type(record["approved"]) is not bool:
                raise ValueError("approved는 true 또는 false여야 합니다.")
            if record.get("approved") is not True:
                continue
            if "location" in record:
                validate_location_id(record["location"])
                if record.get("match_scope") not in (None, "paragraph"):
                    raise ValueError("location과 문서 전체 match_scope를 함께 지정할 수 없습니다.")
            elif record.get("match_scope") != "document":
                raise ValueError("승인 치환에는 location 또는 명시적인 match_scope=document가 필요합니다.")
            if record.get("redaction_type") == "문장 비공개" and "location" not in record:
                raise ValueError("문장 비공개에는 하나의 location이 필요합니다.")
            status = record.get("approval_status")
            if status is not None and (not isinstance(status, str) or status.strip() in NON_APPROVAL_STATUSES):
                raise ValueError("approved=true와 반려·미검토 상태가 충돌합니다. 재검토가 필요합니다.")
            for field in ("issue_id", "decided_by_role", "decided_at", "reason"):
                _nonempty_string(record, field)
            try:
                decided_at = datetime.fromisoformat(record["decided_at"])
            except ValueError as exc:
                raise ValueError("decided_at은 시간대가 포함된 ISO 8601 시각이어야 합니다.") from exc
            if "T" not in record["decided_at"] or decided_at.tzinfo is None or decided_at.utcoffset() is None:
                raise ValueError("decided_at에는 시각과 시간대가 필요합니다.")
            references = record.get("evidence_refs")
            if not isinstance(references, list) or not references or any(
                not isinstance(ref, str) or REFERENCE_ID.fullmatch(ref) is None for ref in references
            ):
                raise ValueError("evidence_refs에는 원문 없는 scheme:ref-id 형식의 참조 식별자를 하나 이상 기록하세요.")
            _nonempty_string(record, "from")
            if not isinstance(record.get("to"), str):
                raise ValueError("승인 항목의 to는 문자열이어야 합니다.")


def validate_source_contract(specification: Any, source: Path) -> None:
    validate_approval_spec(specification, sha256_file(source))
