# HWPX 처리 도구 사용법

## 범위와 안전 원칙

- `scripts/` 도구는 HWPX 원본을 수정하지 않고 새 파일만 생성한다.
- 실제 사건 HWPX, 검토 모델 JSON, 승인 목록, 산출물은 `case-data/` 또는 기관 승인 경로에서 관리하고 Git에 커밋하지 않는다.
- 복잡한 표·이미지·양식이 있는 실제 HWPX는 먼저 한글파일 처리 도구의 구조 분석을 수행한다. 이 스크립트는 승인된 전체 문구 치환만 지원하며, 문구가 여러 XML 텍스트 런에 나뉜 경우 자동 수정하지 않는다.
- 구조 검사는 ZIP·XML·문단/표 수 비교를 제공한다. 최종 제출 전에는 한글 프로그램에서 두 HWPX를 실제로 열어 형식·페이지·표 넘침을 확인한다.

## 1. 입력 검사와 검토 모델 추출

```powershell
py -X utf8 scripts/inspect_hwpx.py case-data/회의록_1차수정.hwpx --json case-data/inspect.json
py -X utf8 scripts/extract_minutes_model.py case-data/회의록_1차수정.hwpx --output case-data/minutes-model.json
```

`minutes-model.json`에는 회의록 원문이 포함될 수 있으므로 사건자료와 같은 접근통제로 관리한다.

## 2. 승인 목록 작성

아래 JSON은 로컬 사건 폴더에서만 작성한다. `approved: true`인 항목만 반영한다.

```json
{
  "edits": [
    {
      "id": "edit-001",
      "approved": true,
      "scope": "both",
      "from": "정정 전 전체 문구",
      "to": "정정 후 전체 문구",
      "reason": "오기 정정",
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
      "min_matches": 1
    }
  ]
}
```

일반 `edits`의 `scope` 값은 `both` 또는 `approval`만 사용한다. 이 수정은 두 HWPX에 동일하게 적용된다. 정보공개 청구용에만 적용하는 식별정보 처리는 반드시 `redactions`에 `scope: "disclosure"`로 기록한다. `from`은 XML 텍스트 런 하나 안에 있는 전체 문구와 정확히 일치해야 한다. 결과 파일이 이미 있거나 치환 횟수가 `min_matches`보다 작으면 도구가 중단한다.

역할 표기 주변의 성명 후보를 로컬 승인 목록으로 준비할 때는 다음을 사용한다. 이 JSON에는 실제 성명이 들어가므로 사건자료 경로에서만 관리한다.

```powershell
py -X utf8 scripts/prepare_redactions.py case-data/회의록_1차수정.hwpx `
  --output case-data/redaction-candidates.json
```

후보를 사람이 승인한 뒤 `approved: true`로 바꾸거나, 명시적으로 자동 승인 사용이 허용된 경우에만 `--approve-detected`를 사용한다.

## 3. 두 HWPX 생성

```powershell
py -X utf8 scripts/apply_approved_edits.py case-data/회의록_1차수정.hwpx `
  --approved case-data/approved-edits.json `
  --approval-output case-data/회의록_결재용_실명정본.hwpx `
  --disclosure-output case-data/회의록_정보공개청구용_비실명본.hwpx `
  --audit case-data/변경이력.json `
  --redaction-ledger case-data/비실명처리_대장.json
```

결재용 실명 정본은 승인된 일반 수정만 반영한다. 정보공개 청구용 비실명본은 같은 일반 수정 뒤 승인된 `redactions`만 추가 적용한다.

## 4. 교차검수

```powershell
py -X utf8 scripts/validate_hwpx.py case-data/회의록_결재용_실명정본.hwpx --compare-base case-data/회의록_1차수정.hwpx
py -X utf8 scripts/validate_hwpx.py case-data/회의록_정보공개청구용_비실명본.hwpx --compare-base case-data/회의록_1차수정.hwpx
py -X utf8 scripts/verify_release_pair.py `
  --approval case-data/회의록_결재용_실명정본.hwpx `
  --disclosure case-data/회의록_정보공개청구용_비실명본.hwpx `
  --approved case-data/approved-edits.json
```

`verify_release_pair.py`는 결재용 실명 정본에 승인된 비실명 처리만 적용했을 때 정보공개 청구용 비실명본과 정확히 같아지는지 확인한다. 승인 목록에 없는 문구 차이가 있으면 실패한다.

비실명 처리 후보를 별도 목록으로 대조하려면 다음을 사용한다. 결과에는 실제 검색어를 쓰지 않고 위치·항목번호·횟수만 남긴다.

```powershell
py -X utf8 scripts/scan_sensitive_content.py case-data/회의록_결재용_실명정본.hwpx `
  --terms case-data/identifiers.json --output case-data/식별정보_탐지결과.json
```

마지막으로 결재용 실명 정본과 정보공개 청구용 비실명본을 한글 프로그램에서 모두 열고, 체크리스트의 문단·표 구조·의결·표결·비실명 처리 대장 항목을 확인한다.
