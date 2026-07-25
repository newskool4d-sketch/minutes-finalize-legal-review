#!/usr/bin/env python3
"""Synthetic end-to-end tests for the safe two-version HWPX pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PYTHON = sys.executable


def run(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, *arguments], cwd=cwd, text=True, capture_output=True, check=False, encoding="utf-8", errors="replace"
    )


def synthetic_hwpx(path: Path, label: str = "기본") -> None:
    section = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<hp:section xmlns:hp=\"http://www.hancom.co.kr/hwpml/2011/paragraph\">
  <hp:p><hp:run><hp:t>위원1(위원장) 홍길동</hp:t></hp:run></hp:p>
  <hp:p><hp:run><hp:t>합성 검증 사례: {label}</hp:t></hp:run></hp:p>
  <hp:p><hp:run><hp:t>위원 홍길동은 오타라고 진술함.</hp:t></hp:run></hp:p>
  <hp:linesegarray/>
  <hp:tbl><hp:tr><hp:tc><hp:subList><hp:p><hp:run><hp:t>표결 3명 찬성</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl>
</hp:section>""".encode("utf-8")
    header = b'<?xml version="1.0" encoding="UTF-8"?><hh:head xmlns:hh="urn:test"/>'
    with zipfile.ZipFile(path, "w") as archive:
        mimetype = zipfile.ZipInfo("mimetype")
        mimetype.compress_type = zipfile.ZIP_STORED
        archive.writestr(mimetype, b"application/hwp+zip")
        archive.writestr("Contents/header.xml", header, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("Contents/section0.xml", section, compress_type=zipfile.ZIP_DEFLATED)


class HwpxPipelineTests(unittest.TestCase):
    def test_legal_candidate_detector_keeps_text_out_of_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "source.hwpx"
            synthetic_hwpx(source, "홍길동은 공식 자료 없는 진단 추정")
            candidates = work / "candidates.json"
            result = run(str(SCRIPTS / "detect_legal_review_candidates.py"), str(source), "--output", str(candidates), cwd=ROOT)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = candidates.read_text(encoding="utf-8")
            self.assertIn("sensitive-health", text)
            self.assertNotIn("진단", text)
            self.assertNotIn("홍길동", text)

    def test_candidate_context_export_masks_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "source.hwpx"
            synthetic_hwpx(source, "홍길동은 공식 자료 없는 진단 추정")
            candidates, contexts = work / "candidates.json", work / "contexts.json"
            candidates.write_text(json.dumps({"candidates": [{"location_id": "section-0/paragraph-1", "rule_id": "sensitive-health"}]}, ensure_ascii=False), encoding="utf-8")
            result = run(str(SCRIPTS / "export_candidate_context.py"), str(source), "--candidates", str(candidates), "--output", str(contexts), cwd=ROOT)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = contexts.read_text(encoding="utf-8")
            self.assertNotIn("홍길동", text)
            self.assertIn("[성명]", text)

    def test_validates_five_distinct_synthetic_hwpx_packages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for number in range(1, 6):
                source = work / f"synthetic-{number}.hwpx"
                synthetic_hwpx(source, f"사례-{number}")
                result = run(str(SCRIPTS / "inspect_hwpx.py"), str(source), cwd=ROOT)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_prepares_role_context_redactions_without_printing_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "source.hwpx"
            synthetic_hwpx(source)
            candidates = work / "candidates.json"
            result = run(
                str(SCRIPTS / "prepare_redactions.py"),
                str(source),
                "--output",
                str(candidates),
                "--approve-detected",
                cwd=ROOT,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(candidates.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["redactions"]), 1)
            self.assertTrue(payload["redactions"][0]["approved"])

    def test_refuses_disclosure_only_content_edit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "source.hwpx"
            synthetic_hwpx(source)
            approved = work / "approved.json"
            approved.write_text(
                json.dumps(
                    {
                        "edits": [
                            {
                                "id": "unsafe-disclosure-edit",
                                "approved": True,
                                "scope": "disclosure",
                                "from": "표결 3명 찬성",
                                "to": "삭제된 문구",
                            }
                        ],
                        "redactions": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = run(
                str(SCRIPTS / "apply_approved_edits.py"),
                str(source),
                "--approved",
                str(approved),
                "--approval-output",
                str(work / "approval.hwpx"),
                "--disclosure-output",
                str(work / "disclosure.hwpx"),
                "--audit",
                str(work / "audit.json"),
                "--redaction-ledger",
                str(work / "ledger.json"),
                cwd=ROOT,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("redactions", result.stderr)

    def test_allows_one_human_approved_disclosure_sentence_mask(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "source.hwpx"
            synthetic_hwpx(source)
            approved = work / "approved.json"
            approved.write_text(
                json.dumps(
                    {
                        "edits": [],
                        "redactions": [
                            {
                                "id": "redact-name-after-mask",
                                "approved": True,
                                "scope": "disclosure",
                                "from": "홍길동",
                                "to": "○○",
                                "location": "section-0/paragraph-1",
                                "redaction_type": "성명",
                            },
                            {
                                "id": "mask-sentence",
                                "approved": True,
                                "scope": "disclosure",
                                "from": "위원 홍길동은 오타라고 진술함.",
                                "to": "[비공개]",
                                "location": "section-0/paragraph-3",
                                "redaction_type": "문장 비공개",
                                "reason": "합성 비공개 사유",
                                "human_decision": "정보공개 담당 확인",
                                "min_matches": 1,
                                "max_matches": 1,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            approval, disclosure = work / "approval.hwpx", work / "disclosure.hwpx"
            result = run(
                str(SCRIPTS / "apply_approved_edits.py"),
                str(source),
                "--approved",
                str(approved),
                "--approval-output",
                str(approval),
                "--disclosure-output",
                str(disclosure),
                "--audit",
                str(work / "audit.json"),
                "--redaction-ledger",
                str(work / "ledger.json"),
                cwd=ROOT,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            pair = run(
                str(SCRIPTS / "verify_release_pair.py"),
                "--approval",
                str(approval),
                "--disclosure",
                str(disclosure),
                "--approved",
                str(approved),
                cwd=ROOT,
            )
            self.assertEqual(pair.returncode, 0, pair.stderr)
            with zipfile.ZipFile(approval) as archive:
                self.assertIn("위원 홍길동은 오타라고 진술함.", archive.read("Contents/section0.xml").decode("utf-8"))
            with zipfile.ZipFile(disclosure) as archive:
                self.assertIn("[비공개]", archive.read("Contents/section0.xml").decode("utf-8"))

    def test_generates_two_safe_versions_and_audits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "source.hwpx"
            synthetic_hwpx(source)
            approved = work / "approved.json"
            approved.write_text(
                json.dumps(
                    {
                        "edits": [
                            {
                                "id": "edit-typo",
                                "approved": True,
                                "scope": "both",
                                "from": "오타",
                                "to": "정정",
                                "reason": "오기 정정",
                            }
                        ],
                        "redactions": [
                            {
                                "id": "redact-name",
                                "approved": True,
                                "scope": "disclosure",
                                "from": "홍길동",
                                "to": "○○",
                                "location": "section-0/paragraph-1",
                                "redaction_type": "성명",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            approval = work / "approval.hwpx"
            disclosure = work / "disclosure.hwpx"
            audit = work / "audit.json"
            ledger = work / "ledger.json"

            result = run(
                str(SCRIPTS / "apply_approved_edits.py"),
                str(source),
                "--approved",
                str(approved),
                "--approval-output",
                str(approval),
                "--disclosure-output",
                str(disclosure),
                "--audit",
                str(audit),
                "--redaction-ledger",
                str(ledger),
                cwd=ROOT,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            for output in (approval, disclosure):
                validation = run(
                    str(SCRIPTS / "validate_hwpx.py"),
                    str(output),
                    "--compare-base",
                    str(source),
                    cwd=ROOT,
                )
                self.assertEqual(validation.returncode, 0, validation.stderr)

            pair = run(
                str(SCRIPTS / "verify_release_pair.py"),
                "--approval",
                str(approval),
                "--disclosure",
                str(disclosure),
                "--approved",
                str(approved),
                cwd=ROOT,
            )
            self.assertEqual(pair.returncode, 0, pair.stderr)

            with zipfile.ZipFile(approval) as archive:
                approval_text = archive.read("Contents/section0.xml").decode("utf-8")
            with zipfile.ZipFile(disclosure) as archive:
                disclosure_text = archive.read("Contents/section0.xml").decode("utf-8")
            self.assertIn("홍길동", approval_text)
            self.assertNotIn("○○", approval_text)
            self.assertIn("정정", approval_text)
            self.assertNotIn("hp:linesegarray", approval_text)
            self.assertIn("○○", disclosure_text)
            self.assertNotIn("홍길동", disclosure_text)
            self.assertIn("정정", disclosure_text)
            self.assertNotIn("hp:linesegarray", disclosure_text)

            ledger_text = ledger.read_text(encoding="utf-8")
            self.assertNotIn("홍길동", ledger_text)
            # The same approved name appears in the roster and in the body.
            self.assertEqual(json.loads(ledger_text)[0]["changed_count"], 2)

            model = work / "model.json"
            extraction = run(
                str(SCRIPTS / "extract_minutes_model.py"), str(approval), "--output", str(model), cwd=ROOT
            )
            self.assertEqual(extraction.returncode, 0, extraction.stderr)
            self.assertGreaterEqual(len(json.loads(model.read_text(encoding="utf-8"))["paragraphs"]), 2)

            terms = work / "terms.json"
            terms.write_text(json.dumps(["홍길동"], ensure_ascii=False), encoding="utf-8")
            sensitive = work / "sensitive.json"
            scan = run(
                str(SCRIPTS / "scan_sensitive_content.py"),
                str(approval),
                "--terms",
                str(terms),
                "--output",
                str(sensitive),
                cwd=ROOT,
            )
            self.assertEqual(scan.returncode, 0, scan.stderr)
            self.assertNotIn("홍길동", sensitive.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(sensitive.read_text(encoding="utf-8"))["findings"][0]["match_count"], 1)

            second_run = run(
                str(SCRIPTS / "apply_approved_edits.py"),
                str(source),
                "--approved",
                str(approved),
                "--approval-output",
                str(approval),
                "--disclosure-output",
                str(disclosure),
                "--audit",
                str(audit),
                "--redaction-ledger",
                str(ledger),
                cwd=ROOT,
            )
            self.assertNotEqual(second_run.returncode, 0)


if __name__ == "__main__":
    unittest.main()
