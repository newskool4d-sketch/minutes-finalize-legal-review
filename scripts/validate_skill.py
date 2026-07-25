#!/usr/bin/env python3
"""Repository-local structural validation for CI and offline use."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "minutes-hwpx-finalize-legal-review"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if not skill.startswith("---\n"):
        fail("SKILL.md frontmatter가 없습니다.")
    frontmatter = skill.split("---\n", 2)[1]
    if not re.search(rf"^name:\s*{re.escape(SKILL_NAME)}\s*$", frontmatter, re.MULTILINE):
        fail("SKILL.md name이 올바르지 않습니다.")
    if not re.search(r"^description:\s*.+$", frontmatter, re.MULTILINE):
        fail("SKILL.md description이 없습니다.")

    for reference in re.findall(r"\[[^\]]+\]\((references/[^)]+)\)", skill):
        if not (ROOT / reference).is_file():
            fail(f"참조 파일이 없습니다: {reference}")

    required = [
        "agents/openai.yaml",
        "VERSION",
        "SECURITY.md",
        "profiles/README.md",
        "references/checklist.md",
        "references/output-schema.md",
        "scripts/apply_approved_edits.py",
        "scripts/prepare_redactions.py",
        "scripts/detect_legal_review_candidates.py",
        "scripts/render_legal_review_report.py",
        "scripts/validate_operation_metrics.py",
        "scripts/verify_release_pair.py",
    ]
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"필수 파일이 없습니다: {relative}")

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail("VERSION은 semver 형식이어야 합니다.")

    agent = (ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
    if f"${SKILL_NAME}" not in agent:
        fail("agents/openai.yaml default_prompt에 스킬 호출명이 없습니다.")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    target = f"skills\\\\{SKILL_NAME}"
    if readme.count(target) != 2:
        fail("README 설치 경로가 Codex·Claude 모두 실제 스킬명과 일치하지 않습니다.")
    if f"- 스킬 버전: `{version}`" not in readme:
        fail("README 스킬 버전이 VERSION과 일치하지 않습니다.")

    print("OK: repository skill structure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
