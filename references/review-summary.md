# 검수요약 계약 (N06)

`scripts/render_review_summary.py`는 현재 로컬 자료를 직접 재검산하여 원문 없는 Markdown·JSON 요약을 만듭니다. 저장된 검증 보고서의 PASS, `completed: true`, 파일 존재만으로 통과시키지 않습니다. 법적 타당성이나 사람 확인 진술의 진위를 인증하지 않습니다.

## 실행

실제 업무자료는 사전 승인된 제한 작업공간에서만 사용합니다. 아래는 경로 예시이며 repo에 실제 자료를 저장하라는 뜻이 아닙니다.

```powershell
python -B -X utf8 scripts/render_review_summary.py `
  --source 'C:\approved-workspace\source.hwpx' `
  --approved 'C:\approved-workspace\approved.json' `
  --approval 'C:\approved-workspace\approval.hwpx' `
  --disclosure 'C:\approved-workspace\disclosure.hwpx' `
  --legal-review 'C:\approved-workspace\legal-review.json' `
  --human-evidence 'C:\approved-workspace\human-evidence.json' `
  --output 'C:\approved-workspace\review-summary.md' `
  --json 'C:\approved-workspace\review-summary.json'
```

`--legal-review`·`--human-evidence`는 선택이며 생략 시 PARTIAL입니다. `--output`·`--json`은 필수이고 서로 다른 새 경로여야 합니다. 기존 파일·입력 파일·선택 입력과의 경로 겹침을 거부하고 exclusive-create로 덮어쓰기를 차단합니다. 정상/PARTIAL은 exit 0, FAIL·인자/출력 계약 위반은 exit 1입니다. 잘못된 입력도 가능한 범위에서 안전한 FAIL 요약을 생성하지만 기존 파일은 변경하지 않습니다. 쓰기 중 I/O 실패 시 새 빈 파일이 남을 수 있으므로 완료 산출물로 취급하지 않습니다.

## 현재 자료 재검산

매번 자료를 한 번 캡처한 바이트에서 SHA-256 계산·JSON/ZIP 파싱·검증을 수행합니다. 해시를 계산한 뒤 경로를 다시 읽어 다른 내용으로 검증하지 않습니다. 종료 전에는 경로의 현재 바이트를 캡처와 재대조하고, 선택 입력인 담당자 확인 기록도 이 안정성 검사에 포함합니다.

| JSON 결속 키 | 고정 출력 참조 | 자료 |
| --- | --- | --- |
| `source` | `artifact:source` | 실제 원본 HWPX |
| `approved_plan` | `artifact:approved-plan` | 승인 계획 JSON |
| `approval` | `artifact:approval` | 결재용 HWPX |
| `disclosure` | `artifact:disclosure` | 공개용 HWPX |
| `legal_review` | `artifact:legal-review` | 법률 검토 JSON |

원본 계약 v2·`structural-v2`를 검증하고 원본/두 출력의 구조를 비교합니다. 세 HWPX의 ZIP 중복 엔트리명은 거부합니다. 공통 `build_entry_pair`·`compare_entries`로 원본·승인 계획에서 출력 엔트리 바이트를 다시 계산하고, ZIP 패키지/엔트리 주석·확장 필드도 대조합니다.

법률 JSON은 `validate_payload` 형식 검사, 루트 `location_scheme`, `case.source_document_hash`, 개별 `location_id`와 공통 parser `own_text` SHA-256을 대조합니다. 명시적 해시 불일치는 FAIL, 위치/해시/좌표계가 불명확하면 PARTIAL입니다. 명시적으로 다른 좌표계는 FAIL입니다. 유효한 case에 `issues: []`이면 발견사항을 만들지 않고 PARTIAL로 남기며 malformed case는 FAIL입니다.

문단 해시는 앞뒤 공백을 포함한 `own_text` 원문 그대로 계산합니다. 구버전 후보에서 공백을 제거한 해시를 만들었다면 현재 원본에서 후보를 다시 생성하고 재검토합니다. 기존 승인 상태나 담당자 확인을 자동 승계하지 않습니다.

미검토·반려, 충분하지 않은 confidence, 사건·심의·처분·정본화 일자 미확인, 원문확인이 아닌 법적 근거 또는 근거 시점 미확인은 미해결로 집계합니다. `높음`/`L`은 항목 자체가 `법무 확인`이 되기 전에는 미해결입니다. `V`+`담당자 승인`도 PARTIAL이며 `수정 반영` 또는 `법무 확인`일 때만 다른 요건을 대조해 해결로 셉니다. 전체 사람 완료 진술이 개별 미확인을 덮지 않습니다. 날짜는 달력 유효성도 검사하지만 법령 내용·관할·사건 적용의 실질적 타당성은 자동 판단하지 않습니다.

`수정 반영`은 상태 문자열만으로 해결되지 않습니다. 같은 `issue_id`의 승인 항목이 해당 `location_id`에서 실제 변경을 일으켰고, 권고 범위에 맞는 최종 산출물에 변경이 남아 있어야 합니다. 다른 이슈·다른 위치의 수정, 무변경 치환, 결재용 수정 대신 공개용만 가린 경우는 근거가 되지 않습니다. 후속 수정 때문에 해당 수정의 잔존 여부를 입증할 수 없으면 PARTIAL로 남깁니다. 정당한 무수정 결론은 실제 검토 결과에 따라 `법무 확인` 등 해당 상태로 기록하며 AI가 임의로 상태를 바꾸지 않습니다.

