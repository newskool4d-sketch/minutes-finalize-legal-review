# 회의록 정본화·법률검토 스킬

HWPX 회의록의 1차 수정본을 2차 정본으로 정리하면서, 발언별 법률·절차 위험과 근거자료를 함께 검토하는 범용 스킬입니다.

- 스킬 버전: `0.4.1`
- 지원 환경: Windows PowerShell 5.1 이상, Python 3.10 이상(표준 라이브러리만 사용)
- 법령 프로필: 사건별 시행일 확인이 필요하며, 최종 확인일은 각 프로필에 별도로 기록합니다.

### 2026-10-30 작업트리의 1차 개선

정식 버전·릴리스와 별도로, 현재 소스에는 승인 계약 v2와 `structural-v2` 위치 체계가 적용돼 있습니다. 기존 승인 JSON은 검토한 입력본 해시·승인 역할·시각·근거 참조를 채워 다시 승인해야 합니다. 자세한 형식과 재검토 절차는 [HWPX 처리 도구](references/hwpx-tooling.md)를 따릅니다.

공개본은 표준 미리보기를 중립 대체하고 메타데이터 등 비본문을 검사합니다. 이미지·첨부 등 미검사 범위는 별도 표시하며, 기술적인 쌍 검사 통과를 정보공개 승인으로 간주하지 않습니다. 각 1차 과제의 구현·검증 상태는 [개선계획 9절](IMPROVEMENT_PLAN.md#9-차기-개선-실행계획-2026-10-30)에 기록합니다.

같은 소스의 2차 개선(N05·N06)은 공유 배포 목록·복구 가능한 설치와 파일 해시에 결속된 검수요약을 추가합니다. `VERSION`은 `0.4.1`로 유지하며, 이 소스 개선과 별도의 버전 태그·릴리스 발행은 구분합니다.

## 지원 범위

- 1차 수정본 → 2차 정본 정리
- 시나리오·사안자료·서면·표결자료 대조
- 사실·출처·개인정보·절차·점수 근거 검토
- 유지·요지화·중립화·삭제 검토·근거 확인·법무 확인 제안
- 결재용 실명 정본 HWPX와 정보공개 청구용 비실명 HWPX 분리

이 패키지는 특정 사건의 HWP/HWPX 원본 또는 실명 자료를 포함하지 않습니다. 법률 기준은 기관·관할·시행일에 따라 `profiles/`에서 선택합니다.

## 설치 방법

### 1. GitHub에서 내려받기

저장소를 원하는 위치에 복제합니다.

```powershell
git clone https://github.com/newskool4d-sketch/minutes-finalize-legal-review.git
```

### 2. Codex에 설치

복제한 저장소 폴더로 이동한 뒤 설치 스크립트를 사용합니다. 기본 설치 경로는 `%USERPROFILE%\.codex\skills\minutes-hwpx-finalize-legal-review`입니다.

```powershell
Set-Location -LiteralPath .\minutes-finalize-legal-review
$sourceRoot = (Get-Location).Path
.\scripts\install.ps1 -Target Codex
.\scripts\install.ps1 -Target Codex -Apply
.\scripts\verify_install.ps1 -Target Codex -SourceRoot $sourceRoot
```

설치 후 Codex를 새로 시작하면 스킬 목록에서 `minutes-hwpx-finalize-legal-review`를 사용할 수 있습니다.

첫 실행은 미리보기입니다. `-Apply` 실행은 배포 목록의 전체 파일을 스테이징에 복사하고 해시·링크를 검사한 뒤 교체합니다. 기존 설치본과 실패한 후보는 설치 부모 폴더 밖의 `.minutes-skill-deployment`에 보존하며 자동 삭제하지 않습니다. 출력의 `BACKUP_PATH`와 `VERIFY_COMMAND`로 실제 백업·검증 대상을 확인합니다.

사용자 지정 경로를 쓰면 설치·검증에 같은 부모 경로를 전달합니다. 아래 자리표시자는 본인이 정한 실제 절대경로로 바꿉니다.

```powershell
$destinationRoot = '<스킬 설치 부모 폴더의 절대경로>'
.\scripts\install.ps1 -Target Codex -DestinationRoot $destinationRoot
.\scripts\install.ps1 -Target Codex -DestinationRoot $destinationRoot -Apply
.\scripts\verify_install.ps1 -Target Codex -DestinationRoot $destinationRoot -SourceRoot $sourceRoot
```

### 3. Claude Code에 설치

Claude Code도 같은 배포 목록을 사용합니다. 기본 경로는 `%USERPROFILE%\.claude\skills\minutes-hwpx-finalize-legal-review`입니다. 같은 저장소 폴더에서 실행합니다.

```powershell
$sourceRoot = (Get-Location).Path
.\scripts\install.ps1 -Target Claude
.\scripts\install.ps1 -Target Claude -Apply
.\scripts\verify_install.ps1 -Target Claude -SourceRoot $sourceRoot
```

Claude Code를 새로 시작한 후 다음과 같이 요청합니다.

> 1차 수정된 회의록 HWPX와 시나리오를 기준으로 결재용 실명 정본 HWPX와 정보공개 청구용 비실명 HWPX를 제안하고, 발언별 법률위험을 검토해 주세요.

두 도구 모두 사용자 지정 `-DestinationRoot`를 지원합니다. 설치본 안에 있는 검증 스크립트를 직접 실행할 때도 신뢰할 수 있는 원본 저장소를 `-SourceRoot`로 지정해야 합니다. 설치 매니페스트만 바꿔 내용 변조를 숨길 수 없도록 원본과 대조합니다.

```powershell
# 저장소 폴더에서 설치 제거 대상과 백업 위치부터 확인
.\scripts\uninstall.ps1 -Target Claude
# 제거를 결정한 경우에만 실행: 등록된 설치 폴더를 복구 가능한 보관 경로로 이동
.\scripts\uninstall.ps1 -Target Claude -Apply
```

제거 스크립트도 기본은 미리보기이며 영구 삭제하지 않습니다. 설치 매니페스트가 없는 과거 수동 설치본은 제거하지 않습니다. 필요하면 먼저 새 설치기로 재설치하여 과거 폴더 전체를 백업하고 등록된 설치본을 만듭니다. 설치·제거 경로가 원본과 겹치거나 재분석 지점인 경우에는 중단합니다.

PowerShell 7의 격리 설치·복구와 Windows PowerShell 5.1의 격리 신규 설치·검증을 시험합니다. 버전별 기본 모듈 경로를 사용하며, 시험용 5.1 자식 프로세스에는 Python에서 상속된 PowerShell 7 모듈 경로를 전달하지 않습니다. 제한된 환경에서 실행정책으로 차단되면 미확인으로 기록하며 실행정책·보안 설정은 변경하지 않습니다.

## 기본 사용 순서

1. `SKILL.md`를 읽고 입력·출력 범위를 확인합니다.
2. 업무 관할에 맞는 `profiles/` 파일을 선택합니다.
3. 1차 수정본 HWPX와 시나리오를 입력합니다.
4. 결재용 실명 정본 HWPX, 정보공개 청구용 비실명 HWPX, 법률위험 검토표를 별도로 생성합니다.
5. 사람이 승인한 변경만 결재용 실명 정본에 반영하고, 승인된 비실명 처리만 정보공개 청구용 HWPX에 적용합니다.

소스 정본은 개발용 Git 저장소, Codex·Claude 설치본은 실행용 복사본입니다. 실제 사건자료·승인 JSON·검토 기록·두 HWPX 산출물은 **저장소와 설치 폴더 밖의 기관 승인 제한 작업공간**에 둡니다. `.gitignore`만으로 실자료의 보관·접근통제가 확보되지는 않습니다. [저장 경계](references/storage-boundaries.md)를 확인합니다.

아래 명령은 저장소 폴더에서 실행하며, `$caseRoot`는 이미 승인된 실제 절대경로로 바꿉니다. 도구가 승인이나 접근권한을 부여하지 않습니다.

```powershell
$caseRoot = '<기관에서 승인한 repo·설치 폴더 밖 제한 작업공간 절대경로>'
```

법률위험 검토표는 실명·사건번호를 넣지 않은 JSON을 준비한 뒤 다음과 같이 생성합니다. 높은 위험 항목에 사실 요지·확인 자료·시점이 기록된 공식 근거·`L 법무 확인`이 없으면 파일이 생성되지 않습니다.

```powershell
py -X utf8 scripts\render_legal_review_report.py "$caseRoot\review.json" `
  --output "$caseRoot\법률위험_검토표.md"
```

입력 필드 형식은 [출력 스키마](references/output-schema.md)를 따릅니다. 이 명령은 회의록 HWPX를 읽거나 외부 MCP로 전송하지 않으며, 검토자가 별도로 작성한 비식별 기록만 렌더링합니다.

초기 후보 위치만 로컬에서 찾으려면 아래 도구를 쓸 수 있습니다. 후보 JSON에는 원문·일치 단어를 저장하지 않으며, 자동 법률판단이나 자동 수정도 하지 않습니다.

```powershell
py -X utf8 scripts\detect_legal_review_candidates.py "$caseRoot\회의록_1차수정.hwpx" `
  --output "$caseRoot\법률위험_후보.json"
```

후보 위치를 사람 검토용 검토표 JSON으로 옮길 때는 다음을 사용합니다. 이 템플릿은 미완성 상태이므로, 실무자가 발언 요지·증거·법령 근거·승인 판단을 채운 뒤에만 검토표 렌더링을 실행합니다.

```powershell
py -X utf8 scripts\prepare_legal_review_template.py "$caseRoot\법률위험_후보.json" `
  --case-token "기관내부-비식별값" `
  --output "$caseRoot\법률위험_검토표_작성템플릿.json"
```

시범 운영에서는 [운영 성과지표](references/operation-metrics.md)에 주무관·담당 장학사 검토시간과 비식별 반려 사유 코드를 기록합니다.

전사 원본이 없는 경우에도 사용할 수 있습니다. 이때는 전사 누락 여부를 판단하지 않고 1차 수정본의 정본화·법률위험 검토만 수행합니다.

## HWPX 산출 도구

저장소의 `scripts/`는 승인된 수정만 반영해 결재용 실명 정본 HWPX와 정보공개 청구용 비실명 HWPX를 새 파일로 만듭니다. 원본 HWPX를 덮어쓰지 않으며, 결과의 ZIP·XML 구조와 원본 대비 문단·표 수를 검사합니다.

실제 사건자료는 저장소·설치 폴더 밖의 기관 승인 제한 작업공간에서만 처리하고 Git에 커밋하지 않습니다. 전체 사용법과 승인 목록 형식은 [HWPX 처리 도구](references/hwpx-tooling.md)를 확인합니다. 최종 제출 전에는 한글 프로그램에서 두 HWPX를 실제로 열어 형식·페이지·표 구조를 확인해야 합니다.

## 최종 검수요약

원본·승인 계획·두 HWPX·법률 검토표 JSON을 현재 파일의 해시로 연결하고, 기술 검사와 담당자 미확인 사항을 한 표로 모읍니다. 아래 경로도 모두 앞서 지정한 제한 작업공간입니다.

```powershell
py -X utf8 scripts\render_review_summary.py `
  --source "$caseRoot\회의록_1차수정.hwpx" `
  --approved "$caseRoot\approved-edits.json" `
  --approval "$caseRoot\회의록_결재용_실명정본.hwpx" `
  --disclosure "$caseRoot\회의록_정보공개청구용_비실명본.hwpx" `
  --legal-review "$caseRoot\review.json" `
  --human-evidence "$caseRoot\human-evidence.json" `
  --output "$caseRoot\검수요약.md" --json "$caseRoot\검수요약.json"
```

법률 검토표나 담당자 확인 기록을 아직 준비하지 않았다면 해당 옵션을 생략해 미확인 상태와 다음 조치를 먼저 확인할 수 있습니다. 기존 파일은 덮어쓰지 않습니다. [검수요약 계약과 확인 기록 예시](references/review-summary.md)를 따릅니다.

`PASS`는 재계산한 기술 검사와 **입력된 담당자 확인 기록**의 완결성입니다. `PARTIAL`은 미확인·미해결 법률 검토, `FAIL`은 변조·불일치·담당자 확인의 명시적 실패 등을 뜻합니다. 법률 항목의 반려는 미해결로 남습니다. 담당자 확인 기록은 전자서명·실행 증명이 아니며 AI가 임의로 작성하지 않습니다. `external_release_authorized`는 항상 `false`이고, 요약 PASS가 법률 결론이나 정보공개 승인으로 바뀌지 않습니다.

## Korean Law MCP 설치 및 연결

이 스킬은 법률 검토가 필요한 경우 설치되어 있는 법령·판례 MCP를 우선 사용합니다. 아래는 [Korean Law MCP 안내 페이지](https://chris.gomdori.app/pages/korean-law-mcp)와 [공식 설치 문서](https://github.com/chrisryugj/korean-law-mcp)를 기준으로 정리한 선택형 설치 방법입니다.

### 먼저: 법제처 Open API 키(OC) 발급

1. [법제처 Open API](https://open.law.go.kr/)에 로그인합니다.
2. `Open API 사용 신청`에서 OC 키를 발급받습니다.
3. 키는 비밀번호와 같이 취급하고 README, Git 저장소, 로그, 화면 캡처에 남기지 않습니다.

아래 예시의 `본인_OC키`는 실제 키로 바꾸되, 명령 기록이나 설정 파일을 공유할 때는 반드시 삭제합니다.

### 권장: 민감한 회의록은 로컬 MCP로 설치

실명·건강정보·교권침해 내용이 포함된 회의록을 검토할 때는 기관에서 허용한 PC에 로컬 MCP를 설치하는 방법을 우선합니다. Node.js 18 이상이 필요합니다.

자동 설정 마법사:

```powershell
npx korean-law-mcp setup
```

수동 설치 및 API 키 설정(PowerShell):

```powershell
npm install -g korean-law-mcp
$env:LAW_OC = "본인_OC키"
```

MCP 클라이언트가 stdio 서버 설정을 요구하면 다음 형태를 사용합니다.

```json
{
  "mcpServers": {
    "korean-law": {
      "command": "korean-law-mcp",
      "env": {
        "LAW_OC": "본인_OC키"
      }
    }
  }
}
```

Codex에서는 설치된 버전의 MCP 설정 UI 또는 설정 파일 형식에 맞춰 `command`와 `LAW_OC`를 등록합니다. API 키를 대화 입력에 반복해서 붙여 넣거나 저장소 파일에 기록하지 않습니다.

### Claude Code 플러그인 설치

Claude Code에서 공식 플러그인을 사용할 수 있습니다.

```text
/plugin marketplace add chrisryugj/korean-law-mcp
/plugin install korean-law@korean-law-marketplace
```

설치 과정에서 OC 키를 입력합니다. 업데이트할 때는 다음을 실행합니다.

```text
/plugin marketplace update korean-law-marketplace
```

`Permission denied (publickey)`가 표시되면 SSH 대신 HTTPS로 GitHub를 사용하도록 한 번 설정한 뒤 다시 시도합니다.

```powershell
git config --global url."https://github.com/".insteadOf "git@github.com:"
```

### Claude Desktop 연결

Claude Desktop은 `%APPDATA%\Claude\claude_desktop_config.json`에 설정하며 Node.js 18 이상과 `mcp-remote`가 필요합니다.

```json
{
  "mcpServers": {
    "korean-law": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://mcp.gomdori.app/law?oc=본인_OC키"
      ]
    }
  }
}
```

저장 후 Claude Desktop을 재시작하고 MCP 도구가 표시되는지 확인합니다.

### 원격 커넥터(기관 승인 및 비민감 질의에 한함)

Korean Law MCP의 원격 주소는 `https://mcp.gomdori.app/law`입니다. Claude.ai·Cursor·Windsurf 등에서 원격 HTTP MCP를 지원하면 다음 URL을 등록할 수 있습니다.

