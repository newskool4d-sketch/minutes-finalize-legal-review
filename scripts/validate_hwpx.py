#!/usr/bin/env python3
"""Validate an HWPX package and optionally compare its structure with a base file."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from typing import Any

from hwpx_common import count_structure, section_names, validate_basic_hwpx, write_json


def structure_by_section(path: Path) -> dict[str, dict[str, int]]:
    with zipfile.ZipFile(path, "r") as archive:
        names = section_names(archive.namelist())
        return {name: count_structure(archive.read(name)) for name in names}


def compare_structure(base: Path, candidate: Path) -> dict[str, Any]:
    base_sections = structure_by_section(base)
    candidate_sections = structure_by_section(candidate)
    mismatches: list[dict[str, Any]] = []
    for name in sorted(set(base_sections) | set(candidate_sections)):
        if base_sections.get(name) != candidate_sections.get(name):
            mismatches.append(
                {"section": name, "base": base_sections.get(name), "candidate": candidate_sections.get(name)}
            )
    return {"base": str(base), "candidate": str(candidate), "mismatches": mismatches}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="검증할 HWPX 파일")
    parser.add_argument("--compare-base", type=Path, help="구조를 비교할 원본 또는 결재용 HWPX")
    parser.add_argument("--json", type=Path, help="검증 결과 JSON 경로")
    args = parser.parse_args()

    try:
        result: dict[str, Any] = {"package": validate_basic_hwpx(args.input)}
        if args.compare_base:
            result["comparison"] = compare_structure(args.compare_base, args.input)
            if result["comparison"]["mismatches"]:
                raise ValueError("원본과 문단·표 구조가 다릅니다.")
        if args.json:
            write_json(args.json, result)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {args.input}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
