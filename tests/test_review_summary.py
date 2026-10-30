"""Synthetic N06 evidence summaries; no real minutes or application access."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from test_hwpx_pipeline import approval_spec, synthetic_hwpx

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def dump(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class ReviewSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = importlib.import_module("render_review_summary")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name)
        self.paths = {key: self.work / name for key, name in {
            "source": "source.hwpx", "approved": "approved.json", "approval": "approval.hwpx",
            "disclosure": "disclosure.hwpx", "legal_review": "legal.json", "human_evidence": "human.json",
        }.items()}
        synthetic_hwpx(self.paths["source"])
        self.plan = approval_spec({"edits": [], "redactions": [{
            "id": "redact-name", "approved": True, "scope": "disclosure", "from": "홍길동", "to": "○○",
            "redaction_type": "성명", "match_scope": "document",
        }]}, self.paths["source"])
        dump(self.paths["approved"], self.plan)
        self.rebuild_pair()
        self.legal = {
            "location_scheme": "structural-v2",
            "case": {"case_token": "synthetic-case", "reviewed_at": "2026-10-30", "reviewer_role": "합성 역할",
                     "source_document_hash": self.sha("source"), "event_dates": {
                         key: "2026-10-30" for key in ("event_date", "hearing_date", "disposition_date", "minutes_finalized_date")}},
            "issues": [{"issue_id": "synthetic-issue", "location": "합성 위치", "location_id": "section-0/paragraph-2",
                        "speaker_role": "합성 발언자", "statement_summary": "합성 검토", "statement_text_hash":
                        hashlib.sha256("합성 검증 사례: 기본".encode("utf-8")).hexdigest(), "source_level": "E1",
                        "legal_factor": ["F"], "legal_issue_type": ["기록무결성"], "risk_type": ["합성"],
                        "evidence_to_check": ["합성 확인자료"], "reasoning_summary": "합성 근거", "suggested_wording": "합성 유지",
                        "risk_level": "낮음", "action_code": "K", "recommended_scope": "양쪽", "confidence": "충분",
                        "approval_status": "담당자 승인", "legal_basis": [{
                            "jurisdiction": "합성", "law_name": "합성 근거", "article": "합성 조항",
                            "promulgation_date": "2026-01-01", "effective_date": "2026-01-01",
                            "applicable_event_date": "2026-10-30", "retrieved_at": "2026-10-30", "source_type": "합성",
                            "source_id": "fixture:law-001", "verification_status": "원문확인"}]}],
        }
        dump(self.paths["legal_review"], self.legal)
        self.human = self.make_human()
        dump(self.paths["human_evidence"], self.human)

    def sha(self, key: str) -> str:
        return hashlib.sha256(self.paths[key].read_bytes()).hexdigest()

    def rebuild_pair(self) -> None:
        from apply_approved_edits import build_entry_pair
        from hwpx_common import read_entry_map, write_preserving_zip
        infos, entries = read_entry_map(self.paths["source"])
        pair = build_entry_pair(entries, self.plan)
        for key in ("approval", "disclosure"):
            self.paths[key].unlink(missing_ok=True)
            write_preserving_zip(self.paths[key], infos, pair[key + "_entries"])

    def make_human(self) -> dict:
        roles = {"approval_open": "document_reviewer", "disclosure_open": "document_reviewer",
                 "legal_review": "legal_reviewer", "public_decision": "disclosure_officer", "final_confirmation": "final_owner"}
        return {"schema_version": 1, "artifact_hashes": {
            "source": self.sha("source"), "approved_plan": self.sha("approved"), "approval": self.sha("approval"),
            "disclosure": self.sha("disclosure"), "legal_review": self.sha("legal_review")},
            "checks": {key: {"result": "pass", "reviewer_role": role,
                              "checked_at": "2026-10-30T15:00:00+09:00", "evidence_refs": ["fixture:check-001"]}
                       for key, role in roles.items()}}

    def build(self, **overrides: object) -> dict:
        return self.summary.build_summary(**(self.paths | overrides))

    def cli(self, *extra: str, omit_optional: bool = False, **overrides: Path) -> subprocess.CompletedProcess[str]:
        paths = self.paths | overrides
        args = [sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "render_review_summary.py")]
        for key in ("source", "approved", "approval", "disclosure", "legal_review", "human_evidence"):
            if omit_optional and key in {"legal_review", "human_evidence"}:
                continue
            args.extend(["--" + key.replace("_", "-"), str(paths[key])])
        args.extend(["--output", str(self.work / "summary.md"), "--json", str(self.work / "summary.json"), *extra])
        return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, encoding="utf-8", check=False)

    def test_fully_bound_human_claims_can_pass_without_authorizing_release(self) -> None:
        before = {key: self.sha(key) for key in self.paths}
        result = self.build()
        self.assertEqual(result["quality_result"], "PASS", result)
        self.assertFalse(result["external_release_authorized"])
        self.assertIs(result["disclosure_package"]["release_ready"], False)
        self.assertIn("사람의 진술", self.summary.render_summary(result))
        self.assertEqual(before, {key: self.sha(key) for key in self.paths})

    def test_missing_human_or_legal_is_partial_not_execution_failure(self) -> None:
        self.assertEqual(self.build(human_evidence=None)["quality_result"], "PARTIAL")
        self.assertEqual(self.build(legal_review=None, human_evidence=None)["quality_result"], "PARTIAL")

    def test_each_of_five_artifact_substitutions_fails_current_hash_binding(self) -> None:
        for key in ("source", "approved", "approval", "disclosure", "legal_review"):
            with self.subTest(artifact=key):
                before = self.paths[key].read_bytes()
                self.paths[key].write_bytes(before + b"\n")
                self.assertEqual(self.build()["quality_result"], "FAIL")
                self.paths[key].write_bytes(before)

    def test_unverified_basis_remains_partial_after_global_completion_claim(self) -> None:
        self.legal["issues"][0]["legal_basis"][0]["verification_status"] = "시점확인필요"
        self.legal["issues"][0]["approval_status"] = "법무 확인"
        dump(self.paths["legal_review"], self.legal)
        self.human = self.make_human() | {"completed": True, "quality_result": "PASS"}
        dump(self.paths["human_evidence"], self.human)
        result = self.build()
        self.assertEqual(result["quality_result"], "PARTIAL")
        self.assertEqual(result["counts"]["unresolved_legal_issues"], 1)

    def test_pending_one_application_is_partial(self) -> None:
        self.human["checks"]["disclosure_open"] = {"result": "pending"}
        dump(self.paths["human_evidence"], self.human)
        result = self.build()
        self.assertEqual(result["quality_result"], "PARTIAL")
        markdown = self.summary.render_summary(result)
        self.assertIn("공개용 한글 열람 (`disclosure_open`) | PARTIAL | document_reviewer | OPEN_DISCLOSURE_IN_HANCOM", markdown)
        self.assertIn("결재용 한글 열람 (`approval_open`) | PASS", markdown)
        self.assertEqual(result["next_actions"], [{"owner_role": "document_reviewer", "action_code": "OPEN_DISCLOSURE_IN_HANCOM"}])

    def test_completed_only_and_missing_pass_metadata_cannot_pass(self) -> None:
        for payload in ({"schema_version": 1, "completed": True},
                        self.human | {"checks": {key: {"result": "pass", "completed": True} for key in self.human["checks"]}}):
            dump(self.paths["human_evidence"], payload)
            self.assertEqual(self.build()["quality_result"], "PARTIAL")

    def test_high_risk_and_l_need_record_level_legal_confirmation(self) -> None:
        self.legal["issues"][0].update(risk_level="높음", action_code="L")
        dump(self.paths["legal_review"], self.legal)
        dump(self.paths["human_evidence"], self.make_human())
        self.assertEqual(self.build()["quality_result"], "PARTIAL")

    def test_confidence_unknown_dates_and_unreviewed_are_independent_partial_gates(self) -> None:
        baseline = copy.deepcopy(self.legal)
        for field, value in (("confidence", "부족"), ("approval_status", "미검토"), ("event_date", "미확인")):
            self.legal = copy.deepcopy(baseline)
            target = self.legal["case"]["event_dates"] if field == "event_date" else self.legal["issues"][0]
            target[field] = value
            dump(self.paths["legal_review"], self.legal)
            dump(self.paths["human_evidence"], self.make_human())
            with self.subTest(field=field):
                self.assertEqual(self.build()["quality_result"], "PARTIAL")

    def test_explicit_legal_source_and_statement_mismatches_fail(self) -> None:
        self.legal["case"]["source_document_hash"] = "0" * 64
        dump(self.paths["legal_review"], self.legal)
        self.assertEqual(self.build(human_evidence=None)["quality_result"], "FAIL")
        self.legal["case"]["source_document_hash"] = self.sha("source")
        self.legal["issues"][0]["statement_text_hash"] = "0" * 64
        dump(self.paths["legal_review"], self.legal)
        self.assertEqual(self.build(human_evidence=None)["quality_result"], "FAIL")

    def test_unclear_location_or_hash_is_partial(self) -> None:
        for field, value in (("location_id", "legacy:unclear"), ("statement_text_hash", "미확인")):
            legal = copy.deepcopy(self.legal)
            legal["issues"][0][field] = value
            dump(self.paths["legal_review"], legal)
            dump(self.paths["human_evidence"], self.make_human())
            self.assertEqual(self.build()["quality_result"], "PARTIAL")

    def test_wrong_location_scheme_fails(self) -> None:
        self.legal["location_scheme"] = "legacy"
        dump(self.paths["legal_review"], self.legal)
        self.assertEqual(self.build(human_evidence=None)["quality_result"], "FAIL")

    def test_empty_issues_valid_case_is_partial_but_malformed_case_fails(self) -> None:
        self.legal["issues"] = []
        dump(self.paths["legal_review"], self.legal)
        dump(self.paths["human_evidence"], self.make_human())
        result = self.build()
        self.assertEqual(result["quality_result"], "PARTIAL")
        self.assertEqual(result["counts"]["legal_issues"], 0)
        del self.legal["case"]["event_dates"]
        dump(self.paths["legal_review"], self.legal)
        self.assertEqual(self.build()["quality_result"], "FAIL")

    def test_v_requires_record_correction_or_legal_confirmation(self) -> None:
        self.legal["issues"][0]["action_code"] = "V"
        for state, expected in (("담당자 승인", "PARTIAL"), ("수정 반영", "PASS"), ("법무 확인", "PASS")):
            self.legal["issues"][0]["approval_status"] = state
            dump(self.paths["legal_review"], self.legal)
            dump(self.paths["human_evidence"], self.make_human())
            self.assertEqual(self.build()["quality_result"], expected)

    def test_duplicate_entries_in_any_hwpx_fail_closed(self) -> None:
        for key in ("source", "approval", "disclosure"):
            with self.subTest(artifact=key):
                original = self.paths[key].read_bytes()
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(self.paths[key], "a") as archive:
                        header = archive.read("Contents/header.xml")
                        archive.writestr("Contents/header.xml", b"<metadata>PRIVATE-HIDDEN</metadata>")
                        archive.writestr("Contents/header.xml", header)
                result = self.build(human_evidence=None)
                self.assertEqual(result["quality_result"], "FAIL")
                self.assertEqual(result["checks"]["package_structure"]["status"], "FAIL")
                self.assertEqual(result["checks"]["technical_pair"]["status"], "FAIL")
                self.paths[key].write_bytes(original)

    def test_transcript_warning_is_fixed_for_pass_and_partial(self) -> None:
        warning = "전사 원본 대조 미실행: 전사 누락·전사 정확도 확인 불가"
        for result in (self.build(), self.build(human_evidence=None)):
            self.assertIn(warning, result["warnings"])
            self.assertIn(warning, self.summary.render_summary(result))
        self.assertEqual(self.build()["next_actions"], [{"owner_role": "final_owner", "action_code": "OBTAIN_SEPARATE_INSTITUTIONAL_RELEASE_APPROVAL"}])

    def test_opaque_resources_require_each_current_entry_coverage(self) -> None:
        with zipfile.ZipFile(self.paths["source"], "a") as archive:
            archive.writestr("BinData/private-name-one.bin", b"opaque-one")
            archive.writestr("BinData/private-name-two.bin", b"opaque-two")
        self.plan["source_sha256"] = self.sha("source")
        dump(self.paths["approved"], self.plan)
        self.rebuild_pair()
        self.legal["case"]["source_document_hash"] = self.sha("source")
        dump(self.paths["legal_review"], self.legal)
        self.human = self.make_human()
        dump(self.paths["human_evidence"], self.human)
        result = self.build()
        self.assertEqual(result["quality_result"], "PARTIAL")
        refs = result["disclosure_package"]["manual_review_refs"]
        self.assertEqual(len(refs), 2)
        self.human["checks"]["public_decision"]["coverage"] = {"manual_entry_ids": refs[:1], "finding_ids": []}
        dump(self.paths["human_evidence"], self.human)
        self.assertEqual(self.build()["quality_result"], "PARTIAL")
        self.human["checks"]["public_decision"]["coverage"]["manual_entry_ids"] = refs
        dump(self.paths["human_evidence"], self.human)
        self.assertEqual(self.build()["quality_result"], "PASS")

    def test_residual_terms_require_each_finding_coverage(self) -> None:
        with zipfile.ZipFile(self.paths["source"], "a") as archive:
            archive.writestr("META-INF/private.xml", "<metadata>홍길동</metadata>".encode("utf-8"))
        self.plan["source_sha256"] = self.sha("source")
        dump(self.paths["approved"], self.plan)
        self.rebuild_pair()
        self.legal["case"]["source_document_hash"] = self.sha("source")
        dump(self.paths["legal_review"], self.legal)
        self.human = self.make_human()
        dump(self.paths["human_evidence"], self.human)
        result = self.build()
        self.assertEqual(result["quality_result"], "PARTIAL")
        self.assertEqual(result["disclosure_package"]["residual_finding_refs"], ["finding-1"])
        self.human["checks"]["public_decision"]["coverage"] = {"manual_entry_ids": [], "finding_ids": ["finding-1"]}
        dump(self.paths["human_evidence"], self.human)
        self.assertEqual(self.build()["quality_result"], "PASS")

    def test_raw_text_names_ids_paths_and_free_reason_never_appear(self) -> None:
        forbidden = "PRIVATE-홍길동-C:\\secret\\case.hwpx"
        self.legal["issues"][0].update(issue_id=forbidden, statement_summary=forbidden, speaker_role=forbidden)
        self.legal["case"]["reviewer_role"] = forbidden
        self.plan["redactions"][0]["reason"] = forbidden
        dump(self.paths["approved"], self.plan)
        dump(self.paths["legal_review"], self.legal)
        dump(self.paths["human_evidence"], self.make_human())
        result = self.build()
        text = json.dumps(result, ensure_ascii=False) + self.summary.render_summary(result)
        for value in (forbidden, "홍길동", str(self.work), "case.hwpx", "합성 검토", "fixture:check-001"):
            self.assertNotIn(value, text)

    def test_invalid_human_role_reference_and_hash_are_rejected(self) -> None:
        for field, value in (("reviewer_role", "Someone's Name"), ("evidence_refs", ["원문 문장"])):
            payload = copy.deepcopy(self.human)
            payload["checks"]["public_decision"][field] = value
            dump(self.paths["human_evidence"], payload)
            self.assertEqual(self.build()["quality_result"], "FAIL")
        payload = copy.deepcopy(self.human)
        payload["artifact_hashes"]["legal_review"] = "f" * 64
        dump(self.paths["human_evidence"], payload)
        self.assertEqual(self.build()["quality_result"], "FAIL")

    def test_cli_existing_either_output_preserves_all_inputs_and_outputs(self) -> None:
        for filename in ("summary.md", "summary.json"):
            with self.subTest(output=filename):
                output = self.work / filename
                output.write_bytes(b"existing-output")
                result = self.cli()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output.read_bytes(), b"existing-output")
                other = self.work / ("summary.json" if filename.endswith(".md") else "summary.md")
                self.assertFalse(other.exists())
                output.unlink()

    def test_cli_refuses_input_overlap_and_duplicate_outputs(self) -> None:
        before = self.paths["source"].read_bytes()
        self.assertNotEqual(self.cli("--output", str(self.paths["source"])).returncode, 0)
        self.assertEqual(self.paths["source"].read_bytes(), before)
        self.assertNotEqual(self.cli("--output", str(self.work / "summary.json")).returncode, 0)
        self.assertFalse((self.work / "summary.json").exists())

    def test_cli_writes_sanitized_fail_for_malformed_input_and_success_for_partial(self) -> None:
        self.paths["legal_review"].write_text("PRIVATE-홍길동 malformed", encoding="utf-8")
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        text = (self.work / "summary.json").read_text(encoding="utf-8") + result.stdout + result.stderr
        self.assertEqual(json.loads((self.work / "summary.json").read_text(encoding="utf-8"))["quality_result"], "FAIL")
        for value in ("홍길동", str(self.work), "JSONDecodeError", "PRIVATE"):
            self.assertNotIn(value, text)
        (self.work / "summary.md").unlink()
        (self.work / "summary.json").unlink()
        result = self.cli(omit_optional=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "SUMMARY_PARTIAL")
        partial = json.loads((self.work / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(partial["quality_result"], "PARTIAL")
        self.assertIn("품질판정: PARTIAL", (self.work / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