현재 자동 증명은 해당 문단의 마지막 실제 변경에 결속합니다. 같은 문단에서 서로 다른 이슈의 수정을 연속 적용하면 선행 수정이 남아 있더라도 자동 증명 범위를 벗어나 PARTIAL이 될 수 있습니다. 이는 담당자 재검토 대상으로 표시하며 미확인을 완료로 바꾸지 않습니다.

## 사람 증거 schema_version 1

[미완료 예시](../examples/human-evidence.example.json)는 승인이나 확인을 만들어내지 않는 빈 대장입니다. null 해시는 실제 다섯 파일의 해시로 채워야 합니다. 원문·실명·파일 경로·자유 사유는 기록하지 않습니다.

최상위 `artifact_hashes`의 다섯 키는 위 표와 같습니다. 누락/null은 PARTIAL, 잘못된 형식·현재 자료와 다른 해시는 FAIL입니다. 법률 자료가 없으면 모든 결속이 확인된 것으로 취급하지 않습니다.

`checks`는 다음 고정 ID만 사용합니다.

| 확인 ID | `reviewer_role` 고정값 | 확인 대상 |
| --- | --- | --- |
| `approval_open` | `document_reviewer` | 현재 결재용 파일 한글 실물 열람 |
| `disclosure_open` | `document_reviewer` | 현재 공개용 파일 한글 실물 열람 |
| `legal_review` | `legal_reviewer` | 법률 검토 담당 확인 |
| `public_decision` | `disclosure_officer` | 공개 판단 및 미검사 자원·잔존어 전건 확인 |
| `final_confirmation` | `final_owner` | 최종 담당 확인 |

항목별 `result`는 `pass`, `pending`, `fail` 중 하나입니다. `pass`에는 위 고정 역할 ID, 시간대 있는 ISO 8601 `checked_at`, 비어 있지 않은 `evidence_refs` 배열이 필요합니다. 예: `2026-10-30T15:00:00+09:00`, `["record:open-001"]`. 참조는 공통 승인 계약의 ASCII `scheme:ref-id` 정규식만 인정하며 원문·URL·경로·문장을 넣지 않습니다. 메타 누락은 PARTIAL, 잘못된 역할·시각·참조는 FAIL입니다. 역할 ID는 실명·실제 역할 분리나 독립성을 인증하지 않습니다.

현재 재계산한 공개 패키지에 미검사 자원 또는 잔존 검사어가 있으면 `public_decision.coverage`에 모든 참조를 명시합니다.

```json
{
  "result": "pass",
  "reviewer_role": "disclosure_officer",
  "checked_at": "2026-10-30T15:00:00+09:00",
  "evidence_refs": ["record:public-001"],
  "coverage": {
    "manual_entry_ids": ["zip-entry-5", "zip-entry-6"],
    "finding_ids": ["finding-1"]
  }
}
```

`manual_entry_ids`는 `disclosure_package.manual_review_refs`, `finding_ids`는 `disclosure_package.residual_finding_refs`의 현재 집합과 각각 일치해야 합니다. 대표 1건·중복 참조·과거 보고서·전역 completed는 전건 확인이 아닙니다. 필요한 참조 누락은 PARTIAL입니다. 원본 ZIP 이름·미검사 사유 원문·잔존 검사어는 요약에 복제하지 않습니다. 전건 확인은 담당자의 판단 진술이며 자원 자동 삭제나 외부 공개 실행이 아닙니다.

## 판정·개인정보 경계

- `quality_result: PASS`: 현재 자료의 기술요건과 제공 사람 증거의 형식·결속·전건 확인 충족. 법적 타당성·한글 실제 실행의 진위·외부 공개 승인 인증이 아님.
- `PARTIAL`: 유효한 결과와 필수 미확인 공존.
- `FAIL`: 현물·계약·해시·명시적 실패 등 필수 불일치 확인.
- `external_release_authorized: false`는 항상 유지합니다. `disclosure_package.release_ready: false`도 사람 완료 여부와 무관하게 보존합니다.

Markdown은 다섯 사람 확인을 한글 항목명·상태·고정 역할·조치로 나누고 안전한 `zip-entry-N`/`finding-N` 참조와 전건 확인 상태를 표시합니다. JSON `next_actions`는 미해결 그룹만 포함하며 PASS에는 별도 기관 공개 승인 확인 알림만 남습니다.

출력은 고정 artifact 참조·해시·상태·건수·전건 검토 참조·고정 담당 역할/다음 조치로 제한합니다. 원문·발언 요지·실명·입력 issue ID·자유 사유·증거 참조 문자열·원본 경로·예외 메시지를 복제하지 않습니다. 오류는 일반 코드로만 표시합니다. 항상 `전사 원본 대조 미실행: 전사 누락·전사 정확도 확인 불가`를 표시하며, 전사 원본이 없다고 추정하지 않습니다. 실제 자료·외부 MCP·한글 UI·설치본·레지스트리는 합성 검증 범위 밖입니다.
