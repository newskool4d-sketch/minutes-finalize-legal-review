#!/usr/bin/env python3
"""Build a new, allowlisted runtime bundle; never read case data or install skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from minutes_engine import assert_plain_path, inside, json_bytes, strict_json, write_new

ROOT = Path(__file__).resolve().parents[1]


def git_bytes(*args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, check=True, timeout=15
    ).stdout


def build_bundle(destination: Path, source_commit: str, *, committed: bool = False) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source commit must be a full SHA")
    destination = destination.absolute()
    assert_plain_path(destination)
    if destination.exists() or destination.resolve().is_relative_to(ROOT):
        raise ValueError("new destination outside source required")
    if committed and git_bytes("rev-parse", "HEAD").decode("ascii").strip() != source_commit:
        raise ValueError("checked-out commit does not match the requested SHA")

    def read_source(name: str) -> bytes:
        target = inside(ROOT, name, file=True)
        if committed:
            # Read Git objects, not worktree bytes transformed by core.autocrlf.
            mode, kind, _, _ = git_bytes("ls-tree", source_commit, "--", name).split(maxsplit=3)
            if mode not in {b"100644", b"100755"} or kind != b"blob":
                raise ValueError("bundle inputs must be regular Git blobs")
            return git_bytes("cat-file", "blob", f"{source_commit}:{name}")
        return target.read_bytes()

    specification = strict_json(read_source("engine-runtime-manifest.json"))
    names = specification["include"]
    if specification["schema_version"] != 1 or not isinstance(names, list) or len(set(names)) != len(names):
        raise ValueError("invalid runtime manifest")
    captured = {name: read_source(name) for name in names}
    if specification["entrypoint"] not in captured:
        raise ValueError("entrypoint missing")
    # Read all allowlisted files before creating any destination. No recursive copy.
    source_state = "committed" if committed else "working_tree"
    manifest = {"schema_version": 1, "protocol_version": specification["protocol_version"],
                "engine_version": captured["VERSION"].decode("utf-8").strip(), "source_commit": source_commit,
                "source_state": source_state,
                "entrypoint": specification["entrypoint"],
                "files": [{"path": name, "sha256": hashlib.sha256(captured[name]).hexdigest()} for name in sorted(captured)]}
    destination.parent.mkdir(parents=True, exist_ok=True)
    assert_plain_path(destination.parent)
    destination.mkdir()
    for name, contents in captured.items():
        target = inside(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_new(target, contents)
    contents = json_bytes(manifest)
    write_new(destination / "bundle-manifest.json", contents)
    return {"status": "ok", "manifest_sha256": hashlib.sha256(contents).hexdigest(),
            "engine_version": manifest["engine_version"], "protocol_version": manifest["protocol_version"],
            "source_commit": source_commit, "source_state": source_state, "file_count": len(captured)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--committed", action="store_true", help="read allowlisted bytes from Git, not the worktree")
    args = parser.parse_args()
    try:
        source_commit = args.source_commit
        if source_commit is None:
            source_commit = git_bytes("rev-parse", "HEAD").decode("ascii").strip()
        print(json.dumps(build_bundle(args.output, source_commit, committed=args.committed), ensure_ascii=False))
        return 0
    except Exception:
        print(json.dumps({"status": "error", "code": "BUNDLE_BUILD_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
