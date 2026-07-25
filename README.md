# 회의록 정본화·법률검토 스킬

HWPX 회의록의 1차 수정본을 2차 정본으로 정리하면서, 발언별 법률·절차 위험과 근거자료를 함께 검토하는 범용 스킬입니다.

## 지원 범위

- 1차 수정본 → 2차 정본 정리
- 시나리오·사안자료·서면·표결자료 대조
- 사실·출처·개인정보·절차·점수 근거 검토
- 유지·요지화·중립화·삭제 검토·근거 확인·법무 확인 제안
- 결재용 원본과 공개용 비식별본 분리

이 패키지는 특정 사건의 HWP/HWPX 원본 또는 실명 자료를 포함하지 않습니다. 법률 기준은 기관·관할·시행일에 따라 `profiles/`에서 선택합니다.

## 설치 방법

### 1. GitHub에서 내려받기

저장소를 원하는 위치에 복제합니다.

```powershell
git clone https://github.com/사용자명/minutes-finalize-legal-review.git
```

`사용자명`은 실제 저장소가 생성된 뒤의 GitHub 계정명으로 바꿉니다.

### 2. Codex에 설치

PowerShell에서 저장소 폴더 전체를 Codex 스킬 경로에 복사합니다.

```powershell
$source = '.\\minutes-finalize-legal-review'
$target = "$env:USERPROFILE\\.codex\\skills\\minutes-finalize-legal-review"
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item "$source\\SKILL.md" "$target\\SKILL.md" -Force
Copy-Item "$source\\agents" "$target" -Recurse -Force
Copy-Item "$source\\references" "$target" -Recurse -Force
Copy-Item "$source\\profiles" "$target" -Recurse -Force
```

설치 후 Codex를 새로 시작하면 스킬 목록에서 `minutes-hwpx-finalize-legal-review`를 사용할 수 있습니다.

### 3. Claude Code에 설치

Claude Code도 같은 파일 구조를 사용합니다. 아래 명령으로 Claude 전용 경로에 복사합니다.

```powershell
$source = '.\\minutes-finalize-legal-review'
$target = "$env:USERPROFILE\\.claude\\skills\\minutes-finalize-legal-review"
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item "$source\\SKILL.md" "$target\\SKILL.md" -Force
Copy-Item "$source\\references" "$target" -Recurse -Force
Copy-Item "$source\\profiles" "$target" -Recurse -Force
```

Claude Code를 새로 시작한 후 다음과 같이 요청합니다.

> 1차 수정된 회의록 HWPX와 시나리오를 기준으로 2차 정본을 제안하고, 발언별 법률위험을 검토해 주세요.

## 기본 사용 순서

1. `SKILL.md`를 읽고 입력·출력 범위를 확인합니다.
2. 업무 관할에 맞는 `profiles/` 파일을 선택합니다.
3. 1차 수정본 HWPX와 시나리오를 입력합니다.
4. 정본화 제안과 법률위험 검토표를 별도로 생성합니다.
5. 사람이 승인한 변경만 최종 HWPX에 반영합니다.

전사 원본이 없는 경우에도 사용할 수 있습니다. 이때는 전사 누락 여부를 판단하지 않고 1차 수정본의 정본화·법률위험 검토만 수행합니다.

## 법령 MCP

법령·판례 MCP가 설치되어 있으면 법률 검토 시 이를 우선 사용합니다. 사건일·처분일·관할을 기준으로 조문과 시행일을 확인하고, MCP 출처 식별자를 검토표에 기록합니다. MCP가 없거나 호출되지 않으면 공식 법령 원문·고시와 기관 프로필로 대체합니다. MCP 요약만으로 위법 여부를 확정하지 않습니다.

## 개인정보·파일 정책

- HWP·HWPX·실명 자료는 이 저장소에 커밋하지 않습니다.
- 결재용 실명본과 공개용 비식별본을 별도 파일로 관리합니다.
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
