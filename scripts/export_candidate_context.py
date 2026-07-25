#!/usr/bin/env python3
"""Export local-only, best-effort masked context for human review of candidate locations.

Do not commit the output: it can still contain sensitive context despite masking.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from hwpx_common import local_name, read_json, section_names, validate_basic_hwpx, write_json


PHONE = re.compile(r"(?<!\d)01[0-9][- ]?\d{3,4}[- ]?\d{4}(?!\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LONG_NUMBER = re.compile(r"(?<!\d)\d{4,}(?!\d)")
NAME_WITH_PARTICLE = re.compile(r"(?<![가-힣])([가-힣]{2,4})(?=(?:은|는|이|가|을|를|의|에게|께서|씨|님)\b)")
ROSTER_PATTERNS = (
    re.compile(r"위원\s*\d+(?:\([^)]*\))?\s+([가-힣](?:\s*[가-힣]){1,3})(?=\s|\(|$)"),
    re.compile(r"(?:교\s*사|학\s*생|보\s*호\s*자|장학사|주무관)\s+([가-힣](?:\s*[가-힣]){1,3})(?=\s|\(|$)"),
)


def roster_names(all_text: str) -> set[str]:
    end = all_text.find("6. 회")
    if end < 0:
        end = all_text.find("7. 상정 안건")
    roster = all_text if end < 0 else all_text[:end]
    return {
        re.sub(r"\s+", "", match.group(1))
        for pattern in ROSTER_PATTERNS
        for match in pattern.finditer(roster)
    }


def mask(text: str, names: set[str]) -> str:
    for name in sorted(names, key=len, reverse=True):
        text = re.sub(r"\s*".join(map(re.escape, name)), "[성명]", text)
    text = EMAIL.sub("[이메일]", text)
    text = PHONE.sub("[연락처]", text)
    text = LONG_NUMBER.sub("[번호]", text)
    return NAME_WITH_PARTICLE.sub("[개인]", text)


def paragraphs(xml_bytes: bytes, section_index: int) -> dict[str, str]:
    root = ET.fromstring(xml_bytes)
    result: dict[str, str] = {}
    number = 0
    for node in root.iter():
        if local_name(node.tag) == "p":
            number += 1
            result[f"section-{section_index}/paragraph-{number}"] = "".join(node.itertext()).strip()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="로컬 HWPX")
    parser.add_argument("--candidates", required=True, type=Path, help="원문 없는 후보 JSON")
    parser.add_argument("--output", required=True, type=Path, help="로컬 마스킹 문맥 JSON")
    parser.add_argument("--max-chars", type=int, default=600, help="문맥당 최대 글자 수")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.output}")
        validate_basic_hwpx(args.input)
        candidate_data = read_json(args.candidates)
        candidates = candidate_data.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("후보 목록 형식이 올바르지 않습니다.")
        grouped: dict[str, list[str]] = defaultdict(list)
        for candidate in candidates:
            grouped[candidate["location_id"]].append(candidate["rule_id"])
        lookup: dict[str, str] = {}
        with zipfile.ZipFile(args.input, "r") as archive:
            for index, name in enumerate(section_names(archive.namelist())):
                lookup.update(paragraphs(archive.read(name), index))
        names = roster_names("\n".join(lookup.values()))
        contexts = []
        for location_id, rules in grouped.items():
            text = lookup.get(location_id)
            if text is None:
                raise ValueError(f"후보 위치를 찾을 수 없습니다: {location_id}")
            contexts.append({"location_id": location_id, "candidate_rules": sorted(set(rules)), "masked_context": mask(text, names)[: args.max_chars]})
        write_json(args.output, {"contexts": contexts, "note": "로컬 검토용 마스킹 문맥입니다. 재식별 가능성이 남을 수 있어 외부 전송·커밋 금지."})
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: contexts={len(contexts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
