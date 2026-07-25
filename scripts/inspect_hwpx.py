#!/usr/bin/env python3
"""Inspect an HWPX package without exposing its text content."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hwpx_common import validate_basic_hwpx, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="검사할 HWPX 파일")
    parser.add_argument("--json", type=Path, help="검사 결과 JSON 경로")
    args = parser.parse_args()

    try:
        result = validate_basic_hwpx(args.input)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if args.json:
        write_json(args.json, result)
    print(f"OK: {args.input} | sections={len(result['sections'])} | entries={result['entry_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
