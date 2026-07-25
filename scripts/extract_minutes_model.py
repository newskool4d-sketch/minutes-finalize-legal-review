#!/usr/bin/env python3
"""Extract HWPX paragraph/table locations and text into a review model."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from hwpx_common import local_name, section_names, validate_basic_hwpx, write_json


def text_of(node: ET.Element) -> str:
    return "".join(part for part in node.itertext() if part).strip()


def extract_section(section_index: int, xml_bytes: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    records: list[dict[str, Any]] = []
    counters = {"paragraph": 0, "table": 0, "row": 0, "cell": 0}

    def walk(node: ET.Element, context: list[str], cell_paragraph: int | None = None) -> None:
        name = local_name(node.tag)
        if name == "tbl":
            counters["table"] += 1
            table_context = context + [f"table-{counters['table']}"]
            for child in node:
                walk(child, table_context)
            return
        if name == "tr":
            counters["row"] += 1
            row_context = context + [f"row-{counters['row']}"]
            for child in node:
                walk(child, row_context)
            return
        if name == "tc":
            counters["cell"] += 1
            cell_context = context + [f"cell-{counters['cell']}"]
            local_paragraph = 0
            for child in node:
                if local_name(child.tag) == "p":
                    local_paragraph += 1
                    walk(child, cell_context, local_paragraph)
                else:
                    walk(child, cell_context)
            return
        if name == "p":
            counters["paragraph"] += 1
            location = [f"section-{section_index}"] + context
            if cell_paragraph is None:
                location.append(f"paragraph-{counters['paragraph']}")
            else:
                location.append(f"paragraph-{cell_paragraph}")
            records.append(
                {
                    "location_id": "/".join(location),
                    "paragraph_index": counters["paragraph"],
                    "text": text_of(node),
                }
            )
            return
        for child in node:
            walk(child, context, cell_paragraph)

    walk(root, [])
    return records


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
