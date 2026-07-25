#!/usr/bin/env python3
"""Create final real-name and disclosure HWPX copies from approved edit records.

This script accepts exact whole-text replacements only. It never edits the source file,
never performs unapproved edits, and writes a redaction ledger without raw source values.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from hwpx_common import (
    read_entry_map,
    read_json,
    replace_text_nodes,
    replace_paragraph_text,
    section_names,
    sha256_file,
    validate_basic_hwpx,
    write_json,
    write_preserving_zip,
)

REAL_SCOPES = {"both", "approval", "결재용", "양쪽"}
DISCLOSURE_REDACTION_SCOPES = {"disclosure", "정보공개청구용"}


def selected(records: list[dict[str, Any]], scopes: set[str]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record.get("approved") is True and str(record.get("scope", "both")) in scopes
    ]


def require_replacement(record: dict[str, Any]) -> tuple[str, str]:
    source = record.get("from")
    replacement = record.get("to")
    if not isinstance(source, str) or not source:
        raise ValueError(f"{record.get('id', 'unknown')}의 from 값이 비어 있습니다.")
    if not isinstance(replacement, str):
        raise ValueError(f"{record.get('id', 'unknown')}의 to 값이 문자열이 아닙니다.")
    return source, replacement


def validate_disclosure_redaction(record: dict[str, Any]) -> None:
    """Require an explicit human decision before masking a whole disclosure sentence."""
    require_replacement(record)
    if record.get("redaction_type") != "문장 비공개":
        return
    if not isinstance(record.get("location"), str) or not record["location"].strip():
        raise ValueError(f"{record.get('id', 'unknown')} 문장 비공개에는 location이 필요합니다.")
    if not isinstance(record.get("reason"), str) or not record["reason"].strip():
        raise ValueError(f"{record.get('id', 'unknown')} 문장 비공개에는 reason이 필요합니다.")
    if record.get("human_decision") not in {"담당자 승인", "정보공개 담당 확인", "법무 확인"}:
        raise ValueError(f"{record.get('id', 'unknown')} 문장 비공개에는 실무자 판단 상태가 필요합니다.")
    if int(record.get("min_matches", 1)) != 1 or int(record.get("max_matches", 1)) != 1:
        raise ValueError(f"{record.get('id', 'unknown')} 문장 비공개는 정확히 한 곳만 처리해야 합니다.")


def apply_records(
    entries: dict[str, bytes], section_files: list[str], records: list[dict[str, Any]], label: str
) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    updated = dict(entries)
    audit: list[dict[str, Any]] = []
    for record in records:
        source, replacement = require_replacement(record)
        total = 0
        per_file: dict[str, int] = {}
        if record.get("redaction_type") == "문장 비공개":
            location = str(record["location"])
            try:
                section_part, paragraph_part = location.split("/", 1)
                section_index = int(section_part.removeprefix("section-"))
                paragraph_number = int(paragraph_part.removeprefix("paragraph-"))
                filename = section_files[section_index]
            except (IndexError, ValueError) as exc:
                raise ValueError(f"{record.get('id', 'unknown')} 문장 비공개 위치 형식이 올바르지 않습니다: {location}") from exc
            changed_xml, total = replace_paragraph_text(updated[filename], paragraph_number, source, replacement)
            if total:
                updated[filename] = changed_xml
                per_file[filename] = total
        else:
            for filename in section_files:
                changed_xml, count = replace_text_nodes(updated[filename], source, replacement)
                if count:
                    updated[filename] = changed_xml
                    per_file[filename] = count
                    total += count
        required = int(record.get("min_matches", 1))
        if total < required:
            raise ValueError(
                f"{label} {record.get('id', 'unknown')}의 치환 횟수 {total}가 최소값 {required}보다 작습니다."
            )
        maximum = record.get("max_matches")
        if maximum is not None and total > int(maximum):
            raise ValueError(
                f"{label} {record.get('id', 'unknown')}의 치환 횟수 {total}가 최대값 {maximum}보다 큽니다."
            )
        audit.append(
            {
                "id": record.get("id", "unknown"),
                "kind": record.get("kind", "edit"),
                "scope": record.get("scope", "both"),
                "changed_count": total,
                "files": per_file,
                "reason": record.get("reason", ""),
            }
        )
    return updated, audit


def public_ledger(redactions: list[dict[str, Any]], audit: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = {str(item["id"]): item["changed_count"] for item in audit}
    return [
        {
            "id": record.get("id", "unknown"),
            "location": record.get("location", "위치 미지정"),
            "redaction_type": record.get("redaction_type", "기타 직접식별정보"),
            "replacement": record.get("to", ""),
            "reason": record.get("reason", "정보공개 청구용 비실명 처리"),
            "scope": "정보공개청구용 비실명 HWPX만",
            "approval_status": "승인",
            "changed_count": counts.get(str(record.get("id", "unknown")), 0),
        }
        for record in redactions
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="1차 수정 HWPX 또는 승인 전 정본 HWPX")
    parser.add_argument("--approved", required=True, type=Path, help="승인된 수정·비실명 처리 JSON")
    parser.add_argument("--approval-output", required=True, type=Path, help="결재용 실명 정본 HWPX")
    parser.add_argument("--disclosure-output", required=True, type=Path, help="정보공개 청구용 비실명 HWPX")
    parser.add_argument("--audit", required=True, type=Path, help="변경이력 JSON")
    parser.add_argument("--redaction-ledger", required=True, type=Path, help="비실명처리 대장 JSON")
    args = parser.parse_args()

    outputs = [args.approval_output.resolve(), args.disclosure_output.resolve()]
    source = args.source.resolve()
    if source in outputs:
        print("FAIL: 원본 파일을 출력 파일로 지정할 수 없습니다.", file=sys.stderr)
        return 1
    if len(set(outputs)) != 2:
        print("FAIL: 결재용과 정보공개 청구용 출력 파일은 달라야 합니다.", file=sys.stderr)
        return 1
    derived_outputs = outputs + [args.audit.resolve(), args.redaction_ledger.resolve()]
    existing = [str(path) for path in derived_outputs if path.exists()]
    if existing:
        print(f"FAIL: 기존 산출물을 덮어쓸 수 없습니다: {', '.join(existing)}", file=sys.stderr)
        return 1

    try:
        validate_basic_hwpx(source)
        specification = read_json(args.approved)
        edits = specification.get("edits", [])
        redactions = specification.get("redactions", [])
        if not isinstance(edits, list) or not isinstance(redactions, list):
            raise ValueError("edits와 redactions는 배열이어야 합니다.")

        infos, entries = read_entry_map(source)
        sections = section_names(entries.keys())
        invalid_edits = [record.get("id", "unknown") for record in selected(edits, {"disclosure", "정보공개청구용"})]
        invalid_redactions = [
            record.get("id", "unknown")
            for record in redactions
            if record.get("approved") is True
            and str(record.get("scope", "disclosure")) not in DISCLOSURE_REDACTION_SCOPES
        ]
        if invalid_edits:
            raise ValueError(f"정보공개 전용 일반 수정은 허용하지 않습니다. redactions로 이동하세요: {invalid_edits}")
        if invalid_redactions:
            raise ValueError(f"비실명 처리는 정보공개 청구용 범위만 허용합니다: {invalid_redactions}")
        for record in selected(redactions, DISCLOSURE_REDACTION_SCOPES):
            validate_disclosure_redaction(record)

        approval_records = selected(edits, REAL_SCOPES)
        disclosure_edits = approval_records
        # Whole-sentence masks need to compare against the untouched paragraph.
        # Apply them before name-level masks that may occur inside that paragraph.
        disclosure_redactions = sorted(
            selected(redactions, DISCLOSURE_REDACTION_SCOPES),
            key=lambda record: 0 if record.get("redaction_type") == "문장 비공개" else 1,
        )

        approval_entries, approval_audit = apply_records(entries, sections, approval_records, "결재용")
        disclosure_entries, disclosure_audit = apply_records(
            entries, sections, disclosure_edits + disclosure_redactions, "정보공개 청구용"
        )
        write_preserving_zip(args.approval_output, infos, approval_entries)
        write_preserving_zip(args.disclosure_output, infos, disclosure_entries)
        approval_validation = validate_basic_hwpx(args.approval_output)
        disclosure_validation = validate_basic_hwpx(args.disclosure_output)

        write_json(
            args.audit,
            {
                "source_sha256": sha256_file(source),
                "approval_output": {"path": str(args.approval_output), "sha256": approval_validation["sha256"]},
                "disclosure_output": {"path": str(args.disclosure_output), "sha256": disclosure_validation["sha256"]},
                "approval_changes": approval_audit,
                "disclosure_changes": disclosure_audit,
                "note": "원문과 직접식별정보는 이 변경이력에 저장하지 않습니다.",
            },
        )
        write_json(args.redaction_ledger, public_ledger(disclosure_redactions, disclosure_audit))
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {args.approval_output} | {args.disclosure_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
