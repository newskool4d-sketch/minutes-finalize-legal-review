#!/usr/bin/env python3
"""Keep the synthetic legal-review regression fixture complete and non-sensitive."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic-review-cases.json"
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


if __name__ == "__main__":
    unittest.main()
