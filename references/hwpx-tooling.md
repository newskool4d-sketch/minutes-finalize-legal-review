# HWPX 처리 도구 사용법

## 범위와 안전 원칙

- `scripts/` 도구는 HWPX 원본을 수정하지 않고 새 파일만 생성한다.
- 실제 사건 HWPX, 검토 모델 JSON, 승인 목록, 산출물은 저장소·설치 폴더 밖의 기관 승인 제한 작업공간에서 관리하고 Git에 커밋하지 않는다. [저장 경계](storage-boundaries.md)를 따른다.
- 복잡한 표·이미지·양식이 있는 실제 HWPX는 먼저 한글파일 처리 도구의 구조 분석을 수행한다. 승인된 문구는 같은 문단의 여러 텍스트 런에 걸쳐 치환할 수 있지만, 문단·셀 경계를 넘지 않는다. 내부 markup이 있는 텍스트 노드는 자동 편집하지 않고 중단한다.
- 구조 검사는 ZIP·XML·문단/표 수 비교를 제공한다. 최종 제출 전에는 한글 프로그램에서 두 HWPX를 실제로 열어 형식·페이지·표 넘침을 확인한다.

## 1. 입력 검사와 검토 모델 추출

저장소 또는 설치본 폴더에서 명령을 실행한다. `$caseRoot`는 기관이 이미 승인한 repo·설치 폴더 밖의 실제 절대경로로 바꾸며, 도구가 폴더 승인·접근권한을 설정하지 않는다.

```powershell
$caseRoot = '<기관에서 승인한 repo·설치 폴더 밖 제한 작업공간 절대경로>'
py -X utf8 scripts/inspect_hwpx.py "$caseRoot/회의록_1차수정.hwpx" --json "$caseRoot/inspect.json"
py -X utf8 scripts/extract_minutes_model.py "$caseRoot/회의록_1차수정.hwpx" --output "$caseRoot/minutes-model.json"
```

`minutes-model.json`에는 회의록 원문이 포함될 수 있으므로 사건자료와 같은 접근통제로 관리한다.

## 2. 승인 목록 작성

아래 JSON은 로컬 사건 폴더에서만 작성한다. 승인 계약 v2와 실제 원본 해시가 일치하고 필수 승인 메타가 있는 `approved: true` 항목만 반영한다. 예시 해시·역할·시각은 실제 검토 결과로 교체하며 도구가 승인 메타를 만들어 주지 않는다.

```json
{
  "schema_version": 2,
  "location_scheme": "structural-v2",
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "edits": [
    {
      "id": "edit-001",
      "approved": true,
      "scope": "both",
      "location": "section-0/paragraph-12",
      "from": "정정 전 전체 문구",
      "to": "정정 후 전체 문구",
      "reason": "오기 정정",
      "issue_id": "issue-001",
      "decided_by_role": "담당 검토자",
      "decided_at": "2026-10-30T09:00:00+09:00",
      "evidence_refs": ["review:issue-001"],
      "min_matches": 1
    }
  ],
  "redactions": [
    {
      "id": "redact-001",
      "approved": true,
      "scope": "disclosure",
      "from": "식별정보 전체 문구",
      "to": "○○",
      "location": "section-0/paragraph-12",
      "redaction_type": "성명",
      "reason": "정보공개 청구용 비실명 처리",
      "issue_id": "issue-002",
      "decided_by_role": "정보공개 담당자",
      "decided_at": "2026-10-30T09:00:00+09:00",
      "evidence_refs": ["review:issue-002"],
      "min_matches": 1
    }
  ]
}
```

일반 `edits`의 `scope` 값은 `both` 또는 `approval`만 사용한다. 이 수정은 두 HWPX에 동일하게 적용된다. 정보공개 청구용에만 적용하는 식별정보 처리는 반드시 `redactions`에 `scope: "disclosure"`로 기록한다. `from`은 지정 문단의 자체 텍스트와 정확히 일치하는 문구여야 한다. 결과 파일이 이미 있거나 치환 횟수가 `min_matches`보다 작으면 도구가 중단한다.

### N04 공통 좌표·치환 계약

승인 목록과 모델·탐지 후보·문맥 출력은 `location_scheme: "structural-v2"`를 명시한다. 본문은 `section-0/paragraph-1`, 표 셀은 `section-0/table-1/row-1/cell-1/paragraph-1`, 중첩 표는 해당 셀 뒤에 `/table-1/row-1/cell-1/paragraph-1`을 잇는다. section은 0부터, 나머지는 1부터 센다. 문단·표는 section 또는 셀별, 행은 표별, 셀은 행별 순번이다. `run`·`subList`는 좌표를 바꾸지 않으며 부모 문단 텍스트에는 하위 셀 문단을 합치지 않는다.

일반 치환도 `location`이 지정한 문단에만 적용한다. 문서 전체의 반복 성명 등을 모두 치환하려면 `location`을 빼고 `match_scope: "document"`를 명시한다. 둘을 함께 지정할 수 없다. 성명 준비 도구는 이 문서 범위를 미승인 후보에 명시한다. 문장 전체 비공개는 반드시 한 `location`에 결속한다. 과거 평면 좌표는 같은 문자열처럼 보여도 자동 승계하지 않고 원본·좌표를 재검토한다. 문맥 내보내기는 후보의 원본 해시도 실제 입력과 대조한다.

