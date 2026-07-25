#!/usr/bin/env python3
"""Find local-only legal-review candidate locations without exporting minutes text.

The output deliberately contains no paragraph text or matched word.  A human must
write the de-identified summary, check evidence, and decide whether to use it in
the legal-review report.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from hwpx_common import local_name, section_names, validate_basic_hwpx, write_json


RULES = (
    ("sensitive-health", re.compile(r"진단|복약|ADHD|장애|정신질환|병원|치료"), ["개인정보", "사실인정"], "높음", "L"),
    ("bias-or-reputation", re.compile(r"외모|체격|몸무게|눈빛|문제아|평소|과거|평판|친구관계"), ["편견·예단", "재량판단"], "중간", "V"),
    ("procedure-opportunity", re.compile(r"의견.?진술|불참|서면|제척|기피|회피|정족수|표결"), ["절차", "기록무결성"], "중간", "V"),
    ("assessment-reason", re.compile(r"심각성|지속성|고의성|점수"), ["재량판단"], "중간", "V"),
    ("unsupported-assertion", re.compile(r"추정|소문|들었다|보인다|같다"), ["사실인정"], "중간", "V"),
)


def text_of(node: ET.Element) -> str:
    return "".join(part for part in node.itertext() if part).strip()


def paragraphs(section_index: int, xml_bytes: bytes) -> list[tuple[str, str]]:
    root = ET.fromstring(xml_bytes)
    records: list[tuple[str, str]] = []
    paragraph = 0
    for node in root.iter():
        if local_name(node.tag) == "p":
            paragraph += 1
            records.append((f"section-{section_index}/paragraph-{paragraph}", text_of(node)))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="로컬에서 검사할 HWPX")
    parser.add_argument("--output", required=True, type=Path, help="텍스트 없는 후보 목록 JSON")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.output}")
        metadata = validate_basic_hwpx(args.input)
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        with zipfile.ZipFile(args.input, "r") as archive:
            for index, name in enumerate(section_names(archive.namelist())):
                for location_id, text in paragraphs(index, archive.read(name)):
                    for rule_id, pattern, issue_types, risk_level, action_code in RULES:
                        if pattern.search(text) and (location_id, rule_id) not in seen:
                            seen.add((location_id, rule_id))
                            candidates.append({
                                "candidate_id": f"candidate-{len(candidates) + 1:03d}",
                                "location_id": location_id,
                                "statement_text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                                "rule_id": rule_id,
                                "legal_issue_type": issue_types,
                                "risk_level": risk_level,
                                "action_code": action_code,
                                "requires_human_summary": True,
                            })
        write_json(args.output, {"source_document_hash": metadata["sha256"], "candidates": candidates})
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
