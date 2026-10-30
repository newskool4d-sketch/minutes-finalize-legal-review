#!/usr/bin/env python3
"""Extract HWPX paragraph/table locations and text into a review model."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from hwpx_common import section_names, validate_basic_hwpx, write_json
from hwpx_locations import LOCATION_SCHEME, parse_section


def extract_section(section_index: int, xml_bytes: bytes) -> list[dict[str, Any]]:
    return [
        {"location_id": item.location_id, "paragraph_index": item.paragraph_index, "text": item.own_text.strip()}
        for item in parse_section(section_index, xml_bytes)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="읽을 HWPX 파일")
    parser.add_argument("--output", required=True, type=Path, help="검토 모델 JSON 경로")
    args = parser.parse_args()

    try:
        metadata = validate_basic_hwpx(args.input)
        records: list[dict[str, Any]] = []
        with zipfile.ZipFile(args.input, "r") as archive:
            for index, name in enumerate(section_names(archive.namelist())):
                records.extend(extract_section(index, archive.read(name)))
        write_json(
            args.output,
            {
                "location_scheme": LOCATION_SCHEME,
                "source": {"path": str(args.input), "sha256": metadata["sha256"]},
                "paragraphs": records,
                "note": "원문 텍스트가 포함됩니다. 이 파일은 사건자료와 같은 접근통제로 관리하고 저장소에 커밋하지 마십시오.",
            },
        )
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {args.output} | paragraphs={len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