```text
https://mcp.gomdori.app/law?oc=본인_OC키
```

원격 연결은 질의가 외부 서버로 전송될 수 있으므로, 기관의 보안·개인정보·외부 AI 사용 승인을 먼저 확인합니다. 실명 회의록 전문, 주민번호, 주소, 건강정보, 사건 식별정보를 원격 MCP에 붙여 넣지 말고 조문·판례 검색어처럼 비식별화된 최소 질의만 사용합니다. 승인이 없으면 로컬 설치를 사용합니다.

### 설치 확인용 CLI 테스트

```powershell
npm install -g korean-law-mcp
$env:LAW_OC = "본인_OC키"
korean-law "교원의 지위 향상 및 교육활동 보호를 위한 특별법 제25조"
korean-law list
```

정상 작동 후에는 회의록 법률 검토표에 법령명·조문·시행일·조회일·MCP 출처 식별자를 남깁니다. 검색 결과의 요약만으로 위법 여부를 확정하지 않고, 공식 원문과 사건의 사실관계를 담당자가 대조합니다.

### 연결 문제 및 폐쇄망 참고

기본 통신은 HTTPS입니다. 폐쇄망에서 기관 정책상 HTTP 프록시가 필요한 경우에만 MCP 운영자 안내와 보안 승인을 확인한 뒤 다음 환경변수를 검토합니다.

