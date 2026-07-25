#!/usr/bin/env python3
"""Fail when a repository Markdown file points to a missing local file."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)]+)\)")


def main() -> int:
    errors: list[str] = []
    for markdown in ROOT.rglob("*.md"):
        if any(part in {".git", "__pycache__"} for part in markdown.parts):
            continue
        text = markdown.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            target = target.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if target.startswith("/"):
                errors.append(f"{markdown.relative_to(ROOT)}: 절대 로컬 링크는 허용하지 않습니다: {target}")
                continue
            if not (markdown.parent / target).is_file():
                errors.append(f"{markdown.relative_to(ROOT)}: 링크 대상이 없습니다: {target}")
    if errors:
        print("FAIL:\n" + "\n".join(errors), file=sys.stderr)
        return 1
    print("OK: Markdown local links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
