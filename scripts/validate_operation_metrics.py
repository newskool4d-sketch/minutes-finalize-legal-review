#!/usr/bin/env python3
"""Validate privacy-safe, per-case operational metrics for pilot operation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REJECTION_CODES = {"근거부족", "사실불일치", "범위과다", "표현부적절", "기관기준확인", "법무확인", "기타비식별"}
INTEGER_FIELDS = {
    "pages", "review_minutes_before", "review_minutes_after", "officer_review_minutes", "supervisor_review_minutes",
    "ai_suggestions", "approved_suggestions", "rejected_suggestions", "high_risk_items", "legal_confirmation_items",
    "human_found_omissions", "metadata_or_vote_errors",
}


def validate(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("최상위 JSON은 객체여야 합니다.")
    token = payload.get("case_token")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("case_token이 필요합니다.")
    for field in INTEGER_FIELDS:
        value = payload.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{field}은 0 이상의 정수여야 합니다.")
    for field in ("hwpx_structure_pass", "hancom_open_pass"):
        if not isinstance(payload.get(field), bool):
            raise ValueError(f"{field}은 true/false여야 합니다.")
    codes = payload.get("rejection_reason_codes")
    if not isinstance(codes, list) or any(code not in REJECTION_CODES for code in codes):
        raise ValueError("rejection_reason_codes에는 허용된 비식별 코드만 사용합니다.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="비식별 운영지표 JSON")
    args = parser.parse_args()
    try:
        validate(json.loads(args.input.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("OK: operation metrics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
