#!/usr/bin/env python3
"""Find configured sensitive terms in HWPX text without writing matched values to the report."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from hwpx_common import local_name, read_json, section_names, validate_basic_hwpx, write_json


def paragraph_text(node: ET.Element) -> str:
    return "".join(part for part in node.itertext() if part)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="검사할 HWPX 파일")
    parser.add_argument("--terms", required=True, type=Path, help="terms 배열 또는 {terms: [...]} JSON")
    parser.add_argument("--output", required=True, type=Path, help="탐지 결과 JSON")
    args = parser.parse_args()

    try:
        validate_basic_hwpx(args.input)
        configured = read_json(args.terms)
        terms = configured["terms"] if isinstance(configured, dict) else configured
        if not isinstance(terms, list) or not all(isinstance(term, str) and term for term in terms):
            raise ValueError("terms는 비어 있지 않은 문자열 배열이어야 합니다.")
        if args.output.exists():
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.output}")

        findings: list[dict[str, Any]] = []
        with zipfile.ZipFile(args.input, "r") as archive:
            for section_index, name in enumerate(section_names(archive.namelist())):
                root = ET.fromstring(archive.read(name))
                paragraph_index = 0
                for node in root.iter():
                    if local_name(node.tag) != "p":
                        continue
                    paragraph_index += 1
                    text = paragraph_text(node)
                    for term_index, term in enumerate(terms, start=1):
                        count = text.count(term)
                        if count:
                            findings.append(
                                {
                                    "location_id": f"section-{section_index}/paragraph-{paragraph_index}",
                                    "term_id": f"term-{term_index}",
                                    "match_count": count,
                                }
                            )
        write_json(args.output, {"input": str(args.input), "findings": findings})
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {args.output} | findings={len(findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
