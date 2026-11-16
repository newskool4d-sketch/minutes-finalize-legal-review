"""Synthetic regressions for approval separation and ZIP-container integrity."""

from __future__ import annotations

import copy
import io
import json
import struct
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from test_hwpx_pipeline import ROOT, SCRIPTS, approval_spec, run, synthetic_hwpx

sys.path.insert(0, str(SCRIPTS))


class EngineSecurityRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.source = self.work / "source.hwpx"
        synthetic_hwpx(self.source)

    def plan(self, edits=None) -> Path:
        plan = self.work / "approved.json"
        plan.write_text(json.dumps(approval_spec({"edits": edits or [], "redactions": []}, self.source),
                                   ensure_ascii=False), encoding="utf-8")
        return plan

    def apply(self, plan: Path):
        return run(str(SCRIPTS / "apply_approved_edits.py"), str(self.source), "--approved", str(plan),
                   "--approval-output", str(self.work / "approval.hwpx"),
                   "--disclosure-output", str(self.work / "disclosure.hwpx"),
                   "--audit", str(self.work / "audit.json"), "--redaction-ledger", str(self.work / "ledger.json"), cwd=ROOT)

    def verify(self, plan: Path, **overrides):
        paths = {"source": self.source, "approval": self.work / "approval.hwpx",
                 "disclosure": self.work / "disclosure.hwpx"} | overrides
        return run(str(SCRIPTS / "verify_release_pair.py"), "--source", str(paths["source"]),
                   "--approval", str(paths["approval"]), "--disclosure", str(paths["disclosure"]),
                   "--approved", str(plan), cwd=ROOT)

    @staticmethod
    def rewrite_metadata(path: Path, field: str, value: bytes) -> None:
        with zipfile.ZipFile(path) as archive:
            comment = archive.comment
            entries = [(copy.copy(info), archive.read(info)) for info in archive.infolist()]
        with zipfile.ZipFile(path, "w") as archive:
            archive.comment = value if field == "archive_comment" else comment
            for info, data in entries:
                if info.filename == "Contents/header.xml" and field != "archive_comment":
                    setattr(info, field, value)
                archive.writestr(info, data)

    @staticmethod
    def duplicate_entry(path: Path) -> None:
        with zipfile.ZipFile(path) as archive:
            value = archive.read("Contents/header.xml")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("Contents/header.xml", value)

    def test_general_edits_reject_disclosure_redaction_fields(self) -> None:
        from approval_contract import validate_approval_spec

        for redaction_type in ("문장 비공개", "성명"):
            with self.subTest(redaction_type=redaction_type):
                record = {"id": "mixed-scope", "approved": True, "scope": "both",
                          "location": "section-0/paragraph-3", "from": "위원 홍길동은 오타라고 진술함.",
                          "to": "[비공개]", "redaction_type": redaction_type, "human_decision": "담당자 승인"}
                spec = approval_spec({"edits": [record], "redactions": []}, self.source)
                with self.assertRaises(ValueError):
                    validate_approval_spec(spec)

    def test_general_edits_cannot_mask_approval_copy(self) -> None:
        record = {"id": "misplaced-mask", "approved": True, "scope": "both",
                  "location": "section-0/paragraph-3", "from": "위원 홍길동은 오타라고 진술함.",
                  "to": "[비공개]", "redaction_type": "문장 비공개", "human_decision": "담당자 승인"}
        result = self.apply(self.plan([record]))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.work / "approval.hwpx").exists())
        self.assertFalse((self.work / "disclosure.hwpx").exists())

    def test_disclosure_scrubs_container_metadata_and_approval_preserves_it(self) -> None:
        marker = b"SYNTHETIC-METADATA"
        extra = struct.pack("<HH", 0xCAFE, len(marker)) + marker
        for field, value in (("archive_comment", marker), ("comment", marker), ("extra", extra)):
            self.rewrite_metadata(self.source, field, value)
        original = self.source.read_bytes()
        plan = self.plan()
        result = self.apply(plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(original, self.source.read_bytes())
        with zipfile.ZipFile(self.work / "approval.hwpx") as archive:
            self.assertEqual(archive.comment, marker)
            info = archive.getinfo("Contents/header.xml")
            self.assertEqual(info.comment, marker)
            self.assertEqual(info.extra, extra)
        with zipfile.ZipFile(self.work / "disclosure.hwpx") as archive:
            self.assertEqual(archive.comment, b"")
            for info in archive.infolist():
                self.assertEqual(info.comment, b"")
                self.assertEqual(info.extra, b"")
        self.assertEqual(self.verify(plan).returncode, 0)

    def test_pair_rejects_disclosure_container_metadata_tampering(self) -> None:
        plan = self.plan()
        result = self.apply(plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        original = (self.work / "disclosure.hwpx").read_bytes()
        marker = b"SYNTHETIC-ALTERED"
        for field, value in (("archive_comment", marker), ("comment", marker),
                             ("extra", struct.pack("<HH", 0xCAFE, len(marker)) + marker)):
            with self.subTest(field=field):
                candidate = self.work / (field + ".hwpx")
                candidate.write_bytes(original)
                self.rewrite_metadata(candidate, field, value)
                self.assertNotEqual(self.verify(plan, disclosure=candidate).returncode, 0)

    def test_pair_rejects_approval_container_metadata_tampering(self) -> None:
        plan = self.plan()
        result = self.apply(plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        original = (self.work / "approval.hwpx").read_bytes()
        marker = b"SYNTHETIC-ALTERED"
        for field, value in (("archive_comment", marker), ("comment", marker),
                             ("extra", struct.pack("<HH", 0xCAFE, len(marker)) + marker)):
            with self.subTest(field=field):
                candidate = self.work / (field + ".hwpx")
                candidate.write_bytes(original)
                self.rewrite_metadata(candidate, field, value)
                self.assertNotEqual(self.verify(plan, approval=candidate).returncode, 0)

    def test_duplicate_names_are_rejected_by_common_readers(self) -> None:
        from hwpx_common import read_entry_map, validate_basic_hwpx

        self.duplicate_entry(self.source)
        for reader in (read_entry_map, validate_basic_hwpx):
            with self.subTest(reader=reader.__name__), self.assertRaises(ValueError):
                reader(self.source)

    def test_duplicate_names_are_rejected_before_generation(self) -> None:
        self.duplicate_entry(self.source)
        result = self.apply(self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.work / "approval.hwpx").exists())
        self.assertFalse((self.work / "disclosure.hwpx").exists())

    def test_duplicate_names_are_rejected_by_pair_verifier(self) -> None:
        plan = self.plan()
        result = self.apply(plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.duplicate_entry(self.work / "disclosure.hwpx")
        self.assertNotEqual(self.verify(plan).returncode, 0)

    def test_duplicate_names_are_rejected_by_scanner(self) -> None:
        self.duplicate_entry(self.source)
        terms = self.work / "terms.json"
        output = self.work / "scan.json"
        terms.write_text('["SYNTHETIC"]', encoding="utf-8")
        result = run(str(SCRIPTS / "scan_sensitive_content.py"), str(self.source), "--terms", str(terms),
                     "--output", str(output), cwd=ROOT)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_local_only_extra_fields_block_generation(self) -> None:
        marker = b"SYNTHETIC-CENTRAL"
        extra = struct.pack("<HH", 0xCAFE, len(marker)) + marker
        self.rewrite_metadata(self.source, "extra", extra)
        data = self.source.read_bytes()
        # The first occurrence is in the local header; central metadata remains unchanged.
        self.source.write_bytes(data.replace(marker, b"SYNTHETIC-LOCAL!!", 1))
        plan = self.plan()
        result = self.apply(plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.work / "approval.hwpx").exists())
        self.assertIn("로컬", result.stderr)

    def test_pair_rejects_local_header_only_metadata_change(self) -> None:
        marker = b"SYNTHETIC-CENTRAL"
        extra = struct.pack("<HH", 0xCAFE, len(marker)) + marker
        self.rewrite_metadata(self.source, "extra", extra)
        plan = self.plan()
        self.assertEqual(self.apply(plan).returncode, 0)
        approval = self.work / "approval.hwpx"
        approval.write_bytes(approval.read_bytes().replace(marker, b"SYNTHETIC-LOCAL!!", 1))
        self.assertNotEqual(self.verify(plan).returncode, 0)

    def test_scanner_checks_zip_metadata_without_echoing_values(self) -> None:
        marker = b"SYNTHETIC-METADATA"
        for field, value in (("archive_comment", marker), ("comment", marker),
                             ("extra", struct.pack("<HH", 0xCAFE, len(marker)) + marker)):
            self.rewrite_metadata(self.source, field, value)
        terms, output = self.work / "terms.json", self.work / "metadata-scan.json"
        terms.write_text('["SYNTHETIC-METADATA"]', encoding="utf-8")
        result = run(str(SCRIPTS / "scan_sensitive_content.py"), str(self.source), "--terms", str(terms),
                     "--output", str(output), cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = output.read_text(encoding="utf-8")
        self.assertNotIn(marker.decode(), text)
        report = json.loads(text)
        self.assertTrue(report["coverage"]["zip_metadata_checked"])
        self.assertFalse(report["configured_terms_check_pass"])
        self.assertEqual(len(report["findings"]), 4)

    def test_generator_hashes_and_parses_one_source_snapshot(self) -> None:
        from apply_approved_edits import main

        plan = self.plan()
        open_file = io.open
        source_reads = []

        def one_read(path, mode="r", *args, **kwargs):
            if not isinstance(path, int) and Path(path).resolve() == self.source.resolve() and mode.startswith("r"):
                source_reads.append(path)
                if len(source_reads) > 1:
                    raise AssertionError("source was reopened after its bound snapshot")
            return open_file(path, mode, *args, **kwargs)

        argv = ["apply", str(self.source), "--approved", str(plan),
                "--approval-output", str(self.work / "approval.hwpx"),
                "--disclosure-output", str(self.work / "disclosure.hwpx"),
                "--audit", str(self.work / "audit.json"), "--redaction-ledger", str(self.work / "ledger.json")]
        with patch.object(sys, "argv", argv), patch.object(io, "open", one_read):
            self.assertEqual(main(), 0)
        self.assertEqual(len(source_reads), 1)

    def test_verifier_reads_each_hwpx_once(self) -> None:
        from verify_release_pair import main

        plan = self.plan()
        self.assertEqual(self.apply(plan).returncode, 0)
        paths = [self.source, self.work / "approval.hwpx", self.work / "disclosure.hwpx"]
        counts = {path.resolve(): 0 for path in paths}
        open_file = io.open

        def one_read(path, mode="r", *args, **kwargs):
            resolved = Path(path).resolve() if not isinstance(path, int) else None
            if resolved in counts and mode.startswith("r"):
                counts[resolved] += 1
                if counts[resolved] > 1:
                    raise AssertionError("HWPX was reopened after its bound snapshot")
            return open_file(path, mode, *args, **kwargs)

        argv = ["verify", "--source", str(paths[0]), "--approval", str(paths[1]),
                "--disclosure", str(paths[2]), "--approved", str(plan)]
        with patch.object(sys, "argv", argv), patch.object(io, "open", one_read):
            self.assertEqual(main(), 0)
        self.assertEqual(list(counts.values()), [1, 1, 1])


if __name__ == "__main__":
    unittest.main()
