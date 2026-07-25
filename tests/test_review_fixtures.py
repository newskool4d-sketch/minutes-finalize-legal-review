#!/usr/bin/env python3
"""Keep the synthetic legal-review regression fixture complete and non-sensitive."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic-review-cases.json"
ROOT = FIXTURE.parents[2]
RENDER = ROOT / "scripts" / "render_legal_review_report.py"
METRICS = ROOT / "scripts" / "validate_operation_metrics.py"
REQUIRED_TYPES = {"절차", "사실인정", "재량판단", "편견·예단", "개인정보", "기록무결성", "법적 근거"}


class ReviewFixtureTests(unittest.TestCase):
    def test_fixture_has_ten_unique_high_value_cases(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cases = payload["cases"]
        self.assertEqual(len(cases), 10)
        self.assertEqual(len({case["id"] for case in cases}), 10)
        observed = set()
        for case in cases:
            self.assertTrue(case["minutes"])
            self.assertTrue(case["scenario"])
            expected = case["expected"]
            self.assertIn(expected["action_code"], {"D", "L", "V"})
            self.assertIn(expected["risk_level"], {"높음", "중간", "낮음"})
            observed.update(expected["legal_issue_type"])
        self.assertTrue(REQUIRED_TYPES.issubset(observed))

    def test_high_risk_review_requires_evidence_and_renders_without_case_text(self) -> None:
        payload = {
            "case": {"case_token": "synthetic-001", "reviewed_at": "2026-07-25", "reviewer_role": "담당 장학사", "source_document_hash": "a" * 64},
            "issues": [{
                "issue_id": "issue-001", "location": "section-1/paragraph-2", "location_id": "section-1/paragraph-2",
                "speaker_role": "위원", "statement_summary": "공식 자료 없는 민감정보 추정 발언", "statement_text_hash": "b" * 64,
                "source_level": "E5", "legal_factor": ["F"], "legal_issue_type": ["개인정보", "사실인정"],
                "risk_type": ["민감정보", "추측"], "risk_level": "높음", "action_code": "L",
                "suggested_wording": "사실확정 없이 기록하지 않고 출처를 확인함.", "evidence_to_check": ["회의자료"],
                "counterevidence": ["의료 서면 미확인"], "reasoning_summary": "추정만으로 민감정보를 심의 근거로 쓰면 사실인정과 개인정보 쟁점이 생김.",
                "legal_basis": [{"law_name": "합성 법령", "article": "제1조", "effective_date": "2025-01-01", "applicable_event_date": "2026-01-01", "retrieved_at": "2026-07-25", "source_type": "법령", "source_id": "https://example.invalid/law", "verification_status": "법무확인필요"}],
                "recommended_scope": "결재용", "confidence": "부족", "approval_status": "법무 확인",
            }],
        }
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            source = work / "review.json"
            output = work / "report.md"
            source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([sys.executable, str(RENDER), str(source), "--output", str(output)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = output.read_text(encoding="utf-8")
            self.assertIn("issue-001", report)
            self.assertIn("법무 확인", report)

            payload["issues"][0]["legal_basis"] = []
            source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            rejected = subprocess.run([sys.executable, str(RENDER), str(source), "--output", str(work / "reject.md")], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertNotEqual(rejected.returncode, 0)

    def test_operation_metrics_accepts_only_deidentified_reason_codes(self) -> None:
        metrics = {
            "case_token": "synthetic-002", "pages": 12, "review_minutes_before": 100, "review_minutes_after": 50,
            "officer_review_minutes": 20, "supervisor_review_minutes": 30, "ai_suggestions": 3,
            "approved_suggestions": 2, "rejected_suggestions": 1, "rejection_reason_codes": ["근거부족"],
            "high_risk_items": 1, "legal_confirmation_items": 1, "human_found_omissions": 0,
            "metadata_or_vote_errors": 0, "hwpx_structure_pass": True, "hancom_open_pass": True,
        }
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "metrics.json"
            source.write_text(json.dumps(metrics, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([sys.executable, str(METRICS), str(source)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics["rejection_reason_codes"] = ["실제 회의 발언"]
            source.write_text(json.dumps(metrics, ensure_ascii=False), encoding="utf-8")
            rejected = subprocess.run([sys.executable, str(METRICS), str(source)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertNotEqual(rejected.returncode, 0)


if __name__ == "__main__":
    unittest.main()
