#!/usr/bin/env python3
"""Prepare locally stored, role-context name redaction records for HWPX review.

The output contains detected names and is case data. Do not commit it or print it to logs.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from hwpx_common import section_names, sha256_file, validate_basic_hwpx, write_json
from hwpx_locations import LOCATION_SCHEME, parse_section

ROSTER_PATTERNS = (
    re.compile(r"위원\s*\d+(?:\([^)]*\))?\s+([가-힣](?:\s*[가-힣]){1,3})(?=\s|\(|$)"),
    re.compile(r"(?:교\s*사|학\s*생|보\s*호\s*자)\s+([가-힣](?:\s*[가-힣]){1,3})(?=\s|\(|$)"),
    re.compile(r"(?:장학사|주무관)\s+([가-힣](?:\s*[가-힣]){1,3})(?=\s|\(|$)"),
)


def text_from_xml(xml_bytes: bytes) -> str:
    return "\n".join(item.own_text for item in parse_section(0, xml_bytes))


def variants(text: str, normalized: str) -> set[str]:
    letters = [re.escape(letter) for letter in normalized]
    pattern = re.compile(r"\s*".join(letters))
    return {match.group(0) for match in pattern.finditer(text)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="검사할 HWPX 파일")
    parser.add_argument("--output", required=True, type=Path, help="로컬 승인 목록 JSON 경로")
    parser.add_argument("--approve-detected", action="store_true", help="호환 옵션: 탐지 후보는 여전히 추가 승인 필요 상태로만 기록")
    args = parser.parse_args()

    try:
        validate_basic_hwpx(args.input)
        if args.output.exists():
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.output}")
        chunks: list[str] = []
        with zipfile.ZipFile(args.input, "r") as archive:
            for name in section_names(archive.namelist()):
                chunks.append(text_from_xml(archive.read(name)))
        text = "\n".join(chunks)
        roster_end = text.find("6. 회")
        if roster_end < 0:
            roster_end = text.find("7. 상정 안건")
        roster = text if roster_end < 0 else text[:roster_end]
        detected: set[str] = set()
        for pattern in ROSTER_PATTERNS:
            for match in pattern.finditer(roster):
                normalized = re.sub(r"\s+", "", match.group(1))
                if 2 <= len(normalized) <= 4:
                    detected.update(variants(text, normalized))
        redactions = [
            {
                "id": f"redact-name-{index:03d}",
                "approved": False,
                "approval_status": "추가 승인 필요" if args.approve_detected else "미검토",
                "scope": "disclosure",
                "from": value,
                "to": "○○",
                "match_scope": "document",
                "redaction_type": "성명",
                "reason": "정보공개 청구용 비실명 처리",
                "min_matches": 1,
            }
            for index, value in enumerate(sorted(detected), start=1)
        ]
        write_json(args.output, {"schema_version": 2, "location_scheme": LOCATION_SCHEME, "source_sha256": sha256_file(args.input),
                                 "edits": [], "redactions": redactions})
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"OK: candidates={len(redactions)} | approved=False | human_approval_required=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
