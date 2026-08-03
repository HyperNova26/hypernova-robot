# ROS packages

온보드 로봇 소프트웨어와 운영자용 관제 소프트웨어를 기능별 ROS 2 package로 둡니다. ROS 2 배포판과 workspace 구성은 첫 실행 베이스라인을 만들면서 정합니다.

## 예상 기능 경계

후보만 적어 둡니다. package를 만들거나 책임 범위를 정한 단계는 아닙니다.

- `interfaces`: message, service, action과 외부 protocol
- `bringup`: 기체·센서 구성별 통합 실행
- `locomotion`: 이동 제어와 state estimation
- `localization` / `navigation`: 지도, 위치 추정, 경로와 임무 실행
- `perception`: camera·LiDAR 처리
- `monitoring`: 진단, 기록, 상태 전달
- `operator`: 관제 UI와 원격 개입

## 기본 규칙

- package가 쓰는 `config/`, `launch/`, `test/`는 그 package 안에 둡니다.
- 기체 형상과 frame·joint는 [`description/`](../description/)이 기준본입니다. 복제하지 마세요.
- 재사용 가능한 core 알고리즘과 ROS 2·하드웨어 adapter를 분리합니다.
- 좌표계, 단위, timestamp, QoS, timeout은 인터페이스 문서에 적습니다.
- 외부 의존성은 복사하지 말고 package manager나 `.repos`, submodule로 버전을 고정합니다.
