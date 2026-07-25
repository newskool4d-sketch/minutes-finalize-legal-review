# 출력 스키마

## 법률위험 검토표 행

```json
{
  "issue_id": "issue-001",
  "location": "쪽·문단·표셀 식별자",
  "location_id": "section-1/paragraph-42",
  "speaker_role": "발언자 역할",
  "statement_summary": "실명 없는 발언 요지",
  "statement_text_hash": "SHA-256 또는 입력파일 내 위치 기반 식별자",
  "source_level": "E1|E2|E3|E4|E5",
  "legal_factor": ["F", "S"],
  "legal_issue_type": ["절차", "사실인정"],
  "risk_type": ["민감정보", "추측"],
  "risk_level": "높음|중간|낮음",
  "action_code": "K|S|N|D|L|V",
  "suggested_wording": "수정 제안",
  "evidence_to_check": ["시나리오", "보호자 서면"],
  "counterevidence": ["학생 또는 보호자 서면"],
  "reasoning_summary": "발언 요지와 확인된 자료가 절차·사실인정 쟁점으로 연결되는 이유",
  "legal_basis": [
    {
      "law_name": "법령명",
      "article": "제N조",
      "effective_date": "YYYY-MM-DD",
      "applicable_event_date": "YYYY-MM-DD",
      "retrieved_at": "YYYY-MM-DD",
      "source_type": "법령|고시|판례|재결례|내부규정",
      "source_id": "공식 URL 또는 식별자",
      "verification_status": "원문확인|시점확인필요|법무확인필요"
    }
  ],
  "recommended_scope": "결재용|정보공개청구용|양쪽",
  "confidence": "충분|부분|부족",
  "approval_status": "미검토|담당자 승인|수정 반영|법무 확인"
}
```

## 변경이력 행

```json
{
  "location": "쪽·문단·표셀 식별자",
  "before_summary": "변경 전 요지",
  "after_summary": "변경 후 요지",
  "reason": "오기|형식|중립화|중복|법률위험|표결 보완",
  "evidence": ["시나리오", "표결지"],
  "reviewer": "검토자 역할",
  "approval_status": "제안|승인|반려|법무 확인"
}
```

## 비실명처리 대장 행

```json
{
  "location": "쪽·문단·표셀 식별자",
  "source_value_summary": "실명 원문을 그대로 저장하지 않는 식별정보 요지",
  "redaction_type": "성명|기관명|연락처|주소|기타 직접식별정보",
  "replacement": "○○|역할명|승인된 대체 표기",
  "reason": "정보공개 청구용 비실명 처리",
  "scope": "정보공개청구용 비실명 HWPX만",
  "approval_status": "제안|승인|반려|정보공개 담당 확인",
  "reviewer": "검토자 역할"
}
```

## 위험 코드

- `K`: 유지
- `S`: 요지화
- `N`: 중립화
- `D`: 삭제·가림 검토(자동 반영 금지)
- `L`: 법무 확인
- `V`: 근거 확인

## 검토표 생성 전제

`scripts/render_legal_review_report.py`는 회의록을 직접 전송하거나 법률 결론을 자동 생성하지 않는다. 담당자가 작성한 **비식별** JSON을 검증해 Markdown 검토표로 렌더링한다. 특히 `높음` 위험은 `L` 법무 확인, 발언 요지, 확인 자료, 법령 근거와 시행일·사건 기준일을 모두 갖추지 않으면 생성하지 않는다.
