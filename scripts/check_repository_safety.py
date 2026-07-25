#!/usr/bin/env python3
"""Fail when tracked repository paths contain prohibited case-document extensions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROHIBITED_SUFFIXES = {".hwp", ".hwpx", ".hwpml"}
PROHIBITED_PATH_MARKERS = ("실명", "원본", "초안", "수정본", "case-data", "samples-real")


def repository_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return [entry.decode("utf-8") for entry in result.stdout.split(b"\0") if entry]


def main() -> int:
    problems: list[str] = []
    try:
        paths = repository_paths()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: git 추적 파일 목록을 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 1
    for relative in paths:
        path = Path(relative)
        normalized = relative.replace("\\", "/").lower()
        if path.suffix.lower() in PROHIBITED_SUFFIXES:
            problems.append(f"금지된 문서 확장자: {relative}")
        if any(marker in normalized for marker in PROHIBITED_PATH_MARKERS):
            problems.append(f"사건자료로 보이는 추적 경로: {relative}")
    if problems:
        print("FAIL:\n" + "\n".join(problems), file=sys.stderr)
        return 1
    print(f"OK: repository_paths={len(paths)}; no prohibited case-document paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
