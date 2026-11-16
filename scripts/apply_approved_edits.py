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

from approval_contract import (
    DISCLOSURE_REDACTION_SCOPES,
    REAL_SCOPES,
    approval_metadata,
    validate_approval_spec,
)
from hwpx_common import (
    read_hwpx_snapshot,
    require_preservable_metadata,
    read_json,
    replace_text_nodes,
    replace_paragraph_text,
    section_names,
    strip_stale_linesegarrays,
    validate_basic_hwpx,
    validate_snapshot,
    write_json,
    write_preserving_zip,
)
from hwpx_locations import parse_section, validate_location_id
from disclosure_package import inspect_disclosure_package, neutralize_disclosure_previews

def selected(records: list[dict[str, Any]], scopes: set[str]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record.get("approved") is True and record.get("scope") in scopes
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
        before_record = dict(updated)
        source, replacement = require_replacement(record)
        total = 0
        per_file: dict[str, int] = {}
        if "location" in record:
            location = record["location"]
            try:
                section_index = validate_location_id(location)
                filename = section_files[section_index]
            except (IndexError, ValueError) as exc:
                raise ValueError(f"{record.get('id', 'unknown')} 승인 치환 위치 형식이 올바르지 않습니다: {location}") from exc
            if record.get("match_scope") not in (None, "paragraph"):
                raise ValueError("location과 문서 전체 match_scope를 함께 지정할 수 없습니다.")
            if record.get("redaction_type") == "문장 비공개":
                changed_xml, total = replace_paragraph_text(
                    updated[filename], location, source, replacement, section_index=section_index
                )
            else:
                changed_xml, total = replace_text_nodes(
                    updated[filename], source, replacement, location_id=location, section_index=section_index
                )
            if total:
                updated[filename] = changed_xml
                per_file[filename] = total
        else:
            if record.get("match_scope") != "document" or record.get("redaction_type") == "문장 비공개":
                raise ValueError("승인 치환에는 location 또는 명시적인 match_scope=document가 필요합니다.")
            for section_index, filename in enumerate(section_files):
                changed_xml, count = replace_text_nodes(updated[filename], source, replacement, section_index=section_index)
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
                "changed_locations": [
                    after.location_id
                    for section_index, filename in enumerate(section_files) if filename in per_file
                    for before, after in zip(parse_section(section_index, before_record[filename]),
                                             parse_section(section_index, updated[filename]))
                    if before.own_text != after.own_text
                ],
                "reason": record.get("reason", ""),
                **approval_metadata(record),
            }
        )
    return updated, audit


def strip_layout_caches(entries: dict[str, bytes], section_files: list[str]) -> tuple[dict[str, bytes], int]:
    updated = dict(entries)
    stripped = 0
    for filename in section_files:
        updated[filename], count = strip_stale_linesegarrays(updated[filename])
        stripped += count
    return updated, stripped


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
            **approval_metadata(record),
        }
        for record in redactions
    ]


