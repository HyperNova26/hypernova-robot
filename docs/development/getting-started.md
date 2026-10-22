# 개발 시작 안내

개발 환경은 [ADR-0002](../decisions/0002-dev-environment.md)에서 정했습니다. Ubuntu 24.04 + ROS 2 Jazzy를 Docker 이미지 두 개로 맞춰 두었고, 저장소를 받은 뒤 명령 하나로 시작합니다. 시작은 [Docker 개발 환경](../../docker/README.md)입니다. 호스트를 한 번 준비하고(드라이버, Docker Engine, NVIDIA Container Toolkit) 이미지를 받은 다음, 맡은 트랙의 빠른 시작을 따라 합니다.

| 트랙 | 이미지 | 빠른 시작 |
| --- | --- | --- |
| 보행 (Isaac Lab 학습, ONNX export, sim2sim) | `hn:sim` | [빠른 시작 — 보행](./quickstart-locomotion.md) |
| 인지·SW (LIO, 지형, 대시보드, ROS 노드) | `hn:ros` | [빠른 시작 — 인지·SW](./quickstart-perception.md) |

개인 환경 설정을 프로젝트 표준인 것처럼 커밋하지 마세요. 패키지가 더 필요하거나 버전을 바꾸려면 컨테이너 안에서 설치하지 말고 Dockerfile을 고치는 PR을 냅니다.

## 저장소 받기

Ubuntu:

```bash
git clone https://github.com/HyperNova26/hypernova-robot.git
cd hypernova-robot
```

Windows(문서·CAD 작업):

```powershell
git clone https://github.com/HyperNova26/hypernova-robot.git
Set-Location hypernova-robot
```

## 첫 작업

1. `README.md`와 `CONTRIBUTING.md`를 읽습니다.
2. 작업할 문제를 Issue로 정의합니다.
3. `main`에서 브랜치를 따서 작업합니다.
4. Pull Request에 확인 방법과 다른 영역에 미치는 영향을 함께 적습니다.

## 아직 정하지 않은 것

- build, lint, test 명령 (ROS 패키지와 policy 코드가 생기면 추가)
- 실기 bringup 전 점검 절차
- 지원 기체·보드·센서 revision
