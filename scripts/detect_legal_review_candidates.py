#!/usr/bin/env python3
"""Find local-only legal-review candidate locations without exporting minutes text.

The output deliberately contains no paragraph text or matched word.  A human must
write the de-identified summary, check evidence, and decide whether to use it in
the legal-review report.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from hwpx_common import read_hwpx_snapshot, section_names, statement_text_hash, validate_snapshot, write_json
from hwpx_locations import LOCATION_SCHEME, parse_section


RULES = (
    ("sensitive-health", re.compile(r"진단|복약|ADHD|장애|정신질환|병원|치료"), ["개인정보", "사실인정"], "높음", "L"),
    ("bias-or-reputation", re.compile(r"외모|체격|몸무게|눈빛|문제아|평소|과거|평판|친구관계"), ["편견·예단", "재량판단"], "중간", "V"),
    ("procedure-opportunity", re.compile(r"의견.?진술|불참|서면|제척|기피|회피|정족수|표결"), ["절차", "기록무결성"], "중간", "V"),
    ("assessment-reason", re.compile(r"심각성|지속성|고의성|점수"), ["재량판단"], "중간", "V"),
    ("unsupported-assertion", re.compile(r"추정|소문|들었다|보인다|같다"), ["사실인정"], "중간", "V"),
)


def paragraphs(section_index: int, xml_bytes: bytes) -> list[tuple[str, str]]:
    # The statement hash binds exact own_text, including leading/trailing space.
    # Never normalize the evidence differently from the final summary verifier.
    return [(item.location_id, item.own_text) for item in parse_section(section_index, xml_bytes)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="로컬에서 검사할 HWPX")
    parser.add_argument("--output", required=True, type=Path, help="텍스트 없는 후보 목록 JSON")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.output}")
        snapshot = read_hwpx_snapshot(args.input)
        metadata = validate_snapshot(snapshot)
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for index, name in enumerate(section_names(snapshot.entries)):
            for location_id, text in paragraphs(index, snapshot.entries[name]):
                for rule_id, pattern, issue_types, risk_level, action_code in RULES:
                    if pattern.search(text) and (location_id, rule_id) not in seen:
                        seen.add((location_id, rule_id))
                        candidates.append({
                            "candidate_id": f"candidate-{len(candidates) + 1:03d}",
                            "location_id": location_id,
                            "statement_text_hash": statement_text_hash(text),
                            "rule_id": rule_id,
                            "legal_issue_type": issue_types,
                            "risk_level": risk_level,
                            "action_code": action_code,
                            "requires_human_summary": True,
                        })
        write_json(args.output, {"location_scheme": LOCATION_SCHEME, "source_document_hash": metadata["sha256"], "candidates": candidates})
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
