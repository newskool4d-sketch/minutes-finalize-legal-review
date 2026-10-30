"""Synthetic regression checks for source-bound, explicit approval contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from test_hwpx_pipeline import ROOT, SCRIPTS, run, synthetic_hwpx

sys.path.insert(0, str(SCRIPTS))


def approved_record(record_id: str = "edit-001") -> dict:
    return {
        "id": record_id, "approved": True, "scope": "both", "match_scope": "document", "from": "오타", "to": "정정",
        "issue_id": "issue-001", "decided_by_role": "합성 검토자", "decided_at": "2026-10-30T09:00:00+09:00",
        "evidence_refs": ["review:issue-001"], "reason": "합성 오기 정정",
    }


def specification(source: Path, records: list | None = None) -> dict:
    return {
        "schema_version": 2, "location_scheme": "structural-v2", "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "edits": records if records is not None else [approved_record()], "redactions": [],
    }


class ApprovalContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.source = self.work / "source.hwpx"
        synthetic_hwpx(self.source)

    def apply(self, spec: dict):
        approved = self.work / "approved.json"
        approved.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return run(str(SCRIPTS / "apply_approved_edits.py"), str(self.source), "--approved", str(approved),
                   "--approval-output", str(self.work / "approval.hwpx"), "--disclosure-output", str(self.work / "disclosure.hwpx"),
                   "--audit", str(self.work / "audit.json"), "--redaction-ledger", str(self.work / "ledger.json"), cwd=ROOT)

    def test_legacy_contract_requires_explicit_rereview(self) -> None:
        result = self.apply({"edits": [approved_record()], "redactions": []})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("재검토", result.stderr)
        self.assertFalse((self.work / "approval.hwpx").exists())

    def test_source_hash_must_be_valid_and_match_before_any_output(self) -> None:
        for value in (None, "short", "z" * 64, "0" * 64):
            with self.subTest(value=value):
                spec = specification(self.source)
                spec["source_sha256"] = value
                result = self.apply(spec)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.work / "approval.hwpx").exists())

    def test_each_approved_metadata_field_is_required(self) -> None:
        for field in ("issue_id", "decided_by_role", "decided_at", "evidence_refs", "reason"):
            with self.subTest(field=field):
                spec = specification(self.source)
                del spec["edits"][0][field]
                self.assertNotEqual(self.apply(spec).returncode, 0)

    def test_timestamp_and_evidence_reference_validation(self) -> None:
        from approval_contract import validate_approval_spec
        cases = [("decided_at", "2026-10-30T09:00:00"), ("decided_at", "2026-99-99T09:00:00+09:00"),
                 ("evidence_refs", []), ("evidence_refs", "review:001"), ("evidence_refs", ["원문 발언 문장"]),
                 ("evidence_refs", ["https://example.invalid/?token=secret"]), ("evidence_refs", ["source:section-0/paragraph-1"]),
                 ("evidence_refs", [" "]), ("reason", " "), ("decided_by_role", " ")]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                spec = specification(self.source)
                spec["edits"][0][field] = value
                with self.assertRaises(ValueError):
                    validate_approval_spec(spec)

    def test_unknown_scope_and_duplicate_ids_fail_closed(self) -> None:
        from approval_contract import validate_approval_spec
        for value in ("unknown", "", None):
            spec = specification(self.source)
            spec["edits"][0]["scope"] = value
            with self.subTest(scope=value), self.assertRaises(ValueError):
                validate_approval_spec(spec)
        spec = specification(self.source)
        duplicate = copy.deepcopy(spec["edits"][0])
        duplicate["scope"] = "disclosure"
        spec["redactions"] = [duplicate]
        with self.assertRaises(ValueError):
            validate_approval_spec(spec)

    def test_rejected_unreviewed_and_false_records_never_apply(self) -> None:
        for status in ("반려", "미검토"):
            spec = specification(self.source)
            spec["edits"][0]["approval_status"] = status
            with self.subTest(status=status):
                self.assertNotEqual(self.apply(spec).returncode, 0)
        spec = specification(self.source, [{"id": "unreviewed", "scope": "both", "from": "오타", "to": "금지"},
                                          {"id": "rejected", "approved": False, "scope": "both", "from": "오타", "to": "금지", "approval_status": "반려"}])
        self.assertEqual(self.apply(spec).returncode, 0)
        with zipfile.ZipFile(self.work / "approval.hwpx") as archive:
            self.assertNotIn("금지", archive.read("Contents/section0.xml").decode("utf-8"))

    def test_audit_and_ledger_link_approval_metadata_without_source_values(self) -> None:
        spec = specification(self.source)
        redaction = approved_record("mask-001") | {"scope": "disclosure", "from": "홍길동", "to": "○○", "redaction_type": "성명"}
        spec["redactions"] = [redaction]
        result = self.apply(spec)
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = json.loads((self.work / "audit.json").read_text(encoding="utf-8"))
        ledger = json.loads((self.work / "ledger.json").read_text(encoding="utf-8"))
        for row in [audit["approval_changes"][0], ledger[0]]:
            for field in ("issue_id", "decided_by_role", "decided_at", "evidence_refs", "reason"):
                self.assertEqual(row[field], redaction[field])
            self.assertNotIn("from", row)
            self.assertNotIn("홍길동", json.dumps(row, ensure_ascii=False))

    def test_pair_rejects_matching_unapproved_tampering_in_both_outputs(self) -> None:
        result = self.apply(specification(self.source))
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("approval.hwpx", "disclosure.hwpx"):
            path = self.work / name
            with zipfile.ZipFile(path) as archive:
                entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
            with zipfile.ZipFile(path, "w") as archive:
                for info, data in entries:
                    if info.filename == "Contents/section0.xml":
                        data = data.replace("표결 3명 찬성".encode(), "표결 9명 찬성".encode())
                    archive.writestr(info, data)
        pair = run(str(SCRIPTS / "verify_release_pair.py"), "--source", str(self.source),
                   "--approval", str(self.work / "approval.hwpx"), "--disclosure", str(self.work / "disclosure.hwpx"),
                   "--approved", str(self.work / "approved.json"), cwd=ROOT)
        self.assertNotEqual(pair.returncode, 0)
        self.assertIn("결재용", pair.stderr)

    def test_sample_builder_requires_matching_base_hash_and_explicit_decision_metadata(self) -> None:
        base = self.work / "base.json"
        spec = specification(self.source, [])
        spec["source_sha256"] = "0" * 64
        base.write_text(json.dumps(spec), encoding="utf-8")
        args = (str(SCRIPTS / "build_sample_sentence_mask_plan.py"), "--input", str(self.source), "--base", str(base),
                "--output", str(self.work / "sample.json"), "--location", "section-0/paragraph-3", "--reason", "합성 사유",
                "--decision", "담당자 승인", "--decided-by-role", "합성 검토자", "--decided-at", "2026-10-30T09:00:00+09:00",
                "--evidence-ref", "review:issue-001", "--issue-id", "issue-001")
        result = run(*args, cwd=ROOT)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source_sha256", result.stderr)
        self.assertFalse((self.work / "sample.json").exists())

    def test_all_output_paths_must_be_distinct_and_not_inputs(self) -> None:
        approved = self.work / "approved.json"
        approved.write_text(json.dumps(specification(self.source)), encoding="utf-8")
        originals = (self.source.read_bytes(), approved.read_bytes())
        for audit_path in (self.work / "approval.hwpx", self.work / "ledger.json", self.source, approved):
            with self.subTest(audit_path=audit_path):
                result = run(str(SCRIPTS / "apply_approved_edits.py"), str(self.source), "--approved", str(approved),
                             "--approval-output", str(self.work / "approval.hwpx"), "--disclosure-output", str(self.work / "disclosure.hwpx"),
                             "--audit", str(audit_path), "--redaction-ledger", str(self.work / "ledger.json"), cwd=ROOT)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.work / "approval.hwpx").exists())
                self.assertFalse((self.work / "disclosure.hwpx").exists())
                self.assertEqual((self.source.read_bytes(), approved.read_bytes()), originals)


if __name__ == "__main__":
    unittest.main()
