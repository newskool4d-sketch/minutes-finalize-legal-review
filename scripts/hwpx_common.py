"""Shared, standard-library-only helpers for safe HWPX inspection and copying."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from hwpx_locations import replace_in_paragraphs, validate_location_id

HWPX_MIMETYPE = b"application/hwp+zip"
LINESEG_ARRAY = re.compile(rb"<hp:linesegarray\b[^>]*(?:/>|>.*?</hp:linesegarray>)", re.DOTALL)


def statement_text_hash(text: str) -> str:
    """Bind a statement to its exact own text, including boundary whitespace."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


@dataclass(frozen=True)
class HwpxSnapshot:
    """One captured byte sequence used for hashing, parsing and validation."""

    data: bytes
    infos: list[zipfile.ZipInfo]
    entries: dict[str, bytes]
    archive_comment: bytes
    local_extras: dict[str, bytes]
    sha256: str


def snapshot_hwpx(data: bytes) -> HwpxSnapshot:
    with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(set(names)) != len(names):
            raise ValueError("중복 ZIP 엔트리는 지원하지 않습니다.")
        entries = {info.filename: archive.read(info) for info in infos}
        local_extras = {}
        for info in infos:
            offset = info.header_offset
            header = data[offset:offset + 30]
            if len(header) != 30 or header[:4] != b"PK\x03\x04":
                raise ValueError("ZIP 로컬 헤더가 올바르지 않습니다.")
            name_size, extra_size = struct.unpack_from("<HH", header, 26)
            start = offset + 30 + name_size
            local_extras[info.filename] = data[start:start + extra_size]
        return HwpxSnapshot(data, infos, entries, archive.comment, local_extras, hashlib.sha256(data).hexdigest())


def read_hwpx_snapshot(path: Path) -> HwpxSnapshot:
    return snapshot_hwpx(path.read_bytes())


def validate_snapshot(snapshot: HwpxSnapshot, path: Path | None = None) -> dict[str, Any]:
    """Validate the captured bytes, never reopening the input path."""
    infos, entries = snapshot.infos, snapshot.entries
    if not infos:
        raise ValueError("빈 ZIP 패키지입니다.")
    if infos[0].filename != "mimetype":
        raise ValueError("mimetype가 첫 ZIP 엔트리가 아닙니다.")
    if infos[0].compress_type != zipfile.ZIP_STORED:
        raise ValueError("mimetype는 ZIP_STORED 방식이어야 합니다.")
    if entries["mimetype"] != HWPX_MIMETYPE:
        raise ValueError("HWPX mimetype가 올바르지 않습니다.")

    names = list(entries)
    sections = section_names(names)
    if not sections:
        raise ValueError("Contents/sectionN.xml이 없습니다.")

    parsed_xml: list[str] = []
    for name in xml_names(names):
        ET.fromstring(entries[name])
        parsed_xml.append(name)

    return {
        "path": str(path) if path is not None else None,
        "sha256": snapshot.sha256,
        "entry_count": len(infos),
        "sections": sections,
        "parsed_xml": parsed_xml,
    }


def validate_basic_hwpx(path: Path) -> dict[str, Any]:
    """Validate ZIP packaging and XML well-formedness from one read."""
    return validate_snapshot(read_hwpx_snapshot(path), path)


def read_entry_map(path: Path) -> tuple[list[zipfile.ZipInfo], dict[str, bytes]]:
    snapshot = read_hwpx_snapshot(path)
    return snapshot.infos, snapshot.entries


def require_preservable_metadata(snapshot: HwpxSnapshot) -> None:
    """The stdlib writer repeats central extra fields in each local header."""
    if any(snapshot.local_extras[info.filename] != info.extra for info in snapshot.infos):
        raise ValueError("ZIP 로컬·중앙 확장 필드가 달라 원본 메타데이터를 보존할 수 없습니다. 별도 검토가 필요합니다.")


def write_preserving_zip(path: Path, infos: list[zipfile.ZipInfo], entries: dict[str, bytes], *,
                         disclosure: bool = False, archive_comment: bytes = b"") -> None:
    if path.exists():
        raise FileExistsError(f"출력 파일이 이미 존재합니다: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "x") as archive:
        archive.comment = b"" if disclosure else archive_comment
        for info in infos:
            copied = copy.copy(info)
            if disclosure:
                # ZIP comments/extra fields are not document content; private
                # metadata must not be carried into the public package.
                copied.comment = b""
                copied.extra = b""
            archive.writestr(copied, entries[info.filename])


def compare_package_metadata(source: HwpxSnapshot, actual: HwpxSnapshot, *, disclosure: bool) -> None:
    """Check ZIP metadata too, including local-header fields hidden by ZipInfo."""
    require_preservable_metadata(source)
    expected_comment = b"" if disclosure else source.archive_comment
    if actual.archive_comment != expected_comment:
        raise ValueError("ZIP 패키지 주석이 승인된 결과와 다릅니다.")
    source_infos = {info.filename: info for info in source.infos}
    if list(source.entries) != list(actual.entries):
        raise ValueError("ZIP 엔트리 순서 또는 목록이 승인된 결과와 다릅니다.")
    for info in actual.infos:
        expected = source_infos[info.filename]
        comment = b"" if disclosure else expected.comment
        extra = b"" if disclosure else expected.extra
        if info.comment != comment or info.extra != extra or actual.local_extras[info.filename] != extra:
            raise ValueError("ZIP 엔트리 주석 또는 확장 필드가 승인된 결과와 다릅니다.")


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
