# 출력 스키마

## 실행 승인 계약 v2

`apply_approved_edits.py`, `verify_release_pair.py`와 샘플 계획 생성기는 아래 계약을 사용한다.

```json
{
  "schema_version": 2,
  "location_scheme": "structural-v2",
  "source_sha256": "실제 원본 파일 바이트의 64자리 SHA-256 hex",
  "edits": [],
  "redactions": []
}
```

모든 항목은 배열 간에도 고유한 `id`와 명시적 `scope`를 가진다. `edits`는 `both|approval|양쪽|결재용`, `redactions`는 `disclosure|정보공개청구용`만 허용한다. `approved: true`인 항목은 아래 승인 연결 필드를 모두 갖춰야 한다.

```json
{
  "issue_id": "issue-001",
  "decided_by_role": "정보공개 담당자",
  "decided_at": "2026-10-30T09:00:00+09:00",
  "evidence_refs": ["review:issue-001", "source:section-0.paragraph-42"],
  "reason": "검토된 수정·가림 사유"
}
```

`evidence_refs`는 비어 있지 않은 문자열 배열이며 원문 대신 ASCII `scheme:ref-id` 식별자만 사용한다. scheme은 소문자로 시작하는 영숫자·점·하이픈, 참조 토큰은 영숫자로 시작하는 영숫자·점·밑줄·하이픈만 허용한다. URL·쿼리·경로·공백·한글 문장·인용문은 거부하고 별도 제한 작업공간의 근거와 연결한다. 공식 URL은 법률 근거의 `source_id`에서 별도로 관리한다. `decided_at`은 시각과 시간대를 포함한 유효한 ISO 8601 값이다. `approved` 누락 또는 `false`는 반영하지 않는다. `approved: true`와 `approval_status: 반려|미검토|제안|검토 중|승인 필요|추가 승인 필요|rejected|unreviewed|pending`의 충돌은 실패한다.

무버전·구버전 JSON은 자동 승인이나 자동 이관하지 않는다. 원본을 재검토한 뒤 현재 원본 해시와 실제 승인자 역할·시각·근거 참조·사유를 입력하고 다시 승인해야 한다. 해시 불일치도 재검토 대상이다. 변경이력과 비실명처리 대장에는 `id` 및 위 승인 필드를 그대로 연결하고 `from` 원문은 저장하지 않는다.

### N04 위치 계약

`location_scheme`은 `structural-v2`만 허용한다. `location`은 `section-0/paragraph-1` 또는 `section-0/table-1/row-1/cell-1/paragraph-1`이며 중첩 표는 셀 뒤에 같은 table/row/cell 계층을 반복한다. section은 0부터, 문단·표·행·셀은 각 소유 계층 안에서 1부터 센다. 부모 문단의 자체 텍스트에는 하위 문단을 포함하지 않는다. 모든 좌표 생산자는 동일한 공통 파서를 사용한다.

`approved: true` 일반 치환은 `location` 또는 명시적인 `match_scope: "document"`가 필요하며 둘은 함께 쓸 수 없다. 문장 전체 비공개에는 문서 범위를 허용하지 않는다. 구 좌표의 묵시적 이관은 거부한다. 후보·모델·문맥·검토 템플릿에도 같은 `location_scheme`을 전달하며 문맥 내보내기는 `source_document_hash`를 실제 원본 해시와 대조한다.

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
      "jurisdiction": "대한민국",
      "law_name": "법령명",
      "article": "제N조",
      "promulgation_date": "YYYY-MM-DD|미확인",
      "effective_date": "YYYY-MM-DD",
      "applicable_event_date": "YYYY-MM-DD|미확인",
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
  "redaction_type": "성명|기관명|연락처|주소|기타 직접식별정보|문장 비공개",
  "replacement": "○○|역할명|승인된 대체 표기",
  "reason": "정보공개 청구용 비실명 처리",
  "scope": "정보공개청구용 비실명 HWPX만",
  "approval_status": "제안|승인|반려|정보공개 담당 확인",
  "human_decision": "담당자 승인|정보공개 담당 확인|법무 확인",
  "min_matches": 1,
  "max_matches": 1,
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

`문장 비공개`는 정보공개 청구용에만 쓴다. `location`, `reason`, `human_decision`과 `min_matches: 1`, `max_matches: 1`을 모두 기록하고 결재용 실명 정본에는 원문을 유지한다.

법령의 공포일·시행일·사건 기준일은 서로 다른 필드다. 아직 확인하지 못한 공포일·사건 기준일은 임의 날짜를 넣지 않고 `미확인`으로 기록하며, 이 경우 `verification_status`는 `시점확인필요` 또는 `법무확인필요`여야 한다.

## 공개본 패키지 검사 결과

변경이력과 쌍 검사 결과의 `disclosure_package`는 `findings`, `coverage.checked_entries`, `coverage.manual_review_entries`, `configured_terms_check_pass`, `preview_changes`, `release_ready`를 포함한다. `findings`는 원문 대신 엔트리 참조·위치·검사어 ID·횟수를 기록한다. `preview_changes`는 표준 미리보기의 중립 대체만 기록한다. 쌍 검사 결과의 `technical_pair_valid`는 법률 검토나 정보공개 승인과 별개이며, 자동 도구는 `release_ready`를 `false`로 유지한다.

## 검토표 렌더링 전제

`scripts/render_legal_review_report.py`는 회의록을 직접 전송하거나 법률 결론을 자동 생성하지 않는다. 담당자가 작성한 **비식별** JSON을 검증해 Markdown 검토표로 렌더링한다. 특히 `높음` 위험은 `L` 법무 확인, 발언 요지, 확인 자료, 법령 근거와 시행일·사건 기준일을 모두 갖추지 않으면 생성하지 않는다.

## 최종 검수요약

정확한 입력·필드·확인 기록 예시는 [검수요약 계약](review-summary.md)을 따른다. 원본·승인 계획·결재용·공개용·법률 검토표는 안전한 고정 참조와 SHA-256으로 연결한다. 원문·실제 경로·자유서술 사유는 요약으로 복사하지 않는다.

`quality_result`는 `PASS|PARTIAL|FAIL`이며 기술 검사와 입력된 담당자 확인 기록의 완결성만 평가한다. `external_release_authorized`는 항상 `false`다. 담당자 기록은 파일 해시·역할 코드·시간대가 있는 시각·원문 없는 근거 참조를 포함하지만 실제 담당자 인증을 대신하지 않는다. 법령 근거 미확인·한글 열기 미실행·공개본 미검사 자원은 다음 담당자 조치로 남긴다.