UTF-8 XML은 namespace를 해석한 공통 Expat 파서로 텍스트 byte 범위를 찾고 그 범위만 수정한다. 다른 태그·속성·접두어·표·런 바이트를 보존하며, 내부 markup·CDATA·주석이 든 텍스트 노드와 DTD 등 미지원 경계는 자동 편집하지 않는다. 이는 한글 프로그램 실물 검증을 대체하지 않는다.

실무자 판단에 따라 공개가 곤란한 **문장 전체**도 정보공개 청구용에서만 `[비공개]`로 가릴 수 있다. 이때도 `edits`가 아니라 `redactions`에 아래처럼 기록한다. 결재용에는 원문을 유지하며, 같은 문장이 여러 곳에 있어도 과다 가림이 생기지 않도록 정확히 한 곳만 처리한다.

```json
{
  "id": "mask-sentence-001",
  "approved": true,
  "scope": "disclosure",
  "from": "승인된 비공개 대상 문장 전체",
  "to": "[비공개]",
  "location": "section-0/paragraph-42",
  "redaction_type": "문장 비공개",
  "reason": "정보공개 시 제3자 권익 또는 심의 공정성 침해 우려",
  "human_decision": "정보공개 담당 확인",
  "issue_id": "issue-003",
  "decided_by_role": "정보공개 담당자",
  "decided_at": "2026-10-30T09:00:00+09:00",
  "evidence_refs": ["review:issue-003"],
  "min_matches": 1,
  "max_matches": 1
}
```

역할 표기 주변의 성명 후보를 로컬 승인 목록으로 준비할 때는 다음을 사용한다. 이 JSON에는 실제 성명이 들어가므로 사건자료 경로에서만 관리한다.

```powershell
py -X utf8 scripts/prepare_redactions.py "$caseRoot/회의록_1차수정.hwpx" `
  --output "$caseRoot/redaction-candidates.json"
```

후보를 사람이 검토한 뒤 `approved: true`와 이슈 ID·검토자 역할·시간대가 있는 승인 시각·근거 참조·사유를 기록한다. `--approve-detected`는 호환 옵션일 뿐 `approved: false`, `추가 승인 필요`로 기록하며 승인 메타를 자동 생성하지 않는다. 근거는 원문 문장 대신 `review:issue-001`과 같은 ASCII 참조 ID로 연결한다. 구버전·무버전 승인 목록은 명시적 재검토 후 v2로 다시 작성해야 하며 기존 승인 상태를 자동 승계하지 않는다.

로컬 샘플 문장 계획에도 승인 결정을 명시한다. `--base`의 v2 원본 해시는 `--input`과 일치해야 한다.

```powershell
py -X utf8 scripts/build_sample_sentence_mask_plan.py --input "$caseRoot/회의록_1차수정.hwpx" `
  --base "$caseRoot/approved-edits.json" --output "$caseRoot/sample-plan.json" `
  --location section-0/paragraph-42 --reason "검토된 샘플 가림 사유" --decision "정보공개 담당 확인" `
  --issue-id issue-003 --decided-by-role "정보공개 담당자" --decided-at "2026-10-30T09:00:00+09:00" `
  --evidence-ref review:issue-003
```

## 3. 두 HWPX 생성

```powershell
py -X utf8 scripts/apply_approved_edits.py "$caseRoot/회의록_1차수정.hwpx" `
  --approved "$caseRoot/approved-edits.json" `
  --approval-output "$caseRoot/회의록_결재용_실명정본.hwpx" `
  --disclosure-output "$caseRoot/회의록_정보공개청구용_비실명본.hwpx" `
  --audit "$caseRoot/변경이력.json" `
  --redaction-ledger "$caseRoot/비실명처리_대장.json"
```

결재용 실명 정본은 승인된 일반 수정만 반영한다. 정보공개 청구용 비실명본은 같은 일반 수정 뒤 승인된 `redactions`만 추가 적용한다.

## 4. 교차검수

```powershell
py -X utf8 scripts/validate_hwpx.py "$caseRoot/회의록_결재용_실명정본.hwpx" --compare-base "$caseRoot/회의록_1차수정.hwpx"
py -X utf8 scripts/validate_hwpx.py "$caseRoot/회의록_정보공개청구용_비실명본.hwpx" --compare-base "$caseRoot/회의록_1차수정.hwpx"
py -X utf8 scripts/verify_release_pair.py `
  --source "$caseRoot/회의록_1차수정.hwpx" `
  --approval "$caseRoot/회의록_결재용_실명정본.hwpx" `
  --disclosure "$caseRoot/회의록_정보공개청구용_비실명본.hwpx" `
  --approved "$caseRoot/approved-edits.json"
```

`verify_release_pair.py`는 실제 원본 해시를 승인 목록과 대조하고, 생성기와 공유하는 `build_entry_pair(entries, specification)` 계산으로 일반 수정과 비실명 처리를 재현한 뒤 두 HWPX의 모든 ZIP 엔트리 바이트를 각각 대조한다. 두 산출물에 같은 무승인 변경이 들어가도 실패한다. `--source`는 필수다.