def build_entry_pair(entries: dict[str, bytes], specification: dict[str, Any]) -> dict[str, Any]:
    """Calculate both outputs from the same source entries for apply and verification."""
    validate_approval_spec(specification)
    sections = section_names(entries.keys())
    approval_records = selected(specification.get("edits", []), REAL_SCOPES)
    disclosure_redactions = sorted(
        selected(specification.get("redactions", []), DISCLOSURE_REDACTION_SCOPES),
        key=lambda record: 0 if record.get("redaction_type") == "문장 비공개" else 1,
    )
    for record in disclosure_redactions:
        validate_disclosure_redaction(record)
    approval_entries, approval_audit = apply_records(entries, sections, approval_records, "결재용")
    disclosure_entries, disclosure_audit = apply_records(
        entries, sections, approval_records + disclosure_redactions, "정보공개 청구용"
    )
    approval_entries, approval_layout_caches = strip_layout_caches(approval_entries, sections)
    disclosure_entries, disclosure_layout_caches = strip_layout_caches(disclosure_entries, sections)
    disclosure_entries, preview_changes = neutralize_disclosure_previews(disclosure_entries)
    disclosure_checks = inspect_disclosure_package(disclosure_entries, [item["from"] for item in disclosure_redactions])
    disclosure_checks["preview_changes"] = preview_changes
    return {
        "approval_entries": approval_entries,
        "disclosure_entries": disclosure_entries,
        "approval_changes": approval_audit,
        "disclosure_changes": disclosure_audit,
        "redactions": disclosure_redactions,
        "disclosure_package": disclosure_checks,
        "layout_cache": {
            "approval_stripped_linesegarrays": approval_layout_caches,
            "disclosure_stripped_linesegarrays": disclosure_layout_caches,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="1차 수정 HWPX 또는 승인 전 정본 HWPX")
    parser.add_argument("--approved", required=True, type=Path, help="승인된 수정·비실명 처리 JSON")
    parser.add_argument("--approval-output", required=True, type=Path, help="결재용 실명 정본 HWPX")
    parser.add_argument("--disclosure-output", required=True, type=Path, help="정보공개 청구용 비실명 HWPX")
    parser.add_argument("--audit", required=True, type=Path, help="변경이력 JSON")
    parser.add_argument("--redaction-ledger", required=True, type=Path, help="비실명처리 대장 JSON")
    args = parser.parse_args()

    outputs = [args.approval_output.resolve(), args.disclosure_output.resolve(),
               args.audit.resolve(), args.redaction_ledger.resolve()]
    source = args.source.resolve()
    if {source, args.approved.resolve()}.intersection(outputs):
        print("FAIL: 원본 또는 승인 목록을 출력 파일로 지정할 수 없습니다.", file=sys.stderr)
        return 1
    if len(set(outputs)) != 4:
        print("FAIL: HWPX·변경이력·대장 4개 출력 경로는 모두 달라야 합니다.", file=sys.stderr)
        return 1
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        print(f"FAIL: 기존 산출물을 덮어쓸 수 없습니다: {', '.join(existing)}", file=sys.stderr)
        return 1

    try:
        snapshot = read_hwpx_snapshot(source)
        validate_snapshot(snapshot, source)
        require_preservable_metadata(snapshot)
        specification = read_json(args.approved)
        validate_approval_spec(specification, snapshot.sha256)
        infos, entries = snapshot.infos, snapshot.entries
        pair = build_entry_pair(entries, specification)
        write_preserving_zip(args.approval_output, infos, pair["approval_entries"], archive_comment=snapshot.archive_comment)
        write_preserving_zip(args.disclosure_output, infos, pair["disclosure_entries"], disclosure=True)
        approval_validation = validate_basic_hwpx(args.approval_output)
        disclosure_snapshot = read_hwpx_snapshot(args.disclosure_output)
        disclosure_validation = validate_snapshot(disclosure_snapshot, args.disclosure_output)
        disclosure_checks = inspect_disclosure_package(
            disclosure_snapshot.entries, [item["from"] for item in pair["redactions"]], snapshot=disclosure_snapshot)
        disclosure_checks["preview_changes"] = pair["disclosure_package"]["preview_changes"]
        pair["disclosure_package"] = disclosure_checks

        write_json(
            args.audit,
            {
                "schema_version": 2,
                "source_sha256": snapshot.sha256,
                "approval_output": {"path": str(args.approval_output), "sha256": approval_validation["sha256"]},
                "disclosure_output": {"path": str(args.disclosure_output), "sha256": disclosure_validation["sha256"]},
                "approval_changes": pair["approval_changes"],
                "disclosure_changes": pair["disclosure_changes"],
                "layout_cache": pair["layout_cache"],
                "disclosure_package": pair["disclosure_package"],
                "note": "원문과 직접식별정보는 이 변경이력에 저장하지 않습니다.",
            },
        )
        write_json(args.redaction_ledger, public_ledger(pair["redactions"], pair["disclosure_changes"]))
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {args.approval_output} | {args.disclosure_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
