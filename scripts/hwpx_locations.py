"""Structural HWPX paragraph addresses and byte-preserving text edits (stdlib only)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.parsers import expat

LOCATION_SCHEME = "structural-v2"
PARAGRAPH_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_LOCATION = re.compile(
    r"section-(0|[1-9][0-9]*)(?:/table-[1-9][0-9]*/row-[1-9][0-9]*/cell-[1-9][0-9]*)*/paragraph-[1-9][0-9]*\Z"
)


def validate_location_id(location_id: str) -> int:
    if not isinstance(location_id, str) or _LOCATION.fullmatch(location_id) is None:
        raise ValueError("structural-v2 문단 위치 형식이 올바르지 않습니다.")
    return int(location_id.split("/", 1)[0][8:])


def require_location_scheme(payload: dict) -> None:
    if payload.get("location_scheme") != LOCATION_SCHEME:
        raise ValueError("location_scheme='structural-v2'가 필요합니다. 기존 좌표는 재검토 후 다시 작성하세요.")


@dataclass
class TextSpan:
    start: int
    end: int
    text: str = ""
    supported: bool = True
    self_closing: bool = False


@dataclass
class Paragraph:
    location_id: str
    paragraph_index: int
    text_nodes: list[TextSpan] = field(default_factory=list)

    @property
    def own_text(self) -> str:
        return "".join(node.text for node in self.text_nodes)


def _tag_end(data: bytes, start: int) -> int:
    quote = 0
    for index in range(start, len(data)):
        byte = data[index]
        if quote:
            if byte == quote:
                quote = 0
        elif byte in (34, 39):
            quote = byte
        elif byte == 62:
            return index + 1
    raise ValueError("XML 태그가 끝나지 않았습니다.")


def parse_section(section_index: int, xml_bytes: bytes) -> list[Paragraph]:
    """Enumerate paragraphs once; a parent never owns a nested paragraph's text.

    Tables are numbered within their section/cell, rows within a table, cells
    within a row, and paragraphs within their section/cell. Wrapper runs and
    subLists do not change addresses. Byte spans refer to the original input.
    """
    if type(section_index) is not int or section_index < 0:
        raise ValueError("section_index는 0 이상의 정수여야 합니다.")
    try:
        xml_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("byte 보존 편집은 UTF-8 XML만 지원합니다.") from exc
    parser = expat.ParserCreate(namespace_separator="}")
    records: list[Paragraph] = []
    # Each frame restores the semantic scope after arbitrary XML wrappers.
    frames: list[tuple[str, str, Paragraph | None, TextSpan | None]] = []
    context = f"section-{section_index}"
    paragraph: Paragraph | None = None
    active_text: TextSpan | None = None
    counts: dict[tuple[str, str], int] = {}

    def next_number(owner: str, kind: str) -> int:
        key = (owner, kind)
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    def start(name: str, attributes: dict[str, str]) -> None:
        nonlocal context, paragraph, active_text
        frames.append((name, context, paragraph, active_text))
        if active_text is not None:
            active_text.supported = False
        if not name.startswith(PARAGRAPH_NS + "}"):
            return
        local = name.rsplit("}", 1)[-1]
        if local == "tbl":
            context += f"/table-{next_number(context, 'table')}"
        elif local == "tr":
            if "/table-" not in context or "/row-" in context.rsplit("/table-", 1)[-1]:
                raise ValueError("표 행의 구조를 해석할 수 없습니다.")
            context += f"/row-{next_number(context, 'row')}"
        elif local == "tc":
            if "/row-" not in context or "/cell-" in context.rsplit("/row-", 1)[-1]:
                raise ValueError("표 셀의 구조를 해석할 수 없습니다.")
            context += f"/cell-{next_number(context, 'cell')}"
        elif local == "p":
            location = context + f"/paragraph-{next_number(context, 'paragraph')}"
            validate_location_id(location)
            paragraph = Paragraph(location, len(records) + 1)
            records.append(paragraph)
            active_text = None
        elif local == "t" and paragraph is not None:
            tag_start = parser.CurrentByteIndex
            tag_end = _tag_end(xml_bytes, tag_start)
            self_closing = xml_bytes[tag_start:tag_end].rstrip().endswith(b"/>")
            active_text = TextSpan(tag_end, tag_end, self_closing=self_closing)
            paragraph.text_nodes.append(active_text)

    def end(name: str) -> None:
        nonlocal context, paragraph, active_text
        if name == PARAGRAPH_NS + "}t" and active_text is not None and not active_text.self_closing:
            active_text.end = parser.CurrentByteIndex
        _, context, paragraph, active_text = frames.pop()

    def characters(value: str) -> None:
        if active_text is not None:
            active_text.text += value

    def unsupported(*args: object) -> None:
        if active_text is not None:
            active_text.supported = False

    def reject_dtd(*args: object) -> None:
        raise ValueError("DTD 또는 외부 entity가 있는 XML은 지원하지 않습니다.")

    def declaration(version: str, encoding: str | None, standalone: int) -> None:
        if encoding is not None and encoding.lower().replace("-", "") != "utf8":
            raise ValueError("byte 보존 편집은 UTF-8 XML만 지원합니다.")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = characters
    parser.CommentHandler = unsupported
    parser.StartCdataSectionHandler = unsupported
    parser.ProcessingInstructionHandler = unsupported
    parser.StartDoctypeDeclHandler = reject_dtd
    parser.ExternalEntityRefHandler = reject_dtd
    parser.XmlDeclHandler = declaration
    try:
        parser.Parse(xml_bytes, True)
    except expat.ExpatError as exc:
        raise ValueError("HWPX section XML을 해석할 수 없습니다.") from exc
    return records


def _boundaries(raw: bytes, expected: str) -> list[int]:
    """Map decoded XML character boundaries back to original UTF-8 bytes."""
    value = raw.decode("utf-8")
    result = [0]
    decoded: list[str] = []
    char_index = byte_index = 0
    while char_index < len(value):
        char = value[char_index]
        if char == "<":
            raise ValueError("내부 markup이 있는 hp:t는 자동 편집할 수 없습니다.")
        if char == "&":
            end = value.find(";", char_index + 1)
            if end < 0:
                raise ValueError("XML entity 경계를 해석할 수 없습니다.")
            token = value[char_index:end + 1]
            if token.startswith("&#x"):
                decoded_char = chr(int(token[3:-1], 16))
            elif token.startswith("&#"):
                decoded_char = chr(int(token[2:-1], 10))
            else:
                decoded_char = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}.get(token)
                if decoded_char is None:
                    raise ValueError("지원하지 않는 XML entity입니다.")
        elif char == "\r":
            token = "\r\n" if value[char_index:char_index + 2] == "\r\n" else "\r"
            decoded_char = "\n"
        else:
            token = char
            decoded_char = char
        char_index += len(token)
        byte_index += len(token.encode("utf-8"))
        decoded.append(decoded_char)
        result.append(byte_index)
    if "".join(decoded) != expected:
        raise ValueError("XML 텍스트와 byte 경계가 일치하지 않습니다.")
    return result


def _escape(value: str) -> bytes:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").encode("utf-8")


def replace_in_paragraphs(
    xml_bytes: bytes, section_index: int, source: str, replacement: str,
    *, location_id: str | None = None, whole: bool = False,
) -> tuple[bytes, int]:
    if not isinstance(source, str) or not source:
        raise ValueError("치환 원문은 비어 있지 않은 문자열이어야 합니다.")
    if location_id is not None and validate_location_id(location_id) != section_index:
        raise ValueError("위치의 section이 대상 section과 다릅니다.")
    paragraphs = parse_section(section_index, xml_bytes)
    if location_id is not None:
        paragraphs = [item for item in paragraphs if item.location_id == location_id]
    patches: list[tuple[int, int, bytes]] = []
    changed = 0
    for paragraph in paragraphs:
        text = paragraph.own_text
        if whole:
            if text.strip() != source:
                continue
            ranges = [(0, len(text))]
        else:
            ranges = [(match.start(), match.end()) for match in re.finditer(re.escape(source), text)]
        if not ranges:
            continue
        if any(not node.supported for node in paragraph.text_nodes):
            raise ValueError("내부 markup이 있는 hp:t는 자동 편집할 수 없습니다.")
        positions: list[tuple[TextSpan, int, int, list[int]]] = []
        offset = 0
        for node in paragraph.text_nodes:
            positions.append((node, offset, offset + len(node.text), _boundaries(xml_bytes[node.start:node.end], node.text)))
            offset += len(node.text)
        for left, right in ranges:
            first = True
            for node, node_left, node_right, boundaries in positions:
                overlap_left = max(left, node_left)
                overlap_right = min(right, node_right)
                if overlap_left >= overlap_right:
                    continue
                start = node.start + boundaries[overlap_left - node_left]
                end = node.start + boundaries[overlap_right - node_left]
                patches.append((start, end, _escape(replacement) if first else b""))
                first = False
            if not first:
                changed += 1
    for start, end, value in sorted(patches, reverse=True):
        xml_bytes = xml_bytes[:start] + value + xml_bytes[end:]
    return xml_bytes, changed
