"""Exercise installation only in disposable Korean/space paths (no user skills)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = "minutes-hwpx-finalize-legal-review"
PWSH = (shutil.which("pwsh.exe") or shutil.which("pwsh")) if os.name == "nt" else None
STRICT_WINDOWS = os.environ.get("MINUTES_STRICT_WINDOWS_TESTS") == "1"
if STRICT_WINDOWS and (os.name != "nt" or not PWSH or not shutil.which("powershell.exe")):
    raise RuntimeError("Windows strict gate requires Windows, pwsh.exe and powershell.exe; skipping is forbidden")


def tree_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()} if root.exists() else {}


@unittest.skipUnless(PWSH, "Windows pwsh.exe unavailable: isolated installation tests not run")
class InstallationTests(unittest.TestCase):
    def skipTest(self, reason: str) -> None:
        if STRICT_WINDOWS:
            self.fail("Windows strict gate forbids skipped installation tests: " + reason)
        super().skipTest(reason)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="회의록 설치 시험 ")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.source = self.work / "한글 소스 정본"
        shutil.copytree(ROOT, self.source, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        self.dest = self.work / "코덱스 사용자" / "skills with spaces"
        self.installed = self.dest / SKILL

    def run_ps(self, script: str, *args: str, ok: bool = True,
               source: Path | None = None, phase: str | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("MINUTES_INSTALL_TEST_FAIL_PHASE", None)
        if phase:
            env["MINUTES_INSTALL_TEST_FAIL_PHASE"] = phase
        result = subprocess.run([str(PWSH), "-NoProfile", "-NonInteractive", "-File",
                                 str((source or self.source) / "scripts" / script), *args],
                                cwd=self.work, env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=90)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def install(self, *args: str, **kwargs) -> subprocess.CompletedProcess[str]:
        return self.run_ps("install.ps1", "-DestinationRoot", str(self.dest), *args, **kwargs)

    def verify(self, *, ok: bool = True, from_install: bool = False) -> dict:
        result = self.run_ps("verify_install.ps1", "-DestinationRoot", str(self.dest),
                             "-SourceRoot", str(self.source), ok=ok,
                             source=self.installed if from_install else None)
        return json.loads(result.stdout)

    def test_preview_is_read_only_and_lists_files(self) -> None:
        before = tree_hashes(self.work)
        result = self.install()
        self.assertEqual(tree_hashes(self.work), before)
        self.assertIn("scripts/install.ps1", result.stdout.replace("\\", "/"))
        self.assertFalse(self.dest.exists())

    def test_new_and_reinstall_codex_claude_exclude_caches_and_keep_backup(self) -> None:
        (self.source / "scripts" / "__pycache__").mkdir()
        (self.source / "scripts" / "__pycache__" / "secret.pyc").write_bytes(b"cache")
        for name in ("debug.log", "scratch.tmp", "private.hwpx"):
            (self.source / "examples" / name).write_bytes(b"not for deployment")
        for target in ("Codex", "Claude"):
            with self.subTest(target=target):
                self.dest = self.work / (target + " 한글 사용자") / "skills with spaces"
                self.installed = self.dest / SKILL
                self.install("-Target", target, "-Apply")
                check = self.verify()
                self.assertTrue(check["valid"])
                self.assertEqual(check["file_count"], len(tree_hashes(self.installed)) - 1)
                paths = tree_hashes(self.installed)
                self.assertFalse(any("__pycache__" in p or p.endswith((".pyc", ".log", ".tmp", ".hwpx")) for p in paths))
                (self.installed / "user-note.txt").write_text("preserve me", encoding="utf-8")
                previous = tree_hashes(self.installed)
                result = self.install("-Target", target, "-Apply")
                backup_line = next(line for line in result.stdout.splitlines() if line.startswith("BACKUP_PATH: "))
                backup = Path(backup_line.removeprefix("BACKUP_PATH: "))
                self.assertNotIn(self.dest, backup.parents)
                self.assertEqual(tree_hashes(backup), previous)
                self.assertTrue(self.verify()["valid"])

    def test_unlisted_markdown_json_and_scripts_are_not_deployed(self) -> None:
        for name in ("private-note.md", "private-case.json", "local-helper.py"):
            (self.source / "examples" / name).write_text("local only", encoding="utf-8")
        self.install("-Apply")
        self.assertFalse(any(p.name.startswith(("private-", "local-")) for p in self.installed.rglob("*")))
        self.assertTrue(self.verify()["valid"])

    def test_allowlist_missing_file_or_directory_is_rejected(self) -> None:
        required = self.source / "examples" / "human-evidence.example.json"
        required.unlink()
        self.install("-Apply", ok=False)
        self.assertFalse(self.installed.exists())
        required.mkdir()
        self.install("-Apply", ok=False)
        self.assertFalse(self.installed.exists())

    def test_install_and_uninstall_share_exclusive_target_lock(self) -> None:
        self.install("-Apply")
        before = tree_hashes(self.installed)
        def quote(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"
        command = ". " + quote(str(self.source / "scripts" / "deployment_common.ps1")) + "; "
        command += "$d = Get-DeploymentDestination Codex " + quote(str(self.dest)) + "; "
        command += "$held = Enter-DeploymentLock $d.Path $d.Storage; "
        command += "try { [Console]::WriteLine('LOCKED'); [Console]::Out.Flush(); [Console]::ReadLine() | Out-Null } finally { $held.Dispose() }"
        holder = subprocess.Popen([str(PWSH), "-NoProfile", "-NonInteractive", "-Command", command],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8", errors="replace", cwd=self.work)
        try:
            ready: queue.Queue[str] = queue.Queue()
            threading.Thread(target=lambda: ready.put(holder.stdout.readline()), daemon=True).start()
            self.assertEqual(ready.get(timeout=20).strip(), "LOCKED")
            for script in ("install.ps1", "uninstall.ps1"):
                result = self.run_ps(script, "-DestinationRoot", str(self.dest), "-Apply", ok=False)
                self.assertIn("DEPLOYMENT_BUSY", result.stderr)
                self.assertEqual(tree_hashes(self.installed), before)
        finally:
            try:
                holder.communicate("release\n", timeout=20)
            except subprocess.TimeoutExpired:
                holder.kill()
                holder.communicate(timeout=10)
                self.fail("lock holder did not exit within 20 seconds")
        self.assertEqual(holder.returncode, 0)
        self.install("-Apply")
        self.assertTrue(self.verify()["valid"])

    def test_exclusive_move_and_candidate_ownership(self) -> None:
        self.install("-Apply")
        existing = self.work / "existing directory"
        existing.mkdir()
        before = tree_hashes(self.installed)
        command = ". '" + str(self.source / "scripts" / "deployment_common.ps1").replace("'", "''") + "'; "
        command += "$root = '" + str(self.installed).replace("'", "''") + "'; "
        command += "$receipt = Get-Content -LiteralPath (Join-Path $root '.minutes-install-manifest.json') -Raw | ConvertFrom-Json; "
        command += "if (-not (Test-DeploymentCandidateOwner $root $receipt.install_id)) { throw 'expected owned' }; "
        command += "if (Test-DeploymentCandidateOwner $root 'foreign-id') { throw 'foreign owner accepted' }; "
        command += "Write-Output 'OWNER_CHECKS_PASSED'; try { Move-DeploymentDirectory $root '"
        command += str(existing).replace("'", "''") + "'; throw 'MOVE_ACCEPTED_EXISTING_TARGET' } "
        command += "catch [IO.IOException] { Write-Output 'MOVE_COLLISION_BLOCKED' }"
        result = subprocess.run([str(PWSH), "-NoProfile", "-NonInteractive", "-Command", command],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OWNER_CHECKS_PASSED", result.stdout)
        self.assertIn("MOVE_COLLISION_BLOCKED", result.stdout)
        self.assertEqual(tree_hashes(self.installed), before)
        self.assertEqual(list(existing.iterdir()), [])

    def test_rollback_preserves_foreign_active_tree_and_original_backup(self) -> None:
        self.install("-Apply")
        before = tree_hashes(self.installed)
        helper = self.source / "scripts" / "deployment_common.ps1"
        with helper.open("a", encoding="utf-8") as out:
            out.write("""
