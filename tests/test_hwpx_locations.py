"""Synthetic structural-v2 addresses, split runs and original-byte edit boundaries."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from approval_contract import validate_approval_spec
from apply_approved_edits import build_entry_pair
from build_sample_sentence_mask_plan import paragraph_lookup
from detect_legal_review_candidates import paragraphs as candidate_paragraphs
from export_candidate_context import paragraphs as context_paragraphs
from extract_minutes_model import extract_section
from hwpx_common import replace_paragraph_text, replace_text_nodes
from hwpx_locations import LOCATION_SCHEME, PARAGRAPH_NS, parse_section, validate_location_id


def p(text: str) -> str:
    return f"<q:p><q:run><q:t>{text}</q:t></q:run></q:p>"


NESTED = "<q:tbl><q:tr><q:tc><q:subList>" + p("중첩 내용") + "</q:subList></q:tc></q:tr></q:tbl>"
TABLE = (
    "<q:tbl id='table-a'><q:tr><q:tc><q:subList>"
    "<q:p><q:run charPrIDRef='7'><q:t>진단 홍</q:t></q:run>"
    "<q:run charPrIDRef='8'><q:t>길&#46041;</q:t>" + NESTED + "</q:run></q:p>"
    + p("둘째 셀문단") + "</q:subList></q:tc><q:tc><q:subList>" + p("다른 셀")
    + "</q:subList></q:tc></q:tr><q:tr><q:tc><q:subList>" + p("둘째 행")
    + "</q:subList></q:tc></q:tr></q:tbl>"
)
TABLE2 = "<q:tbl><q:tr><q:tc><q:subList>" + p("다른 표") + "</q:subList></q:tc></q:tr></q:tbl>"
XML = (
    f"<?xml version='1.0' encoding='UTF-8'?>\n<q:section xmlns:q='{PARAGRAPH_NS}'>"
    "<q:p id='outer'><q:run note='a>b'><q:t>부모 &amp; </q:t>" + TABLE + TABLE2
    + "<q:t>끝</q:t></q:run></q:p>" + p("반복 홍길동") + "</q:section>"
).encode("utf-8")
CELL = "section-0/table-1/row-1/cell-1/paragraph-1"
INNER = "section-0/table-1/row-1/cell-1/table-1/row-1/cell-1/paragraph-1"


def package(path: Path, sections: list[bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        for index, xml in enumerate(sections):
            archive.writestr(f"Contents/section{index}.xml", xml)


def spec(record: dict | None = None) -> dict:
    record = {"id": "edit-001", "scope": "both", "approved": True,
              "from": "홍길동", "to": "○○", "location": CELL,
              "issue_id": "issue-001", "decided_by_role": "합성 검토자",
              "decided_at": "2026-10-30T09:00:00+09:00", "evidence_refs": ["fixture:synthetic-001"],
              "reason": "합성 승인 사유", **(record or {})}
    return {"schema_version": 2, "location_scheme": LOCATION_SCHEME, "source_sha256": "a" * 64,
            "edits": [record], "redactions": []}


class HwpxLocationTests(unittest.TestCase):
    def test_nested_tables_sublists_and_scoped_counters(self) -> None:
        lookup = {item.location_id: item.own_text for item in parse_section(0, XML)}
        self.assertEqual(len(lookup), 8)
        self.assertEqual(lookup["section-0/paragraph-1"], "부모 & 끝")
        self.assertEqual(lookup[CELL], "진단 홍길동")
        self.assertEqual(lookup[INNER], "중첩 내용")
        self.assertEqual(lookup["section-0/table-1/row-1/cell-1/paragraph-2"], "둘째 셀문단")
        self.assertEqual(lookup["section-0/table-1/row-1/cell-2/paragraph-1"], "다른 셀")
        self.assertEqual(lookup["section-0/table-1/row-2/cell-1/paragraph-1"], "둘째 행")
        self.assertEqual(lookup["section-0/table-2/row-1/cell-1/paragraph-1"], "다른 표")
        self.assertEqual(lookup["section-0/paragraph-2"], "반복 홍길동")

    def test_all_producer_helpers_share_the_same_addresses_and_own_text(self) -> None:
        expected = {item.location_id: item.own_text.strip() for item in parse_section(0, XML)}
        self.assertEqual(dict(candidate_paragraphs(0, XML)), expected)
        self.assertEqual(context_paragraphs(XML, 0), expected)
        self.assertEqual({item["location_id"]: item["text"] for item in extract_section(0, XML)}, expected)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "synthetic.hwpx"
            package(source, [XML, XML])
            lookup = paragraph_lookup(source)
            self.assertEqual(len(lookup), 16)
            self.assertEqual(lookup[CELL.replace("section-0", "section-1")], "진단 홍길동")

    def test_whole_parent_replacement_keeps_all_nested_paragraph_bytes(self) -> None:
        changed, count = replace_paragraph_text(XML, "section-0/paragraph-1", "부모 & 끝", "[비공개]")
        expected = XML.replace("부모 &amp; ".encode(), "[비공개]".encode()).replace("<q:t>끝</q:t>".encode(), b"<q:t></q:t>")
        self.assertEqual((changed, count), (expected, 1))
        self.assertIn(TABLE.encode(), changed)
        self.assertIn(TABLE2.encode(), changed)

    def test_split_run_replacement_preserves_namespace_attributes_and_other_bytes(self) -> None:
        changed, count = replace_text_nodes(XML, "홍길동", "○○", location_id=CELL)
        expected = XML.replace("진단 홍".encode(), "진단 ○○".encode()).replace("길&#46041;".encode(), b"")
        self.assertEqual((changed, count), (expected, 1))
        self.assertIn("반복 홍길동".encode(), changed)

    def test_document_matching_counts_each_paragraph_once(self) -> None:
        changed, count = replace_text_nodes(XML, "홍길동", "○○")
        self.assertEqual(count, 2)
        lookup = {item.location_id: item.own_text for item in parse_section(0, changed)}
        self.assertEqual(lookup[CELL], "진단 ○○")
        self.assertEqual(lookup["section-0/paragraph-2"], "반복 ○○")

    def test_escaped_entities_and_crlf_map_to_original_byte_boundaries(self) -> None:
        xml = f"<q:section xmlns:q='{PARAGRAPH_NS}'>" + p("가 &#x26; 나\r\n끝 &amp; 보존") + "</q:section>"
        original = xml.encode()
        changed, count = replace_text_nodes(original, "& 나\n끝", "<새&값>", location_id="section-0/paragraph-1")
        expected = original.replace("&#x26; 나\r\n끝".encode(), "&lt;새&amp;값&gt;".encode())
        self.assertEqual((changed, count), (expected, 1))
        self.assertIn(b"&amp;", changed)

    def test_multiple_matches_in_split_nodes_are_applied_right_to_left(self) -> None:
        xml = (f"<q:section xmlns:q='{PARAGRAPH_NS}'><q:p><q:run><q:t>홍</q:t></q:run>"
               "<q:run><q:t>길동 홍길</q:t></q:run><q:run><q:t>동</q:t></q:run></q:p></q:section>").encode()
        changed, count = replace_text_nodes(xml, "홍길동", "○")
        self.assertEqual(count, 2)
        self.assertEqual(parse_section(0, changed)[0].own_text, "○ ○")

    def test_no_match_crosses_paragraph_or_cell_boundaries(self) -> None:
        changed, count = replace_text_nodes(XML, "끝진단", "금지")
        self.assertEqual((changed, count), (XML, 0))
        self.assertEqual(replace_text_nodes(XML, "홍길동", "○", location_id=INNER), (XML, 0))

    def test_empty_text_nodes_and_empty_paragraph_do_not_shift_addresses(self) -> None:
        xml = (f"<q:section xmlns:q='{PARAGRAPH_NS}'><q:p/><q:p><q:run><q:t/>"
               "<q:t>문장</q:t><q:t></q:t></q:run></q:p></q:section>").encode()
        changed, count = replace_paragraph_text(xml, "section-0/paragraph-2", "문장", "새문장")
        self.assertEqual(count, 1)
        self.assertEqual([item.own_text for item in parse_section(0, changed)], ["", "새문장"])
        self.assertIn(b"<q:t/>", changed)

    def test_inline_markup_comments_and_cdata_fail_closed_on_edit(self) -> None:
        for body in ("가<q:tab/>나", "가<!-- cache -->나", "<![CDATA[가나]]>"):
            with self.subTest(body=body):
                xml = (f"<q:section xmlns:q='{PARAGRAPH_NS}'>" + p(body) + "</q:section>").encode()
                self.assertEqual(parse_section(0, xml)[0].own_text, "가나")
                with self.assertRaises(ValueError):
                    replace_text_nodes(xml, "가나", "변경")

    def test_dtd_and_non_utf8_or_malformed_xml_are_rejected(self) -> None:
        for xml in (b'<!DOCTYPE root [<!ENTITY x "x">]><root/>', b"<root>\xff</root>", b"<root>",
                    b'<?xml version="1.0" encoding="ISO-8859-1"?><root/>'):
            with self.subTest(xml=xml):
                with self.assertRaises(ValueError):
                    parse_section(0, xml)

    def test_invalid_or_legacy_locations_and_section_mismatch_are_rejected(self) -> None:
        for location in (1, "section--1/paragraph-1", "section-0/paragraph-0", "section-01/paragraph-1",
                         "section-0/table-1/paragraph-1", "section-0/paragraph-1/trailing"):
            with self.subTest(location=location):
                with self.assertRaises(ValueError):
                    validate_location_id(location)
        with self.assertRaises(ValueError):
            replace_text_nodes(XML, "홍길동", "○", location_id="section-1/paragraph-1")
        with self.assertRaises(ValueError):
            replace_paragraph_text(XML, 1, "부모 & 끝", "가림")

    def test_approval_scheme_and_explicit_scope_are_required(self) -> None:
        base = spec()
        validate_approval_spec(base)
        for mode in ("missing-scheme", "legacy-scheme", "missing-scope", "conflicting-scope"):
            payload = copy.deepcopy(base)
            if mode == "missing-scheme":
                payload.pop("location_scheme")
            elif mode == "legacy-scheme":
                payload["location_scheme"] = "flat-v1"
            elif mode == "missing-scope":
                payload["edits"][0].pop("location")
            else:
                payload["edits"][0]["match_scope"] = "document"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                validate_approval_spec(payload)

    def test_apply_location_is_binding_and_document_scope_is_explicit(self) -> None:
        entries = {"Contents/section0.xml": XML, "Contents/section1.xml": XML}
        pair = build_entry_pair(entries, spec())
        self.assertEqual(pair["approval_changes"][0]["changed_count"], 1)
        self.assertEqual(pair["approval_entries"]["Contents/section1.xml"], XML)
        payload = spec()
        payload["edits"][0].pop("location")
        payload["edits"][0]["match_scope"] = "document"
        pair = build_entry_pair(entries, payload)
        self.assertEqual(pair["approval_changes"][0]["changed_count"], 4)

    def test_cli_detector_scanner_and_context_use_cell_not_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source, candidates, findings, contexts = [work / name for name in ("source.hwpx", "candidates.json", "findings.json", "contexts.json")]
            terms = work / "terms.json"
            package(source, [XML, XML])
            terms.write_text(json.dumps(["진단"]), encoding="utf-8")
            commands = [
                ["detect_legal_review_candidates.py", str(source), "--output", str(candidates)],
                ["scan_sensitive_content.py", str(source), "--terms", str(terms), "--output", str(findings)],
                ["export_candidate_context.py", str(source), "--candidates", str(candidates), "--output", str(contexts)],
            ]
            for script, *arguments in commands:
                result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts" / script), *arguments],
                                        cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
            for path, key in ((candidates, "candidates"), (findings, "findings"), (contexts, "contexts")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["location_scheme"], LOCATION_SCHEME)
                self.assertEqual({item["location_id"] for item in payload[key]}, {CELL, CELL.replace("section-0", "section-1")})
            wrong = json.loads(candidates.read_text(encoding="utf-8"))
            wrong["source_document_hash"] = "f" * 64
            candidates.write_text(json.dumps(wrong), encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "export_candidate_context.py"), str(source),
                                     "--candidates", str(candidates), "--output", str(work / "must-not-exist.json")],
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((work / "must-not-exist.json").exists())


if __name__ == "__main__":
    unittest.main()
