"""Shared, standard-library-only helpers for safe HWPX inspection and copying."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from hwpx_locations import replace_in_paragraphs, validate_location_id

HWPX_MIMETYPE = b"application/hwp+zip"
LINESEG_ARRAY = re.compile(rb"<hp:linesegarray\b[^>]*(?:/>|>.*?</hp:linesegarray>)", re.DOTALL)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def section_names(names: Iterable[str]) -> list[str]:
    return sorted(
        (name for name in names if re.fullmatch(r"Contents/section\d+\.xml", name)),
        key=lambda name: int(re.search(r"\d+", name).group()),
    )


def xml_names(names: Iterable[str]) -> list[str]:
    return sorted(name for name in names if name.lower().endswith(".xml"))


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def validate_basic_hwpx(path: Path) -> dict[str, Any]:
    """Validate ZIP packaging and XML well-formedness without changing the file."""
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if not infos:
            raise ValueError("빈 ZIP 패키지입니다.")
        if infos[0].filename != "mimetype":
            raise ValueError("mimetype가 첫 ZIP 엔트리가 아닙니다.")
        if infos[0].compress_type != zipfile.ZIP_STORED:
            raise ValueError("mimetype는 ZIP_STORED 방식이어야 합니다.")
        if archive.read("mimetype") != HWPX_MIMETYPE:
            raise ValueError("HWPX mimetype가 올바르지 않습니다.")

        names = archive.namelist()
        sections = section_names(names)
        if not sections:
            raise ValueError("Contents/sectionN.xml이 없습니다.")

        parsed_xml: list[str] = []
        for name in xml_names(names):
            ET.fromstring(archive.read(name))
            parsed_xml.append(name)

    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "entry_count": len(infos),
        "sections": sections,
        "parsed_xml": parsed_xml,
    }


def read_entry_map(path: Path) -> tuple[list[zipfile.ZipInfo], dict[str, bytes]]:
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        return infos, {info.filename: archive.read(info.filename) for info in infos}


def write_preserving_zip(path: Path, infos: list[zipfile.ZipInfo], entries: dict[str, bytes]) -> None:
    if path.exists():
        raise FileExistsError(f"출력 파일이 이미 존재합니다: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for info in infos:
            copied = copy.copy(info)
            archive.writestr(copied, entries[info.filename])


def count_structure(xml_bytes: bytes) -> dict[str, int]:
    root = ET.fromstring(xml_bytes)
    counts = {"paragraphs": 0, "tables": 0, "rows": 0, "cells": 0, "text_nodes": 0}
    for node in root.iter():
        name = local_name(node.tag)
        if name == "p":
            counts["paragraphs"] += 1
        elif name == "tbl":
            counts["tables"] += 1
        elif name == "tr":
            counts["rows"] += 1
        elif name == "tc":
            counts["cells"] += 1
        elif name == "t":
            counts["text_nodes"] += 1
    return counts


def replace_text_nodes(
    xml_bytes: bytes, source: str, replacement: str, *,
    location_id: str | None = None, section_index: int = 0,
) -> tuple[bytes, int]:
    """Replace own paragraph text across runs, retaining all surrounding bytes."""
    return replace_in_paragraphs(xml_bytes, section_index, source, replacement, location_id=location_id)


def strip_stale_linesegarrays(xml_bytes: bytes) -> tuple[bytes, int]:
    """Remove cached line-layout arrays after changing text in an HWPX section.

    Hancom regenerates these caches when the file opens.  Keeping a cache that
    was calculated for different text can make an otherwise well-formed HWPX
    fail its real-application open gate.
    """
    return LINESEG_ARRAY.subn(b"", xml_bytes)


def replace_paragraph_text(
    xml_bytes: bytes, location_id: str, source: str, replacement: str, *, section_index: int = 0,
) -> tuple[bytes, int]:
    """Replace one canonical paragraph's own text, never any nested paragraph."""
    validate_location_id(location_id)
    return replace_in_paragraphs(
        xml_bytes, section_index, source, replacement, location_id=location_id, whole=True
    )
