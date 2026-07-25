#!/usr/bin/env python3
"""Aggregate three or more privacy-safe pilot metric records without case text."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from hwpx_common import write_json
from validate_operation_metrics import INTEGER_FIELDS, validate


def read_metrics(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate(payload)
    return payload


def rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator else None


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    tokens = [record["case_token"] for record in records]
    if len(set(tokens)) != len(tokens):
        raise ValueError("중복 case_token은 시범 운영 집계에 포함할 수 없습니다.")
    totals = {field: sum(record[field] for record in records) for field in INTEGER_FIELDS}
    before, after = totals["review_minutes_before"], totals["review_minutes_after"]
    return {
        "case_count": len(records),
        "pilot_status": "3~5건 시범 완료" if 3 <= len(records) <= 5 else "확장 운영",
        "totals": totals,
        "rates": {
            "review_time_reduction_percent": rate(before - after, before),
            "suggestion_approval_percent": rate(totals["approved_suggestions"], totals["ai_suggestions"]),
            "suggestion_rejection_percent": rate(totals["rejected_suggestions"], totals["ai_suggestions"]),
        },
        "quality_gates": {
            "hancom_open_failures": sum(not record["hancom_open_pass"] for record in records),
            "hwpx_structure_failures": sum(not record["hwpx_structure_pass"] for record in records),
            "human_found_omissions": totals["human_found_omissions"],
            "metadata_or_vote_errors": totals["metadata_or_vote_errors"],
        },
        "rejection_reason_code_counts": {
            code: sum(code in record["rejection_reason_codes"] for record in records)
            for code in sorted({code for record in records for code in record["rejection_reason_codes"]})
        },
        "note": "case_token, 회의록 원문, 실명, 발언 내용은 집계 결과에 포함하지 않았습니다.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="건별 비식별 운영지표 JSON 3개 이상")
    parser.add_argument("--output", required=True, type=Path, help="새 집계 JSON 경로")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.output}")
        if len(args.inputs) < 3:
            raise ValueError("시범 운영 집계에는 최소 3건의 운영지표가 필요합니다.")
        result = summarize([read_metrics(path) for path in args.inputs])
        write_json(args.output, result)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: pilot_cases={result['case_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
