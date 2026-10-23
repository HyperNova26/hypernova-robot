# GitHub 저장소 설정

## About

| 항목 | 값 |
| --- | --- |
| Repository | `HyperNova26/hypernova-robot` |
| Description | `Autonomous mobile robot project by HYPERNOVA.` |
| Topics | `robotics`, `ros2`, `student-project` |
| Social preview | 조직 프로필과 같은 HYPERNOVA banner — UI 적용 대기 |
| Visibility | `public` |

기체 형태, 센서 모델, 임무 시나리오는 아직 검토 중이라 About에 넣지 않았습니다.

## 공개와 라이선스

- 저장소와 Issue, Pull Request, Actions 기록은 공개합니다.
- public 저장소라 누구나 fork할 수 있습니다.
- 소프트웨어 계열은 Apache-2.0, 하드웨어 설계는 CERN-OHL-S-2.0, 문서는 CC BY 4.0.
- HYPERNOVA 이름과 로고, 배너는 공개 라이선스에서 뺍니다.

자세한 적용 범위는 [`LICENSE.md`](../../LICENSE.md)에서 관리합니다.

## 팀과 권한

| 팀 | 저장소 권한 | 구성 |
| --- | --- | --- |
| `leads` | Maintain | 팀장 4명 (공동 PM 포함) |
| `ai-cv`, `sw`, `hw`, `ee` | Write | 각 팀원 |

조직 기본 권한이 아니라 팀 권한으로 접근합니다. `CODEOWNERS`에 쓰는 팀은 저장소에 write 이상 권한이 있어야 인식됩니다.

## `main` 브랜치 보호

- Pull Request 필수, 일반 승인 0명
- Code Owner 리뷰 필수 — [`CODEOWNERS`](../../.github/CODEOWNERS)에 적힌 경로만 해당 팀 승인이 필요합니다
- 관리자도 같은 규칙을 따릅니다
- force push와 브랜치 삭제 금지
- squash merge만 허용, 병합 후 브랜치 삭제
- 필수 status check는 아직 없습니다. 경로 필터가 걸린 workflow를 필수로 두면 해당 workflow가 돌지 않는 PR이 병합되지 못하므로, CI 구조가 잡힌 뒤 정합니다

## 코드 소유자

여러 팀이 같이 쓰는 경로에만 소유자를 둡니다. 팀 내부 경로까지 지정하면 팀장이 모든 PR의 병목이 됩니다.

| 경로 | 소유 팀 | 이유 |
| --- | --- | --- |
| `.github/`, `docs/decisions/` | `leads` | CI·CODEOWNERS 자체와 ADR은 프로젝트 전체 결정 |
| `docker/` | `ai-cv`, `sw` | 두 팀이 같은 개발 이미지를 씀 |
| `description/` | `hw`, `ai-cv` | 실기와 시뮬레이션이 같은 기체 정의를 씀 |

ROS 2 인터페이스 package가 생기면 `sw`, `ai-cv` 공동 소유로 추가합니다.

## 보안

- Secret scanning과 push protection을 켭니다. public 저장소라 비용이 없고, NGC API key나 GHCR token 같은 비밀값이 commit에 섞이면 push 단계에서 막습니다.

## 컨테이너 이미지 (GHCR)

- `hn:ros` 이미지는 `ghcr.io/hypernova26/hn`에 올라갑니다. `main`에 병합될 때 [`docker-ros.yml`](../../.github/workflows/docker-ros.yml)이 `GITHUB_TOKEN`(`packages: write`)으로 올리고, 태그는 `docker/.env`의 `HN_IMAGE_TAG`입니다. PR에서는 빌드와 점검만 합니다.
- 처음 올라간 패키지는 **private**입니다. 조직 관리자가 한 번 패키지 설정(Package settings → Danger Zone → Change visibility)에서 Public으로 바꿔야 팀원이 로그인 없이 `./docker/hn pull ros`로 받을 수 있습니다. 패키지는 Dockerfile의 `org.opencontainers.image.source` 라벨로 이 저장소와 연결됩니다.
- public 패키지는 무료입니다. `hn:sim`은 NVIDIA 베이스 이미지를 재배포하지 않으려고 올리지 않습니다([ADR-0002](../decisions/0002-dev-environment.md)).

## Issue 라벨

- `bug`, `enhancement`, `documentation`, `question`
- `area:firmware`, `area:hardware`, `area:simulation`, `area:software`
- `safety`
- `good first issue`, `help wanted`, `duplicate`, `invalid`, `wontfix`
