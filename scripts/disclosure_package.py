"""Disclosure preview hygiene and explicit, term-limited package inspection.

This never certifies legal/public-release readiness. Opaque objects require a
human check; unmatched/unconfigured personal data cannot be ruled out here.
"""

from __future__ import annotations

import struct
import zlib
import posixpath
from typing import Any
from xml.etree import ElementTree as ET
from xml.parsers import expat

from hwpx_common import HwpxSnapshot, local_name, section_names
from hwpx_locations import parse_section


PREVIEW_TEXT = "정보공개 검토본 — 내용은 본문에서 확인하십시오.\n".encode("utf-8")


def _png_chunk(name: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)


# A neutral thumbnail, not a reduced or re-encoded copy of the original image.
PREVIEW_PNG = (b"\x89PNG\r\n\x1a\n"
               + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
               + _png_chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
               + _png_chunk(b"IEND", b""))


def neutralize_disclosure_previews(entries: dict[str, bytes]) -> tuple[dict[str, bytes], list[dict[str, str]]]:
    """Keep package names/relationships while replacing only standard previews."""
    preview_names = {name for name in entries if name.casefold() in {"preview/prvtext.txt", "preview/prvimage.png"}}
    if preview_names:
        references = set()
        for name in section_names(entries):
            _xml_notes(entries[name])
            root = ET.fromstring(entries[name])
            references.update(value.lstrip("#") for node in root.iter() for value in node.attrib.values())
        preview_ids = set()
        for name, data in entries.items():
            if not name.casefold().endswith(".hpf"):
                continue
            _xml_notes(data)
            for node in ET.fromstring(data).iter():
                href, item_id = node.get("href"), node.get("id")
                if not href or not item_id:
                    continue
                href = href.split("#", 1)[0].replace("\\", "/")
                candidates = {posixpath.normpath(href), posixpath.normpath(posixpath.join(posixpath.dirname(name), href))}
                if candidates.intersection(preview_names):
                    preview_ids.add(item_id)
        direct_paths = preview_names | {"../" + name for name in preview_names}
        if references.intersection(preview_ids | direct_paths):
            raise ValueError("미리보기가 본문 자원으로도 참조됩니다. 원본 내용을 보존하기 위해 담당자 확인 후 별도로 처리하세요.")
    updated = dict(entries)
    changes = []
    for name, data in entries.items():
        replacement = {"preview/prvtext.txt": PREVIEW_TEXT, "preview/prvimage.png": PREVIEW_PNG}.get(name.casefold())
        if replacement is not None and data != replacement:
            updated[name] = replacement
            changes.append({"entry": name, "action": "neutral_preview_placeholder"})
    return updated, changes


