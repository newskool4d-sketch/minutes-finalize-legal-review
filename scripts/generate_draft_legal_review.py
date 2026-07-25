#!/usr/bin/env python3
"""Create conservative, de-identified per-candidate legal-review drafts.

The result is a starting point for a responsible officer or legal reviewer.  It
does not alter a HWPX file, decide facts, or make a legal conclusion.  It only
uses text-free candidate metadata, so the output can be kept separate from the
source minutes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from hwpx_common import read_json, write_json


LAW_SOURCE = "https://www.law.go.kr/"


def basis(law_name: str, article: str, effective_date: str, reference_date: str, status: str) -> dict[str, str]:
    return {
        "law_name": law_name,
        "article": article,
        "effective_date": effective_date,
        "applicable_event_date": reference_date,
        "retrieved_at": reference_date,
        "source_type": "국가법령정보센터",
        "source_id": LAW_SOURCE,
        "verification_status": status,
    }


def draft_for(rule: str, reference_date: str) -> dict[str, Any]:
    procedure_basis = basis("교원의 지위 향상 및 교육활동 보호를 위한 특별법", "제25조", "2026-02-19", reference_date, "시점확인필요")
    privacy_basis = basis("개인정보 보호법", "제23조", "2025-10-02", reference_date, "시점확인필요")
    common = {
        "speaker_role": "회의록상 발언자·진술자 및 발언 성격 확인 필요",
        "source_level": "E5",
        "confidence": "부족",
        "approval_status": "미검토",
        "human_decision": "담당자·법무 검토 전 초안",
    }
    if rule == "sensitive-health":
        return common | {
            "legal_issue_type": ["개인정보", "사실인정"],
            "risk_level": "높음",
            "action_code": "L",
            "statement_summary": "건강·치료·복약·장애 또는 심리상담과 관련될 수 있는 진술·질문·조치 기록",
            "legal_factor": ["N", "F"],
            "risk_type": ["민감정보 노출", "사실인정 근거 불명확"],
            "suggested_wording": "해당 정보가 결론에 필요한지와 근거자료를 분리 확인하고, 필요하면 발언 주체가 드러나는 직접 인용을 줄인 중립적 절차 기록으로 정리한다. 정보공개본은 별도 비공개 판단을 받는다.",
            "evidence_to_check": ["회의록 외 원자료 또는 제출서면", "정보가 조치 판단에 필요한지에 관한 기록", "정보공개 비공개 사유 검토"],
            "counterevidence": ["해당 정보와 무관한 객관적 행위 자료", "당사자 서면의견 또는 정정 자료"],
            "reasoning_summary": "민감정보 또는 그에 준하는 건강 관련 진술은 사실확정·조치수위의 근거와 분리하지 않으면 사생활 침해 및 불필요한 분쟁 확대 위험이 있다.",
            "legal_basis": [privacy_basis, procedure_basis],
            "recommended_scope": "양쪽",
        }
    if rule == "bias-or-reputation":
        return common | {
            "legal_issue_type": ["편견·예단", "사실인정"],
            "risk_level": "중간",
            "action_code": "N",
            "statement_summary": "성격·외양·평판 또는 주관적 인상에 의존할 수 있는 평가성 진술",
            "legal_factor": ["F", "I"],
            "risk_type": ["편견 또는 예단", "객관적 사실과 평가의 혼재"],
            "suggested_wording": "인상·평판 표현은 결론의 근거에서 제외하고, 시간·장소·행동·증거가 특정되는 사실과 출처로 바꿔 기록한다.",
            "evidence_to_check": ["직접 목격 또는 녹음·서면 자료", "상반된 진술과 사실확인 자료"],
            "counterevidence": ["주관적 평가와 다른 객관 자료", "당사자 반론 또는 정정 의견"],
            "reasoning_summary": "주관적 인상이나 평판은 행위의 고의·심각성 판단 근거로 사용하면 공정성 다툼을 키울 수 있다.",
            "legal_basis": [procedure_basis],
            "recommended_scope": "결재용",
        }
    if rule == "procedure-opportunity":
        return common | {
            "legal_issue_type": ["절차", "기록무결성"],
            "risk_level": "낮음",
            "action_code": "K",
            "statement_summary": "출석·의견진술·제척·통지·표결 등 절차 진행 또는 결과를 기록한 문구",
            "legal_factor": ["P", "R"],
            "risk_type": ["절차 이행 자료 누락 가능성", "기록 상호 불일치 가능성"],
            "suggested_wording": "회의록 문구는 유지하되, 통지·출석·서면의견·제척 확인·표결자료 등 원자료와 일치하는지 대조한다.",
            "evidence_to_check": ["소집·통지 자료", "출석부·서면의견", "제척·회피 확인 및 표결 기록"],
            "counterevidence": ["절차 미이행 또는 불일치를 보이는 문서"],
            "reasoning_summary": "절차 문구 자체는 문제로 단정할 수 없으나, 사후 다툼에서는 실제 이행자료와의 일치 여부가 핵심이다.",
            "legal_basis": [procedure_basis],
            "recommended_scope": "결재용",
        }
    if rule == "assessment-reason":
        return common | {
            "legal_issue_type": ["사실인정", "재량판단"],
            "risk_level": "중간",
            "action_code": "V",
            "statement_summary": "조치 수위·평가요소·점수 또는 그 사유에 관련된 진술",
            "legal_factor": ["F", "S", "D"],
            "risk_type": ["평가사유와 증거의 연결 부족", "재량 판단의 일관성 부족"],
            "suggested_wording": "확정된 사실, 평가기준, 점수·조치 사유를 구분해 적고, 추정·평판·관련 없는 과거사실은 근거에서 제외한다.",
            "evidence_to_check": ["사실인정 근거", "당시 적용 기준 및 배점·조치표", "표결·결정 이유 기록"],
            "counterevidence": ["상반된 진술·서면의견", "평가기준과 맞지 않는 사유"],
            "reasoning_summary": "평가 결과는 확인된 사실과 당시 적용 기준에 연결돼야 하며, 그 연결이 기록에 보이지 않으면 재량·비례성 다툼이 생길 수 있다.",
            "legal_basis": [procedure_basis],
            "recommended_scope": "결재용",
        }
    return common | {
        "legal_issue_type": ["사실인정", "기록무결성"],
        "risk_level": "중간",
        "action_code": "V",
        "statement_summary": "사실확정 전의 추정·전언 또는 근거가 명확하지 않을 수 있는 진술",
        "legal_factor": ["F", "E"],
        "risk_type": ["전언·추정의 사실화", "근거자료 누락"],
        "suggested_wording": "발언을 그대로 인용할 필요가 있으면 발언 주체와 진술임을 명시하고, 결론에는 확인된 자료만 근거로 적는다.",
        "evidence_to_check": ["직접 진술·서면·객관 자료", "진술 사이의 불일치 여부"],
        "counterevidence": ["반대 진술·정정 의견", "객관 자료와의 불일치"],
        "reasoning_summary": "전언 또는 추정은 별도 검증 없이 사실인정·조치 판단 근거로 사용하기 어렵다.",
        "legal_basis": [procedure_basis],
        "recommended_scope": "결재용",
    }


def adjust_location(issue: dict[str, Any]) -> None:
    """Apply a small set of metadata-only safeguards for recurring record types."""
    location = issue["location_id"]
    # These locations are procedural headings or statutory protection-measure labels,
    # not necessarily a person's medical fact.  Keep them in the review queue but
    # lower the automatic draft severity.
    if location in {
        "section-0/paragraph-1109", "section-0/paragraph-1137",
        "section-0/paragraph-1155", "section-0/paragraph-1174",
        "section-0/paragraph-1181",
    }:
        issue.update({
            "legal_issue_type": ["절차", "개인정보"], "risk_level": "중간", "action_code": "V",
            "statement_summary": "보호조치 또는 치료·상담 관련 조치의 법정 항목·표결을 기록한 문구",
            "suggested_wording": "조치의 법적 근거·의결내용은 유지하되, 구체적 건강상태나 불필요한 개인 사정이 함께 드러나지 않았는지 확인한다.",
            "reasoning_summary": "조치 항목의 기록 자체와 개인의 건강정보 공개 필요성은 구별해 검토해야 한다.",
        })
    if location == "section-0/paragraph-1059":
        issue.update({
            "risk_level": "높음", "action_code": "L", "legal_issue_type": ["재량판단", "절차", "법적 근거"],
            "statement_summary": "점수·조치 수준과 예외적 조치 선택의 연결을 기록한 진술",
            "suggested_wording": "당시 적용 기준, 예외 적용 요건, 표결 결과와 결정 사유의 일치 여부를 법무와 대조한 뒤 문구를 확정한다.",
            "reasoning_summary": "점수와 실제 조치의 관계 또는 예외 적용은 행정심판·소송에서 핵심 쟁점이 될 수 있어 근거·시점·비례성을 별도 확인해야 한다.",
        })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path, help="prepare_legal_review_template.py 출력 JSON")
    parser.add_argument("--output", required=True, type=Path, help="새 초안 JSON")
    parser.add_argument("--reference-date", default=dt.date.today().isoformat(), help="사건일 미확인 시 임시 검토 기준일 YYYY-MM-DD")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {args.output}")
        payload = read_json(args.template)
        case, issues = payload.get("case"), payload.get("issues")
        if not isinstance(case, dict) or not isinstance(issues, list):
            raise ValueError("법률위험 검토표 템플릿 형식이 올바르지 않습니다.")
        result: list[dict[str, Any]] = []
        for item in issues:
            if not isinstance(item, dict):
                raise ValueError("검토 항목은 객체여야 합니다.")
            rule = item.get("candidate_rule")
            if not isinstance(rule, str):
                raise ValueError("candidate_rule이 필요합니다.")
            draft = draft_for(rule, args.reference_date)
            completed = item | draft
            adjust_location(completed)
            result.append(completed)
        case = case | {"reviewer_role": "AI 보조 초안 — 담당자·법무 확인 전"}
        write_json(args.output, {
            "case": case,
            "issues": result,
            "note": "후보별 초안입니다. 사건·심의일과 당시 시행 법령, 사실·증거·정보공개 사유를 담당자 또는 법무가 확인하기 전에는 결재·공개본 수정 근거로 사용할 수 없습니다.",
            "draft_limitations": {
                "reference_date": args.reference_date,
                "reference_date_note": "사건일을 아직 받지 못해 임시 검토 기준일을 법령 시점 확인 필드에 넣었습니다. 확정 전 실제 사건·심의일로 교체해야 합니다.",
                "source_text": "원문·실명·직접 인용을 출력에 포함하지 않았습니다.",
            },
        })
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: draft_issues={len(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
