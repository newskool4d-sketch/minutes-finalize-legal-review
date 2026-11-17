"""Local M1 protocol/bundle tests using fictional, generated HWPX inputs only."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
import zipfile
from unittest.mock import patch

from test_hwpx_pipeline import synthetic_hwpx, approval_spec

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import minutes_engine as engine
from build_engine_bundle import build_bundle
from test_legal_profiles import context, synthetic_catalog
from legal_profiles import canonical_bytes, fingerprint, get_profile, load_catalog


class MinutesEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="회의록 M1 시험 ")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.source = self.work / "source.hwpx"
        synthetic_hwpx(self.source, "  진단 없이 추정한 합성 사례  ")
        self.original = self.source.read_bytes()
        self.digest = hashlib.sha256(self.original).hexdigest()
        self.plan = approval_spec({"edits": [], "redactions": [{"id": "mask-name", "approved": True,
            "scope": "disclosure", "from": "홍길동", "to": "위원 A", "redaction_type": "성명"}]}, self.source)
        (self.work / "approved.json").write_bytes(engine.json_bytes(self.plan))

    def request(self, operation="inspect", **changes):
        req = {"protocol_version": 1, "request_id": str(uuid.uuid4()), "operation": operation}
        if operation != "capabilities":
            req.update(workspace=str(self.work), source="source.hwpx", source_sha256=self.digest,
                       profile_id="education-rights-ko")
        if operation == "build_pair":
            req.update(approved="approved.json", output_dir="runs/first")
        return req | changes

    def cli(self, request, *, executable=ROOT / "scripts" / "minutes_engine.py"):
        data = request if isinstance(request, bytes) else engine.json_bytes(request)
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(executable)], input=data,
                                capture_output=True, cwd=self.work, timeout=30)
        self.assertEqual(result.stderr, b"")
        return result, json.loads(result.stdout)

    def test_capabilities_and_reserved_profiles_are_not_legal_validation(self):
        result, value = self.cli(self.request("capabilities"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(value["result"]["operations"], ["capabilities", "inspect", "build_pair"])
        self.assertEqual(len(value["result"]["profiles"]), 3)
        self.assertEqual([p["legal_profile_status"] for p in value["result"]["profiles"]],
                         ["rules_implemented", "rules_implemented", "not_validated"])
        self.assertTrue(all("profile_sha256" in p for p in value["result"]["profiles"]))

    def test_inspect_preserves_exact_text_hash_and_source_bytes(self):
        result, value = self.cli(self.request())
        self.assertEqual(result.returncode, 0, value)
        data = value["result"]
        self.assertEqual(data["source_sha256"], self.digest)
        self.assertEqual(data["legal_review"]["status"], "needs_date_verification")
        self.assertEqual(data["legal_review"]["context_sha256"], hashlib.sha256(b"null").hexdigest())
        self.assertTrue(data["candidates"])
        for paragraph in data["paragraphs"]:
            self.assertEqual(paragraph["statement_text_hash"], hashlib.sha256(paragraph["text"].encode()).hexdigest())
        self.assertIn("  진단 없이 추정한 합성 사례  ", data["paragraphs"][1]["text"])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_build_pair_outputs_are_bound_partial_and_distinct(self):
        result, value = self.cli(self.request("build_pair"))
        self.assertEqual(result.returncode, 0, value)
        data = value["result"]
        self.assertEqual(data["summary"]["quality_result"], "PARTIAL")
        self.assertEqual(data["summary"]["checks"]["technical_pair"]["status"], "PASS")
        self.assertFalse(data["external_release_authorized"])
        self.assertEqual(len(data["outputs"]), 6)
        for item in data["outputs"]:
            path = self.work / item["relative_path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])
        marker = json.loads((self.work / "runs/first/COMPLETE.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["outputs"], data["outputs"])
        self.assertEqual(marker["legal_review"], data["legal_review"])
        self.assertEqual(data["summary"]["legal_profile_review"], data["legal_review"])
        for name, expected in (("approval.hwpx", "홍길동"), ("disclosure.hwpx", "위원 A")):
            with zipfile.ZipFile(self.work / "runs/first" / name) as archive:
                self.assertIn(expected, archive.read("Contents/section0.xml").decode())
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(list(self.work.glob(".minutes-stage-*")), [])

    def test_existing_output_and_wrong_source_are_rejected_without_overwrite(self):
        self.cli(self.request("build_pair"))
        original = (self.work / "runs/first/COMPLETE.json").read_bytes()
        _, value = self.cli(self.request("build_pair"))
        self.assertEqual(value["error"]["code"], "OUTPUT_EXISTS")
        self.assertEqual((self.work / "runs/first/COMPLETE.json").read_bytes(), original)
        _, value = self.cli(self.request(source_sha256="0" * 64))
        self.assertEqual(value["error"]["code"], "SOURCE_CHANGED")

    def test_approval_is_never_inferred_or_manufactured(self):
        self.plan["redactions"][0].pop("decided_at")
        (self.work / "approved.json").write_bytes(engine.json_bytes(self.plan))
        _, value = self.cli(self.request("build_pair"))
        self.assertEqual(value["status"], "error")
        self.assertFalse((self.work / "runs/first").exists())

    def test_bad_paths_are_rejected_without_input_text_in_errors(self):
        for path in ("../secret.hwpx", "C:/private.hwpx", "\\server\\share", "x:stream", "NUL", "source.hwpx.", "./source.hwpx"):
            with self.subTest(path=path):
                result, value = self.cli(self.request(source=path))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(value["error"]["code"], "UNSAFE_PATH")
                self.assertNotIn(path, result.stdout.decode())
                self.assertNotIn("홍길동", result.stdout.decode())

    def test_protocol_unknown_fields_duplicate_keys_and_profile_are_rejected(self):
        for req in (self.request(protocol_version=True), self.request(extra="private"),
                    self.request(profile_id="wrong"), self.request(request_id="private-name")):
            _, value = self.cli(req)
            self.assertEqual(value["status"], "error")
            self.assertNotIn("private-name", json.dumps(value))
        _, value = self.cli(b'{"protocol_version":1,"protocol_version":1}')
        self.assertEqual(value["error"]["code"], "INVALID_JSON")

    def test_resource_limits_and_doctype_are_rejected(self):
        with patch.dict(engine.LIMITS, {"source_bytes": 8}):
            self.assertEqual(engine.handle(self.request())["error"]["code"], "RESOURCE_LIMIT")
        with patch.dict(engine.LIMITS, {"zip_entries": 1}):
            self.assertEqual(engine.handle(self.request())["error"]["code"], "RESOURCE_LIMIT")
        with zipfile.ZipFile(self.source, "a") as archive:
            archive.writestr("Contents/unsafe.xml", b'<!DOCTYPE a [<!ENTITY b "private">]><a/>')
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.assertEqual(engine.handle(self.request())["error"]["code"], "UNSUPPORTED_PACKAGE")

    def test_inspection_reads_original_once_and_hashes_that_snapshot(self):
        original_read = engine.limited_read
        reads = []
        def counted(path, maximum):
            reads.append(path)
            return original_read(path, maximum)
        with patch.object(engine, "limited_read", side_effect=counted):
            result = engine.handle(self.request())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(reads, [self.source.resolve()])

    def test_changed_original_during_build_cannot_be_published(self):
        original_summary = engine.build_summary
        def mutate_after_capture(*args, **kwargs):
            result = original_summary(*args, **kwargs)
            self.source.write_bytes(self.original + b"changed by synthetic concurrent writer")
            return result
        with patch.object(engine, "build_summary", side_effect=mutate_after_capture):
            result = engine.handle(self.request("build_pair"))
        self.assertEqual(result["error"]["code"], "INPUT_CHANGED")
        self.assertFalse((self.work / "runs/first").exists())
        self.assertEqual(list(self.work.glob(".minutes-stage-*")), [])

    def test_output_traversal_and_unknown_operations_are_not_executed(self):
        for relative in ("../outside", "/outside", "source.hwpx", "runs/../outside"):
            result = engine.handle(self.request("build_pair", output_dir=relative))
            self.assertEqual(result["status"], "error")
            self.assertEqual(self.source.read_bytes(), self.original)
        result = engine.handle(self.request(operation="run_shell"))
        self.assertEqual(result["error"]["code"], "UNSUPPORTED_OPERATION")

    def test_partial_publish_has_no_complete_marker_and_preserves_source(self):
        original_write = engine.write_new
        def fail_on_summary(path, contents):
            if path == self.work / "runs/first/summary.md":
                raise OSError("fictional path must not leak")
            return original_write(path, contents)
        with patch.object(engine, "write_new", side_effect=fail_on_summary):
            value = engine.handle(self.request("build_pair"))
        self.assertEqual(value["status"], "error")
        self.assertFalse((self.work / "runs/first/COMPLETE.json").exists())
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertNotIn("fictional path", json.dumps(value))

    def test_symlink_is_rejected_before_read(self):
        link = self.work / "linked.hwpx"
        try:
            link.symlink_to(self.source)
        except OSError:
            # Windows CI may forbid creating symlinks; exercise the same stat flag
            # boundary without calling the test skipped or accepting the path.
            real_stat = Path.lstat
            class Reparse:
                st_mode = 0o100644
                st_file_attributes = 0x400
            def mocked(path):
                return Reparse() if path == self.source else real_stat(path)
            with patch.object(Path, "lstat", mocked):
                self.assertEqual(engine.handle(self.request())["error"]["code"], "UNSAFE_PATH")
        else:
            self.assertEqual(engine.handle(self.request(source="linked.hwpx"))["error"]["code"], "UNSAFE_PATH")

    def test_bundle_is_explicit_fingerprinted_and_runs_without_source_checkout(self):
        destination = self.work / "bundle"
        value = build_bundle(destination, "a" * 40)
        manifest_bytes = (destination / "bundle-manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(value["manifest_sha256"], hashlib.sha256(manifest_bytes).hexdigest())
        self.assertEqual(manifest["source_state"], "working_tree")
        for item in manifest["files"]:
            self.assertEqual(hashlib.sha256((destination / item["path"]).read_bytes()).hexdigest(), item["sha256"])
        self.assertFalse((destination / "tests").exists())
        result, response = self.cli(self.request(), executable=destination / manifest["entrypoint"])
        self.assertEqual(result.returncode, 0, response)
        with self.assertRaises(ValueError):
            build_bundle(destination, "a" * 40)

    def test_both_profiles_build_pair_with_bound_dates_and_unresolved_human_checks(self):
        for pid, kind in (("education-rights-ko", "education_rights"), ("school-violence-ko", "school_violence")):
            with self.subTest(profile_id=pid):
                req = self.request("build_pair", profile_id=pid, legal_context=context(kind), output_dir="runs/" + kind)
                result, value = self.cli(req)
                self.assertEqual(result.returncode, 0, value)
                data = value["result"]
                review = data["legal_review"]
                self.assertEqual(data["legal_profile_status"], "rules_implemented")
                self.assertEqual(review["context_sha256"], fingerprint(context(kind)))
                self.assertEqual(review["status"], "requires_human_review")
                self.assertTrue(review["checklist"])
                self.assertTrue(all(item["status"] == "awaiting_documentary_and_human_review" for item in review["checklist"]))
                self.assertEqual(data["summary"]["quality_result"], "PARTIAL")
                marker = json.loads((self.work / req["output_dir"] / "COMPLETE.json").read_text(encoding="utf-8"))
                self.assertEqual(marker["legal_review"], review)
                self.assertEqual(self.source.read_bytes(), self.original)

    def test_real_catalog_profiles_have_distinct_rules_and_exact_official_references(self):
        synthetic_hwpx(self.source, "피해교원 교육활동 침해 선도 가능성 관계 회복 진술 제척 기피 회피 전학 퇴학 학교폭력 피해학생 가해학생 보복 합의 표결")
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        found = []
        catalog, catalog_hash = load_catalog()
        for pid, kind in (("education-rights-ko", "education_rights"), ("school-violence-ko", "school_violence")):
            with self.subTest(profile_id=pid):
                result, value = self.cli(self.request(profile_id=pid, legal_context=context(kind)))
                self.assertEqual(result.returncode, 0, value)
                data = value["result"]
                profile = get_profile(catalog, pid)
                self.assertEqual(data["legal_review"]["catalog_sha256"], catalog_hash)
                self.assertEqual(data["legal_review"]["profile_sha256"], fingerprint(profile))
                ids = {item["id"] for item in profile["rules"]}
                candidates = [item for item in data["candidates"] if item["rule_id"] in ids]
                self.assertTrue(candidates)
                for candidate in candidates:
                    rule = next(item for item in profile["rules"] if item["id"] == candidate["rule_id"])
                    expected = [item for sid in rule["source_ids"] for item in data["legal_review"]["sources"] if item["id"] == sid]
                    self.assertEqual(candidate["legal_basis"], expected)
                    self.assertEqual(candidate["legal_conclusion"], "not_determined")
                found.append({item["rule_id"] for item in candidates})
        self.assertTrue(found[0].isdisjoint(found[1]))

    def test_bad_context_is_rejected_before_build_output_and_never_echoed(self):
        for value in (context("school_violence"), context(incident_date="2026-02-30"), context(secret="private-value"),
                      context(incident_date="2026-10-15")):
            with self.subTest(context=value):
                result, response = self.cli(self.request("build_pair", legal_context=value))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(response["status"], "error")
                self.assertNotIn("private-value", result.stdout.decode())
                self.assertFalse((self.work / "runs/first").exists())

    def test_missing_catalog_reference_fails_closed(self):
        catalog = synthetic_catalog()
        catalog["profiles"][0]["rules"][0]["source_ids"] = ["missing"]
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "catalog.json"
            target.write_bytes(canonical_bytes(catalog))
            with patch.object(engine, "load_catalog", side_effect=lambda: load_catalog(target)):
                value = engine.handle(self.request())
            self.assertEqual(value["status"], "error")
            self.assertEqual(value["error"]["code"], "LEGAL_CATALOG_INVALID")


if __name__ == "__main__":
    unittest.main()