```powershell
$env:LAW_API_PROTOCOL = "http"
```

이 설정은 기본값이 아니며, 네트워크 정책을 우회하기 위한 용도로 사용하지 않습니다. MCP가 없거나 호출되지 않으면 공식 법령 원문·고시와 기관 프로필로 대체합니다.

## 개인정보·파일 정책

- HWP·HWPX·실명 자료는 이 저장소에 커밋하지 않습니다.
- 결재용 실명 정본 HWPX와 정보공개 청구용 비실명 HWPX를 별도 파일로 관리합니다.
- 정보공개 청구용 비실명 HWPX는 결재용 실명 정본의 의결·표결·사실관계·표와 문단 구조를 유지하고, 승인된 식별정보만 처리합니다.
- AI가 자동으로 발언을 삭제하거나 사실·법률 위반을 확정하지 않습니다.
- `D 삭제 검토`와 `L 법무 확인`은 담당자 승인 전까지 제안 상태로 유지합니다.

## 저장소에 포함하지 않는 파일

다음 파일은 저장소에 커밋하지 않습니다.

- 실제 회의록 HWP·HWPX
- 전사 원본·시나리오 원본
- 실명·연락처·주소·건강정보가 포함된 자료
- 기관 내부 전용 업무편람과 비공개 법률자료

`.gitignore`가 HWP/HWPX와 일반적인 원본·실명 파일명을 제외하지만, 커밋 전 `git status`와 `git ls-files`를 반드시 확인합니다.

## 법적·운영상 주의

이 스킬은 법률 자문이나 처분 결정을 대신하지 않습니다. 법령 MCP 또는 공식 법령 원문으로 기준을 확인하고, 중대한 조치·상반 증거·민감정보가 있는 경우 담당 법무자의 확인을 거칩니다.

## 보안 제보

실제 회의록·실명·API 키 없이 문제를 제보합니다. 자세한 기준은 [보안·민감자료 제보](SECURITY.md)를 확인합니다.
