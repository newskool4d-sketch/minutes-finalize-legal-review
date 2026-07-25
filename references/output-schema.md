# 출력 스키마

## 법률위험 검토표 행

```json
{
  "location": "쪽·문단·표셀 식별자",
  "speaker_role": "발언자 역할",
  "statement_summary": "실명 없는 발언 요지",
  "source_level": "E1|E2|E3|E4|E5",
  "legal_factor": ["F", "S"],
  "risk_type": ["민감정보", "추측"],
  "risk_level": "높음|중간|낮음",
  "action_code": "K|S|N|D|L|V",
  "suggested_wording": "수정 제안",
  "evidence_to_check": ["시나리오", "보호자 서면"],
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

## 위험 코드

- `K`: 유지
- `S`: 요지화
- `N`: 중립화
- `D`: 삭제 검토
- `L`: 법무 확인
- `V`: 근거 확인
