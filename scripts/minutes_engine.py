#!/usr/bin/env python3
"""Single-request, local-only JSON bridge; no AI or human decisions are invented."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from approval_contract import validate_approval_spec
from apply_approved_edits import build_entry_pair, public_ledger
from detect_legal_review_candidates import RULES
from hwpx_common import (compare_package_metadata, require_preservable_metadata, section_names,
                         snapshot_hwpx, statement_text_hash, validate_snapshot, write_preserving_zip)
from hwpx_locations import LOCATION_SCHEME, parse_section
from legal_profiles import (LegalProfileError, fingerprint, get_profile, load_catalog, profile_candidates,
                            profile_status, render_profile_summary, review_profile)
from render_review_summary import build_summary, render_summary
from verify_release_pair import compare_entries

PROTOCOL_VERSION = 1
ENGINE_VERSION = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
OPERATIONS = ("capabilities", "inspect", "build_pair")
PROFILES = ("education-rights-ko", "school-violence-ko", "generic-committee-ko")
LIMITS = {"request_bytes": 1024 * 1024, "json_bytes": 8 * 1024 * 1024,
          "source_bytes": 64 * 1024 * 1024, "uncompressed_bytes": 256 * 1024 * 1024,
          "zip_entries": 8192, "response_bytes": 32 * 1024 * 1024}
SHA = re.compile(r"[0-9a-f]{64}\Z")
RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)


class EngineError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def strict_json(data: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise EngineError("INVALID_JSON")
            result[key] = value
        return result
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(EngineError("INVALID_JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise EngineError("INVALID_JSON") from exc


def assert_plain_path(path: Path) -> None:
    """Check lexical ancestors before resolving so a junction cannot disappear."""
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise EngineError("UNSAFE_PATH")


def workspace_path(value: Any) -> Path:
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise EngineError("UNSAFE_PATH")
    path = Path(os.path.abspath(value))
    assert_plain_path(path)
    if not path.is_dir():
        raise EngineError("WORKSPACE_UNAVAILABLE")
    return path.resolve()


def inside(root: Path, relative: Any, *, file: bool = False) -> Path:
    if not isinstance(relative, str) or not relative or len(relative) > 512 or "\\" in relative:
        raise EngineError("UNSAFE_PATH")
    parts = relative.split("/")
    if any(not p or p in {".", ".."} or p[-1:] in {".", " "} or
           any(ord(c) < 32 or c in ':*?"<>|' for c in p) or RESERVED.fullmatch(p) for p in parts):
        raise EngineError("UNSAFE_PATH")
    path = root.joinpath(*parts)
    assert_plain_path(path)
    if not path.resolve().is_relative_to(root) or path.resolve() == root:
        raise EngineError("UNSAFE_PATH")
    if file and not path.is_file():
        raise EngineError("INPUT_UNAVAILABLE")
    return path


def limited_read(path: Path, maximum: int) -> bytes:
    assert_plain_path(path)
    if path.stat().st_size > maximum:
        raise EngineError("RESOURCE_LIMIT")
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise EngineError("RESOURCE_LIMIT")
    return data


def capture_source(path: Path, expected: Any):
    if not isinstance(expected, str) or not SHA.fullmatch(expected):
        raise EngineError("INVALID_SOURCE_HASH")
    data = limited_read(path, LIMITS["source_bytes"])
    if hashlib.sha256(data).hexdigest() != expected:
        raise EngineError("SOURCE_CHANGED")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > LIMITS["zip_entries"] or sum(i.file_size for i in infos) > LIMITS["uncompressed_bytes"]:
            raise EngineError("RESOURCE_LIMIT")
        if any(i.flag_bits & 1 for i in infos):
            raise EngineError("UNSUPPORTED_PACKAGE")
    snapshot = snapshot_hwpx(data)
    if any(b"<!DOCTYPE" in value or b"<!ENTITY" in value for name, value in snapshot.entries.items()
           if name.lower().endswith(".xml")):
        raise EngineError("UNSUPPORTED_PACKAGE")
    validate_snapshot(snapshot)
    return snapshot


def inspect(snapshot, profile_id: str, profile: dict[str, Any], legal_review: dict[str, Any]) -> dict[str, Any]:
    paragraphs, candidates = [], []
    for section_index, name in enumerate(section_names(snapshot.entries)):
        for paragraph in parse_section(section_index, snapshot.entries[name]):
            digest = statement_text_hash(paragraph.own_text)
            paragraphs.append({"location_id": paragraph.location_id, "text": paragraph.own_text,
                               "statement_text_hash": digest})
            for rule_id, pattern, issue_types, risk, action in RULES:
                if pattern.search(paragraph.own_text):
                    candidates.append({"candidate_id": f"candidate-{len(candidates) + 1:03d}",
                                       "location_id": paragraph.location_id, "statement_text_hash": digest,
                                       "rule_id": rule_id, "legal_issue_type": issue_types,
                                       "risk_level": risk, "action_code": action, "requires_human_summary": True,
                                       "legal_basis": [], "legal_basis_status": "unlinked_common_rule",
                                       "legal_conclusion": "not_determined"})
            for candidate in profile_candidates(profile, legal_review, paragraph.own_text):
                candidates.append({"candidate_id": f"candidate-{len(candidates) + 1:03d}",
                                   "location_id": paragraph.location_id, "statement_text_hash": digest, **candidate})
    return {"source_sha256": snapshot.sha256, "location_scheme": LOCATION_SCHEME,
            "profile_id": profile_id, "legal_profile_status": profile_status(profile_id), "legal_review": legal_review,
            "paragraphs": paragraphs, "candidates": candidates}


def write_new(path: Path, data: bytes) -> None:
    assert_plain_path(path)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def build_pair(request: dict[str, Any], root: Path, source: Path, snapshot, legal_review: dict[str, Any]) -> dict[str, Any]:
    approved = inside(root, request["approved"], file=True)
    approval_bytes = limited_read(approved, LIMITS["json_bytes"])
    specification = strict_json(approval_bytes)
    validate_approval_spec(specification, snapshot.sha256)
    require_preservable_metadata(snapshot)
    destination = inside(root, request["output_dir"])
    if destination.exists():
        raise EngineError("OUTPUT_EXISTS")
    if source.is_relative_to(destination) or approved.is_relative_to(destination):
        raise EngineError("UNSAFE_PATH")
    pair = build_entry_pair(snapshot.entries, specification)
    filenames = {"approval": "approval.hwpx", "disclosure": "disclosure.hwpx", "audit": "audit.json",
                 "redaction_ledger": "redaction-ledger.json", "summary_json": "summary.json", "summary_md": "summary.md"}
    # Raw captured inputs never leave the chosen workspace. A killed process may leave
    # this private, uncommitted stage; only COMPLETE.json makes an output set complete.
    with tempfile.TemporaryDirectory(prefix=".minutes-stage-", dir=root) as temporary:
        stage = Path(temporary)
        captured_source, captured_plan = stage / "input.hwpx", stage / "approved.json"
        write_new(captured_source, snapshot.data)
        write_new(captured_plan, approval_bytes)
        write_preserving_zip(stage / filenames["approval"], snapshot.infos, pair["approval_entries"],
                             archive_comment=snapshot.archive_comment)
        write_preserving_zip(stage / filenames["disclosure"], snapshot.infos, pair["disclosure_entries"], disclosure=True)
        generated = {}
        for role in ("approval", "disclosure"):
            generated[role] = snapshot_hwpx((stage / filenames[role]).read_bytes())
            validate_snapshot(generated[role])
            compare_entries(pair[role + "_entries"], generated[role].entries, role)
            compare_package_metadata(snapshot, generated[role], disclosure=role == "disclosure")
        audit = {"schema_version": 2, "source_sha256": snapshot.sha256,
                 "approval_output": {"artifact_ref": "artifact:approval", "sha256": generated["approval"].sha256},
                 "disclosure_output": {"artifact_ref": "artifact:disclosure", "sha256": generated["disclosure"].sha256},
                 "approval_changes": pair["approval_changes"], "disclosure_changes": pair["disclosure_changes"],
                 "layout_cache": pair["layout_cache"], "disclosure_package": pair["disclosure_package"]}
        write_new(stage / filenames["audit"], json_bytes(audit))
        write_new(stage / filenames["redaction_ledger"], json_bytes(public_ledger(pair["redactions"], pair["disclosure_changes"])))
        summary = build_summary(captured_source, captured_plan, stage / filenames["approval"], stage / filenames["disclosure"])
        if summary["checks"]["technical_pair"]["status"] != "PASS" or summary["quality_result"] == "FAIL":
            raise EngineError("PAIR_VERIFICATION_FAILED")
        summary["legal_profile_review"] = legal_review
        summary["quality_result"] = "PARTIAL"
        write_new(stage / filenames["summary_json"], json_bytes(summary))
        write_new(stage / filenames["summary_md"], (render_summary(summary) + render_profile_summary(legal_review)).encode("utf-8"))
        # A changed source/decision file invalidates this run, even though generation
        # itself used only the immutable snapshot above.
        if limited_read(source, LIMITS["source_bytes"]) != snapshot.data or limited_read(approved, LIMITS["json_bytes"]) != approval_bytes:
            raise EngineError("INPUT_CHANGED")
        inside(root, request["output_dir"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        assert_plain_path(destination.parent)
        destination.mkdir()  # exclusive publication ownership
        outputs = []
        for role, name in filenames.items():
            contents = (stage / name).read_bytes()
            write_new(destination / name, contents)
            outputs.append({"role": role, "relative_path": (destination / name).relative_to(root).as_posix(),
                            "sha256": hashlib.sha256(contents).hexdigest()})
        result = {"source_sha256": snapshot.sha256, "profile_id": request["profile_id"],
                  "legal_profile_status": profile_status(request["profile_id"]), "legal_review": legal_review,
                  "technical_pair_valid": True,
                  "external_release_authorized": False, "outputs": outputs, "summary": summary}
        marker = {"schema_version": 1, "protocol_version": PROTOCOL_VERSION, "request_id": request["request_id"],
                  **{key: value for key, value in result.items() if key != "summary"}}
        write_new(destination / "COMPLETE.json", json_bytes(marker))
        return result


def execute(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict) or type(request.get("protocol_version")) is not int or request["protocol_version"] != PROTOCOL_VERSION:
        raise EngineError("PROTOCOL_MISMATCH")
    if not isinstance(request.get("request_id"), str):
        raise EngineError("INVALID_REQUEST")
    try:
        if str(uuid.UUID(request["request_id"])) != request["request_id"]:
            raise ValueError
    except ValueError as exc:
        raise EngineError("INVALID_REQUEST") from exc
    operation = request.get("operation")
    if operation not in OPERATIONS:
        raise EngineError("UNSUPPORTED_OPERATION")
    allowed = {"protocol_version", "request_id", "operation"}
    if operation != "capabilities":
        allowed |= {"workspace", "source", "source_sha256", "profile_id"}
    if operation == "build_pair":
        allowed |= {"approved", "output_dir"}
    optional = {"legal_context"} if operation != "capabilities" else set()
    if not allowed <= set(request) or set(request) - allowed - optional:
        raise EngineError("INVALID_REQUEST")
    catalog, catalog_hash = load_catalog()
    if operation == "capabilities":
        return {"protocol_version": PROTOCOL_VERSION, "operations": list(OPERATIONS),
                "location_scheme": LOCATION_SCHEME, "profiles": [
                    {"id": item, "legal_profile_status": profile_status(item),
                     "profile_version": get_profile(catalog, item)["version"],
                     "profile_sha256": fingerprint(get_profile(catalog, item)), "catalog_sha256": catalog_hash} for item in PROFILES],
                "limits": LIMITS}
    if request["profile_id"] not in PROFILES:
        raise EngineError("UNSUPPORTED_PROFILE")
    legal_review = review_profile(catalog, catalog_hash, request["profile_id"], request.get("legal_context"))
    root = workspace_path(request["workspace"])
    source = inside(root, request["source"], file=True)
    snapshot = capture_source(source, request["source_sha256"])
    if operation == "inspect":
        return inspect(snapshot, request["profile_id"], get_profile(catalog, request["profile_id"]), legal_review)
    return build_pair(request, root, source, snapshot, legal_review)


def handle(request: Any) -> dict[str, Any]:
    response = {"protocol_version": PROTOCOL_VERSION, "request_id": None, "operation": None,
                "engine_version": ENGINE_VERSION}
    if isinstance(request, dict):
        request_id = request.get("request_id")
        if isinstance(request_id, str) and re.fullmatch(r"[0-9a-f-]{36}", request_id):
            response["request_id"] = request_id
        if request.get("operation") in OPERATIONS:
            response["operation"] = request["operation"]
    try:
        response.update(status="ok", result=execute(request))
    except Exception as exc:
        code = exc.code if isinstance(exc, (EngineError, LegalProfileError)) else "INVALID_INPUT_OR_OPERATION_FAILED"
        response.update(status="error", error={"code": code, "message": "회의록 작업을 완료하지 못했습니다. 입력·승인·작업 상태를 확인하세요."})
    return response


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(LIMITS["request_bytes"] + 1)
        if len(raw) > LIMITS["request_bytes"]:
            raise EngineError("RESOURCE_LIMIT")
        request = strict_json(raw)
        response = handle(request)
        output = json_bytes(response)
        if len(output) > LIMITS["response_bytes"]:
            response = {"protocol_version": PROTOCOL_VERSION, "request_id": response["request_id"],
                        "operation": response["operation"], "engine_version": ENGINE_VERSION, "status": "error",
                        "error": {"code": "RESOURCE_LIMIT", "message": "응답 크기 제한을 초과했습니다."}}
            output = json_bytes(response)
    except Exception as exc:
        response = {"protocol_version": PROTOCOL_VERSION, "request_id": None, "operation": None,
                    "engine_version": ENGINE_VERSION, "status": "error", "error": {
                        "code": exc.code if isinstance(exc, EngineError) else "INVALID_REQUEST",
                        "message": "요청 형식을 확인하세요."}}
        output = json_bytes(response)
    sys.stdout.buffer.write(output)
    return 0 if response["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
