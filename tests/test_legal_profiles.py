"""Synthetic legal catalog/date tests; not real case or legal outcome evidence."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import legal_profiles as legal


def synthetic_catalog():
    profiles = []
    for pid, kind, word in (("education-rights-ko", "education_rights", "피해교원"),
                            ("school-violence-ko", "school_violence", "피해학생")):
        source_id = kind.replace("_", "-") + "-law"
        profiles.append({"id": pid, "version": "synthetic.1", "committee_type": kind, "jurisdiction": "KR",
            "sources": [{"id": source_id, "law_name": "합성 법령 시험", "kind": "synthetic", "official_url": "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=1",
                         "mst": "1", "promulgated_on": "2026-01-01", "effective_from": "2026-02-01",
                         "effective_to_exclusive": "2026-11-20", "verified_through": "2026-11-16", "articles": ["제1조"],
                         "temporal_basis": list(legal.DATE_FIELDS), "summary": "합성 자료만을 위한 검증 항목",
                         "transition_notes": "실제 법률 근거가 아닌 합성 테스트"}],
            "rules": [{"id": kind.replace("_", "-") + "-rule", "pattern": word, "issue_types": ["절차"], "risk_level": "중간",
                       "action_code": "V", "source_ids": [source_id], "factors": ["진술기회"],
                       "evidence_to_check": ["합성 의견서"], "reason": "합성 시험의 진술기회 확인"}],
            "required_checks": [{"id": kind.replace("_", "-") + "-check", "source_ids": [source_id],
                                 "evidence_to_check": ["합성 표결지"], "reason": "합성 필수 확인"}]})
    return {"schema_version": 1, "catalog_version": "synthetic.1", "checked_on": "2026-11-16", "profiles": profiles}


def context(kind="education_rights", **changes):
    return {"committee_type": kind, "jurisdiction": "KR", "incident_date": "2026-10-01",
            "deliberation_date": "2026-10-10", "disposition_date": "2026-10-11", "knowledge_date": "2026-10-02",
            "report_date": "2026-10-03", **changes}


class LegalProfilesTests(unittest.TestCase):
    def setUp(self):
        self.catalog = synthetic_catalog()
        legal.validate_catalog(self.catalog)
        self.catalog_hash = hashlib.sha256(legal.canonical_bytes(self.catalog)).hexdigest()

    def review(self, value=None, pid="education-rights-ko"):
        return legal.review_profile(self.catalog, self.catalog_hash, pid, value)

    def test_two_profiles_select_distinct_rules_for_same_text(self):
        found = []
        for pid, kind in (("education-rights-ko", "education_rights"), ("school-violence-ko", "school_violence")):
            review = self.review(context(kind), pid)
            candidates = legal.profile_candidates(legal.get_profile(self.catalog, pid), review, "피해교원과 피해학생 합성 확인")
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["legal_basis"], review["sources"])
            self.assertEqual(candidates[0]["legal_conclusion"], "not_determined")
            found.append(candidates[0]["rule_id"])
        self.assertNotEqual(found[0], found[1])

    def test_covered_dates_still_require_documentary_and_human_review(self):
        value = self.review(context())
        self.assertEqual(value["status"], "requires_human_review")
        self.assertEqual(value["blockers"], ["documentary_evidence_required", "human_legal_review_required"])
        self.assertTrue(value["requires_human_review"])
        self.assertFalse(value["external_release_authorized"])
        self.assertEqual(value["legal_conclusion"], "not_determined")
        self.assertEqual(value["checklist"][0]["status"], "awaiting_documentary_and_human_review")

    def test_missing_context_and_each_missing_date_remain_unverified(self):
        self.assertEqual(self.review()["context_sha256"], hashlib.sha256(b"null").hexdigest())
        self.assertEqual(self.review()["status"], "needs_date_verification")
        for field in legal.DATE_FIELDS:
            with self.subTest(field=field):
                value = self.review(context(**{field: None}))
                self.assertEqual(value["status"], "needs_date_verification")
                self.assertTrue(any(f":{field}:missing_date" in item for item in value["blockers"]))

    def test_effective_day_inclusive_and_following_version_exclusive(self):
        for day, expected in (("2026-01-31", "historical_version_required"), ("2026-02-01", "within_verified_version_range"),
                              ("2026-11-16", "within_verified_version_range"), ("2026-11-17", "after_verification_date"),
                              ("2026-11-20", "unverified_version")):
            with self.subTest(day=day):
                value = self.review(context(**{field: day for field in legal.DATE_FIELDS}))
                self.assertTrue(all(item["status"] == expected for item in value["sources"][0]["date_checks"]))

    def test_invalid_calendar_types_unknown_fields_and_chronology_rejected(self):
        bad = [context(incident_date="2026-02-30"), context(incident_date=True), context(incident_date="2026-2-01"),
               context(extra="ignored?"), context(incident_date="2026-10-12"), context(disposition_date="2026-09-01"),
               context(deliberation_date=None, disposition_date="2026-09-01"), {"committee_type": "education_rights"}]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(legal.LegalProfileError):
                self.review(item)

    def test_profile_and_jurisdiction_mismatch_rejected(self):
        for value, pid in ((context("school_violence"), "education-rights-ko"),
                           (context(jurisdiction="OTHER"), "education-rights-ko"), (context(), "unknown")):
            with self.subTest(pid=pid), self.assertRaises(legal.LegalProfileError):
                self.review(value, pid)

    def test_context_fingerprint_is_order_independent_and_changes_on_date(self):
        value = context()
        self.assertEqual(legal.fingerprint(value), legal.fingerprint(dict(reversed(list(value.items())))))
        self.assertNotEqual(legal.fingerprint(value), legal.fingerprint(context(report_date="2026-10-04")))

    def test_generic_is_explicitly_unconfigured_and_never_complete(self):
        value = self.review(context("generic"), "generic-committee-ko")
        self.assertEqual(value["profile_version"], "unconfigured")
        self.assertEqual(value["profile_sha256"], legal.fingerprint(legal.get_profile(self.catalog, "generic-committee-ko")))
        self.assertEqual(value["status"], "needs_date_verification")
        self.assertIn("profile_not_configured", value["blockers"])
        self.assertFalse(value["external_release_authorized"])

    def test_catalog_rejects_bad_references_duplicates_and_unknown_keys(self):
        variants = []
        bad = deepcopy(self.catalog); bad["profiles"][0]["rules"][0]["source_ids"] = ["unknown"]; variants.append(bad)
        bad = deepcopy(self.catalog); bad["profiles"][0]["required_checks"][0]["source_ids"] = ["unknown"]; variants.append(bad)
        bad = deepcopy(self.catalog); bad["profiles"][1] = deepcopy(bad["profiles"][0]); variants.append(bad)
        bad = deepcopy(self.catalog); bad["profiles"][0]["rules"] = []; variants.append(bad)
        bad = deepcopy(self.catalog); bad["profiles"][0]["sources"][0]["fake_verified"] = True; variants.append(bad)
        bad = deepcopy(self.catalog); bad["schema_version"] = True; variants.append(bad)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(legal.LegalProfileError):
                legal.validate_catalog(value)

    def test_catalog_rejects_invalid_dates_urls_and_oversized_patterns(self):
        for key, value in (("effective_from", "2026-02-30"), ("verified_through", "2027-01-01"),
                           ("effective_to_exclusive", "2026-01-01"), ("official_url", "https://law.go.kr.evil.test/a"),
                           ("official_url", "https://private:secret@www.law.go.kr/a"), ("temporal_basis", ["unknown_date"])):
            bad = deepcopy(self.catalog); bad["profiles"][0]["sources"][0][key] = value
            with self.subTest(key=key), self.assertRaises(legal.LegalProfileError):
                legal.validate_catalog(bad)
        bad = deepcopy(self.catalog); bad["profiles"][0]["rules"][0]["pattern"] = "x" * 513
        with self.assertRaises(legal.LegalProfileError):
            legal.validate_catalog(bad)

    def test_load_binds_raw_bytes_and_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "synthetic.json"
            raw = json.dumps(self.catalog, ensure_ascii=False, indent=2).encode("utf-8")
            target.write_bytes(raw)
            loaded, digest = legal.load_catalog(target)
            self.assertEqual(loaded, self.catalog)
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
            target.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaises(legal.LegalProfileError):
                legal.load_catalog(target)

    def test_legal_summary_does_not_claim_complete_or_automatic_disclosure(self):
        rendered = legal.render_profile_summary(self.review(context()))
        self.assertIn("법률적 결론: 미확정", rendered)
        self.assertIn("https://www.law.go.kr/", rendered)
        self.assertIn("2026-02-01", rendered)
        self.assertNotIn("법률 검토 완료", rendered)

    def test_checked_catalog_all_sixteen_rules_match_synthetic_examples_and_bind_sources(self):
        catalog, digest = legal.load_catalog()
        cases = {
            "education-rights-ko": {
                "edu-activity-elements": ("합성 교육활동 침해 여부를 검토한다.", ["edu-definition", "edu-notice"]),
                "edu-opportunity": ("합성 의견 진술 기회를 확인한다.", ["edu-procedure"]),
                "edu-transfer-expulsion": ("합성 전학 조치의 근거를 검토한다.", ["edu-measures", "edu-notice"]),
                "edu-guardian-measure": ("합성 보호자 조치의 요건을 확인한다.", ["edu-measures", "edu-procedure"]),
                "edu-emergency-ratification": ("합성 긴급 조치의 추인 자료를 확인한다.", ["edu-emergency"]),
                "edu-assessment-factors": ("합성 선도 가능성 판단자료를 확인한다.", ["edu-assessment", "edu-notice"]),
                "edu-quorum-conflict": ("합성 제척 사유를 검토한다.", ["edu-quorum"]),
                "edu-record-integrity": ("합성 회의록 변경 이력을 검토한다.", ["edu-records", "edu-confidentiality"]),
            },
            "school-violence-ko": {
                "sv-student-specific-facts": ("합성 맞폭 주장의 각 행위를 확인한다.", ["sv-definition"]),
                "sv-opportunity-and-records": ("합성 서면 의견자료를 확인한다.", ["sv-records-procedure"]),
                "sv-disability-expert-request": ("합성 특수교육 전문가 요청을 확인한다.", ["sv-disability-expert", "sv-notice"]),
                "sv-transfer-expulsion": ("합성 전학 조치 요청의 근거를 검토한다.", ["sv-measures", "sv-notice"]),
                "sv-assessment-factors": ("합성 화해 판단자료를 확인한다.", ["sv-assessment", "sv-notice"]),
                "sv-quorum-conflict": ("합성 기피 신청자료를 확인한다.", ["sv-quorum"]),
                "sv-separation-exception": ("합성 분리 예외 요건을 확인한다.", ["sv-separation", "sv-measures"]),
                "sv-disclosure-and-integrity": ("합성 개인별 발언 공개 범위를 검토한다.", ["sv-records-procedure", "sv-disclosure", "sv-confidentiality"]),
            },
        }
        exercised = 0
        for pid, examples in cases.items():
            profile = legal.get_profile(catalog, pid)
            self.assertEqual({rule["id"] for rule in profile["rules"]}, set(examples))
            review = legal.review_profile(catalog, digest, pid, context(legal.PROFILE_TYPES[pid]))
            for rule_id, (text, source_ids) in examples.items():
                with self.subTest(profile=pid, rule=rule_id):
                    matches = [item for item in legal.profile_candidates(profile, review, text) if item["rule_id"] == rule_id]
                    self.assertEqual(len(matches), 1)
                    candidate = matches[0]
                    self.assertEqual([source["id"] for source in candidate["legal_basis"]], source_ids)
                    self.assertTrue(all(source["articles"] and source["official_url"].startswith("https://www.law.go.kr/") for source in candidate["legal_basis"]))
                    self.assertTrue(candidate["evidence_to_check"])
                    self.assertEqual(candidate["legal_basis_status"], "requires_human_review")
                    self.assertEqual(candidate["legal_conclusion"], "not_determined")
                    exercised += 1
        self.assertEqual(exercised, 16)

    def test_checked_catalog_official_versions_and_distinct_transitional_date_bases(self):
        catalog, digest = legal.load_catalog()
        education = legal.get_profile(catalog, "education-rights-ko")
        school = legal.get_profile(catalog, "school-violence-ko")
        edu = {source["id"]: source for source in education["sources"]}
        sv = {source["id"]: source for source in school["sources"]}
        self.assertEqual(catalog["checked_on"], "2026-11-16")
        self.assertEqual(edu["edu-emergency"]["mst"], "283357")
        self.assertEqual(edu["edu-emergency"]["effective_from"], "2026-02-19")
        self.assertEqual(edu["edu-emergency"]["effective_to_exclusive"], "2026-11-20")
        self.assertIn("부칙 제21350호 제2조", edu["edu-emergency"]["articles"])
        self.assertEqual(edu["edu-emergency"]["temporal_basis"], ["knowledge_date", "disposition_date"])
        self.assertIn("학교장 인지일", edu["edu-emergency"]["transition_notes"])
        self.assertEqual(sv["sv-disability-expert"]["mst"], "286361")
        self.assertEqual(sv["sv-disability-expert"]["effective_from"], "2026-06-02")
        self.assertEqual(sv["sv-disability-expert"]["temporal_basis"], ["deliberation_date"])
        self.assertIn("부칙 제21723호 제2조", sv["sv-disability-expert"]["articles"])
        self.assertEqual(sv["sv-measures"]["temporal_basis"], ["incident_date", "report_date", "disposition_date"])
        self.assertIn("제19741호", sv["sv-measures"]["transition_notes"])
        self.assertIn("2024-03-01", sv["sv-measures"]["transition_notes"])
        self.assertEqual(sv["sv-separation"]["temporal_basis"], ["knowledge_date"])
        self.assertIn("2025-05-22", sv["sv-separation"]["transition_notes"])
        self.assertIn("stale_internal_cross_reference", sv["sv-notice"]["transition_notes"])
        self.assertIn("제17조제13항", sv["sv-notice"]["transition_notes"])
        self.assertIn("의무", sv["sv-notice"]["transition_notes"])
        for pid, field, day, sid in (("education-rights-ko", "knowledge_date", "2026-02-18", "edu-emergency"),
                                     ("school-violence-ko", "report_date", "2026-06-01", "sv-measures")):
            with self.subTest(profile=pid, field=field):
                value = legal.review_profile(catalog, digest, pid, context(legal.PROFILE_TYPES[pid], incident_date=day, **{field: day}))
                self.assertEqual(value["status"], "needs_date_verification")
                self.assertIn(f"{sid}:{field}:historical_version_required", value["blockers"])
                self.assertEqual(value["legal_conclusion"], "not_determined")


if __name__ == "__main__":
    unittest.main()