function Invoke-DeploymentTestFailure {
    param([string]$Phase)
    if ($Phase -eq 'after-swap') {
        $path = Join-Path $dest.Path $script:MinutesManifestName
        $receipt = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        $receipt.install_id = 'foreign-owner'
        $receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $path -Encoding UTF8
        throw 'FOREIGN_OWNER_TEST'
    }
}
""")
        result = self.install("-Apply", ok=False)
        self.assertIn("FOREIGN_OWNER_TEST", result.stderr)
        receipt = json.loads((self.installed / ".minutes-install-manifest.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(receipt["install_id"], "foreign-owner")
        backups = list((self.dest.parent / ".minutes-skill-deployment").glob("backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(tree_hashes(backups[0]), before)
        self.assertFalse((self.installed / SKILL).exists())

    def test_missing_and_modified_files_fail(self) -> None:
        self.install("-Apply")
        path = self.installed / "references" / "checklist.md"
        path.unlink()
        check = self.verify(ok=False)
        self.assertIn("references/checklist.md", check["missing"])
        self.install("-Apply")
        path.write_text("changed", encoding="utf-8")
        check = self.verify(ok=False)
        self.assertIn("references/checklist.md", check["modified"])

    def test_installed_manifest_cannot_hide_tampering(self) -> None:
        self.install("-Apply")
        path = self.installed / "references" / "checklist.md"
        path.write_text("changed", encoding="utf-8")
        manifest_path = self.installed / ".minutes-install-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        for entry in manifest["files"]:
            if entry["path"] == "references/checklist.md":
                entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
                entry["length"] = path.stat().st_size
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        check = self.verify(ok=False)
        self.assertFalse(check["valid"])
        self.assertIn("references/checklist.md", check["modified"])
        self.assertTrue(check["manifest_errors"])

    def test_installed_verifier_refuses_before_loading_installed_helper(self) -> None:
        self.install("-Apply")
        helper = self.installed / "scripts" / "deployment_common.ps1"
        helper.write_text("throw 'UNTRUSTED_HELPER_EXECUTED'", encoding="utf-8-sig")
        for args in ((), ("-SourceRoot", str(self.source))):
            result = self.run_ps("verify_install.ps1", "-DestinationRoot", str(self.dest),
                                 *args, source=self.installed, ok=False)
            self.assertIn("TRUSTED_SOURCE_REQUIRED", result.stderr)
            self.assertNotIn("UNTRUSTED_HELPER_EXECUTED", result.stderr)
        check = self.verify(ok=False)
        self.assertIn("scripts/deployment_common.ps1", check["modified"])

    def test_verifier_cannot_use_another_source_root(self) -> None:
        self.install("-Apply")
        result = self.run_ps("verify_install.ps1", "-DestinationRoot", str(self.dest),
                             "-SourceRoot", str(self.installed), ok=False)
        self.assertIn("TRUSTED_SOURCE_REQUIRED", result.stderr)

    def test_installed_broken_links_are_reported(self) -> None:
        self.install("-Apply")
        with (self.installed / "profiles" / "README.md").open("a", encoding="utf-8") as out:
            out.write("\n[bad](missing-installed-profile.md)\n")
        check = self.verify(ok=False)
        self.assertTrue(any("missing-installed-profile.md" in item for item in check["broken_links"]))

    def test_normal_python_use_reports_only_known_runtime_cache(self) -> None:
        self.install("-Apply")
        env = os.environ.copy()
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        imported = subprocess.run([sys.executable, "-X", "utf8", "-c",
                                   "import sys; sys.path.insert(0, sys.argv[1]); import hwpx_common",
                                   str(self.installed / "scripts")], env=env, capture_output=True,
                                  text=True, encoding="utf-8", timeout=30)
        self.assertEqual(imported.returncode, 0, imported.stderr)
        cache = self.installed / "scripts" / "__pycache__"
        self.assertTrue(list(cache.glob("*.pyc")))
        check = self.verify()
        self.assertTrue(check["valid"])
        self.assertTrue(check["runtime_cache"])
        (cache / "unknown.cpython-312.pyc").write_bytes(b"not a deployed module cache")
        (self.installed / "debug.log").write_text("unexpected", encoding="utf-8")
        (self.installed / "actual.hwpx").write_bytes(b"unexpected")
        check = self.verify(ok=False)
        self.assertIn("scripts/__pycache__/unknown.cpython-312.pyc", check["unexpected"])
        self.assertIn("debug.log", check["unexpected"])
        self.assertIn("actual.hwpx", check["unexpected"])

    def test_broken_link_blocks_staged_install_and_preserves_current(self) -> None:
        self.install("-Apply")
        previous = tree_hashes(self.installed)
        with (self.source / "profiles" / "README.md").open("a", encoding="utf-8") as out:
            out.write("\n[broken](missing-profile.md)\n")
        result = self.install("-Apply", ok=False)
        self.assertIn("missing-profile.md", result.stdout + result.stderr)
        self.assertEqual(tree_hashes(self.installed), previous)

    def test_each_injected_failure_restores_exact_hashes(self) -> None:
        self.install("-Apply")
        (self.installed / "local extra.txt").write_text("keep", encoding="utf-8")
        previous = tree_hashes(self.installed)
        for phase in ("stage", "copy", "verify", "swap", "after-swap"):
            with self.subTest(phase=phase):
                self.install("-Apply", ok=False, phase=phase)
                self.assertEqual(tree_hashes(self.installed), previous)

    def test_new_install_swap_failure_does_not_leave_active_candidate(self) -> None:
        for phase in ("swap", "after-swap"):
            with self.subTest(phase=phase):
                self.install("-Apply", ok=False, phase=phase)
                self.assertFalse(self.installed.exists())

    def test_printed_verification_command_targets_custom_path(self) -> None:
        result = self.install("-Apply")
        command = next(line.removeprefix("VERIFY_COMMAND: ") for line in result.stdout.splitlines()
                       if line.startswith("VERIFY_COMMAND: "))
        # The hosted runner can expose TEMP through an 8.3 alias; PowerShell prints the long path.
        destination = str(self.dest.resolve(strict=True)).replace("'", "''")
        self.assertIn(os.path.normcase(f"-DestinationRoot '{destination}' "), os.path.normcase(command))
        executed = subprocess.run([str(PWSH), "-NoProfile", "-NonInteractive", "-Command", command],
                                  cwd=self.work, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=90)
        self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
        self.assertTrue(self.installed.samefile(Path(json.loads(executed.stdout)["path"])))

    def test_uninstall_preview_and_apply_moves_complete_tree(self) -> None:
        self.install("-Apply")
        note = self.installed / "local note.txt"
        note.write_text("keep", encoding="utf-8")
        before = tree_hashes(self.work)
        preview = self.run_ps("uninstall.ps1", "-DestinationRoot", str(self.dest))
        self.assertEqual(tree_hashes(self.work), before)
        self.assertIn(os.path.normcase(str(note.resolve(strict=True))), os.path.normcase(preview.stdout).splitlines())
        previous = tree_hashes(self.installed)
        result = self.run_ps("uninstall.ps1", "-DestinationRoot", str(self.dest), "-Apply")
        backup = Path(next(line.removeprefix("BACKUP_PATH: ") for line in result.stdout.splitlines()
                           if line.startswith("BACKUP_PATH: ")))
        self.assertFalse(self.installed.exists())
        self.assertNotIn(self.dest, backup.parents)
        self.assertEqual(tree_hashes(backup), previous)

    def test_unregistered_folder_is_not_uninstalled(self) -> None:
        self.installed.mkdir(parents=True)
        (self.installed / "SKILL.md").write_text("not registered", encoding="utf-8")
        before = tree_hashes(self.work)
        self.run_ps("uninstall.ps1", "-DestinationRoot", str(self.dest), "-Apply", ok=False)
        self.assertEqual(tree_hashes(self.work), before)

    def test_overlapping_paths_and_manifest_traversal_rejected(self) -> None:
        self.run_ps("install.ps1", "-DestinationRoot", str(self.source / "nested skills"), "-Apply", ok=False)
        self.assertFalse((self.source / "nested skills").exists())
        self.run_ps("install.ps1", "-DestinationRoot", str(self.work), "-Apply", ok=False)
        self.run_ps("install.ps1", "-DestinationRoot", str(self.work / ".minutes-skill-deployment"), "-Apply", ok=False)
        manifest = self.source / "distribution-manifest.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["include"].append("../outside.txt")
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.install("-Apply", ok=False)
        self.assertFalse(self.installed.exists())
        payload["include"][-1] = str(self.work / "outside.md")
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.install("-Apply", ok=False)
        self.assertFalse(self.installed.exists())

    def test_duplicate_manifest_paths_and_destination_junction_are_rejected(self) -> None:
        manifest = self.source / "distribution-manifest.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["include"].append("SKILL.md")
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.install("-Apply", ok=False)
        payload["include"].pop()
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        outside = self.work / "do not touch"
        outside.mkdir()
        self.dest.parent.mkdir(parents=True)
        try:
            self.dest.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlink unavailable: {error}")
        self.install("-Apply", ok=False)
        self.assertEqual(list(outside.iterdir()), [])

    @unittest.skipUnless(shutil.which("powershell.exe"), "Windows PowerShell 5.1 unavailable")
    def test_windows_powershell_51_new_install_and_verify(self) -> None:
        executable = str(shutil.which("powershell.exe"))
        # A PS7 host's module search path must not make PS5 load PS7's Utility
        # module through Python. Let this child construct its native PS5 paths;
        # do not alter the parent environment or execution policy.
        ps51_env = {key: value for key, value in os.environ.items()
                    if key.casefold() != "psmodulepath"}
        for script in ("install.ps1", "verify_install.ps1"):
            def quote(value: str) -> str:
                return "'" + value.replace("'", "''") + "'"
            command = "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); & "
            command += quote(str(self.source / "scripts" / script))
            command += " -DestinationRoot " + quote(str(self.dest))
            command += " -Apply" if script == "install.ps1" else " -SourceRoot " + quote(str(self.source))
            result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", command],
                                    cwd=self.work, env=ps51_env, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=90)
            if "AuthorizationManager check failed" in result.stderr or "PSSecurityException" in result.stderr:
                self.skipTest("Windows PowerShell 5.1 execution policy blocked isolated scripts; policy unchanged")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if script == "verify_install.ps1":
                self.assertTrue(json.loads(result.stdout)["valid"])

    def test_reparse_source_is_rejected_before_copy(self) -> None:
        target = self.work / "outside.md"
        target.write_text("outside", encoding="utf-8")
        link = self.source / "references" / "checklist.md"
        link.unlink()
        try:
            link.symlink_to(target)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        self.install("-Apply", ok=False)
        self.assertFalse(self.installed.exists())


if __name__ == "__main__":
    unittest.main()
