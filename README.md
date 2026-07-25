# 회의록 정본화·법률검토 스킬

HWPX 회의록의 1차 수정본을 2차 정본으로 정리하면서, 발언별 법률·절차 위험과 근거자료를 함께 검토하는 범용 스킬입니다.

- 스킬 버전: `0.3.0`
- 지원 환경: Windows PowerShell 5.1 이상, Python 3.10 이상(표준 라이브러리만 사용)
- 법령 프로필: 사건별 시행일 확인이 필요하며, 최종 확인일은 각 프로필에 별도로 기록합니다.

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

PowerShell에서 저장소 폴더 전체를 Codex 스킬 경로에 복사합니다.

```powershell
$source = '.\\minutes-finalize-legal-review'
$target = "$env:USERPROFILE\\.codex\\skills\\minutes-hwpx-finalize-legal-review"
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item "$source\\SKILL.md" "$target\\SKILL.md" -Force
Copy-Item "$source\\agents" "$target" -Recurse -Force
Copy-Item "$source\\references" "$target" -Recurse -Force
Copy-Item "$source\\profiles" "$target" -Recurse -Force
Copy-Item "$source\\scripts" "$target" -Recurse -Force
Copy-Item "$source\\VERSION" "$target\\VERSION" -Force
```

설치 후 Codex를 새로 시작하면 스킬 목록에서 `minutes-hwpx-finalize-legal-review`를 사용할 수 있습니다.

반복 설치에는 저장소의 스크립트를 사용할 수 있습니다. 기본은 미리보기이며, 실제 복사·백업은 `-Apply`가 있을 때만 수행합니다.

```powershell
.\scripts\install.ps1 -Target Codex
.\scripts\install.ps1 -Target Codex -Apply
.\scripts\verify_install.ps1 -Target Codex
```

### 3. Claude Code에 설치

Claude Code도 같은 파일 구조를 사용합니다. 아래 명령으로 Claude 전용 경로에 복사합니다.

```powershell
$source = '.\\minutes-finalize-legal-review'
$target = "$env:USERPROFILE\\.claude\\skills\\minutes-hwpx-finalize-legal-review"
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item "$source\\SKILL.md" "$target\\SKILL.md" -Force
Copy-Item "$source\\references" "$target" -Recurse -Force
Copy-Item "$source\\profiles" "$target" -Recurse -Force
Copy-Item "$source\\agents" "$target" -Recurse -Force
Copy-Item "$source\\scripts" "$target" -Recurse -Force
Copy-Item "$source\\VERSION" "$target\\VERSION" -Force
```

Claude Code를 새로 시작한 후 다음과 같이 요청합니다.

> 1차 수정된 회의록 HWPX와 시나리오를 기준으로 결재용 실명 정본 HWPX와 정보공개 청구용 비실명 HWPX를 제안하고, 발언별 법률위험을 검토해 주세요.

Claude Code 자동 설치는 `-Target Claude`를 사용합니다.

```powershell
.\scripts\install.ps1 -Target Claude
.\scripts\install.ps1 -Target Claude -Apply
.\scripts\verify_install.ps1 -Target Claude
```

제거 스크립트도 기본은 미리보기입니다. `-Apply`를 쓰면 해당 스킬 폴더만 백업 후 제거합니다.

## 기본 사용 순서

1. `SKILL.md`를 읽고 입력·출력 범위를 확인합니다.
2. 업무 관할에 맞는 `profiles/` 파일을 선택합니다.
3. 1차 수정본 HWPX와 시나리오를 입력합니다.
4. 결재용 실명 정본 HWPX, 정보공개 청구용 비실명 HWPX, 법률위험 검토표를 별도로 생성합니다.

법률위험 검토표는 실명·사건번호를 넣지 않은 JSON을 준비한 뒤 다음과 같이 생성합니다. 높은 위험 항목에 사실 요지·확인 자료·시점이 기록된 공식 근거·`L 법무 확인`이 없으면 파일이 생성되지 않습니다.

```powershell
py -X utf8 scripts\render_legal_review_report.py .\case-data\review.json `
  --output .\case-data\법률위험_검토표.md
```

입력 필드 형식은 [출력 스키마](references/output-schema.md)를 따릅니다. 이 명령은 회의록 HWPX를 읽거나 외부 MCP로 전송하지 않으며, 검토자가 별도로 작성한 비식별 기록만 렌더링합니다.

시범 운영에서는 [운영 성과지표](references/operation-metrics.md)에 주무관·담당 장학사 검토시간과 비식별 반려 사유 코드를 기록합니다.
5. 사람이 승인한 변경만 결재용 실명 정본에 반영하고, 승인된 비실명 처리만 정보공개 청구용 HWPX에 적용합니다.

전사 원본이 없는 경우에도 사용할 수 있습니다. 이때는 전사 누락 여부를 판단하지 않고 1차 수정본의 정본화·법률위험 검토만 수행합니다.

## HWPX 산출 도구

저장소의 `scripts/`는 승인된 수정만 반영해 결재용 실명 정본 HWPX와 정보공개 청구용 비실명 HWPX를 새 파일로 만듭니다. 원본 HWPX를 덮어쓰지 않으며, 결과의 ZIP·XML 구조와 원본 대비 문단·표 수를 검사합니다.

실제 사건자료는 `case-data/` 등 기관 승인 경로에서만 처리하고 Git에 커밋하지 않습니다. 전체 사용법과 승인 목록 형식은 [HWPX 처리 도구](references/hwpx-tooling.md)를 확인합니다. 최종 제출 전에는 한글 프로그램에서 두 HWPX를 실제로 열어 형식·페이지·표 구조를 확인해야 합니다.

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
