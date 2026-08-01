# 개발 시작 안내

공통 개발 환경은 아직 정하지 않았습니다. 지금 필요한 것은 Git과 Markdown 편집기, 그리고 저장소·PR 작업에 쓸 GitHub CLI(`gh`) 정도입니다.

ROS 2 배포판, 운영체제, 컴파일러, 컨테이너, 시뮬레이터 버전은 첫 소프트웨어 ADR에서 정합니다. 그전까지 개인 환경 설정을 프로젝트 표준처럼 커밋하지 않습니다.

## 저장소 받기

```powershell
git clone https://github.com/HyperNova26/hypernova-robot.git
Set-Location hypernova-robot
```

## 첫 작업

1. `README.md`와 `CONTRIBUTING.md`를 읽습니다.
2. 작업할 문제를 Issue로 정의합니다.
3. `main`에서 브랜치를 만들어 작업합니다.
4. Pull Request에 확인 방법과 다른 영역에 미치는 영향을 함께 적습니다.

## 환경이 정해지면 추가할 내용

- 지원 OS와 ROS 2 배포판
- 의존성 목록과 설치 명령
- build, lint, test 명령
- 실기 bringup 전 점검 절차
- 지원 기체·보드·센서 revision
