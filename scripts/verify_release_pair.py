#!/usr/bin/env python3
"""Verify that a disclosure HWPX differs from the approval HWPX only by approved redactions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from hwpx_common import read_entry_map, read_json, replace_text_nodes, section_names, validate_basic_hwpx, write_json

DISCLOSURE_REDACTION_SCOPES = {"disclosure", "정보공개청구용"}


def approved_redactions(specification: dict[str, Any]) -> list[dict[str, Any]]:
    records = specification.get("redactions", [])
    if not isinstance(records, list):
        raise ValueError("redactions는 배열이어야 합니다.")
    selected = []
    for record in records:
        if record.get("approved") is not True:
            continue
        if str(record.get("scope", "disclosure")) not in DISCLOSURE_REDACTION_SCOPES:
            raise ValueError(f"비실명 처리 범위가 올바르지 않습니다: {record.get('id', 'unknown')}")
        if not isinstance(record.get("from"), str) or not record["from"]:
            raise ValueError(f"from 값이 비어 있습니다: {record.get('id', 'unknown')}")
        if not isinstance(record.get("to"), str):
            raise ValueError(f"to 값이 문자열이 아닙니다: {record.get('id', 'unknown')}")
        if record.get("redaction_type") == "문장 비공개":
            if not isinstance(record.get("location"), str) or not record["location"].strip():
                raise ValueError(f"문장 비공개 위치가 없습니다: {record.get('id', 'unknown')}")
            if not isinstance(record.get("reason"), str) or not record["reason"].strip():
                raise ValueError(f"문장 비공개 사유가 없습니다: {record.get('id', 'unknown')}")
            if record.get("human_decision") not in {"담당자 승인", "정보공개 담당 확인", "법무 확인"}:
                raise ValueError(f"문장 비공개 실무자 판단이 없습니다: {record.get('id', 'unknown')}")
            if int(record.get("min_matches", 1)) != 1 or int(record.get("max_matches", 1)) != 1:
                raise ValueError(f"문장 비공개는 정확히 한 곳만 처리해야 합니다: {record.get('id', 'unknown')}")
        selected.append(record)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", required=True, type=Path, help="결재용 실명 정본 HWPX")
    parser.add_argument("--disclosure", required=True, type=Path, help="정보공개 청구용 비실명 HWPX")
    parser.add_argument("--approved", required=True, type=Path, help="승인 목록 JSON")
    parser.add_argument("--json", type=Path, help="검증 결과 JSON")
    args = parser.parse_args()

    try:
        validate_basic_hwpx(args.approval)
        validate_basic_hwpx(args.disclosure)
        specification = read_json(args.approved)
        redactions = approved_redactions(specification)
        _, approval_entries = read_entry_map(args.approval)
        _, disclosure_entries = read_entry_map(args.disclosure)
        if set(approval_entries) != set(disclosure_entries):
            raise ValueError("두 HWPX의 ZIP 엔트리 목록이 다릅니다.")

        expected = dict(approval_entries)
        counts: list[dict[str, Any]] = []
        for record in redactions:
            total = 0
            per_file: dict[str, int] = {}
            for filename in section_names(expected.keys()):
                changed_xml, count = replace_text_nodes(expected[filename], record["from"], record["to"])
                if count:
                    expected[filename] = changed_xml
                    per_file[filename] = count
                    total += count
            required = int(record.get("min_matches", 1))
            if total < required:
                raise ValueError(f"비실명 처리 대조 실패: {record.get('id', 'unknown')} 치환 횟수 {total}")
            maximum = record.get("max_matches")
            if maximum is not None and total > int(maximum):
                raise ValueError(f"비실명 처리 최대 횟수 초과: {record.get('id', 'unknown')} 치환 횟수 {total}")
            counts.append({"id": record.get("id", "unknown"), "changed_count": total, "files": per_file})

        changed_entries = [name for name in expected if expected[name] != disclosure_entries[name]]
        if changed_entries:
            raise ValueError(f"승인된 비실명 처리 외의 차이가 있습니다: {', '.join(changed_entries)}")
        result = {"status": "ok", "redactions": counts, "entry_count": len(expected)}
        if args.json:
            if args.json.exists():
                raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.json}")
            write_json(args.json, result)
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"OK: redactions={len(redactions)} | entries={len(expected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
