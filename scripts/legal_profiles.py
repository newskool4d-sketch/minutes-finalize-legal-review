#!/usr/bin/env python3
"""Local, version-bound legal review candidates; never a legal determination.

The checked catalog is deliberately bounded to the official versions actually
researched. Dates outside that coverage require renewed official-source review.
No network requests, inferred case dates, automatic approvals, or scoring occur.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

CATALOG_PATH = Path(__file__).resolve().parents[1] / "profiles" / "legal-profiles.json"
PROFILE_TYPES = {"education-rights-ko": "education_rights", "school-violence-ko": "school_violence",
                 "generic-committee-ko": "generic"}
DATE_FIELDS = ("incident_date", "deliberation_date", "disposition_date", "knowledge_date", "report_date")
CONTEXT_FIELDS = {"committee_type", "jurisdiction", *DATE_FIELDS}
CATALOG_LIMIT = 2 * 1024 * 1024
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,95}\Z")


class LegalProfileError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _error() -> None:
    raise LegalProfileError("LEGAL_CATALOG_INVALID")


def _fields(value: Any, keys: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        _error()


def _text(value: Any, maximum: int = 4096) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 and c not in "\n\t" for c in value):
        _error()


def _identifier(value: Any) -> None:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        _error()


def _texts(value: Any, *, maximum: int = 64) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        _error()
    for item in value:
        _text(item)
    if len(set(value)) != len(value):
        _error()


def _date(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date")
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("date")
    return value


def validate_context(value: Any, profile_id: str) -> dict[str, Any] | None:
    if profile_id not in PROFILE_TYPES:
        raise LegalProfileError("UNSUPPORTED_PROFILE")
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != CONTEXT_FIELDS:
        raise LegalProfileError("INVALID_LEGAL_CONTEXT")
    if value["committee_type"] != PROFILE_TYPES[profile_id] or value["jurisdiction"] != "KR":
        raise LegalProfileError("LEGAL_PROFILE_CONTEXT_MISMATCH")
    try:
        for key in DATE_FIELDS:
            if value[key] is not None:
                _date(value[key])
    except (ValueError, TypeError):
        raise LegalProfileError("INVALID_LEGAL_DATE") from None
    for earlier, later in (("incident_date", "deliberation_date"), ("deliberation_date", "disposition_date"),
                           ("incident_date", "disposition_date")):
        if value[earlier] is not None and value[later] is not None and value[earlier] > value[later]:
            raise LegalProfileError("INVALID_LEGAL_CHRONOLOGY")
    return deepcopy(value)


def validate_catalog(catalog: Any) -> None:
    try:
        _fields(catalog, {"schema_version", "catalog_version", "checked_on", "profiles"})
        if type(catalog["schema_version"]) is not int or catalog["schema_version"] != 1:
            _error()
        _text(catalog["catalog_version"], 64)
        _date(catalog["checked_on"])
        profiles = catalog["profiles"]
        if not isinstance(profiles, list) or len(profiles) != 2:
            _error()
        profile_ids = set()
        for profile in profiles:
            _fields(profile, {"id", "version", "committee_type", "jurisdiction", "sources", "rules", "required_checks"})
            pid = profile["id"]
            if pid not in {"education-rights-ko", "school-violence-ko"} or pid in profile_ids:
                _error()
            profile_ids.add(pid)
            if profile["committee_type"] != PROFILE_TYPES[pid] or profile["jurisdiction"] != "KR":
                _error()
            _text(profile["version"], 64)
            sources = profile["sources"]
            if not isinstance(sources, list) or not 1 <= len(sources) <= 64:
                _error()
            source_ids = set()
            for source in sources:
                _fields(source, {"id", "law_name", "kind", "official_url", "mst", "promulgated_on", "effective_from",
                                 "effective_to_exclusive", "verified_through", "articles", "temporal_basis", "summary", "transition_notes"})
                _identifier(source["id"])
                if source["id"] in source_ids:
                    _error()
                source_ids.add(source["id"])
                for key in ("law_name", "kind", "official_url", "summary", "transition_notes"):
                    _text(source[key])
                url = urlsplit(source["official_url"])
                if url.scheme != "https" or url.hostname not in {"law.go.kr", "www.law.go.kr", "moe.go.kr", "www.moe.go.kr"} or url.username or url.password or url.port not in (None, 443):
                    _error()
                if source["mst"] is not None and (not isinstance(source["mst"], str) or not re.fullmatch(r"\d{1,20}", source["mst"])):
                    _error()
                for key in ("promulgated_on", "effective_from", "verified_through"):
                    _date(source[key])
                if source["effective_to_exclusive"] is not None:
                    _date(source["effective_to_exclusive"])
                    if source["effective_to_exclusive"] <= source["effective_from"]:
                        _error()
                if not source["promulgated_on"] <= source["effective_from"] <= source["verified_through"] <= catalog["checked_on"]:
                    _error()
                _texts(source["articles"])
                _texts(source["temporal_basis"], maximum=5)
                if any(key not in DATE_FIELDS for key in source["temporal_basis"]):
                    _error()
            ids = set()
            for collection in ("rules", "required_checks"):
                rows = profile[collection]
                if not isinstance(rows, list) or not 1 <= len(rows) <= 128:
                    _error()
                for row in rows:
                    keys = {"id", "source_ids", "evidence_to_check", "reason"}
                    if collection == "rules":
                        keys |= {"pattern", "issue_types", "risk_level", "action_code", "factors"}
                    _fields(row, keys)
                    _identifier(row["id"])
                    if row["id"] in ids:
                        _error()
                    ids.add(row["id"])
                    _texts(row["source_ids"])
                    if any(source_id not in source_ids for source_id in row["source_ids"]):
                        _error()
                    _texts(row["evidence_to_check"])
                    _text(row["reason"])
                    if collection == "rules":
                        _text(row["pattern"], 512)
                        re.compile(row["pattern"])
                        _texts(row["issue_types"])
                        _texts(row["factors"])
                        if row["risk_level"] not in {"중간", "높음"} or row["action_code"] not in {"V", "L"}:
                            _error()
    except LegalProfileError:
        raise
    except (TypeError, ValueError, KeyError, re.error, OverflowError):
        raise LegalProfileError("LEGAL_CATALOG_INVALID") from None


def load_catalog(path: Path = CATALOG_PATH) -> tuple[dict[str, Any], str]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _error()
            result[key] = value
        return result
    try:
        with path.open("rb") as stream:
            raw = stream.read(CATALOG_LIMIT + 1)
        if len(raw) > CATALOG_LIMIT:
            _error()
        catalog = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda _: _error())
        validate_catalog(catalog)
        return catalog, hashlib.sha256(raw).hexdigest()
    except LegalProfileError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise LegalProfileError("LEGAL_CATALOG_INVALID") from None


def get_profile(catalog: dict[str, Any], profile_id: str) -> dict[str, Any]:
    if profile_id == "generic-committee-ko":
        return {"id": profile_id, "version": "unconfigured", "committee_type": "generic", "jurisdiction": "KR",
                "sources": [], "rules": [], "required_checks": []}
    for profile in catalog["profiles"]:
        if profile["id"] == profile_id:
            return profile
    raise LegalProfileError("UNSUPPORTED_PROFILE")


def profile_status(profile_id: str) -> str:
    return "not_validated" if profile_id == "generic-committee-ko" else "rules_implemented"


def review_profile(catalog: dict[str, Any], catalog_hash: str, profile_id: str, context: Any) -> dict[str, Any]:
    context = validate_context(context, profile_id)
    profile = get_profile(catalog, profile_id)
    sources, blockers = [], []
    for source in profile["sources"]:
        checks = []
        for field in source["temporal_basis"]:
            value = context[field] if context is not None else None
            if value is None:
                status = "missing_date"
            elif value < source["effective_from"]:
                status = "historical_version_required"
            elif source["effective_to_exclusive"] is not None and value >= source["effective_to_exclusive"]:
                status = "unverified_version"
            elif value > source["verified_through"]:
                status = "after_verification_date"
            else:
                status = "within_verified_version_range"
            checks.append({"field": field, "date": value, "status": status})
            if status != "within_verified_version_range":
                blockers.append(f"{source['id']}:{field}:{status}")
        sources.append({**deepcopy(source), "temporal_status": "needs_date_verification" if any(c["status"] != "within_verified_version_range" for c in checks) else "within_verified_version_range",
                        "date_checks": checks})
    source_map = {source["id"]: source for source in sources}
    checklist = [{**deepcopy(item), "status": "awaiting_documentary_and_human_review",
                  "legal_basis": [deepcopy(source_map[key]) for key in item["source_ids"]]}
                 for item in profile["required_checks"]]
    if profile_id == "generic-committee-ko":
        blockers.append("profile_not_configured")
    temporal_missing = bool(blockers)
    blockers.extend(["documentary_evidence_required", "human_legal_review_required"])
    return {"schema_version": 1, "profile_version": profile["version"], "profile_sha256": fingerprint(profile),
            "catalog_sha256": catalog_hash, "context_sha256": fingerprint(context), "context": context,
            "status": "needs_date_verification" if temporal_missing else "requires_human_review",
            "sources": sources, "checklist": checklist, "blockers": blockers,
            "legal_conclusion": "not_determined", "requires_human_review": True, "external_release_authorized": False}


def profile_candidates(profile: dict[str, Any], review: dict[str, Any], text: str) -> list[dict[str, Any]]:
    sources = {source["id"]: source for source in review["sources"]}
    result = []
    for rule in profile["rules"]:
        if re.search(rule["pattern"], text):
            basis = [deepcopy(sources[key]) for key in rule["source_ids"]]
            result.append({"rule_id": rule["id"], "legal_issue_type": rule["issue_types"],
                           "risk_level": rule["risk_level"], "action_code": rule["action_code"],
                           "requires_human_summary": True, "legal_factors": rule["factors"],
                           "reason": rule["reason"], "evidence_to_check": rule["evidence_to_check"], "legal_basis": basis,
                           "legal_basis_status": "needs_date_verification" if any(item["temporal_status"] != "within_verified_version_range" for item in basis) else "requires_human_review",
                           "legal_conclusion": "not_determined"})
    return result


def render_profile_summary(review: dict[str, Any]) -> str:
    """Only validated catalog text and bounded identifiers enter this appendix."""
    lines = ["", "## 위원회별 법률 검토 프로필", "", "- 법률적 결론: 미확정", "- 담당자·법무 확인: 필수",
             f"- 적용 시점 검토: {review['status']}", f"- 프로필 버전: {review['profile_version']}",
             f"- 카탈로그 SHA-256: {review['catalog_sha256']}", f"- 검토 맥락 SHA-256: {review['context_sha256']}", "",
             "아래는 공식 근거에 연결한 검토 후보·체크리스트이며 사실인정·위법 여부·조치를 자동 결정하지 않습니다.", ""]
    for source in review["sources"]:
        lines.extend([f"- {source['law_name']} ({', '.join(source['articles'])})", f"  - 공식 출처: {source['official_url']}",
                      f"  - 시행일: {source['effective_from']} / 근거 확인 범위 말일: {source['verified_through']}",
                      f"  - 시점 상태: {source['temporal_status']}"])
    lines.extend(["", "### 필수 자료·법무 확인", ""])
    for item in review["checklist"]:
        lines.append(f"- {item['id']}: {item['reason']} 확인할 자료: {', '.join(item['evidence_to_check'])}")
    lines.extend(["", "근거 범위 밖의 과거/미래 일자와 부칙·경과조치는 공식 원문을 다시 확인해야 합니다. 확인되지 않은 근거를 정본 확정이나 외부 공개 승인으로 사용하지 않습니다.", ""])
    return "\n".join(lines)
