#!/usr/bin/env python3
"""Build a local-only disclosure sample plan from explicitly selected paragraphs.

The resulting JSON contains exact source text and must not be committed.  It
exists only to let an authorised sample use the same strict one-location mask
contract as a production disclosure workflow.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path
from typing import Any

from approval_contract import validate_approval_spec, validate_source_contract
from hwpx_common import read_json, section_names, validate_basic_hwpx, write_json
from hwpx_locations import LOCATION_SCHEME, parse_section, validate_location_id


DECISIONS = {"담당자 승인", "정보공개 담당 확인", "법무 확인"}


def paragraph_lookup(input_path: Path) -> dict[str, str]:
    validate_basic_hwpx(input_path)
    lookup: dict[str, str] = {}
    with zipfile.ZipFile(input_path, "r") as archive:
        for section_index, filename in enumerate(section_names(archive.namelist())):
            for item in parse_section(section_index, archive.read(filename)):
                lookup[item.location_id] = item.own_text.strip()
    return lookup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="로컬 원본 HWPX")
    parser.add_argument("--base", required=True, type=Path, help="기존 승인 비실명 처리 JSON")
    parser.add_argument("--output", required=True, type=Path, help="새 로컬 전용 샘플 계획 JSON")
    parser.add_argument("--location", required=True, action="append", help="문장 단위로 가릴 paragraph 위치; 반복 지정 가능")
    parser.add_argument("--reason", required=True, help="정보공개용 문장 비공개 사유")
    parser.add_argument("--decision", required=True, choices=sorted(DECISIONS), help="샘플 작성 승인 상태")
    parser.add_argument("--decided-by-role", required=True, help="명시적으로 승인한 검토자 역할")
    parser.add_argument("--decided-at", required=True, help="시간대가 포함된 실제 승인 시각(ISO 8601)")
    parser.add_argument("--evidence-ref", required=True, action="append", help="원문 없는 scheme:ref-id 근거 참조; 반복 지정 가능")
    parser.add_argument("--issue-id", required=True, help="문장 비공개 승인이 연결되는 검토 이슈 ID")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.output}")
        base = read_json(args.base)
        validate_source_contract(base, args.input)
        lookup = paragraph_lookup(args.input)
        redactions = base.get("redactions", [])
        edits = base.get("edits", [])
        if not isinstance(redactions, list) or not isinstance(edits, list):
            raise ValueError("기존 계획의 edits/redactions 형식이 올바르지 않습니다.")
        requested = list(dict.fromkeys(args.location))
        existing_ids = {str(item.get("id")) for item in edits + redactions}
        additions: list[dict[str, Any]] = []
        for number, location in enumerate(requested, start=1):
            validate_location_id(location)
            text = lookup.get(location)
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"문장 비공개 대상 위치를 찾지 못했습니다: {location}")
            item_id = f"sample-sentence-mask-{number:03d}"
            if item_id in existing_ids:
                raise ValueError(f"중복된 샘플 ID: {item_id}")
            additions.append({
                "id": item_id,
                "approved": True,
                "scope": "disclosure",
                "from": text,
                "to": "[비공개]",
                "location": location,
                "redaction_type": "문장 비공개",
                "reason": args.reason,
                "human_decision": args.decision,
                "issue_id": args.issue_id,
                "decided_by_role": args.decided_by_role,
                "decided_at": args.decided_at,
                "evidence_refs": args.evidence_ref,
                "min_matches": 1,
                "max_matches": 1,
                "sample_only": True,
            })
        plan = {
            "schema_version": 2,
            "location_scheme": LOCATION_SCHEME,
            "source_sha256": base["source_sha256"],
            "edits": edits,
            "redactions": redactions + additions,
            "sample_only": True,
            "sample_note": "사용자 승인에 따른 샘플 산출 전용 계획입니다. 실제 공개·결재 전에는 정보공개 담당자와 법무 검토를 다시 받아야 합니다.",
        }
        validate_approval_spec(plan)
        write_json(args.output, plan)
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: sample_sentence_masks={len(additions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
