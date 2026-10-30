#!/usr/bin/env python3
"""Find configured sensitive terms in HWPX text without writing matched values to the report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from hwpx_common import read_json, read_entry_map, validate_basic_hwpx, write_json
from hwpx_locations import LOCATION_SCHEME
from disclosure_package import inspect_disclosure_package


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

        _, entries = read_entry_map(args.input)
        report = inspect_disclosure_package(entries, terms)
        findings = report["findings"]
        write_json(args.output, {"location_scheme": LOCATION_SCHEME, "input": str(args.input), **report})
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {args.output} | findings={len(findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
