"""Synthetic disclosure coverage beyond the editable body XML."""

import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from test_hwpx_pipeline import ROOT, SCRIPTS, approval_spec, run, synthetic_hwpx


class DisclosurePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def source(self, extra=None):
        base = self.work / "base.hwpx"
        synthetic_hwpx(base)
        with zipfile.ZipFile(base) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        entries.update(extra or {})
        path = self.work / "source.hwpx"
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data, compress_type=zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED)
        return path

    def apply(self, source):
        spec = approval_spec({"edits": [], "redactions": [{
            "id": "name", "approved": True, "scope": "disclosure", "match_scope": "document",
            "from": "홍길동", "to": "○○", "redaction_type": "성명", "min_matches": 2, "max_matches": 2,
        }]}, source)
        plan = self.work / "approved.json"
        plan.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        result = run(str(SCRIPTS / "apply_approved_edits.py"), str(source), "--approved", str(plan),
                     "--approval-output", str(self.work / "approval.hwpx"), "--disclosure-output", str(self.work / "disclosure.hwpx"),
                     "--audit", str(self.work / "audit.json"), "--redaction-ledger", str(self.work / "ledger.json"), cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        return plan

    def scan(self, source):
        terms, output = self.work / "terms.json", self.work / "scan.json"
        terms.write_text(json.dumps(["홍길동"], ensure_ascii=False), encoding="utf-8")
        result = run(str(SCRIPTS / "scan_sensitive_content.py"), str(source), "--terms", str(terms), "--output", str(output), cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = output.read_text(encoding="utf-8")
        self.assertNotIn("홍길동", text)
        return json.loads(text)

    def test_preview_is_neutralized_without_changing_approval_or_source(self):
        secret = "홍길동".encode()
        source = self.source({"Preview/PrvText.txt": secret, "Preview/PrvImage.png": b"synthetic-old-thumbnail:" + secret})
        before = source.read_bytes()
        self.apply(source)
        self.assertEqual(source.read_bytes(), before)
        with zipfile.ZipFile(self.work / "approval.hwpx") as archive:
            self.assertEqual(archive.read("Preview/PrvText.txt"), secret)
            self.assertIn(secret, archive.read("Preview/PrvImage.png"))
        with zipfile.ZipFile(self.work / "disclosure.hwpx") as archive:
            self.assertNotIn(secret, archive.read("Preview/PrvText.txt"))
            png = archive.read("Preview/PrvImage.png")
            self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(struct.unpack(">II", png[16:24]), (1, 1))
            self.assertNotIn(secret, png)

    def test_scanner_finds_header_attributes_comments_hpf_and_preview(self):
        source = self.source({
            "Contents/header.xml": '<hh:head xmlns:hh="urn:test" author="홍길동"><!--홍길동--></hh:head>'.encode(),
            "Contents/content.hpf": '<package><metadata>홍길동</metadata></package>'.encode(),
            "Preview/PrvText.txt": "홍길동".encode(),
        })
        report = self.scan(source)
        entries = {item["entry"] for item in report["findings"]}
        self.assertTrue({"Contents/header.xml", "Contents/content.hpf", "Preview/PrvText.txt"}.issubset(entries))
        self.assertFalse(report["release_ready"])

    def test_binary_and_unreadable_text_require_manual_review(self):
        source = self.source({"BinData/picture.png": b"synthetic-picture", "Attachments/note.txt": b"\xff\xff\xfe"})
        report = self.scan(source)
        manual = {item["entry"] for item in report["coverage"]["manual_review_entries"]}
        self.assertTrue({"BinData/picture.png", "Attachments/note.txt"}.issubset(manual))
        self.assertFalse(report["configured_terms_check_pass"])
        self.assertFalse(report["release_ready"])

    def test_unchecked_objects_are_not_mistaken_for_ready_after_pair_success(self):
        source = self.source({"BinData/attachment.bin": b"synthetic-opaque"})
        plan = self.apply(source)
        result = run(str(SCRIPTS / "verify_release_pair.py"), "--source", str(source), "--approval", str(self.work / "approval.hwpx"),
                     "--disclosure", str(self.work / "disclosure.hwpx"), "--approved", str(plan), "--json", str(self.work / "pair.json"), cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((self.work / "pair.json").read_text(encoding="utf-8"))
        self.assertTrue(data["technical_pair_valid"])
        self.assertFalse(data["disclosure_package"]["release_ready"])
        self.assertTrue(data["disclosure_package"]["coverage"]["manual_review_entries"])

    def test_retained_metadata_is_flagged_and_never_silently_rewritten(self):
        header = '<hh:head xmlns:hh="urn:test" author="홍길동"/>'.encode()
        source = self.source({"Contents/header.xml": header})
        self.apply(source)
        with zipfile.ZipFile(self.work / "disclosure.hwpx") as archive:
            self.assertEqual(archive.read("Contents/header.xml"), header)
        audit = json.loads((self.work / "audit.json").read_text(encoding="utf-8"))
        self.assertFalse(audit["disclosure_package"]["configured_terms_check_pass"])
        self.assertTrue(audit["disclosure_package"]["findings"])

    def test_pair_refuses_original_preview_put_back_in_disclosure(self):
        source = self.source({"Preview/PrvText.txt": "홍길동".encode()})
        plan = self.apply(source)
        with zipfile.ZipFile(self.work / "disclosure.hwpx") as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        entries["Preview/PrvText.txt"] = "홍길동".encode()
        tampered = self.work / "tampered.hwpx"
        with zipfile.ZipFile(tampered, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data, compress_type=zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED)
        result = run(str(SCRIPTS / "verify_release_pair.py"), "--source", str(source), "--approval", str(self.work / "approval.hwpx"),
                     "--disclosure", str(tampered), "--approved", str(plan), cwd=ROOT)
        self.assertNotEqual(result.returncode, 0)

    def test_no_terms_or_hidden_filename_never_claim_full_privacy_clearance(self):
        import sys
        sys.path.insert(0, str(SCRIPTS))
        from disclosure_package import inspect_disclosure_package
        report = inspect_disclosure_package({"BinData/홍길동.bin": b"opaque"}, ["홍길동"])
        self.assertNotIn("홍길동", json.dumps(report, ensure_ascii=False))
        self.assertFalse(report["release_ready"])
        empty = inspect_disclosure_package({}, [])
        self.assertFalse(empty["configured_terms_check_pass"])
        self.assertFalse(empty["release_ready"])

    def test_comments_and_processing_instructions_outside_root_are_scanned(self):
        import sys
        sys.path.insert(0, str(SCRIPTS))
        from disclosure_package import inspect_disclosure_package
        for data in (b"<!--SYNTH--><root/>", b"<root/><!--SYNTH-->",
                     b"<?SYNTH data?><root/>", b"<root/><?note SYNTH?>"):
            with self.subTest(data=data):
                report = inspect_disclosure_package({"Contents/header.xml": data}, ["SYNTH"])
                self.assertTrue(report["findings"])
                self.assertFalse(report["configured_terms_check_pass"])

    def test_case_variant_mimetype_is_not_a_trusted_package_marker(self):
        import sys
        sys.path.insert(0, str(SCRIPTS))
        from disclosure_package import inspect_disclosure_package
        report = inspect_disclosure_package({"mimetype": b"application/hwp+zip", "MIMETYPE": b"SYNTH"}, ["SYNTH"])
        self.assertFalse(report["configured_terms_check_pass"])
        self.assertTrue(report["coverage"]["manual_review_entries"])

    def test_preview_reused_as_a_body_resource_is_not_blanketed(self):
        import sys
        sys.path.insert(0, str(SCRIPTS))
        from disclosure_package import neutralize_disclosure_previews
        entries = {
            "Preview/PrvImage.png": b"synthetic-body-image-too",
            "Contents/content.hpf": b'<package><item id="body-image" href="../Preview/PrvImage.png"/></package>',
            "Contents/section0.xml": b'<section><pic binaryItemIDRef="body-image"/></section>',
        }
        before = dict(entries)
        with self.assertRaises(ValueError):
            neutralize_disclosure_previews(entries)
        self.assertEqual(entries, before)


if __name__ == "__main__":
    unittest.main()