`apply_approved_edits.py`는 텍스트가 변경된 산출물의 `hp:linesegarray` 레이아웃 캐시를 결재용·정보공개용 모두에서 제거한다. 한글은 열 때 캐시를 다시 계산하므로, 변경 전 문장 길이를 기준으로 남은 캐시 때문에 열기 오류가 생기는 것을 막기 위한 조치다. 변경이력의 `layout_cache`에서 제거 건수를 확인한다.

비실명 처리 후보를 별도 목록으로 대조하려면 다음을 사용한다. 결과에는 실제 검색어를 쓰지 않고 위치·항목번호·횟수만 남긴다.

```powershell
py -X utf8 scripts/scan_sensitive_content.py "$caseRoot/회의록_결재용_실명정본.hwpx" `
  --terms "$caseRoot/identifiers.json" --output "$caseRoot/식별정보_탐지결과.json"
```

마지막으로 결재용 실명 정본과 정보공개 청구용 비실명본을 한글 프로그램에서 모두 열고, 체크리스트의 문단·표 구조·의결·표결·비실명 처리 대장 항목을 확인한다.

## 5. 미리보기·비본문 검사와 공개 준비 상태

정보공개용은 표준 `Preview/PrvText.txt`와 `Preview/PrvImage.png`를 중립 안내문·흰색 썸네일로 교체한다. 입력본과 결재용의 미리보기는 보존한다. 이는 본문 가림 뒤 미리보기에 원문이 남는 것을 방지하는 패키지 처리이며, 본문이나 기타 첨부의 자동 삭제 기능이 아니다.

표준 미리보기 자원을 본문에서도 직접 또는 매니페스트 ID로 참조하는 특수 문서는 자동 교체를 중단한다. 이 경우 담당자가 본문 자원을 분리·확인한 뒤 다시 처리해야 하며, 도구가 본문 그림까지 흰색으로 바꾸지 않는다.

`scan_sensitive_content.py`는 본문 위치 외에도 XML 속성·주석·처리명령(루트 밖 포함), HWPX 메타데이터, UTF-8/UTF-16 텍스트 파일에서 설정한 검사어를 찾는다. 결과에는 검사어 자체 대신 `term_id`, 위치, 횟수를 남긴다. 식별정보가 파일명에 있으면 파일명 대신 ZIP 엔트리 ID를 표시한다.

이미지·차트·첨부·불명확한 인코딩·미지원 구조는 `coverage.manual_review_entries`에 남긴다. 이미지 안 글자나 첨부 내부를 자동으로 읽었다고 간주하지 않는다. 기타 메타데이터에서 검사어가 발견돼도 승인 없이 지우지 않고 담당자 검토 대상으로 남긴다.

- `configured_terms_check_pass`: 설정한 검사어의 잔존과 미검사 자원이 없을 때만 참. 모든 개인정보를 찾아냈다는 보장은 아니다.
- `technical_pair_valid`: 입력본·승인 계획·지정된 미리보기 처리로 두 결과가 설명되는지에 대한 기술 검사.
- `release_ready`: 자동 처리 도구는 항상 `false`로 남긴다. 법률 검토·정보공개 범위 판단·실물 확인을 끝낸 사람이 최종 제출 여부를 결정한다.

생성기의 변경이력과 쌍 검사 JSON의 `disclosure_package`에 같은 범위·미리보기 처리 결과를 기록한다. 구조 검사·치환 성공만으로 정보공개용의 개인정보 검수가 완료된 것으로 처리하지 않는다.

## 6. 검수요약과 다음 담당자 확인

```powershell
py -X utf8 scripts/render_review_summary.py `
  --source "$caseRoot/회의록_1차수정.hwpx" --approved "$caseRoot/approved-edits.json" `
  --approval "$caseRoot/회의록_결재용_실명정본.hwpx" `
  --disclosure "$caseRoot/회의록_정보공개청구용_비실명본.hwpx" `
  --legal-review "$caseRoot/review.json" --human-evidence "$caseRoot/human-evidence.json" `
  --output "$caseRoot/검수요약.md" --json "$caseRoot/검수요약.json"
```

담당자 확인 전에는 선택 옵션 `--human-evidence`를 생략한다. 법률 검토표도 없으면 `--legal-review`를 생략하고 미확인으로 남긴다. 검수요약은 현재 파일의 구조·승인 반영·공개 패키지를 재계산하며 과거 PASS 파일을 입력으로 받지 않는다. 출력에는 원문·실제 경로를 싣지 않는다.

기술 검사와 다섯 담당자 확인(결재용 열기·공개용 열기·법무·정보공개·최종 확인)을 구분하고, 잔존 식별정보·수동 확인 자원은 개별 ID로 추적한다. 자세한 확인 기록·해시 결속·PASS/PARTIAL/FAIL의 의미는 [검수요약 계약](review-summary.md)을 따른다. 이 기록의 형식 검증은 실제 담당자 인증이나 외부 공개 허가가 아니다.
