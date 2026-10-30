#!/usr/bin/env python3
"""Keep synthetic draft classifications independent of paragraph numbers."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts" / "prepare_legal_review_template.py"
GENERATOR = ROOT / "scripts" / "generate_draft_legal_review.py"


class DraftLocationTests(unittest.TestCase):
    def test_candidate_rules_survive_reused_locations_in_different_documents(self) -> None:
        rules = {
            "sensitive-health": ("높음", "L"),
            "bias-or-reputation": ("중간", "N"),
            "procedure-opportunity": ("낮음", "K"),
            "assessment-reason": ("중간", "V"),
            "unverified-statement": ("중간", "V"),
        }
        locations = [
            "section-0/paragraph-1",
            "section-0/paragraph-1109",
            "section-0/paragraph-1137",
            "section-0/paragraph-1155",
            "section-0/paragraph-1174",
            "section-0/paragraph-1181",
            "section-0/paragraph-1059",
        ]
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for document_number, document_hash in enumerate(("a" * 64, "b" * 64), start=1):
                candidates = [
                    {
                        "location_id": location,
                        "statement_text_hash": f"{index:064x}",
                        "rule_id": rule,
                        "legal_issue_type": ["후보"],
                        "risk_level": risk,
                        "action_code": action,
                    }
                    for index, (rule, location, risk, action) in enumerate(
                        (
                            (rule, location, risk, action)
                            for rule, (risk, action) in rules.items()
                            for location in locations
                        ),
                        start=1,
                    )
                ]
                source = work / f"candidates-{document_number}.json"
                template = work / f"template-{document_number}.json"
                draft = work / f"draft-{document_number}.json"
                source.write_text(
                    json.dumps({"location_scheme": "structural-v2", "source_document_hash": document_hash, "candidates": candidates}, ensure_ascii=False),
                    encoding="utf-8",
                )
                for command in (
                    [str(TEMPLATE), str(source), "--case-token", f"synthetic-{document_number}", "--output", str(template)],
                    [str(GENERATOR), str(template), "--output", str(draft), "--reference-date", "2026-07-25"],
                ):
                    result = subprocess.run(
                        [sys.executable, "-B", "-X", "utf8", *command],
                        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)

                payload = json.loads(draft.read_text(encoding="utf-8"))
                self.assertEqual(payload["case"]["source_document_hash"], document_hash)
                self.assertEqual(len(payload["issues"]), len(candidates))
                controls = {}
                for issue in payload["issues"]:
                    rule = issue["candidate_rule"]
                    with self.subTest(document=document_number, rule=rule, location=issue["location_id"]):
                        self.assertEqual((issue["risk_level"], issue["action_code"]), rules[rule])
                        self.assertEqual(issue["approval_status"], "미검토")
                        self.assertEqual(issue["confidence"], "부족")
                        self.assertEqual(issue["source_level"], "E5")
                        self.assertTrue(
                            {"statement_text", "source_text", "original_text", "speaker_name"}.isdisjoint(issue)
                        )
                        classification = {
                            key: value for key, value in issue.items()
                            if key not in {"issue_id", "location", "location_id", "statement_text_hash"}
                        }
                        if rule in controls:
                            self.assertEqual(classification, controls[rule])
                        else:
                            controls[rule] = classification


if __name__ == "__main__":
    unittest.main()
