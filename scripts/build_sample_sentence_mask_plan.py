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

from hwpx_common import local_name, read_json, section_names, validate_basic_hwpx, write_json


DECISIONS = {"담당자 승인", "정보공개 담당 확인", "법무 확인"}


def paragraph_lookup(input_path: Path) -> dict[str, str]:
    validate_basic_hwpx(input_path)
    lookup: dict[str, str] = {}
    with zipfile.ZipFile(input_path, "r") as archive:
        for section_index, filename in enumerate(section_names(archive.namelist())):
            root = ET.fromstring(archive.read(filename))
            paragraph_number = 0
            for node in root.iter():
                if local_name(node.tag) != "p":
                    continue
                paragraph_number += 1
                lookup[f"section-{section_index}/paragraph-{paragraph_number}"] = "".join(node.itertext()).strip()
    return lookup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="로컬 원본 HWPX")
    parser.add_argument("--base", required=True, type=Path, help="기존 승인 비실명 처리 JSON")
    parser.add_argument("--output", required=True, type=Path, help="새 로컬 전용 샘플 계획 JSON")
    parser.add_argument("--location", required=True, action="append", help="문장 단위로 가릴 paragraph 위치; 반복 지정 가능")
    parser.add_argument("--reason", required=True, help="정보공개용 문장 비공개 사유")
    parser.add_argument("--decision", required=True, choices=sorted(DECISIONS), help="샘플 작성 승인 상태")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.output}")
        base = read_json(args.base)
        lookup = paragraph_lookup(args.input)
        redactions = base.get("redactions", [])
        edits = base.get("edits", [])
        if not isinstance(redactions, list) or not isinstance(edits, list):
            raise ValueError("기존 계획의 edits/redactions 형식이 올바르지 않습니다.")
        requested = list(dict.fromkeys(args.location))
        existing_ids = {str(item.get("id")) for item in redactions if isinstance(item, dict)}
        additions: list[dict[str, Any]] = []
        for number, location in enumerate(requested, start=1):
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
                "min_matches": 1,
                "max_matches": 1,
                "sample_only": True,
            })
        write_json(args.output, {
            "edits": edits,
            "redactions": redactions + additions,
            "sample_only": True,
            "sample_note": "사용자 승인에 따른 샘플 산출 전용 계획입니다. 실제 공개·결재 전에는 정보공개 담당자와 법무 검토를 다시 받아야 합니다.",
        })
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: sample_sentence_masks={len(additions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
