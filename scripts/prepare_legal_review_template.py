#!/usr/bin/env python3
"""Turn text-free candidate locations into a human-completion legal-review template."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from hwpx_common import read_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path, help="detect_legal_review_candidates.py의 JSON")
    parser.add_argument("--output", required=True, type=Path, help="사람 검토용 JSON 템플릿")
    parser.add_argument("--case-token", required=True, help="실명·사건번호 없는 내부 식별자")
    parser.add_argument("--reviewed-at", default=dt.date.today().isoformat(), help="YYYY-MM-DD")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.output}")
        source = read_json(args.candidates)
        candidates = source.get("candidates")
        document_hash = source.get("source_document_hash")
        if not isinstance(candidates, list) or not isinstance(document_hash, str):
            raise ValueError("후보 목록 형식이 올바르지 않습니다.")
        issues: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                raise ValueError("후보 항목은 객체여야 합니다.")
            issues.append(
                {
                    "issue_id": f"issue-{index:03d}",
                    "location": candidate["location_id"],
                    "location_id": candidate["location_id"],
                    "statement_text_hash": candidate["statement_text_hash"],
                    "candidate_rule": candidate["rule_id"],
                    "legal_issue_type": candidate["legal_issue_type"],
                    "risk_level": candidate["risk_level"],
                    "action_code": candidate["action_code"],
                    "speaker_role": "[실무자 확인 필요]",
                    "statement_summary": "[실명 없는 발언 요지 작성]",
                    "source_level": "[E1~E5 확인]",
                    "legal_factor": [],
                    "risk_type": [],
                    "suggested_wording": "[유지·중립화·법무 확인 등 제안]",
                    "evidence_to_check": [],
                    "counterevidence": [],
                    "reasoning_summary": "[사실관계와 법적 쟁점 연결]",
                    "legal_basis": [],
                    "recommended_scope": "[결재용|정보공개청구용|양쪽]",
                    "confidence": "부족",
                    "approval_status": "미검토",
                    "human_decision": "[실무자 판단 필요]",
                }
            )
        write_json(
            args.output,
            {
                "case": {
                    "case_token": args.case_token,
                    "reviewed_at": args.reviewed_at,
                    "reviewer_role": "[실무자 지정 필요]",
                    "source_document_hash": document_hash,
                },
                "issues": issues,
                "note": "후보 위치·해시만 옮긴 미완성 템플릿입니다. 원문·실명은 포함하지 않으며, 작성 후 render_legal_review_report.py로 검증합니다.",
            },
        )
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: template_issues={len(issues)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
