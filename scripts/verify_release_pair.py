#!/usr/bin/env python3
"""Verify both HWPX copies against their source-bound, explicitly approved plan."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from approval_contract import validate_approval_spec
from apply_approved_edits import build_entry_pair
from disclosure_package import inspect_disclosure_package
from hwpx_common import compare_package_metadata, read_hwpx_snapshot, read_json, validate_snapshot, write_json


def compare_entries(expected: dict[str, bytes], actual: dict[str, bytes], label: str) -> None:
    if set(expected) != set(actual):
        raise ValueError(f"{label}의 ZIP 엔트리 목록이 원본 기반 승인 결과와 다릅니다.")
    if any(expected[name] != actual[name] for name in expected):
        raise ValueError(f"{label}에 원본과 승인 목록으로 설명되지 않는 엔트리 바이트 차이가 있습니다.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="승인 목록의 해시와 대조할 실제 원본 HWPX")
    parser.add_argument("--approval", required=True, type=Path, help="결재용 실명 정본 HWPX")
    parser.add_argument("--disclosure", required=True, type=Path, help="정보공개 청구용 비실명 HWPX")
    parser.add_argument("--approved", required=True, type=Path, help="승인 목록 JSON")
    parser.add_argument("--json", type=Path, help="검증 결과 JSON")
    args = parser.parse_args()

    try:
        source = read_hwpx_snapshot(args.source)
        approval = read_hwpx_snapshot(args.approval)
        disclosure = read_hwpx_snapshot(args.disclosure)
        for snapshot in (source, approval, disclosure):
            validate_snapshot(snapshot)
        specification = read_json(args.approved)
        validate_approval_spec(specification, source.sha256)
        source_entries = source.entries
        pair = build_entry_pair(source_entries, specification)
        approval_entries, disclosure_entries = approval.entries, disclosure.entries
        compare_entries(pair["approval_entries"], approval_entries, "결재용")
        compare_entries(pair["disclosure_entries"], disclosure_entries, "정보공개 청구용")
        compare_package_metadata(source, approval, disclosure=False)
        compare_package_metadata(source, disclosure, disclosure=True)
        disclosure_checks = inspect_disclosure_package(
            disclosure.entries, [item["from"] for item in pair["redactions"]], snapshot=disclosure)
        disclosure_checks["preview_changes"] = pair["disclosure_package"]["preview_changes"]
        pair["disclosure_package"] = disclosure_checks
        redaction_ids = {record["id"] for record in pair["redactions"]}
        counts = [row for row in pair["disclosure_changes"] if row["id"] in redaction_ids]
        result = {"status": "ok", "technical_pair_valid": True, "schema_version": 2, "source_sha256": specification["source_sha256"],
                  "disclosure_package": pair["disclosure_package"],
                  "approval_changes": pair["approval_changes"], "redactions": counts, "entry_count": len(source_entries)}
        if args.json:
            if args.json.exists():
                raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.json}")
            write_json(args.json, result)
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"OK: redactions={len(counts)} | entries={len(source_entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
