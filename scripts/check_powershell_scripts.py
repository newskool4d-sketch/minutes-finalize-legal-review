#!/usr/bin/env python3
"""Perform small, cross-platform safety checks on bundled PowerShell scripts."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ("install.ps1", "uninstall.ps1", "verify_install.ps1")


def main() -> int:
    errors: list[str] = []
    for name in SCRIPTS:
        path = ROOT / "scripts" / name
        text = path.read_text(encoding="utf-8")
        if "Set-StrictMode -Version Latest" not in text:
            errors.append(f"{name}: Set-StrictMode가 없습니다.")
        if "$ErrorActionPreference = 'Stop'" not in text:
            errors.append(f"{name}: ErrorActionPreference=Stop이 없습니다.")
        if "Invoke-Expression" in text or "iex " in text.lower():
            errors.append(f"{name}: 동적 명령 실행은 허용하지 않습니다.")
    uninstall = (ROOT / "scripts" / "uninstall.ps1").read_text(encoding="utf-8")
    if "[switch]$Apply" not in uninstall or "if (-not $Apply)" not in uninstall:
        errors.append("uninstall.ps1: -Apply 확인 게이트가 없습니다.")
    if errors:
        print("FAIL:\n" + "\n".join(errors), file=sys.stderr)
        return 1
    print("OK: PowerShell script safety")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
