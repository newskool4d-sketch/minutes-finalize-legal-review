# 운영 성과지표

실제 사건 내용·실명·회의록 문구를 기록하지 않고, 심의 단위의 집계 수치만 남긴다.

## 기록 항목

```json
{
  "case_token": "기관 내부 비식별 식별자",
  "pages": 0,
  "review_minutes_before": 0,
  "review_minutes_after": 0,
  "officer_review_minutes": 0,
  "supervisor_review_minutes": 0,
  "ai_suggestions": 0,
  "approved_suggestions": 0,
  "rejected_suggestions": 0,
  "rejection_reason_codes": ["근거부족", "사실불일치"],
  "high_risk_items": 0,
  "legal_confirmation_items": 0,
  "human_found_omissions": 0,
  "metadata_or_vote_errors": 0,
  "hwpx_structure_pass": true,
  "hancom_open_pass": true
}
```

반려 사유에는 회의록 문장·실명·자유서술을 넣지 않고 `근거부족`, `사실불일치`, `범위과다`, `표현부적절`, `기관기준확인`, `법무확인`, `기타비식별` 중 코드만 사용한다. 기록 전에는 다음으로 형식을 확인한다.

```powershell
py -X utf8 scripts\validate_operation_metrics.py .\case-data\operation-metrics.json
```

3건 이상 누적되면 개인·사건 식별자나 회의록 내용 없이 집계합니다.

```powershell
py -X utf8 scripts\summarize_pilot_metrics.py `
  .\case-data\metric-001.json .\case-data\metric-002.json .\case-data\metric-003.json `
  --output .\case-data\pilot-summary.json
```

집계 결과에는 건수, 시간 절감률, 제안 수용·반려율, 한글 열기·구조 실패 건수, 사람이 발견한 누락 수, 비식별 반려 사유 코드만 들어갑니다. `case_token`은 중복 확인에만 쓰고 출력에는 포함하지 않습니다.

## 활용 기준

- 3~5건 시범 적용 후 승인률·반려 사유·치명적 누락을 검토한다.
- 10건 이상 누적 시 검토시간 절감과 높은 위험 항목 누락 여부를 분석한다.
- 치명적 위험 누락, 사실·표결 변형, HWPX 열기 실패는 건수와 관계없이 즉시 원인 분석 후 수정한다.