def _text(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


def _xml_notes(data: bytes) -> list[str]:
    """Inspect prolog/epilog too, and reject DTDs before constructing a tree."""
    notes: list[str] = []
    parser = expat.ParserCreate()
    parser.CommentHandler = notes.append
    parser.ProcessingInstructionHandler = lambda target, value: notes.append(target + " " + value)

    def reject_dtd(*args: object) -> None:
        raise ValueError("DTD 또는 외부 entity 검사는 지원하지 않습니다.")

    parser.StartDoctypeDeclHandler = reject_dtd
    parser.ExternalEntityRefHandler = reject_dtd
    parser.Parse(data, True)
    return notes


def inspect_disclosure_package(entries: dict[str, bytes], terms: list[str], *,
                               snapshot: HwpxSnapshot | None = None) -> dict[str, Any]:
    if not isinstance(terms, list) or any(not isinstance(term, str) or not term for term in terms):
        raise ValueError("검사어는 비어 있지 않은 문자열 배열이어야 합니다.")
    terms = list(dict.fromkeys(terms))
    section_indexes = {name: index for index, name in enumerate(section_names(entries))}
    findings: list[dict[str, Any]] = []
    checked: list[dict[str, str]] = []
    manual: list[dict[str, str]] = []

    if snapshot is not None:
        if entries != snapshot.entries:
            raise ValueError("ZIP 검사 바이트와 본문 엔트리가 다릅니다.")
        metadata = [("zip-archive", "archive-comment", snapshot.archive_comment)]
        for index, info in enumerate(snapshot.infos, 1):
            metadata.extend((f"zip-entry-{index}", field, value) for field, value in (
                ("entry-comment", info.comment), ("central-extra", info.extra),
                ("local-extra", snapshot.local_extras[info.filename])))
        for entry_id, field, value in metadata:
            if not value:
                continue
            manual.append({"entry": entry_id, "entry_id": entry_id,
                           "reason": "zip_metadata_needs_manual_review"})
            for term_index, term in enumerate(terms):
                encodings = {term.encode(encoding) for encoding in ("utf-8", "utf-16le", "utf-16be")}
                count = max(value.count(encoded) for encoded in encodings)
                if count:
                    findings.append({"entry": entry_id, "entry_id": entry_id,
                                     "location_id": f"{entry_id}/{field}",
                                     "term_id": f"term-{term_index + 1}", "match_count": count})

    for index, (name, data) in enumerate(entries.items(), 1):
        entry_id = f"zip-entry-{index}"
        # File names can themselves identify a person. Never repeat such names.
        entry = name if not any(term in name for term in terms) else entry_id

        def finding(location: str, term_index: int, count: int) -> None:
            if count:
                findings.append({"entry": entry, "entry_id": entry_id, "location_id": location,
                                 "term_id": f"term-{term_index + 1}", "match_count": count})

        def needs_review(reason: str) -> None:
            manual.append({"entry": entry, "entry_id": entry_id, "reason": reason})

        for term_index, term in enumerate(terms):
            finding(entry_id + "/name", term_index, name.count(term))
        lowered = name.casefold()
        if name == "mimetype" and data == b"application/hwp+zip":
            continue
        if lowered == "preview/prvimage.png" and data == PREVIEW_PNG:
            checked.append({"entry": entry, "entry_id": entry_id, "kind": "neutral_thumbnail"})
            continue
        if lowered.endswith((".xml", ".hpf", ".rdf")):
            try:
                notes = _xml_notes(data)
                root = ET.fromstring(data)
            except (ET.ParseError, expat.ExpatError, ValueError):
                needs_review("unreadable_xml")
                continue
            checked.append({"entry": entry, "entry_id": entry_id, "kind": "xml_text_attributes_comments"})
            body_counts = [0] * len(terms)
            if name in section_indexes:
                try:
                    paragraphs = parse_section(section_indexes[name], data)
                except ValueError:
                    paragraphs = []
                    needs_review("unsupported_body_structure")
                for paragraph in paragraphs:
                    for term_index, term in enumerate(terms):
                        count = paragraph.own_text.count(term)
                        finding(paragraph.location_id, term_index, count)
                        body_counts[term_index] += count
            all_text = "".join(root.itertext())
            attributes = [value for node in root.iter() for value in node.attrib.values()]
            for term_index, term in enumerate(terms):
                # Body matches already have precise coordinates; record only the remainder here.
                extra = max(0, all_text.count(term) - body_counts[term_index])
                extra += sum(value.count(term) for value in attributes)
                extra += sum(value.count(term) for value in notes)
                finding(entry_id + "/nonbody-text-or-attribute", term_index, extra)
            if any(isinstance(node.tag, str) and local_name(node.tag) in {"pic", "ole", "object", "video", "audio", "chart"}
                   for node in root.iter()):
                needs_review("embedded_object_needs_visual_review")
        elif lowered.endswith(".txt"):
            try:
                value = _text(data)
            except UnicodeError:
                needs_review("unsupported_text_encoding")
                continue
            checked.append({"entry": entry, "entry_id": entry_id, "kind": "plain_text"})
            for term_index, term in enumerate(terms):
                finding(entry_id + "/text", term_index, value.count(term))
        else:
            needs_review("opaque_resource_needs_manual_review")

    return {
        "findings": findings,
        "coverage": {"terms_configured": len(terms), "checked_entries": checked, "manual_review_entries": manual,
                     "zip_metadata_checked": snapshot is not None},
        "configured_terms_check_pass": bool(terms) and not findings and not manual and snapshot is not None,
        "release_ready": False,
        "readiness_note": "설정된 검사어만 검사했습니다. 자동검사·쌍 일치는 정보공개 판단이나 한글 실물 확인을 대체하지 않습니다.",
    }
